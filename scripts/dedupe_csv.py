"""CSV重複行削除ツール

CSVファイルまたはテキストファイルから重複行を削除し
重複削除版と重複抽出版の2つのファイルを生成する
"""

# ruff: noqa: INP001

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, cast

import pandas as pd


@dataclass(frozen=True)
class ProcessingConfig:
    """CSV処理の設定を管理するデータクラス"""

    # ファイル処理設定
    encoding: str = "utf-8"
    target_extensions: tuple[str, ...] = (".txt", ".csv")

    # 出力設定
    unique_suffix: str = ""
    duplicate_suffix: str = "_d"
    output_extension: str = ".csv"

    # ログ設定
    log_level: str = "INFO"
    verbose: bool = False

    # CSV読み込み設定
    csv_params: dict[str, Any] = field(
        default_factory=lambda: {
            "header": None,
            "dtype": str,
            "na_filter": False,  # NA値として認識しない
            "keep_default_na": False,  # デフォルトNA値を無視
        }
    )

    # CSV出力設定
    output_params: dict[str, Any] = field(
        default_factory=lambda: {
            "index": False,
            "header": False,
            "encoding": "utf-8",
        }
    )


class CSVProcessor:
    """CSV重複削除処理を行うクラス"""

    def __init__(self, config: ProcessingConfig) -> None:
        """CSVProcessorを初期化する

        Args:
            config: 処理設定
        """
        self.config = config
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """ロガーを設定する

        Returns:
            設定済みのロガー
        """
        logger = logging.getLogger(__name__)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(levelname)s: %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        logger.setLevel(getattr(logging, self.config.log_level))
        return logger

    def process_file(self, file_path: pathlib.Path) -> bool:
        """ファイルを処理して重複削除版と重複抽出版の2つのCSVファイルを作成する

        Args:
            file_path: 処理対象のファイルパス

        Returns:
            処理が成功した場合True 失敗した場合False
        """
        # ファイルが空の場合は処理しない
        if file_path.stat().st_size == 0:
            self.logger.warning("スキップ: ファイルが空です: %s", file_path.name)
            return False

        # 出力パスを生成
        output_unique_path = self._generate_output_path(
            file_path, self.config.unique_suffix
        )
        output_duplicates_path = self._generate_output_path(
            file_path, self.config.duplicate_suffix
        )

        try:
            return self._process_file_internal(
                file_path, output_unique_path, output_duplicates_path
            )

        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            self.logger.exception("CSV読み込みエラー (%s)", file_path.name)
            return False
        except OSError:
            self.logger.exception("ファイルアクセスエラー (%s)", file_path.name)
            return False
        except (UnicodeDecodeError, MemoryError):
            self.logger.exception("予期しないエラー (%s)", file_path.name)
            return False

    def _generate_output_path(
        self, input_path: pathlib.Path, suffix: str
    ) -> pathlib.Path:
        """出力ファイルのパスを生成する

        Args:
            input_path: 入力ファイルのパス
            suffix: ファイル名に追加するサフィックス

        Returns:
            出力ファイルのパス
        """
        stem = input_path.stem + suffix
        return input_path.with_name(f"{stem}{self.config.output_extension}")

    def _process_file_internal(
        self,
        file_path: pathlib.Path,
        unique_path: pathlib.Path,
        duplicates_path: pathlib.Path,
    ) -> bool:
        """ファイルを一括処理する

        Args:
            file_path: 処理対象のファイルパス
            unique_path: 重複削除版の出力パス
            duplicates_path: 重複抽出版の出力パス

        Returns:
            処理が成功した場合True
        """
        df = cast(
            "pd.DataFrame",
            pd.read_csv(str(file_path), **self.config.csv_params),  # pyright: ignore[reportUnknownMemberType]
        )

        # データを昇順でソート（全カラムでソート）
        df = df.sort_values(by=df.columns.tolist(), na_position="last")

        # 重複行を削除したファイルを作成
        unique_df = df.drop_duplicates(keep="first")
        unique_df.to_csv(unique_path, **self.config.output_params)

        # 重複している行のみを抽出
        duplicated_mask = df.duplicated(keep=False)
        duplicates_df = df[duplicated_mask]

        # 重複行が存在する場合のみ重複ファイルを作成
        unique_duplicates_df = pd.DataFrame()
        if not duplicates_df.empty:
            unique_duplicates_df = duplicates_df.drop_duplicates(keep="first")
            unique_duplicates_df.to_csv(duplicates_path, **self.config.output_params)

            self.logger.info(
                "処理完了: %s -> %s, %s (元: %d行, 重複削除後: %d行, 重複: %d種類)",
                file_path.name,
                unique_path.name,
                duplicates_path.name,
                len(df),
                len(unique_df),
                len(unique_duplicates_df),
            )
        else:
            self.logger.info(
                "処理完了: %s -> %s (元: %d行, 重複行なし)",
                file_path.name,
                unique_path.name,
                len(df),
            )

        return True


