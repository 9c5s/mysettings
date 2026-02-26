# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "plyer",
#     "pyobjus; sys_platform == 'darwin'",
#     "pyperclip",
#     "python-osc",
# ]
# ///
"""OSCクリップボード・通知スクリプト

指定されたポートでOSCメッセージを監視し、
メッセージを受信するとその内容を抽出してシステムクリップボードにコピーした上で
システム通知で内容を表示する

使用法:
    uv run osc_copy_notify.py [--ip IP] [--port PORT] [--address ADDRESS]
"""

from __future__ import annotations

import argparse
import logging

import pyperclip
from plyer import notification  # type: ignore[import]
from pythonosc import (
    dispatcher as osc_dispatcher,
    osc_server,
)

# OSCメッセージで許容される型定義
OscValue = str | int | float | bool | bytes


def _setup_logger() -> logging.Logger:
    """アプリケーションのロガーを設定、取得する"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%y/%m/%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def handle_message(_address: str, *args: OscValue) -> None:
    """受信したOSCメッセージを処理する

    すべての引数を単一の文字列として結合し、クリップボードにコピーしてから
    システム通知を表示する

    引数:
        _address: OSCアドレスパターン (ロジックでは未使用)
        *args: メッセージ内容を含む可変長引数リスト
    """
    logger = logging.getLogger(__name__)

    if not args:
        logger.warning("空のOSCメッセージを受信しました")
        return

    # 全引数をスペース区切りで結合して単一の文字列にする
    content = " ".join(map(str, args))
    logger.info("メッセージを受信しました: %s", content)

    # クリップボードへのコピー
    try:
        pyperclip.copy(content)
        logger.info("クリップボードにコピーしました")
    except Exception:
        logger.exception("クリップボードへのコピーに失敗しました")

    # システム通知の送信
    try:
        notification.notify(  # type: ignore[no-any-return, operator]
            title="NowPlaying",
            message=content,
            # app_name="OSC Monitor",
            timeout=5,
        )
        logger.info("通知を送信しました")
    except Exception:
        logger.exception("通知の送信に失敗しました")


def main() -> None:
    """スクリプトのメインエントリポイント"""
    logger = _setup_logger()

    parser = argparse.ArgumentParser(
        description="OSCメッセージを受信し、クリップボードへのコピーおよび通知を行います"
    )
    parser.add_argument(
        "--ip",
        default="0.0.0.0",  # noqa: S104
        help="受信するIPアドレス (デフォルト: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="受信するポート番号 (デフォルト: 8000)",
    )
    parser.add_argument(
        "--address",
        default="/print",
        help="監視するOSCアドレス (デフォルト: /print)",
    )
    args = parser.parse_args()

    # OSCディスパッチャの設定
    dispatcher_instance = osc_dispatcher.Dispatcher()
    dispatcher_instance.map(args.address, handle_message)  # type: ignore[no-untyped-call]

    # OSCサーバーの開始
    try:
        server = osc_server.BlockingOSCUDPServer(
            (args.ip, args.port), dispatcher_instance
        )
        logger.info(
            "OSCサーバーを %s:%d で起動中... '%s' を監視します",
            args.ip,
            args.port,
            args.address,
        )
        server.serve_forever()
    except OSError:
        logger.exception(
            "サーバーの起動に失敗しました (ポートが使用中の可能性があります)"
        )
    except KeyboardInterrupt:
        logger.info("ユーザーによってサーバーが停止されました")
    except Exception:
        logger.exception("予期せぬエラーが発生しました")


if __name__ == "__main__":
    main()
