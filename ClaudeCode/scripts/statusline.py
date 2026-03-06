# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

"""Claude Code statusline用のスクリプト

Claude Codeのステータスフックから呼び出され、ターミナル下部に
プロジェクト情報やAPIレートリミット状況を表示する
"""

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# データ型
# ---------------------------------------------------------------------------


class _Color(IntEnum):
    """ANSIカラーコード"""

    GREEN = 32
    YELLOW = 33
    RED = 31
    DIM = 90
    RESET = 0


@dataclass(frozen=True, slots=True)
class Segment:
    """ステータスライン上の1セグメントを表す

    Attributes:
        text: ANSIエスケープ込みの表示文字列
        width: 表示幅(ANSIエスケープを除いた文字数)
    """

    text: str
    width: int


@dataclass(frozen=True, slots=True)
class _LineConfig:
    """行のレイアウト定義

    Attributes:
        segment_fns: セグメント生成関数のリスト
        overflow_index: この位置以降を次行に押し出す分割点(Noneなら分割しない)
    """

    segment_fns: list[Callable[[dict[str, Any]], Segment | None]] = field(
        default_factory=list,
    )
    overflow_index: int | None = None


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_SEPARATOR = " \u2502 "  # " │ "
_SEPARATOR_WIDTH = 3  # ANSIを除いた表示幅
_CACHE_TTL = 360  # 秒
_CACHE_PATH = Path(tempfile.gettempdir()) / "claude-usage-cache.json"
_API_URL = "https://api.anthropic.com/api/oauth/usage"
_API_TIMEOUT = 5

# ---------------------------------------------------------------------------
# Nerd Fontsアイコン
# ---------------------------------------------------------------------------

_ICON_FOLDER = "\uf07c"  # nf-fa-folder_open
_ICON_BRANCH = "\ue725"  # nf-dev-git_branch
_ICON_MODEL = "\U000f068c"  # nf-md-robot (󰚌)
_ICON_CHART = "\uf080"  # nf-fa-bar_chart
_ICON_PENCIL = "\U000f03eb"  # nf-md-pencil (󰏫)
_ICON_CLOCK = "\uf017"  # nf-fa-clock_o
_ICON_CALENDAR = "\uf073"  # nf-fa-calendar


# ---------------------------------------------------------------------------
# ヘルパー関数
# ---------------------------------------------------------------------------


def _colorize(text: str, color: _Color) -> str:
    """テキストにANSIカラーエスケープを付与する

    Args:
        text: 色を付けるテキスト
        color: ANSIカラーコード

    Returns:
        ANSIエスケープシーケンスで囲まれた文字列
    """
    return f"\033[{color.value}m{text}\033[0m"


def _color_for_utilization(pct: float) -> _Color:
    """利用率に応じたカラーを返す

    Args:
        pct: 利用率(0-100)

    Returns:
        0-49%: GREEN, 50-79%: YELLOW, 80-100%: RED
    """
    if pct >= 80:
        return _Color.RED
    if pct >= 50:
        return _Color.YELLOW
    return _Color.GREEN


# ---------------------------------------------------------------------------
# 時刻フォーマット
# ---------------------------------------------------------------------------


def _parse_iso_to_local(iso_str: str) -> datetime:
    """ISO 8601文字列をローカルタイムゾーンのdatetimeに変換する

    Args:
        iso_str: ISO 8601形式の日時文字列

    Returns:
        ローカルタイムゾーンに変換されたdatetime
    """
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone()


def _format_reset_time_short(iso_str: str) -> str:
    """リセット時刻を "hh:mm" 形式でフォーマットする

    Args:
        iso_str: ISO 8601形式の日時文字列

    Returns:
        "HH:MM" 形式の文字列
    """
    local_dt = _parse_iso_to_local(iso_str)
    return f"{local_dt.hour}:{local_dt.minute:02d}"


def _format_reset_date(iso_str: str) -> str:
    """リセット時刻を "M/D hh:mm" 形式でフォーマットする(0埋めなし)

    Args:
        iso_str: ISO 8601形式の日時文字列

    Returns:
        "M/D HH:MM" 形式の文字列(0埋めなし)
    """
    local_dt = _parse_iso_to_local(iso_str)
    return f"{local_dt.month}/{local_dt.day} {local_dt.hour}:{local_dt.minute:02d}"


# ---------------------------------------------------------------------------
# OAuth認証情報のハイブリッド取得
# ---------------------------------------------------------------------------