class FileHandler:
    """ファイル処理を管理するクラス"""

    def __init__(self, config: ProcessingConfig) -> None:
        """FileHandlerを初期化する

        Args:
            config: 処理設定
        """
        self.config = config
        self.processor = CSVProcessor(config)
        self.logger = logging.getLogger(__name__)

    def process_path(self, path: pathlib.Path) -> tuple[int, int]:
        """パス(ファイルまたはディレクトリ)を処理する

        Args:
            path: 処理対象のパス

        Returns:
            (成功したファイル数, 処理したファイル総数) のタプル
        """
        if not path.exists():
            self.logger.error("パスが見つかりません: %s", path)
            return (0, 0)

        if path.is_dir():
            return self._process_directory(path)
        if path.is_file():
            return self._process_single_file(path)

        self.logger.warning("サポートされていないパスタイプ: %s", path)
        return (0, 0)

    def _process_directory(self, dir_path: pathlib.Path) -> tuple[int, int]:
        """ディレクトリ内のファイルを処理する

        Args:
            dir_path: 処理対象のディレクトリパス

        Returns:
            (成功したファイル数, 処理したファイル総数) のタプル
        """
        self.logger.info("ディレクトリを処理中: %s", dir_path)

        target_files: list[pathlib.Path] = []
        for ext in self.config.target_extensions:
            target_files.extend(dir_path.glob(f"*{ext}"))

        if not target_files:
            self.logger.warning(
                "処理対象のファイルが見つかりません(対象拡張子: %s)",
                ", ".join(self.config.target_extensions),
            )
            return (0, 0)

        success_count = 0
        for file_path in target_files:
            if self.processor.process_file(file_path):
                success_count += 1

        return (success_count, len(target_files))

    def _process_single_file(self, file_path: pathlib.Path) -> tuple[int, int]:
        """単一ファイルを処理する

        Args:
            file_path: 処理対象のファイルパス

        Returns:
            (成功したファイル数, 処理したファイル総数) のタプル
        """
        self.logger.info("ファイルを処理中: %s", file_path)

        if self.processor.process_file(file_path):
            return (1, 1)
        return (0, 1)


class CLIInterface:
    """コマンドライン インターフェースを管理するクラス"""

    def __init__(self) -> None:
        """CLIInterfaceを初期化する"""
        self.parser = self._create_parser()

    def _create_parser(self) -> argparse.ArgumentParser:
        """引数パーサーを作成する

        Returns:
            設定済みの引数パーサー
        """
        parser = argparse.ArgumentParser(
            description="CSV重複行削除ツール",
            epilog="ファイルやフォルダをスクリプトアイコンにドラッグ&ドロップしても実行できます",
        )

        parser.add_argument(
            "paths", nargs="*", help="処理対象のファイルまたはディレクトリのパス"
        )

        parser.add_argument(
            "-v", "--verbose", action="store_true", help="詳細なログを出力する"
        )

        parser.add_argument(
            "--encoding",
            default="utf-8",
            help="ファイルエンコーディング(デフォルト: utf-8)",
        )

        return parser

    def parse_args(self, args: list[str] | None = None) -> argparse.Namespace:
        """引数を解析する

        Args:
            args: 解析する引数リスト Noneの場合はsys.argvを使用

        Returns:
            解析済みの引数
        """
        return self.parser.parse_args(args)

    def print_help(self) -> None:
        """ヘルプメッセージを出力する"""
        self.parser.print_help()

    def create_config_from_args(self, args: argparse.Namespace) -> ProcessingConfig:
        """引数からProcessingConfigを作成する

        Args:
            args: 解析済みの引数

        Returns:
            ProcessingConfig インスタンス
        """
        return ProcessingConfig(
            encoding=args.encoding,
            log_level="DEBUG" if args.verbose else "INFO",
            verbose=args.verbose,
        )


def main() -> None:
    """メイン実行関数"""
    cli = CLIInterface()
    args = cli.parse_args()

    # 引数がない場合はヘルプを表示
    if not args.paths:
        cli.print_help()
        sys.exit(0)

    # 設定を作成
    config = cli.create_config_from_args(args)

    # ファイルハンドラーを初期化
    handler = FileHandler(config)
    logger = logging.getLogger(__name__)

    # ログレベルを設定
    logging.basicConfig(
        level=getattr(logging, config.log_level), format="%(levelname)s: %(message)s"
    )

    # 統計情報を記録
    total_success = 0
    total_processed = 0

    # 各パスを処理
    for path_str in args.paths:
        path = pathlib.Path(path_str)
        success, processed = handler.process_path(path)
        total_success += success
        total_processed += processed

    # 最終結果を報告
    if total_processed > 0:
        logger.info(
            "\n処理完了: %d/%d ファイルが正常に処理されました",
            total_success,
            total_processed,
        )
        if total_success < total_processed:
            logger.warning(
                "%d ファイルの処理に失敗しました",
                total_processed - total_success,
            )
            input("\n終了するにはEnterキーを押してください")
            sys.exit(1)
    else:
        logger.warning("処理対象のファイルが見つかりませんでした")
        input("\n終了するにはEnterキーを押してください")
        sys.exit(1)

    input("\n終了するにはEnterキーを押してください")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n処理が中断されました")
        sys.exit(130)
    except Exception:
        logging.getLogger(__name__).exception("予期しないエラーが発生しました")
        input("\n終了するにはEnterキーを押してください")
        sys.exit(1)
