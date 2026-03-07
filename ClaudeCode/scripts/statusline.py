# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///

"""Claude Code statusline用のスクリプト

Claude Codeのステータスフックから呼び出され、ターミナル下部に
プロジェクト情報やAPIレートリミット状況を表示する
"""

# json.loads/dict.get由来のUnknown型が全関数に波及するため、ファイルレベルで抑制する
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

import contextlib
import json
import locale
import os
import platform
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class _Color(IntEnum):
    """ANSIカラーコード"""

    RED = 31
    GREEN = 32
    YELLOW = 33
    BLUE = 34
    RESET = 0


@dataclass(frozen=True, slots=True)
class Segment:
    """ステータスライン上の1セグメントを表す

    Attributes:
        text: ANSIエスケープ込みの表示文字列
    """

    text: str


@dataclass(frozen=True, slots=True)
class _LineConfig:
    """行のレイアウト定義

    Attributes:
        segment_fns: セグメント生成関数のリスト
    """

    segment_fns: list[Callable[[dict[str, Any]], Segment | None]] = field(
        default_factory=list,
    )


_SEPARATOR = " \u2502 "  # " │ "
_CACHE_TTL = 360  # 秒
_CACHE_PATH = Path(tempfile.gettempdir()) / "claude-usage-cache.json"
_API_URL = "https://api.anthropic.com/api/oauth/usage"
_API_TIMEOUT = 5
_GIT_CACHE_TTL = 5  # 秒
_GIT_CACHE_PATH = Path(tempfile.gettempdir()) / "claude-git-cache.json"


@dataclass(frozen=True, slots=True)
class _CurrencyInfo:
    """通貨のフォーマット情報"""

    symbol: str
    decimals: int


_CURRENCIES: dict[str, _CurrencyInfo] = {
    "USD": _CurrencyInfo(symbol="$", decimals=2),
    "EUR": _CurrencyInfo(symbol="\u20ac", decimals=2),
    "GBP": _CurrencyInfo(symbol="\u00a3", decimals=2),
    "JPY": _CurrencyInfo(symbol="\u00a5", decimals=0),
    "CNY": _CurrencyInfo(symbol="\u00a5", decimals=2),
    "KRW": _CurrencyInfo(symbol="\u20a9", decimals=0),
    "INR": _CurrencyInfo(symbol="\u20b9", decimals=2),
    "CAD": _CurrencyInfo(symbol="C$", decimals=2),
    "AUD": _CurrencyInfo(symbol="A$", decimals=2),
    "CHF": _CurrencyInfo(symbol="CHF", decimals=2),
    "BRL": _CurrencyInfo(symbol="R$", decimals=2),
    "SEK": _CurrencyInfo(symbol="kr", decimals=2),
    "NOK": _CurrencyInfo(symbol="kr", decimals=2),
    "DKK": _CurrencyInfo(symbol="kr", decimals=2),
    "PLN": _CurrencyInfo(symbol="z\u0142", decimals=2),
    "CZK": _CurrencyInfo(symbol="K\u010d", decimals=2),
    "TWD": _CurrencyInfo(symbol="NT$", decimals=0),
    "SGD": _CurrencyInfo(symbol="S$", decimals=2),
    "HKD": _CurrencyInfo(symbol="HK$", decimals=2),
    "MXN": _CurrencyInfo(symbol="MX$", decimals=2),
}

_LOCALE_TO_CURRENCY: dict[str, str] = {
    "JP": "JPY",
    "US": "USD",
    "GB": "GBP",
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "NL": "EUR",
    "BE": "EUR",
    "AT": "EUR",
    "FI": "EUR",
    "IE": "EUR",
    "PT": "EUR",
    "GR": "EUR",
    "LU": "EUR",
    "CN": "CNY",
    "KR": "KRW",
    "IN": "INR",
    "CA": "CAD",
    "AU": "AUD",
    "CH": "CHF",
    "BR": "BRL",
    "SE": "SEK",
    "NO": "NOK",
    "DK": "DKK",
    "PL": "PLN",
    "CZ": "CZK",
    "TW": "TWD",
    "SG": "SGD",
    "HK": "HKD",
    "MX": "MXN",
}


@dataclass(frozen=True, slots=True)
class _Icons:
    """アイコンセットの定義"""

    FOLDER: str = "📁"
    BRANCH: str = "🔀"
    MODEL: str = "🤖"
    CHART: str = "📊"
    PENCIL: str = "✏️"
    CLOCK: str = "⏰"
    CALENDAR: str = "📅"
    RESET: str = "🔁"
    MONEY: str = "💰"