def _get_oauth_token() -> str | None:
    """OAuth認証トークンを取得する

    以下の順に試行する:
    1. ~/.claude/.credentials.json からファイル読み取り(Windows/Linux)
    2. macOSのKeychainから取得

    Returns:
        アクセストークン文字列、取得できない場合はNone
    """
    # 1. クレデンシャルファイルから読む
    cred_path = Path.home() / ".claude" / ".credentials.json"
    try:
        cred_text = cred_path.read_text(encoding="utf-8")
        cred_data = json.loads(cred_text)
        token = cred_data.get("claudeAiOauth", {}).get("accessToken")
        if token:
            return str(token)
    except OSError, json.JSONDecodeError, KeyError, TypeError:  # noqa: S110
        pass

    # 2. macOS Keychainから取得
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                [  # noqa: S607
                    "security",
                    "find-generic-password",
                    "-s",
                    "Claude Code-credentials",
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                keychain_data = json.loads(result.stdout.strip())
                token = keychain_data.get("claudeAiOauth", {}).get("accessToken")
                if token:
                    return str(token)
        except (  # noqa: S110
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            OSError,
        ):
            pass

    return None


# ---------------------------------------------------------------------------
# Usage APIクライアント + キャッシュ
# ---------------------------------------------------------------------------


def _fetch_usage(token: str) -> dict[str, Any]:
    """Anthropic Usage APIからレートリミット情報を取得する

    Args:
        token: OAuthアクセストークン

    Returns:
        APIレスポンスのJSON辞書

    Raises:
        URLError: ネットワークエラー
        json.JSONDecodeError: レスポンスのパースに失敗
        OSError: IO関連エラー
    """
    req = Request(
        _API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
        },
    )
    with urlopen(req, timeout=_API_TIMEOUT) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _get_usage() -> dict[str, Any] | None:
    """キャッシュ付きでUsage APIからデータを取得する

    キャッシュのTTLは_CACHE_TTL秒である
    API呼び出しに失敗した場合、期限切れキャッシュも使用する

    Returns:
        使用状況の辞書、取得できない場合はNone
    """
    # キャッシュチェック
    now = datetime.now(UTC).timestamp()
    cached_data = None
    try:
        cache_text = _CACHE_PATH.read_text(encoding="utf-8")
        cache_obj = json.loads(cache_text)
        cached_ts = cache_obj.get("_cached_at", 0)
        cached_data = cache_obj.get("data")
        if now - cached_ts < _CACHE_TTL and cached_data is not None:
            return cached_data
    except OSError, json.JSONDecodeError, KeyError, TypeError:  # noqa: S110
        pass

    # API呼び出し
    token = _get_oauth_token()
    if token is None:
        return cached_data  # トークンがない場合は期限切れキャッシュを返す

    try:
        data = _fetch_usage(token)
    except URLError, json.JSONDecodeError, OSError, TimeoutError:
        return cached_data  # API失敗時は期限切れキャッシュを返す

    # atomic writeでキャッシュ保存
    cache_obj = {"_cached_at": now, "data": data}
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=_CACHE_PATH.parent, suffix=".tmp", prefix="claude-usage-"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(cache_obj, f)
            # Windowsではreplaceが安全に動作する(Python 3.3+)
            Path(tmp_name).replace(_CACHE_PATH)
        except OSError:
            # 書き込み失敗時はtmpファイルを削除する
            with contextlib.suppress(OSError):
                Path(tmp_name).unlink()
    except OSError:  # noqa: S110
        pass

    return data


# ---------------------------------------------------------------------------
# セグメント関数
# ---------------------------------------------------------------------------


def _seg_project(data: dict[str, Any]) -> Segment | None:
    """プロジェクト名セグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        プロジェクト名のSegment
    """
    cwd = str(data.get("cwd", ""))
    name = Path(cwd).name if cwd else "unknown"
    if not name:
        name = "unknown"
    label = f"{_ICON_FOLDER} {name}"
    return Segment(text=label, width=len(name) + 2)  # アイコン(1) + 空白(1) + 名前


def _seg_branch(data: dict[str, Any]) -> Segment | None:
    """Gitブランチ名セグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        ブランチ名のSegment、取得失敗時はNone
    """
    cwd = str(data.get("cwd", ""))
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=cwd or None,
            timeout=3,
            check=False,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
        if not branch:
            return None
    except subprocess.TimeoutExpired, subprocess.SubprocessError, OSError:
        return None

    label = f"{_ICON_BRANCH} {branch}"
    return Segment(text=label, width=len(branch) + 2)


