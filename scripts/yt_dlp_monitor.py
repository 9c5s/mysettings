# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pyperclip",
#     "yt-dlp",
# ]
# ///
"""yt-dlp用クリップボード監視ツール

クリップボードを監視し、URLが検出された場合特定の引数でyt-dlpを実行する
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Final, NoReturn
from urllib.parse import urlparse

import pyperclip
import yt_dlp
from yt_dlp.utils import DownloadError

# 設定
POLLING_INTERVAL: Final[float] = 0.1
DOWNLOAD_DIR: Final[Path] = Path.home() / "Downloads" / "yt_dlp"
YT_DLP_OPTIONS: Final[list[str]] = [
    "-S",
    "codec:avc:aac,res:1080,fps:60,hdr:sdr",
    "-f",
    "bv+ba",
    "-o",
    "%(title)s_%(height)s_%(fps)s_%(vcodec.:4)s_(%(id)s).%(ext)s",
    "--ppa",
    "Merger+ffmpeg_o1:-map_metadata -1",
    "--remote-components",
    "ejs:github",
]


def setup_logger() -> logging.Logger:
    """アプリケーションロガーを構成して返す"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%y/%m/%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def is_valid_url(text: str) -> bool:
    """指定されたテキストが有効なURLかどうかを判定する

    Args:
        text: 検証する文字列

    Returns:
        テキストが有効なHTTP(S) URLの場合はTrue、そうでない場合はFalse
    """
    try:
        parsed = urlparse(text)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def download_video(url: str, logger: logging.Logger) -> None:
    """指定されたURLに対してyt-dlpでダウンロードを実行する

    Args:
        url: ダウンロード対象のURL
        logger: 状態を出力するためのロガーインスタンス
    """
    # ダウンロードディレクトリが存在しない場合は作成する
    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception("ダウンロードディレクトリの作成に失敗しました")
        return

    opts = yt_dlp.parse_options([*YT_DLP_OPTIONS, "-P", str(DOWNLOAD_DIR)]).ydl_opts

    try:
        logger.info("ダウンロードを開始します: %s", url)
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        logger.info("ダウンロードが正常に完了しました")
    except DownloadError:
        logger.exception("ダウンロードに失敗しました")


def monitor_clipboard() -> NoReturn:
    """新しいURLがないかクリップボードを継続的に監視する

    定義された間隔でクリップボードの内容を確認する無限ループを実行する
    変更された内容が有効なURLである場合、ダウンロードプロセスをトリガーする
    """
    logger = setup_logger()
    logger.info("クリップボード監視を開始します")
    logger.info("停止するには Ctrl+C を押してください")

    last_text: str = ""

    try:
        # 起動時に既にURLが存在する場合に反応しないよう、
        # 現在のクリップボードの内容で last_text を初期化する
        last_text = pyperclip.paste()

        while True:
            try:
                current_text = pyperclip.paste()
            except pyperclip.PyperclipException:
                # クリップボードへのアクセスが一時的に失敗した場合の処理
                time.sleep(POLLING_INTERVAL)
                continue

            if current_text != last_text:
                last_text = current_text
                if is_valid_url(current_text):
                    logger.info("URLを検知しました: %s", current_text)
                    download_video(current_text, logger)
                else:
                    logger.debug(
                        "クリップボードの変更を検知しましたが、URLではありません"
                    )

            time.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        logger.info("クリップボード監視を停止します")
        sys.exit(0)


if __name__ == "__main__":
    monitor_clipboard()
