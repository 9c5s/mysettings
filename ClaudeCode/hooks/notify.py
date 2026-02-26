# /// script
# requires-python = ">=3.14"
# dependencies = ["desktop-notifier>=6.0"]
# ///
"""Claude Code hooks用の通知スクリプト"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

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
    except OSError, UnicodeDecodeError:
        raw = ""

    if not raw.strip():
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    event = data.get("hook_event_name", "")
    template = TEMPLATES.get(event)
    if template is None:
        return

    project = get_project_name(data.get("cwd", ""))

    notifier = DesktopNotifierSync(app_name=APP_NAME)
    notifier.send(
        title=template.title,
        message=template.message.format(project=project),
        urgency=template.urgency,
        sound=DEFAULT_SOUND,
    )


if __name__ == "__main__":
    main()