def _seg_model(data: dict[str, Any]) -> Segment | None:
    """モデル名セグメントを生成する

    model.display_nameとmodel.idからバージョンを抽出する
    例: id="claude-opus-4-6", display_name="Opus" -> "Opus 4.6"

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        モデル名のSegment
    """
    model = data.get("model")
    if not isinstance(model, dict):
        return None

    display_name = str(model.get("display_name", ""))
    model_id = str(model.get("id", ""))

    if not display_name:
        return None

    # model_idからバージョン番号を抽出する
    # 例: "claude-opus-4-6" -> "4.6", "claude-sonnet-4-5-20250514" -> "4.5"
    version = _extract_version(model_id)
    if version:
        model_text = f"{display_name} {version}"
    else:
        model_text = display_name

    label = f"{_ICON_MODEL} {model_text}"
    return Segment(text=label, width=len(model_text) + 2)


def _extract_version(model_id: str) -> str:
    """モデルIDからバージョン文字列を抽出する

    "claude-opus-4-6" -> "4.6"
    "claude-sonnet-4-5-20250514" -> "4.5"
    "claude-haiku-3-5-20241022" -> "3.5"

    Args:
        model_id: モデルID文字列

    Returns:
        バージョン文字列、抽出できない場合は空文字列
    """
    # "claude-" プレフィクスを除去
    rest = model_id.removeprefix("claude-")

    # モデルファミリー名を除去(opus, sonnet, haikuなど)
    parts = rest.split("-")
    if len(parts) < 2:
        return ""

    # ファミリー名以降で数字部分を探す
    digit_parts: list[str] = []
    found_digit = False
    for part in parts[1:]:
        if part.isdigit():
            found_digit = True
            digit_parts.append(part)
            # メジャー.マイナーの2つまで取得する
            if len(digit_parts) >= 2:
                break
        elif found_digit:
            break  # 数字の連続が途切れたら終了

    if not digit_parts:
        return ""

    return ".".join(digit_parts)


def _seg_context(data: dict[str, Any]) -> Segment | None:
    """コンテキストウィンドウ使用率セグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        使用率のSegment(色付き)
    """
    ctx = data.get("context_window")
    if not isinstance(ctx, dict):
        return None

    pct = ctx.get("used_percentage")
    if pct is None:
        return None

    pct_val = float(pct)
    pct_int = int(pct_val)
    color = _color_for_utilization(pct_val)
    pct_str = f"{pct_int}%"

    colored_pct = _colorize(pct_str, color)
    label = f"{_ICON_CHART} {colored_pct}"
    # 表示幅: アイコン(1) + 空白(1) + パーセント文字列
    return Segment(text=label, width=len(pct_str) + 2)


def _seg_lines(data: dict[str, Any]) -> Segment | None:
    """変更行数セグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        "+N/-M"形式のSegment、変更がない場合はNone
    """
    cost = data.get("cost")
    if not isinstance(cost, dict):
        return None

    added = int(cost.get("total_lines_added", 0))
    removed = int(cost.get("total_lines_removed", 0))

    if added == 0 and removed == 0:
        return None

    lines_str = f"+{added}/-{removed}"
    label = f"{_ICON_PENCIL} {lines_str}"
    return Segment(text=label, width=len(lines_str) + 2)


def _seg_rate_5h(data: dict[str, Any]) -> Segment | None:
    """5時間レートリミットセグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        "5h NN% <- HH:MM"形式のSegment
    """
    usage = data.get("_usage")
    if not isinstance(usage, dict):
        return None

    five_hour = usage.get("five_hour")
    if not isinstance(five_hour, dict):
        return None

    utilization = five_hour.get("utilization")
    resets_at = five_hour.get("resets_at")
    if utilization is None or resets_at is None:
        return None

    pct_val = float(utilization) * 100
    pct_int = int(pct_val)
    color = _color_for_utilization(pct_val)

    try:
        reset_str = _format_reset_time_short(str(resets_at))
    except ValueError, TypeError:
        return None

    pct_str = f"{pct_int}%"
    colored_pct = _colorize(pct_str, color)
    # "\uf017 5h 42% <- 23:00" 形式
    plain = f"5h {pct_str} \u2190 {reset_str}"
    label = f"{_ICON_CLOCK} 5h {colored_pct} \u2190 {reset_str}"
    return Segment(text=label, width=len(plain) + 2)


