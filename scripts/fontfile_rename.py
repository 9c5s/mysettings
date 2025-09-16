# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "fonttools",
#     "pathvalidate",
# ]
# ///


"""指定ディレクトリ以下のフォントを収集し、整形して別ディレクトリにコピーするスクリプト"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
from typing import Any

from fontTools.ttLib import (  # pyright: ignore[reportMissingTypeStubs]
    TTFont,
    TTLibError,
)
from pathvalidate import sanitize_filename

# OpenType仕様に基づくName ID
# https://learn.microsoft.com/en-us/typography/opentype/spec/name#name-ids
NAME_ID_FAMILY = 1
NAME_ID_SUBFAMILY = 2


def _get_name_from_records(records: list[Any], name_id: int) -> str:
    """nameレコードから指定IDの文字列を取得する

    Args:
        records (list[Any]): フォントのnameテーブルから取得したnameレコードのリスト
        name_id (int): 取得対象のname ID

    Returns:
        str: Unicodeにデコードされたnameレコードの文字列 見つからない場合は空文字列
    """
    for record in records:
        if record.nameID == name_id and record.isUnicode():
            return record.toUnicode()
    return ""


def get_font_info(font_path: pathlib.Path) -> dict[str, str] | None:
    """フォントファイルから詳細情報を取得する

    Args:
        font_path (pathlib.Path): フォントファイルのパス

    Returns:
        dict[str, str] | None: フォント情報の辞書 読み取れない場合はNone
    """
    try:
        font: Any = TTFont(font_path, checkChecksums=False)
    except (TTLibError, OSError):
        return None
    else:
        info: dict[str, str] = {}
        info["format"] = "OTF" if "CFF " in font else "TTF"

        name_records: list[Any] = font["name"].names
        info["family"] = _get_name_from_records(name_records, NAME_ID_FAMILY)
        info["subfamily"] = _get_name_from_records(name_records, NAME_ID_SUBFAMILY)

        # ファミリー名がなければ処理しない
        if not info["family"]:
            return None

        return info


def _process_and_copy_files(target_dir: pathlib.Path, output_dir: pathlib.Path) -> int:
    """ファイルを走査し、フォントをコピーして処理数を返す

    Args:
        target_dir (pathlib.Path): 走査対象のディレクトリ
        output_dir (pathlib.Path): コピー先のディレクトリ

    Returns:
        int: コピーに成功したファイルの総数
    """
    copied_count = 0
    all_files = sorted([p for p in target_dir.rglob("*") if p.is_file()])

    for file_path in all_files:
        font_info = get_font_info(file_path)

        if font_info:
            ext = f".{font_info['format'].lower()}"
            family_name = font_info["family"]
            subfamily_name = font_info.get("subfamily")

            # サブファミリー名が存在し、'Regular'でない場合のみファイル名に含める
            if subfamily_name and subfamily_name.lower() != "regular":
                base_name = sanitize_filename(f"{family_name}-{subfamily_name}")
            else:
                base_name = sanitize_filename(family_name)

            new_path = output_dir / f"{base_name}{ext}"

            # 既存ファイルはスキップ
            if new_path.exists():
                print(f"スキップ: '{new_path.name}' は既に存在します。")
                continue

            # ファイルをコピー
            try:
                shutil.copy2(file_path, new_path)
            except OSError as e:
                print(
                    f"エラー: コピーに失敗しました {file_path.name} ({e})",
                    file=sys.stderr,
                )
            else:
                terminal_width = shutil.get_terminal_size((80, 20)).columns
                original_rel_path = f"'{file_path.relative_to(target_dir)}'"
                new_name = f"'{new_path.name}'"
                message = f"コピー: {original_rel_path} -> {new_name}"
                if len(message) > terminal_width:
                    message = f"コピー:\n  元: {original_rel_path}\n  先: {new_name}"
                print(message)
                copied_count += 1
    return copied_count


def main() -> None:
    """指定ディレクトリを再帰的に走査し、見つかったフォントをリネームしてコピーする"""
    parser = argparse.ArgumentParser(
        description=(
            "指定ディレクトリ以下のフォントを収集し、"
            "整形して別ディレクトリにコピーします。"
        )
    )
    parser.add_argument(
        "target_directory",
        nargs="?",
        default=".",
        help="走査するディレクトリのパス。指定しない場合はカレントディレクトリが対象です。",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "フォントをコピーする先のディレクトリ。"
            "指定しない場合は検索対象ディレクトリ内に'fonts'フォルダが作成されます。"
        ),
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    try:
        target_dir = pathlib.Path(args.target_directory).resolve(strict=True)
    except FileNotFoundError:
        print(
            f"エラー: 検索対象ディレクトリが見つかりません: {args.target_directory}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 出力ディレクトリを決定
    if args.output:
        # -o オプションが指定された場合はそのディレクトリを直接使用
        output_dir = pathlib.Path(args.output).resolve()
    else:
        # -o オプションがない場合は検索対象ディレクトリ内に'fonts'フォルダを作成
        output_dir = target_dir / "fonts"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"エラー: 出力ディレクトリの作成に失敗しました: {output_dir}\n{e}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"--- 検索対象 ---\n{target_dir}")
    print(f"--- コピー先 ---\n{output_dir}")
    print("--------------------")
    print("--- コピー処理開始 ---")

    copied_count = _process_and_copy_files(target_dir, output_dir)

    print("--------------------")
    if copied_count > 0:
        print(f"完了: {copied_count}個のフォントファイルをコピーしました。")
    else:
        print("完了: コピー対象のフォントファイルは見つかりませんでした。")


if __name__ == "__main__":
    main()