_ICONS_NERD = _Icons(
    FOLDER="\uf07b",  # nf-fa-folder
    BRANCH="\ue725",  # nf-dev-git_branch
    MODEL="\U000f068c",  # nf-md-robot
    CHART="\uf080",  # nf-fa-bar_chart
    PENCIL="\U000f03eb",  # nf-md-pencil
    CLOCK="\uf017",  # nf-fa-clock_o
    CALENDAR="\uf073",  # nf-fa-calendar
    RESET="\uf0e2",  # nf-fa-undo
    MONEY="\U000f01f5",  # nf-md-currency_usd
)

_icons: _Icons = _Icons()


def _get_currency_from_locale() -> str:  # pyright: ignore[reportUnusedFunction] 次のPRで_seg_costから呼び出す
    """システムロケールから通貨コードを判定する

    ロケール文字列から国コードを抽出し、対応する通貨コードを返す
    判定できない場合はUSDを返す
    """
    try:
        loc, _ = locale.getlocale()
    except ValueError:
        return "USD"
    if not loc:
        return "USD"
    # "ja_JP" -> "JP", "en_US" -> "US"
    parts = loc.split("_")
    if len(parts) >= 2:
        country = parts[1].split(".")[0].upper()
        return _LOCALE_TO_CURRENCY.get(country, "USD")
    return "USD"


def _get_cwd(data: dict[str, Any]) -> str:
    """stdinデータからカレントディレクトリを取得する

    workspace.current_dirを優先し、フォールバックとしてcwdを使用する
    """
    workspace = data.get("workspace")
    if isinstance(workspace, dict):
        current_dir = workspace.get("current_dir")
        if current_dir:
            return str(current_dir)
    return str(data.get("cwd", ""))


def _osc8_link(url: str, text: str) -> str:
    """OSC 8エスケープシーケンスでクリッカブルリンクを生成する

    対応ターミナル(iTerm2, Kitty, WezTerm等)ではCtrl+クリックで開ける
    非対応ターミナルでは通常テキストとして表示される
    """
    return f"\033]8;;{url}\a{text}\033]8;;\a"