def _seg_rate_7d(data: dict[str, Any]) -> Segment | None:
    """7日間レートリミットセグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        "7d NN% <- M/D HH:MM"形式のSegment
    """
    usage = data.get("_usage")
    if not isinstance(usage, dict):
        return None

    seven_day = usage.get("seven_day")
    if not isinstance(seven_day, dict):
        return None

    utilization = seven_day.get("utilization")
    resets_at = seven_day.get("resets_at")
    if utilization is None or resets_at is None:
        return None

    pct_val = float(utilization) * 100
    pct_int = int(pct_val)
    color = _color_for_utilization(pct_val)

    try:
        reset_str = _format_reset_date(str(resets_at))
    except ValueError, TypeError:
        return None

    pct_str = f"{pct_int}%"
    colored_pct = _colorize(pct_str, color)
    # "\uf073 7d 7% <- 3/9 18:00" 形式
    plain = f"7d {pct_str} \u2190 {reset_str}"
    label = f"{_ICON_CALENDAR} 7d {colored_pct} \u2190 {reset_str}"
    return Segment(text=label, width=len(plain) + 2)


# ---------------------------------------------------------------------------
# レイアウトエンジン
# ---------------------------------------------------------------------------


def _render_line(segments: list[Segment]) -> str:
    """セグメントのリストをセパレータで結合して1行にする

    Args:
        segments: 結合対象のSegmentリスト

    Returns:
        セパレータで結合された文字列
    """
    sep = _colorize(_SEPARATOR, _Color.DIM)
    return sep.join(s.text for s in segments)


def _calc_line_width(segments: list[Segment]) -> int:
    """セグメントリストの合計表示幅を計算する(ANSI除外)

    Args:
        segments: 幅を計算するSegmentリスト

    Returns:
        セパレータ込みの表示幅
    """
    if not segments:
        return 0
    total = sum(s.width for s in segments)
    total += _SEPARATOR_WIDTH * (len(segments) - 1)
    return total


def _build_lines(data: dict[str, Any], terminal_width: int) -> list[str]:
    """行定義に従ってステータスラインを構築する

    overflow_indexが指定されている場合、1行に収まらなければ
    その位置で分割して次行に押し出す

    Args:
        data: stdinから読み込んだJSON辞書(+ _usageキー)
        terminal_width: ターミナルの表示幅

    Returns:
        表示用の文字列リスト(各要素が1行)
    """
    output_lines: list[str] = []

    for line_cfg in _LINES:
        # セグメントを生成する(Noneは除外)
        segments: list[Segment] = []
        for fn in line_cfg.segment_fns:
            seg = fn(data)
            if seg is not None:
                segments.append(seg)

        if not segments:
            continue

        # 1行に収まるかチェックする
        total_width = _calc_line_width(segments)

        if total_width <= terminal_width or line_cfg.overflow_index is None:
            # 収まる場合、またはオーバーフロー分割なしの場合は1行で出力
            output_lines.append(_render_line(segments))
        else:
            # overflow_indexで分割する
            idx = line_cfg.overflow_index
            # 実際のセグメント数に対してidxが有効かチェック
            if idx <= 0 or idx >= len(segments):
                # 分割できない場合はそのまま1行で出力
                output_lines.append(_render_line(segments))
            else:
                first_part = segments[:idx]
                second_part = segments[idx:]
                if first_part:
                    output_lines.append(_render_line(first_part))
                if second_part:
                    output_lines.append(_render_line(second_part))

    return output_lines


# ---------------------------------------------------------------------------
# 行定義
# ---------------------------------------------------------------------------

_LINES = [
    _LineConfig(
        segment_fns=[_seg_project, _seg_branch, _seg_model, _seg_context, _seg_lines],
        overflow_index=2,  # model以降を次行に押し出す
    ),
    _LineConfig(
        segment_fns=[_seg_rate_5h, _seg_rate_7d],
        overflow_index=None,
    ),
]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    """stdinからClaude Codeのステータス情報JSONを読み取り表示する

    Claude Codeのstatuslineフックから呼び出されることを想定する
    stdinにはプロジェクト情報やモデル情報を含むJSONが渡される
    """
    try:
        raw = sys.stdin.read()
    except OSError, UnicodeDecodeError:
        return

    if not raw.strip():
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    if not isinstance(data, dict):
        return

    typed_data = cast("dict[str, Any]", data)

    # レートリミット情報を取得してdataに格納する
    usage = _get_usage()
    if usage is not None:
        typed_data["_usage"] = usage

    terminal_width = shutil.get_terminal_size((120, 24)).columns

    lines = _build_lines(typed_data, terminal_width)
    if lines:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
