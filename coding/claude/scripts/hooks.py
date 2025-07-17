#!/usr/bin/env python3
"""Claude Code hooks processor - リファクタリング版

単一責任の原則に基づいて再設計されたフックプロセッサー。
t-wada式TDDに従って、既存のテストを通しながら設計を改善。
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    import types
    from typing import Self


class HookEventName:
    """フックイベント名の定数クラス

    Claude Codeのフックシステムで使用されるイベント名を定義する
    """

    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    NOTIFICATION = "Notification"
    STOP = "Stop"
    SUBAGENT_STOP = "SubagentStop"

    @classmethod
    def all(cls) -> list[str]:
        """全てのイベント名を返す"""
        return [
            cls.PRE_TOOL_USE,
            cls.POST_TOOL_USE,
            cls.NOTIFICATION,
            cls.STOP,
            cls.SUBAGENT_STOP,
        ]

    @classmethod
    def tool_events(cls) -> list[str]:
        """ツールイベント(tool_nameを持つイベント)のみを返す"""
        return [
            cls.PRE_TOOL_USE,
            cls.POST_TOOL_USE,
        ]


class ToolName:
    """ツール名の定数クラス

    Claude Codeで使用可能なツール名を定義する
    """

    TASK = "Task"
    BASH = "Bash"
    GLOB = "Glob"
    GREP = "Grep"
    LS = "LS"
    EXIT_PLAN_MODE = "exit_plan_mode"
    READ = "Read"
    EDIT = "Edit"
    MULTI_EDIT = "MultiEdit"
    WRITE = "Write"
    NOTEBOOK_READ = "NotebookRead"
    NOTEBOOK_EDIT = "NotebookEdit"
    WEB_FETCH = "WebFetch"
    WEB_SEARCH = "WebSearch"


class ErrorHandler:
    """エラーハンドリングの単一責任クラス

    すべてのエラー処理を統一的に管理する
    """

    @staticmethod
    def handle_warning(error: Exception, context: str) -> None:
        """警告レベルエラーの処理"""
        print(f"WARNING [{context}]: {error}", file=sys.stderr)
        sys.exit(2)

    @staticmethod
    def handle_subprocess_error(
        error: subprocess.CalledProcessError, context: str
    ) -> None:
        """subprocess実行エラーの詳細処理

        外部コマンドエラー時に詳細な出力を表示する
        """
        print(
            f"ERROR [{context}]: Command failed with exit code {error.returncode}",
            file=sys.stderr,
        )
        if error.stdout:
            print("STDOUT:", file=sys.stderr)
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print("STDERR:", file=sys.stderr)
            print(error.stderr, file=sys.stderr)
        sys.exit(2)

    @staticmethod
    def handle_fatal_error(error: BaseException, context: str) -> None:
        """致命的エラーの統一処理"""
        print(f"FATAL ERROR [{context}]: {error}", file=sys.stderr)
        sys.exit(2)


class ExecutionContext:
    """実行コンテキストの構造化クラス

    Pike的: シンプルで明確なデータ構造
    """

    def __init__(self, json_data: dict[str, Any]) -> None:
        """実行コンテキストを初期化する"""
        self.session_id = json_data.get("session_id", "")
        self.hook_event_name = json_data.get("hook_event_name", "")
        self.tool_name = json_data.get("tool_name", "")
        self.timestamp = time.time()
        self.process_id = os.getpid()
        # 一意識別子の生成(Carmack的高速ハッシュ)
        self.execution_id = self._generate_execution_id()

    def _generate_execution_id(self) -> str:
        """実行IDを生成する(高速ハッシュ) - timestamp除外でプロセス間共通化"""
        # timestampを除外し、同一のセッション+イベント+ツールには同一IDを生成
        base_content = f"{self.session_id}:{self.hook_event_name}"
        tool_content = f":{self.tool_name}"
        content = base_content + tool_content
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class ExecutionGuard:
    """プロセス排他制御クラス

    Carmack的: 最小オーバーヘッド、ナノ秒精度
    Martin的: 単一責任の原則
    Pike的: シンプルで理解しやすい実装
    """

    def __init__(self, context: ExecutionContext) -> None:
        """ExecutionGuardを初期化する"""
        self.context = context
        lock_name = f"execution_{context.execution_id}.lock"
        self.lock_file_path = Path(f".claude/log/{lock_name}")
        self.is_locked = False

    def __enter__(self) -> bool:
        """実行許可を判定し、排他制御を開始する"""
        # 既存の同一実行をチェック(Pike的明示的チェック)
        if self._is_duplicate_execution():
            return False

        # ファイルロックで排他制御(Carmack的高速)
        try:
            self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
            self.lock_file = self.lock_file_path.open("w")
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # プロセス情報を記録
            process_info = f"{self.context.process_id}:{self.context.timestamp}"
            self.lock_file.write(process_info)
            self.lock_file.flush()
            self.is_locked = True
        except (OSError, BlockingIOError):
            # ロック取得に失敗(重複実行検出)
            return False
        else:
            return True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """排他制御を終了し、リソースを解放する"""
        if self.is_locked and hasattr(self, "lock_file"):
            # システム終了時の競合を避けるため、全ての例外を抑制
            with contextlib.suppress(OSError, IOError):
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                # ロックファイルを削除(Carmack的クリーンアップ)
                with contextlib.suppress(FileNotFoundError):
                    self.lock_file_path.unlink()

    def _is_duplicate_execution(self) -> bool:
        """重複実行かどうかを判定する(Pike的明示的判定)"""
        # 実行履歴ファイルでグローバルな重複チェック
        history_file = Path("/Users/xin/.claude/log/execution_history.log")
        current_time = self.context.timestamp

        try:
            # 履歴ファイルから最近の実行を確認
            if history_file.exists():
                with history_file.open("r") as f:
                    for line in f:
                        if line.strip():
                            with contextlib.suppress(ValueError):
                                exec_id, timestamp = line.strip().split(":", 1)
                                time_diff = current_time - float(timestamp)
                                # 同じIDで5秒以内の実行は重複とみなす
                                is_same_id = exec_id == self.context.execution_id
                                if is_same_id and time_diff < 5.0:
                                    return True

            # 履歴記録は別の場所で行う(重複チェックと分離)

        except OSError:
            # ファイル操作エラーは重複ではないとみなす
            return False

        return False


class FileLock:
    """ファイルロックのコンテキストマネージャー

    既存の実装を維持 (単一責任で適切に設計済み)
    """

    def __init__(self, lock_file_path: Path) -> None:
        """FileLockを初期化する."""
        self.lock_file_path = lock_file_path
        self.lock_file = None

    def __enter__(self) -> Self:
        """FileLockを取得して自分自身を返す."""
        self.lock_file = self.lock_file_path.open("w")
        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """FileLockを解放してロックファイルを削除する."""
        if self.lock_file:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            self.lock_file.close()
        # ロックファイルを削除
        with contextlib.suppress(FileNotFoundError):
            self.lock_file_path.unlink()


class JsonInputReader:
    """JSON入力の読み取り・解析を担当するクラス

    単一責任: 標準入力からJSONデータを読み取り、パースする
    """

    def read_json_input(self) -> dict[str, Any]:
        """標準入力からJSONデータを読み取る"""
        try:
            json_str = sys.stdin.read()
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            ErrorHandler.handle_fatal_error(e, "JsonInputReader.read_json_input")
            return {}

    def get_json_value(self, json_data: dict[str, Any], field: str) -> str | None:
        """JSONデータから指定したフィールドの値を取得する"""
        return json_data.get(field)


class HookLogger:
    """フックログの記録を担当するクラス

    単一責任: ログファイルへの記録とタイムスタンプ管理
    """

    def __init__(self, log_file_path: Path, lock_file_path: Path) -> None:
        """HookLoggerを初期化する."""
        self.log_file_path = log_file_path
        self.lock_file_path = lock_file_path

    def log_with_timestamp(self, json_data: dict[str, Any]) -> None:
        """タイムスタンプ付きでJSONデータをログファイルに記録する"""
        # ログディレクトリを作成
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)

        # タイムスタンプを追加 (日本時間)
        jst = ZoneInfo("Asia/Tokyo")
        log_entry = {
            "timestamp": datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S"),
            **json_data,
        }

        # ファイルロックを使用してログを追記
        with (
            FileLock(self.lock_file_path),
            self.log_file_path.open("a", encoding="utf-8") as f,
        ):
            json.dump(log_entry, f, ensure_ascii=False)
            f.write("\n")


class BaseToolHandler(ABC):
    """ツールハンドラーの抽象基底クラス

    単一責任: ツール処理の共通インターフェース定義
    """

    @abstractmethod
    def handle_before(self, json_data: dict[str, Any]) -> None:
        """ツール実行前処理"""

    @abstractmethod
    def handle_after(self, json_data: dict[str, Any]) -> None:
        """ツール実行後処理"""

    @abstractmethod
    def handle_error(self, json_data: dict[str, Any]) -> None:
        """エラー処理"""


class BashToolHandler(BaseToolHandler):
    """Bashツールのハンドラー

    単一責任: Bash関連のツール処理
    """

    def handle_before(self, json_data: dict[str, Any]) -> None:
        """bash実行前処理"""
        _ = json_data  # 将来の拡張のために保持
        print("TODO: bash前処理")

    def handle_after(self, json_data: dict[str, Any]) -> None:
        """bash実行後処理"""
        _ = json_data  # 将来の拡張のために保持
        print("TODO: bash後処理")

    def handle_error(self, json_data: dict[str, Any]) -> None:
        """bashエラー処理"""
        error_message = json_data.get("error_message")
        print(f"TODO: bashエラー処理 - Error: {error_message}")


class FileOperationHandler(BaseToolHandler):
    """ファイル操作ツールのハンドラー

    単一責任: ファイル操作 (read, edit, write) の処理
    """

    def handle_before(self, json_data: dict[str, Any]) -> None:
        """ファイル操作前処理"""
        _ = json_data  # 将来の拡張のために保持
        print("TODO: ファイル操作前処理")

    def handle_after(self, json_data: dict[str, Any]) -> None:
        """ファイル操作後処理"""
        # tool_nameを取得してチェック
        tool_name = json_data.get("tool_name")

        # Write、Edit、MultiEditのみでリント・フォーマット実行
        if tool_name in [ToolName.WRITE, ToolName.EDIT, ToolName.MULTI_EDIT]:
            tool_input = json_data.get("tool_input", {})
            file_path = tool_input.get("file_path")

            if file_path and self._is_python_file(file_path):
                self.run_ruff_processing(file_path)

    def handle_error(self, json_data: dict[str, Any]) -> None:
        """ファイル操作エラー処理"""
        error_message = json_data.get("error_message")
        print(f"TODO: ファイル操作エラー処理 - Error: {error_message}")

    def _is_python_file(self, file_path: str) -> bool:
        """Pythonファイルかどうかを判定する"""
        return file_path.endswith((".py", ".pyi"))

    def run_ruff_processing(self, file_path: str) -> None:
        """Ruffリンティングとフォーマットを実行する"""
        # 1. リンティングと自動修正を実行
        self._run_ruff_lint(file_path)

        # 2. フォーマットを実行
        self._run_ruff_format(file_path)

    def _run_ruff_lint(self, file_path: str) -> None:
        """Ruffリンティングと自動修正を実行する"""
        try:
            result = subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "uv",
                    "run",
                    "ruff",
                    "check",
                    "--fix",
                    "--config",
                    "~/projects/mysettings/coding/python/ruff.toml",
                    file_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"Ruffリンティング実行: {file_path} - {result.returncode}")
        except subprocess.CalledProcessError as e:
            ErrorHandler.handle_subprocess_error(e, "_run_ruff_lint")
        except FileNotFoundError as e:
            ErrorHandler.handle_fatal_error(e, "_run_ruff_lint")

    def _run_ruff_format(self, file_path: str) -> None:
        """Ruffフォーマットを実行する"""
        try:
            result = subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "uv",
                    "run",
                    "ruff",
                    "format",
                    "--config",
                    "~/projects/mysettings/coding/python/ruff.toml",
                    file_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"Ruffフォーマット実行: {file_path} - {result.returncode}")
        except subprocess.CalledProcessError as e:
            ErrorHandler.handle_subprocess_error(e, "_run_ruff_format")
        except FileNotFoundError as e:
            ErrorHandler.handle_fatal_error(e, "_run_ruff_format")


class ToolHandlerRegistry:
    """ツールハンドラーの登録・管理を担当するクラス

    単一責任: ツール名とハンドラーの対応管理
    """

    def __init__(self) -> None:
        """ToolHandlerRegistryを初期化する."""
        self._handlers: dict[str, BaseToolHandler] = {}
        self._setup_default_handlers()

    def _setup_default_handlers(self) -> None:
        """デフォルトハンドラーを設定する"""
        bash_handler = BashToolHandler()
        file_handler = FileOperationHandler()

        # 定数を使用してハンドラーを登録
        self._handlers[ToolName.BASH] = bash_handler
        self._handlers[ToolName.READ] = file_handler
        self._handlers[ToolName.EDIT] = file_handler
        self._handlers[ToolName.MULTI_EDIT] = file_handler
        self._handlers[ToolName.WRITE] = file_handler
        self._handlers[ToolName.NOTEBOOK_READ] = file_handler
        self._handlers[ToolName.NOTEBOOK_EDIT] = file_handler

    def register_handler(self, tool_name: str, handler: BaseToolHandler) -> None:
        """ツールハンドラーを登録する"""
        self._handlers[tool_name] = handler

    def get_handler(self, tool_name: str) -> BaseToolHandler:
        """ツール名に対応するハンドラーを取得する"""
        # 直接マッチを試行
        if tool_name in self._handlers:
            return self._handlers[tool_name]

        # デフォルトハンドラー: 何もしない簡単な実装
        class NoOpHandler(BaseToolHandler):
            def handle_before(self, json_data: dict[str, Any]) -> None:
                pass

            def handle_after(self, json_data: dict[str, Any]) -> None:
                pass

            def handle_error(self, json_data: dict[str, Any]) -> None:
                pass

        return NoOpHandler()


class HookCoordinator:
    """フック処理全体を調整するクラス

    単一責任: 各コンポーネントの連携とメイン処理フロー
    """

    def __init__(self) -> None:
        """HookCoordinatorを初期化する."""
        self.json_reader = JsonInputReader()
        self.logger = HookLogger(
            log_file_path=Path(".claude/log/hooks.log"),
            lock_file_path=Path(".claude/log/hooks.log.lock"),
        )
        self.tool_registry = ToolHandlerRegistry()

    def process(self) -> None:
        """メイン処理 - 重複実行防止機能付き"""
        # JSONデータを読み取り
        json_data = self.json_reader.read_json_input()

        # 実行コンテキストを作成
        context = ExecutionContext(json_data)

        # 重複実行防止チェック(Carmack的高速判定)
        with ExecutionGuard(context) as is_allowed:
            if not is_allowed:
                # 重複実行の場合、処理をスキップ
                return

            # 重複でない場合のみ処理を続行
            # 実行履歴に記録
            self._record_execution(context)
            
            # ログに記録
            self.logger.log_with_timestamp(json_data)

            # イベント処理
            self._handle_hook_event(json_data)

    def _record_execution(self, context: ExecutionContext) -> None:
        """実行を履歴に記録する"""
        history_file = Path("/Users/xin/.claude/log/execution_history.log")
        try:
            history_file.parent.mkdir(parents=True, exist_ok=True)
            with history_file.open("a") as f:
                f.write(f"{context.execution_id}:{context.timestamp}\n")
        except OSError:
            # ファイル操作エラーは無視
            pass

    def _handle_hook_event(self, json_data: dict[str, Any]) -> None:
        """フックイベントを処理する"""
        hook_event_name = self.json_reader.get_json_value(json_data, "hook_event_name")
        tool_name = self.json_reader.get_json_value(json_data, "tool_name")

        if hook_event_name == HookEventName.PRE_TOOL_USE and tool_name:
            self.handle_before_tool_use(tool_name, json_data)
        elif hook_event_name == HookEventName.POST_TOOL_USE and tool_name:
            self.handle_after_tool_use(tool_name, json_data)
        elif hook_event_name in (
            HookEventName.NOTIFICATION,
            HookEventName.STOP,
            HookEventName.SUBAGENT_STOP,
        ):
            self._handle_non_tool_event(hook_event_name, json_data)

    def handle_before_tool_use(
        self,
        tool_name: str,
        json_data: dict[str, Any],
    ) -> None:
        """ツール実行前処理"""
        handler = self.tool_registry.get_handler(tool_name)
        handler.handle_before(json_data)

    def handle_after_tool_use(self, tool_name: str, json_data: dict[str, Any]) -> None:
        """ツール実行後処理"""
        handler = self.tool_registry.get_handler(tool_name)
        handler.handle_after(json_data)

    def handle_error(self, tool_name: str, json_data: dict[str, Any]) -> None:
        """エラー処理"""
        handler = self.tool_registry.get_handler(tool_name)
        handler.handle_error(json_data)

    def _handle_non_tool_event(
        self,
        event_name: str,
        json_data: dict[str, Any],
    ) -> None:
        """ツール以外のイベント処理(Notification, Stop, SubagentStop)"""
        if event_name == HookEventName.NOTIFICATION:
            print(f"通知イベント: {json_data.get('message', 'メッセージなし')}")
        elif event_name == HookEventName.STOP:
            stop_hook_active = json_data.get("stop_hook_active", False)
            print(f"停止イベント: stop_hook_active={stop_hook_active}")
        elif event_name == HookEventName.SUBAGENT_STOP:
            print("サブエージェント停止イベント")


def main() -> None:
    """メイン関数"""
    try:
        coordinator = HookCoordinator()
        coordinator.process()
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001
        ErrorHandler.handle_fatal_error(e, "main")


if __name__ == "__main__":
    main()
