# /// script
# requires-python = ">=3.14"
# dependencies = ["desktop-notifier>=6.0"]
# ///
"""Claude Code hooks用の通知スクリプト"""

import json
import sys
from dataclasses import dataclass
from typing import Any, cast

from desktop_notifier import DEFAULT_SOUND, DesktopNotifierSync, Urgency

APP_NAME = "Claude Code"


@dataclass(frozen=True, slots=True)
class _Template:
    """通知テンプレートを保持するデータクラス"""

    title: str
    message: str
    urgency: Urgency


# イベントごとの通知テンプレート
TEMPLATES: dict[str, _Template] = {
    "Notification": _Template(
        title="入力を待っています",
        message="{project} — 操作の許可または入力が必要です",
        urgency=Urgency.Normal,
    ),
    "Stop": _Template(
        title="応答が完了しました",
        message="{project}",
        urgency=Urgency.Normal,
    ),
}


def get_project_name(cwd: str) -> str:
    """作業ディレクトリからプロジェクト名を取得する.

    Args:
        cwd: 作業ディレクトリの絶対パス

    Returns:
        ディレクトリ名。空文字列の場合は "unknown" を返す。
    """
    if not cwd:
        return "unknown"
    # パスの最後のディレクトリ名を返す
    return cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def main() -> None:
    """stdinからhookイベントのJSONを読み取り、トースト通知を表示する.

    Claude Codeのhookから呼び出されることを想定する。
    stdinにはhook_event_name, cwdなどを含むJSONが渡される。
    対応イベント: Notification (入力待ち), Stop (応答完了)。
    通知の送信に失敗しても例外は発生しない。
    """
    try:
        raw = sys.stdin.read()
    except OSError, UnicodeDecodeError:
        raw = ""

    if not raw.strip():
        return

    try:
        raw_data = json.loads(raw)
    except json.JSONDecodeError:
        return

    if not isinstance(raw_data, dict):
        return

    data = cast("dict[str, Any]", raw_data)
    event = str(data.get("hook_event_name", ""))
    template = TEMPLATES.get(event)
    if template is None:
        return

    project = get_project_name(str(data.get("cwd", "")))

    try:
        notifier = DesktopNotifierSync(app_name=APP_NAME)
    except RuntimeError, OSError:
        # バックエンド未検出またはイベントループ生成失敗
        return

    notifier.send(
        title=template.title,
        message=template.message.replace("{project}", project),
        urgency=template.urgency,
        sound=DEFAULT_SOUND,
    )


if __name__ == "__main__":
    main()