def _remote_to_https(remote_url: str) -> str | None:
    """GitリモートURLをHTTPS URLに変換する

    SSH形式(git@github.com:user/repo.git)とHTTPS形式の両方に対応する
    """
    url = remote_url.strip()
    if url.startswith("git@"):
        # git@github.com:user/repo.git -> https://github.com/user/repo
        url = url.replace(":", "/", 1).replace("git@", "https://", 1)
    url = url.removesuffix(".git")
    if url.startswith("https://"):
        return url
    return None


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
        0-59%: GREEN, 60-79%: YELLOW, 80-100%: RED
    """
    if pct >= 80:
        return _Color.RED
    if pct >= 60:
        return _Color.YELLOW
    return _Color.GREEN


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
    """リセット時刻を "h:mm" 形式でフォーマットする

    Args:
        iso_str: ISO 8601形式の日時文字列

    Returns:
        "H:MM" 形式の文字列(時は0埋めなし)
    """
    local_dt = _parse_iso_to_local(iso_str)
    return f"{local_dt.hour}:{local_dt.minute:02d}"


def _format_reset_date(iso_str: str) -> str:
    """リセット時刻を "M/D hh:mm" 形式でフォーマットする(0埋めなし)

    Args:
        iso_str: ISO 8601形式の日時文字列

    Returns:
        "M/D H:MM" 形式の文字列(時は0埋めなし)
    """
    local_dt = _parse_iso_to_local(iso_str)
    return f"{local_dt.month}/{local_dt.day} {local_dt.hour}:{local_dt.minute:02d}"


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
    with contextlib.suppress(
        OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError
    ):
        cred_text = cred_path.read_text(encoding="utf-8")
        cred_data = json.loads(cred_text)
        token = cred_data.get("claudeAiOauth", {}).get("accessToken")
        if token:
            return str(token)

    # 2. macOS Keychainから取得
    if platform.system() == "Darwin":
        with contextlib.suppress(
            subprocess.TimeoutExpired,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            OSError,
        ):
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

    return None


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
    with contextlib.suppress(
        OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError
    ):
        cache_text = _CACHE_PATH.read_text(encoding="utf-8")
        cache_obj = json.loads(cache_text)
        cached_ts = cache_obj.get("_cached_at", 0)
        cached_data = cache_obj.get("data")
        if now - cached_ts < _CACHE_TTL and cached_data is not None:
            return cached_data

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
    with contextlib.suppress(OSError):
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=_CACHE_PATH.parent, suffix=".tmp", prefix="claude-usage-"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(cache_obj, f)
            # Windowsではreplaceが安全に動作する(Python 3.3+)
            Path(tmp_name).replace(_CACHE_PATH)
            _CACHE_PATH.chmod(0o600)
        except OSError:
            # 書き込み失敗時はtmpファイルを削除する
            with contextlib.suppress(OSError):
                Path(tmp_name).unlink()

    return data


def _get_git_info(cwd: str) -> dict[str, Any] | None:
    """Gitのブランチ名とリモートURLをキャッシュ付きで取得する

    キャッシュのTTLは_GIT_CACHE_TTL秒である
    cwdが変わった場合はキャッシュを無効化する
    """
    now = datetime.now(UTC).timestamp()

    # キャッシュチェック
    with contextlib.suppress(OSError, json.JSONDecodeError, KeyError, TypeError):
        cache_text = _GIT_CACHE_PATH.read_text(encoding="utf-8")
        cache_obj = json.loads(cache_text)
        if (
            cache_obj.get("cwd") == cwd
            and now - cache_obj.get("_cached_at", 0) < _GIT_CACHE_TTL
        ):
            return cache_obj.get("data")

    # Git情報を取得する
    info: dict[str, Any] = {}
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=cwd or None,
            timeout=3,
            check=False,
        )
        branch = result.stdout.strip() if result.returncode == 0 else ""

        if branch == "HEAD":
            # Detached HEAD状態では短縮コミットハッシュを取得する
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
                capture_output=True,
                text=True,
                cwd=cwd or None,
                timeout=3,
                check=False,
            )
            branch = result.stdout.strip()

        if not branch:
            return None

        info["branch"] = branch

        # リモートURLを取得する
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=cwd or None,
            timeout=3,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            info["remote_url"] = result.stdout.strip()

    except subprocess.TimeoutExpired, subprocess.SubprocessError, OSError:
        return None

    # キャッシュ保存
    cache_obj = {"_cached_at": now, "cwd": cwd, "data": info}
    with contextlib.suppress(OSError):
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=_GIT_CACHE_PATH.parent, suffix=".tmp", prefix="claude-git-"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(cache_obj, f)
            Path(tmp_name).replace(_GIT_CACHE_PATH)
        except OSError:
            with contextlib.suppress(OSError):
                Path(tmp_name).unlink()

    return info


def _seg_project(data: dict[str, Any]) -> Segment | None:
    """プロジェクト名セグメントを生成する

    GitリモートURLが取得できる場合はOSC 8クリッカブルリンクにする
    """
    cwd = _get_cwd(data)
    name = Path(cwd).name or "unknown"

    # リモートURLからHTTPSリンクを生成する
    git_info = data.get("_git")
    repo_url = None
    if isinstance(git_info, dict):
        remote_url = git_info.get("remote_url", "")
        if remote_url:
            repo_url = _remote_to_https(remote_url)

    display = f"{_icons.FOLDER} {name}"
    if repo_url:
        display = f"{_icons.FOLDER} {_osc8_link(repo_url, name)}"

    label = _colorize(display, _Color.BLUE)
    return Segment(text=label)


def _seg_branch(data: dict[str, Any]) -> Segment | None:
    """Gitブランチ名セグメントを生成する

    GitリモートURLが取得できる場合はOSC 8クリッカブルリンクにする
    """
    git_info = data.get("_git")
    if not isinstance(git_info, dict):
        return None
    branch = git_info.get("branch")
    if not branch:
        return None

    # リモートURLからブランチページのリンクを生成する
    remote_url = git_info.get("remote_url", "")
    branch_url = None
    if remote_url:
        repo_url = _remote_to_https(remote_url)
        if repo_url:
            branch_url = f"{repo_url}/tree/{branch}"

    if branch_url:
        display = f"{_icons.BRANCH} {_osc8_link(branch_url, branch)}"
    else:
        display = f"{_icons.BRANCH} {branch}"

    label = _colorize(display, _Color.YELLOW)
    return Segment(text=label)


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
    if version and version not in display_name:
        model_text = f"{display_name} {version}"
    else:
        model_text = display_name

    label = f"{_icons.MODEL} {model_text}"
    return Segment(text=label)


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
            if len(part) >= 4:
                break  # 日付文字列(20240229等)はバージョンではないためスキップ
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

    try:
        pct_val = float(pct)
    except ValueError, TypeError:
        return None
    pct_int = int(pct_val)
    color = _color_for_utilization(pct_val)
    pct_str = f"{pct_int}%"

    colored_pct = _colorize(pct_str, color)
    label = f"{_icons.CHART} {colored_pct}"
    # 表示幅: アイコン(1) + 空白(1) + パーセント文字列
    return Segment(text=label)


def _seg_lines(data: dict[str, Any]) -> Segment | None:  # pyright: ignore[reportUnusedFunction] 現在は非表示だが将来の再利用のため保持
    """変更行数セグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        "+N/-M"形式のSegment、変更がない場合はNone
    """
    cost = data.get("cost")
    if not isinstance(cost, dict):
        return None

    try:
        added = int(cost.get("total_lines_added", 0))
        removed = int(cost.get("total_lines_removed", 0))
    except ValueError, TypeError:
        return None

    if added == 0 and removed == 0:
        return None

    colored_add = _colorize(f"+{added}", _Color.GREEN)
    colored_del = _colorize(f"-{removed}", _Color.RED)
    label = f"{_icons.PENCIL} {colored_add}/{colored_del}"
    return Segment(text=label)


def _seg_rate_common(
    data: dict[str, Any],
    usage_key: str,
    period_label: str,
    icon: str,
    fmt_reset: Callable[[str], str],
) -> Segment | None:
    """レートリミットセグメントの共通生成ロジック

    Args:
        data: stdinから読み込んだJSON辞書
        usage_key: usageデータ内のキー("five_hour" / "seven_day")
        period_label: 表示用の期間ラベル("5h" / "7d")
        icon: Nerd Fontsアイコン
        fmt_reset: リセット時刻のフォーマット関数

    Returns:
        "{period_label} NN% <- reset_time"形式のSegment
    """
    usage = data.get("_usage")
    if not isinstance(usage, dict):
        return None

    bucket = usage.get(usage_key)
    if not isinstance(bucket, dict):
        return None

    utilization = bucket.get("utilization")
    resets_at = bucket.get("resets_at")
    if utilization is None or resets_at is None:
        return None

    try:
        pct_val = float(utilization)
        reset_str = fmt_reset(str(resets_at))
    except ValueError, TypeError:
        return None

    color = _color_for_utilization(pct_val)

    pct_str = f"{int(pct_val)}%"
    colored_pct = _colorize(pct_str, color)
    label = f"{icon} {period_label} {colored_pct} {_icons.RESET} {reset_str}"
    return Segment(text=label)


def _seg_rate_5h(data: dict[str, Any]) -> Segment | None:
    """5時間レートリミットセグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        "5h NN% <- reset_time"形式のSegment、データ不足時はNone
    """
    return _seg_rate_common(
        data, "five_hour", "5h", _icons.CLOCK, _format_reset_time_short
    )


def _seg_rate_7d(data: dict[str, Any]) -> Segment | None:
    """7日間レートリミットセグメントを生成する

    Args:
        data: stdinから読み込んだJSON辞書

    Returns:
        "7d NN% <- reset_time"形式のSegment、データ不足時はNone
    """
    return _seg_rate_common(
        data, "seven_day", "7d", _icons.CALENDAR, _format_reset_date
    )


def _seg_cost(data: dict[str, Any]) -> Segment | None:
    """セッションコストセグメントを生成する"""
    cost = data.get("cost")
    if not isinstance(cost, dict):
        return None

    total_cost = cost.get("total_cost_usd")
    if total_cost is None:
        return None

    try:
        cost_val = float(total_cost)
    except ValueError, TypeError:
        return None

    label = f"{_icons.MONEY} ${cost_val:.2f}"
    return Segment(text=label)


def _render_line(segments: list[Segment]) -> str:
    """セグメントのリストをセパレータで結合して1行にする

    Args:
        segments: 結合対象のSegmentリスト

    Returns:
        セパレータで結合された文字列
    """
    sep = _SEPARATOR
    return sep.join(s.text for s in segments)


def _build_lines(data: dict[str, Any]) -> list[str]:
    """行定義に従ってステータスラインを構築する

    Args:
        data: stdinから読み込んだJSON辞書(+ _usageキー)

    Returns:
        表示用の文字列リスト(各要素が1行)
    """
    output_lines: list[str] = []

    for line_cfg in _LINES:
        segments: list[Segment] = []
        for fn in line_cfg.segment_fns:
            seg = fn(data)
            if seg is not None:
                segments.append(seg)

        if segments:
            output_lines.append(_render_line(segments))

    return output_lines


_LINES = [
    _LineConfig(segment_fns=[_seg_project, _seg_branch]),
    _LineConfig(segment_fns=[_seg_model, _seg_context, _seg_rate_5h, _seg_rate_7d]),
    _LineConfig(segment_fns=[_seg_cost]),
]


def main() -> None:
    """stdinからClaude Codeのステータス情報JSONを読み取り表示する

    Claude Codeのstatuslineフックから呼び出されることを想定する
    stdinにはプロジェクト情報やモデル情報を含むJSONが渡される
    --icons=nerd を指定するとNerd Fontsアイコンを使用する
    """
    global _icons  # noqa: PLW0603
    _icons = _ICONS_NERD if "--icons=nerd" in sys.argv else _Icons()

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

    # Git情報を取得してdataに格納する
    cwd = _get_cwd(data)
    git_info = _get_git_info(cwd) if cwd else None
    if git_info is not None:
        data["_git"] = git_info

    # レートリミット情報を取得してdataに格納する
    usage = _get_usage()
    if usage is not None:
        data["_usage"] = usage

    lines = _build_lines(data)
    if lines:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
