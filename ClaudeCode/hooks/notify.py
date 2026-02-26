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
    """作業ディレクトリからプロジェクト名を取得する."""
    if not cwd:
        return "unknown"
    # パスの最後のディレクトリ名を返す
    return cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def main() -> None:
    """stdinからhookイベントのJSONを読み取り、トースト通知を表示する."""
    try:
        raw = sys.stdin.read()
    except OSError, UnicodeDecodeError:  # PEP 758 (Python 3.14+)
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
        notifier.send(
            title=template.title,
            message=template.message.replace("{project}", project),
            urgency=template.urgency,
            sound=DEFAULT_SOUND,
        )
    except Exception:  # noqa: BLE001
        # 通知の送信失敗はユーザー操作をブロックすべきではない
        return


if __name__ == "__main__":
    main()
