"""statusline.pyのテスト"""

# テストではプライベートメンバーへのアクセスが必要である
# pyright: reportPrivateUsage=false

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest  # pyright: ignore[reportMissingImports]

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "ClaudeCode" / "scripts")
)
import statusline


class TestGetCurrencyFromLocale:
    """_get_currency_from_locale のテスト"""

    def test_japanese_locale(self) -> None:
        """日本語ロケールの場合はJPYを返す"""
        with patch("statusline.locale.getlocale", return_value=("ja_JP", "utf-8")):
            assert statusline._get_currency_from_locale() == "JPY"

    def test_us_locale(self) -> None:
        """USロケールの場合はUSDを返す"""
        with patch("statusline.locale.getlocale", return_value=("en_US", "utf-8")):
            assert statusline._get_currency_from_locale() == "USD"

    def test_uk_locale(self) -> None:
        """UKロケールの場合はGBPを返す"""
        with patch("statusline.locale.getlocale", return_value=("en_GB", "utf-8")):
            assert statusline._get_currency_from_locale() == "GBP"

    def test_german_locale(self) -> None:
        """ドイツ語ロケールの場合はEURを返す"""
        with patch("statusline.locale.getlocale", return_value=("de_DE", "utf-8")):
            assert statusline._get_currency_from_locale() == "EUR"

    def test_unknown_locale_falls_back_to_usd(self) -> None:
        """未知のロケールの場合はUSDにフォールバックする"""
        with patch("statusline.locale.getlocale", return_value=("xx_XX", "utf-8")):
            assert statusline._get_currency_from_locale() == "USD"

    def test_none_locale_falls_back_to_usd(self) -> None:
        """ロケールがNoneの場合はUSDにフォールバックする"""
        with patch("statusline.locale.getlocale", return_value=(None, None)):
            assert statusline._get_currency_from_locale() == "USD"

    def test_value_error_falls_back_to_usd(self) -> None:
        """ValueError時はUSDにフォールバックする"""
        with patch("statusline.locale.getlocale", side_effect=ValueError):
            assert statusline._get_currency_from_locale() == "USD"

    def test_locale_without_country(self) -> None:
        """国コードなしのロケールはUSDにフォールバックする"""
        with patch("statusline.locale.getlocale", return_value=("ja", "utf-8")):
            assert statusline._get_currency_from_locale() == "USD"


class TestCurrencyData:
    """通貨データのテスト"""

    def test_currencies_has_usd(self) -> None:
        """USDが通貨辞書に含まれている"""
        assert "USD" in statusline._CURRENCIES

    def test_currencies_has_jpy(self) -> None:
        """JPYの通貨情報が正しく設定されている"""
        info = statusline._CURRENCIES["JPY"]
        assert info.symbol == "\u00a5"
        assert info.decimals == 0

    def test_currencies_has_thb(self) -> None:
        """新規追加通貨THBのテスト"""
        info = statusline._CURRENCIES["THB"]
        assert info.symbol == "\u0e3f"
        assert info.decimals == 2

    def test_currencies_has_try(self) -> None:
        """新規追加通貨TRYのテスト"""
        info = statusline._CURRENCIES["TRY"]
        assert info.symbol == "\u20ba"
        assert info.decimals == 2

    def test_twd_removed(self) -> None:
        """TWDはAPI非対応のため削除されている"""
        assert "TWD" not in statusline._CURRENCIES

    def test_locale_to_currency_has_jp(self) -> None:
        """JPロケールがJPY通貨に対応している"""
        assert statusline._LOCALE_TO_CURRENCY["JP"] == "JPY"

    def test_locale_to_currency_has_us(self) -> None:
        """USロケールがUSD通貨に対応している"""
        assert statusline._LOCALE_TO_CURRENCY["US"] == "USD"

    def test_locale_to_currency_tw_removed(self) -> None:
        """TWはAPI非対応のため削除されている"""
        assert "TW" not in statusline._LOCALE_TO_CURRENCY


class TestGetExchangeRate:
    """_get_exchange_rate のテスト"""

    def test_usd_returns_none(self) -> None:
        """USDの場合は変換不要なのでNoneを返す"""
        assert statusline._get_exchange_rate("USD") is None

    def test_fetches_rate_from_api(self, tmp_path: Path) -> None:
        """APIからレートを取得できる"""
        # 存在しないキャッシュファイルを指定してキャッシュミスを発生させる
        cache_file = tmp_path / "nonexistent-cache.json"

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"rates":{"JPY":150.5}}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with (
            patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file),
            patch("statusline.urlopen", return_value=mock_resp),
        ):
            rate = statusline._get_exchange_rate("JPY")
        assert rate == 150.5

    def test_returns_cached_rate(self, tmp_path: Path) -> None:
        """有効なキャッシュからレートを返す"""
        cache_file = tmp_path / "exchange-cache.json"
        cache_data = {"_cached_at": time.time(), "data": 149.0, "currency": "JPY"}
        cache_file.write_text(json.dumps(cache_data))

        with patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file):
            rate = statusline._get_exchange_rate("JPY")
        assert rate == 149.0

    def test_api_failure_returns_expired_cache(self, tmp_path: Path) -> None:
        """API失敗時は期限切れキャッシュを返す"""
        cache_file = tmp_path / "exchange-cache.json"
        cache_data = {"_cached_at": 0, "data": 148.0, "currency": "JPY"}
        cache_file.write_text(json.dumps(cache_data))

        with (
            patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file),
            patch("statusline.urlopen", side_effect=URLError("fail")),
        ):
            rate = statusline._get_exchange_rate("JPY")
        assert rate == 148.0

    def test_api_failure_no_cache_returns_none(self, tmp_path: Path) -> None:
        """API失敗かつキャッシュなしの場合はNoneを返す"""
        # 存在しないキャッシュファイルを指定する
        cache_file = tmp_path / "nonexistent-cache.json"

        with (
            patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file),
            patch("statusline.urlopen", side_effect=URLError("fail")),
        ):
            rate = statusline._get_exchange_rate("JPY")
        assert rate is None

    def test_different_currency_invalidates_cache(self, tmp_path: Path) -> None:
        """キャッシュの通貨が異なる場合はAPIから取得する"""
        cache_file = tmp_path / "exchange-cache.json"
        cache_data = {"_cached_at": time.time(), "data": 0.92, "currency": "EUR"}
        cache_file.write_text(json.dumps(cache_data))

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"rates":{"JPY":150.0}}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with (
            patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file),
            patch("statusline.urlopen", return_value=mock_resp),
        ):
            rate = statusline._get_exchange_rate("JPY")
        assert rate == 150.0


class TestFormatCost:
    """_format_cost のテスト"""

    def test_usd_display(self) -> None:
        """USDの場合は$表示"""
        with patch.object(statusline, "_currency", "USD"):
            assert statusline._format_cost(1.23) == "$1.23"

    def test_jpy_display(self) -> None:
        """JPYの場合は¥表示(小数なし)"""
        with (
            patch.object(statusline, "_currency", "JPY"),
            patch("statusline._get_exchange_rate", return_value=150.0),
        ):
            # 1.23 * 150.0 = 184.5 -> :.0fの偶数丸めで184
            assert statusline._format_cost(1.23) == "¥184"

    def test_eur_display(self) -> None:
        """EURの場合はユーロ表示(小数2桁)"""
        with (
            patch.object(statusline, "_currency", "EUR"),
            patch("statusline._get_exchange_rate", return_value=0.92),
        ):
            assert statusline._format_cost(1.00) == "€0.92"

    def test_exchange_rate_failure_falls_back_to_usd(self) -> None:
        """為替レート取得失敗時はUSDフォールバック"""
        with (
            patch.object(statusline, "_currency", "JPY"),
            patch("statusline._get_exchange_rate", return_value=None),
        ):
            assert statusline._format_cost(1.23) == "$1.23"

    def test_unknown_currency_falls_back_to_usd(self) -> None:
        """_CURRENCIESに存在しない通貨はUSDフォールバック"""
        with (
            patch.object(statusline, "_currency", "XYZ"),
            patch("statusline._get_exchange_rate", return_value=1.5),
        ):
            assert statusline._format_cost(1.23) == "$1.23"


class TestSegCost:
    """_seg_cost のテスト"""

    def test_returns_segment_with_cost(self) -> None:
        """コストデータがある場合はSegmentを返す"""
        with patch.object(statusline, "_currency", "USD"):
            data = {"cost": {"total_cost_usd": 1.23}}
            seg = statusline._seg_cost(data)
            assert seg is not None
            assert "$1.23" in seg.text

    def test_jpy_cost_display(self) -> None:
        """JPYの場合は¥表示"""
        with (
            patch.object(statusline, "_currency", "JPY"),
            patch("statusline._get_exchange_rate", return_value=150.0),
        ):
            data = {"cost": {"total_cost_usd": 1.23}}
            seg = statusline._seg_cost(data)
            assert seg is not None
            # 1.23 * 150.0 = 184.5 -> :.0fの偶数丸めで184
            assert "¥184" in seg.text

    def test_no_cost_data_returns_none(self) -> None:
        """コストデータがない場合はNone"""
        seg = statusline._seg_cost({})
        assert seg is None

    def test_no_total_cost_returns_none(self) -> None:
        """total_cost_usdがない場合はNone"""
        seg = statusline._seg_cost({"cost": {}})
        assert seg is None


class TestCachedFetch:
    """_cached_fetch のテスト"""

    def test_returns_fresh_data_on_cache_miss(self, tmp_path: Path) -> None:
        """キャッシュミス時はfetch_fnからデータを取得する"""
        cache_file = tmp_path / "test-cache.json"
        result = statusline._cached_fetch(cache_file, 60, lambda: {"key": "value"})
        assert result == {"key": "value"}

    def test_returns_cached_data_within_ttl(self, tmp_path: Path) -> None:
        """TTL内のキャッシュを返す"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {"_cached_at": time.time(), "data": {"cached": True}}
        cache_file.write_text(json.dumps(cache_data))
        result = statusline._cached_fetch(cache_file, 60, lambda: {"fresh": True})
        assert result == {"cached": True}

    def test_refetches_on_expired_cache(self, tmp_path: Path) -> None:
        """TTL切れキャッシュは再取得する"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {"_cached_at": 0, "data": {"old": True}}
        cache_file.write_text(json.dumps(cache_data))
        result = statusline._cached_fetch(cache_file, 60, lambda: {"new": True})
        assert result == {"new": True}

    def test_returns_expired_cache_on_fetch_failure(self, tmp_path: Path) -> None:
        """fetch失敗時は期限切れキャッシュを返す"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {"_cached_at": 0, "data": {"expired": True}}
        cache_file.write_text(json.dumps(cache_data))

        def failing_fetch() -> Never:
            raise URLError("fail")

        result = statusline._cached_fetch(cache_file, 60, failing_fetch)
        assert result == {"expired": True}

    def test_returns_none_on_fetch_failure_no_cache(self, tmp_path: Path) -> None:
        """fetch失敗かつキャッシュなしの場合はNoneを返す"""
        cache_file = tmp_path / "nonexistent.json"

        def failing_fetch() -> Never:
            raise URLError("fail")

        result = statusline._cached_fetch(cache_file, 60, failing_fetch)
        assert result is None

    def test_cache_key_mismatch_refetches(self, tmp_path: Path) -> None:
        """cache_keyが異なる場合は再取得する"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {
            "_cached_at": time.time(),
            "data": {"old": True},
            "currency": "EUR",
        }
        cache_file.write_text(json.dumps(cache_data))
        result = statusline._cached_fetch(
            cache_file, 60, lambda: {"new": True}, cache_key={"currency": "JPY"}
        )
        assert result == {"new": True}

    def test_cache_key_match_returns_cache(self, tmp_path: Path) -> None:
        """cache_keyが一致する場合はキャッシュを返す"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {
            "_cached_at": time.time(),
            "data": {"cached": True},
            "currency": "JPY",
        }
        cache_file.write_text(json.dumps(cache_data))
        result = statusline._cached_fetch(
            cache_file, 60, lambda: {"fresh": True}, cache_key={"currency": "JPY"}
        )
        assert result == {"cached": True}

    def test_writes_cache_file(self, tmp_path: Path) -> None:
        """取得後にキャッシュファイルが書き込まれる"""
        cache_file = tmp_path / "test-cache.json"
        statusline._cached_fetch(cache_file, 60, lambda: {"written": True})
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["data"] == {"written": True}
        assert "_cached_at" in data

    def test_fetch_returning_none_returns_expired(self, tmp_path: Path) -> None:
        """fetch_fnがNoneを返した場合は期限切れキャッシュを返す"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {"_cached_at": 0, "data": {"expired": True}}
        cache_file.write_text(json.dumps(cache_data))
        result = statusline._cached_fetch(cache_file, 60, lambda: None)
        assert result == {"expired": True}


class TestGetSupportedCurrencies:
    """_get_supported_currencies のテスト"""

    def test_fetches_from_api(self, tmp_path: Path) -> None:
        """APIから通貨リストを取得する"""
        cache_file = tmp_path / "currencies-cache.json"
        mock_resp = MagicMock()
        mock_resp.read.return_value = (
            b'{"AUD":"Australian Dollar",'
            b'"JPY":"Japanese Yen",'
            b'"USD":"United States Dollar"}'
        )
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with (
            patch.object(statusline, "_CURRENCIES_CACHE_PATH", cache_file),
            patch("statusline.urlopen", return_value=mock_resp),
        ):
            result = statusline._get_supported_currencies()
        assert result is not None
        assert "JPY" in result
        assert "USD" in result

    def test_returns_cached_currencies(self, tmp_path: Path) -> None:
        """キャッシュから通貨リストを返す"""
        cache_file = tmp_path / "currencies-cache.json"
        cache_data = {"_cached_at": time.time(), "data": ["JPY", "USD", "EUR"]}
        cache_file.write_text(json.dumps(cache_data))
        with patch.object(statusline, "_CURRENCIES_CACHE_PATH", cache_file):
            result = statusline._get_supported_currencies()
        assert result is not None
        assert "JPY" in result

    def test_api_failure_returns_none(self, tmp_path: Path) -> None:
        """API失敗かつキャッシュなしの場合はNoneを返す"""
        cache_file = tmp_path / "nonexistent.json"
        with (
            patch.object(statusline, "_CURRENCIES_CACHE_PATH", cache_file),
            patch("statusline.urlopen", side_effect=Exception("fail")),
        ):
            result = statusline._get_supported_currencies()
        assert result is None


class TestParseArgs:
    """_parse_args のテスト"""

    def test_no_args(self) -> None:
        """引数なしの場合はデフォルト値"""
        args = statusline._parse_args([])
        assert args.icons is None
        assert args.currency is None

    def test_icons_nerd(self) -> None:
        """--icons nerd"""
        args = statusline._parse_args(["--icons", "nerd"])
        assert args.icons == "nerd"

    def test_icons_invalid(self) -> None:
        """--icons xxx は無効だがエラーにはならない"""
        args = statusline._parse_args(["--icons", "xxx"])
        assert args.icons == "xxx"

    def test_currency_jpy(self) -> None:
        """--currency jpy は大文字化される"""
        args = statusline._parse_args(["--currency", "jpy"])
        assert args.currency == "JPY"

    def test_currency_and_icons(self) -> None:
        """両方指定"""
        args = statusline._parse_args(["--icons", "nerd", "--currency", "EUR"])
        assert args.icons == "nerd"
        assert args.currency == "EUR"


class TestResolveCurrency:
    """_resolve_currency のテスト"""

    def test_valid_currency_from_arg(self) -> None:
        """CLI引数の通貨がAPI対応なら採用"""
        with patch(
            "statusline._get_supported_currencies", return_value=["JPY", "USD", "EUR"]
        ):
            assert statusline._resolve_currency("JPY") == "JPY"

    def test_invalid_currency_from_arg_falls_back_to_locale(self) -> None:
        """CLI引数の通貨がAPI非対応ならロケール判定"""
        with (
            patch("statusline._get_supported_currencies", return_value=["JPY", "USD"]),
            patch("statusline._get_currency_from_locale", return_value="JPY"),
        ):
            assert statusline._resolve_currency("XYZ") == "JPY"

    def test_none_currency_uses_locale(self) -> None:
        """通貨未指定ならロケール判定"""
        with (
            patch("statusline._get_supported_currencies", return_value=["JPY", "USD"]),
            patch("statusline._get_currency_from_locale", return_value="JPY"),
        ):
            assert statusline._resolve_currency(None) == "JPY"

    def test_locale_currency_not_supported_falls_back_to_usd(self) -> None:
        """ロケール通貨がAPI非対応ならUSD"""
        with (
            patch("statusline._get_supported_currencies", return_value=["USD", "EUR"]),
            patch("statusline._get_currency_from_locale", return_value="XYZ"),
        ):
            assert statusline._resolve_currency(None) == "USD"

    def test_api_failure_falls_back_to_usd(self) -> None:
        """API対応通貨リスト取得失敗時はUSD"""
        with patch("statusline._get_supported_currencies", return_value=None):
            assert statusline._resolve_currency("JPY") == "USD"


class TestExtractVersion:
    """_extract_version のテスト"""

    def test_opus_4_6(self) -> None:
        """claude-opus-4-6 -> '4.6'."""
        assert statusline._extract_version("claude-opus-4-6") == "4.6"

    def test_sonnet_with_date(self) -> None:
        """日付サフィックス付きモデルID"""
        assert statusline._extract_version("claude-sonnet-4-5-20250514") == "4.5"

    def test_haiku_with_date(self) -> None:
        """旧世代モデルIDのバージョン抽出"""
        assert statusline._extract_version("claude-haiku-3-5-20241022") == "3.5"

    def test_empty_string(self) -> None:
        """空文字列は空文字列を返す"""
        assert statusline._extract_version("") == ""

    def test_unknown_model(self) -> None:
        """パースできないIDは空文字列を返す"""
        assert statusline._extract_version("unknown") == ""

    def test_single_version_number(self) -> None:
        """メジャーバージョンのみ"""
        assert statusline._extract_version("claude-opus-4") == "4"


class TestRemoteToHttps:
    """_remote_to_https のテスト"""

    def test_ssh_format(self) -> None:
        """SSH形式をHTTPSに変換する"""
        result = statusline._remote_to_https("git@github.com:user/repo.git")
        assert result == "https://github.com/user/repo"

    def test_https_with_git_suffix(self) -> None:
        """HTTPS形式で.gitサフィックスを除去する"""
        result = statusline._remote_to_https("https://github.com/user/repo.git")
        assert result == "https://github.com/user/repo"

    def test_https_without_git_suffix(self) -> None:
        """HTTPS形式でサフィックスなし"""
        result = statusline._remote_to_https("https://github.com/user/repo")
        assert result == "https://github.com/user/repo"

    def test_unsupported_protocol(self) -> None:
        """非対応プロトコルはNoneを返す"""
        assert statusline._remote_to_https("svn://example.com/repo") is None

    def test_whitespace_trimmed(self) -> None:
        """前後の空白を除去する"""
        result = statusline._remote_to_https("  https://github.com/user/repo  ")
        assert result == "https://github.com/user/repo"


class TestColorForUtilization:
    """_color_for_utilization のテスト"""

    def test_zero_is_green(self) -> None:
        """0%はGREENを返す"""
        assert statusline._color_for_utilization(0) == statusline._Color.GREEN

    def test_59_is_green(self) -> None:
        """59%はGREENを返す"""
        assert statusline._color_for_utilization(59) == statusline._Color.GREEN

    def test_60_is_yellow(self) -> None:
        """60%はYELLOWを返す"""
        assert statusline._color_for_utilization(60) == statusline._Color.YELLOW

    def test_79_is_yellow(self) -> None:
        """79%はYELLOWを返す"""
        assert statusline._color_for_utilization(79) == statusline._Color.YELLOW

    def test_80_is_red(self) -> None:
        """80%はREDを返す"""
        assert statusline._color_for_utilization(80) == statusline._Color.RED

    def test_100_is_red(self) -> None:
        """100%はREDを返す"""
        assert statusline._color_for_utilization(100) == statusline._Color.RED


class TestColorize:
    """_colorize のテスト"""

    def test_red(self) -> None:
        """RED色のANSIエスケープシーケンスを生成する"""
        result = statusline._colorize("hello", statusline._Color.RED)
        assert result == "\033[31mhello\033[0m"

    def test_green(self) -> None:
        """GREEN色のANSIエスケープシーケンスを生成する"""
        result = statusline._colorize("ok", statusline._Color.GREEN)
        assert result == "\033[32mok\033[0m"

    def test_empty_text(self) -> None:
        """空文字列でもエスケープシーケンスは付与される"""
        result = statusline._colorize("", statusline._Color.BLUE)
        assert result == "\033[34m\033[0m"


class TestGetCwd:
    """_get_cwd のテスト"""

    def test_workspace_current_dir(self) -> None:
        """workspace.current_dirを優先する"""
        data = {"workspace": {"current_dir": "/home/user/project"}, "cwd": "/var/data"}
        assert statusline._get_cwd(data) == "/home/user/project"

    def test_falls_back_to_cwd(self) -> None:
        """workspaceがない場合はcwdにフォールバック"""
        data = {"cwd": "/var/data/work"}
        assert statusline._get_cwd(data) == "/var/data/work"

    def test_workspace_without_current_dir(self) -> None:
        """workspace内にcurrent_dirがない場合はcwdにフォールバック"""
        data: dict[str, Any] = {"workspace": {}, "cwd": "/fallback"}
        assert statusline._get_cwd(data) == "/fallback"

    def test_empty_dict(self) -> None:
        """空のdictは空文字列を返す"""
        assert statusline._get_cwd({}) == ""

    def test_workspace_not_dict(self) -> None:
        """workspaceがdictでない場合はcwdにフォールバック"""
        data = {"workspace": "not-a-dict", "cwd": "/correct"}
        assert statusline._get_cwd(data) == "/correct"


class TestOsc8Link:
    """_osc8_link のテスト"""

    def test_generates_osc8_sequence(self) -> None:
        """OSC 8エスケープシーケンスを正しく生成する"""
        result = statusline._osc8_link("https://example.com", "click me")
        assert result == "\033]8;;https://example.com\aclick me\033]8;;\a"

    def test_empty_text(self) -> None:
        """空テキストでもシーケンスは生成される"""
        result = statusline._osc8_link("https://example.com", "")
        assert result == "\033]8;;https://example.com\a\033]8;;\a"


class TestParseIsoToLocal:
    """_parse_iso_to_local のテスト"""

    def test_naive_datetime_treated_as_utc(self) -> None:
        """タイムゾーンなしの入力はUTCとして扱われる"""
        result = statusline._parse_iso_to_local("2025-01-15T14:30:00")
        expected_utc = datetime(2025, 1, 15, 14, 30, tzinfo=UTC)
        assert result.timestamp() == expected_utc.timestamp()

    def test_aware_datetime_preserves_instant(self) -> None:
        """タイムゾーン付きの入力は正しい時刻を保持する"""
        result = statusline._parse_iso_to_local("2025-01-15T14:30:00+09:00")
        # +09:00なのでUTCでは05:30
        expected_utc = datetime(2025, 1, 15, 5, 30, tzinfo=UTC)
        assert result.timestamp() == expected_utc.timestamp()

    def test_result_has_timezone(self) -> None:
        """結果にはタイムゾーン情報が付与される"""
        result = statusline._parse_iso_to_local("2025-01-15T14:30:00Z")
        assert result.tzinfo is not None

    def test_utc_suffix(self) -> None:
        """Z付きのISO文字列をパースできる"""
        result = statusline._parse_iso_to_local("2025-06-01T00:00:00Z")
        expected_utc = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
        assert result.timestamp() == expected_utc.timestamp()


class TestFormatResetTimeShort:
    """_format_reset_time_short のテスト"""

    def test_formats_as_h_mm(self) -> None:
        """H:MM形式でフォーマットされる"""
        fixed_dt = datetime(2025, 1, 15, 14, 30, tzinfo=UTC)
        with patch("statusline._parse_iso_to_local", return_value=fixed_dt):
            result = statusline._format_reset_time_short("2025-01-15T14:30:00Z")
        assert result == "14:30"

    def test_no_zero_padding_hour(self) -> None:
        """時間は0埋めされない"""
        fixed_dt = datetime(2025, 1, 15, 9, 5, tzinfo=UTC)
        with patch("statusline._parse_iso_to_local", return_value=fixed_dt):
            result = statusline._format_reset_time_short("2025-01-15T09:05:00Z")
        assert result == "9:05"

    def test_midnight(self) -> None:
        """0時の表示"""
        fixed_dt = datetime(2025, 1, 15, 0, 0, tzinfo=UTC)
        with patch("statusline._parse_iso_to_local", return_value=fixed_dt):
            result = statusline._format_reset_time_short("2025-01-15T00:00:00Z")
        assert result == "0:00"


class TestFormatResetDate:
    """_format_reset_date のテスト"""

    def test_formats_as_m_d_h_mm(self) -> None:
        """M/D H:MM形式でフォーマットされる"""
        fixed_dt = datetime(2025, 1, 15, 14, 30, tzinfo=UTC)
        with patch("statusline._parse_iso_to_local", return_value=fixed_dt):
            result = statusline._format_reset_date("2025-01-15T14:30:00Z")
        assert result == "1/15 14:30"

    def test_no_zero_padding(self) -> None:
        """月・日・時は0埋めされない"""
        fixed_dt = datetime(2025, 3, 5, 9, 5, tzinfo=UTC)
        with patch("statusline._parse_iso_to_local", return_value=fixed_dt):
            result = statusline._format_reset_date("2025-03-05T09:05:00Z")
        assert result == "3/5 9:05"


class TestCacheKeyMatches:
    """_cache_key_matches のテスト"""

    def test_none_key_always_matches(self) -> None:
        """cache_keyがNoneなら常にTrue"""
        assert statusline._cache_key_matches({"any": "data"}, None) is True

    def test_matching_key(self) -> None:
        """キーが一致する場合はTrue"""
        cache_obj = {"currency": "JPY", "data": 150}
        assert statusline._cache_key_matches(cache_obj, {"currency": "JPY"}) is True

    def test_non_matching_key(self) -> None:
        """キーが不一致の場合はFalse"""
        cache_obj = {"currency": "EUR", "data": 0.92}
        assert statusline._cache_key_matches(cache_obj, {"currency": "JPY"}) is False

    def test_missing_key_in_cache(self) -> None:
        """キャッシュにキーが存在しない場合はFalse"""
        cache_obj = {"data": 150}
        assert statusline._cache_key_matches(cache_obj, {"currency": "JPY"}) is False

    def test_empty_cache_key(self) -> None:
        """空のcache_keyはTrueを返す(falsyなので)"""
        assert statusline._cache_key_matches({"data": 1}, {}) is True


class TestRenderLine:
    """_render_line のテスト"""

    def test_multiple_segments(self) -> None:
        """複数セグメントをセパレータで結合する"""
        segs = [statusline.Segment(text="A"), statusline.Segment(text="B")]
        result = statusline._render_line(segs)
        assert result == "A \u2502 B"

    def test_single_segment(self) -> None:
        """単一セグメントはそのまま返す"""
        segs = [statusline.Segment(text="only")]
        assert statusline._render_line(segs) == "only"

    def test_empty_list(self) -> None:
        """空リストは空文字列を返す"""
        assert statusline._render_line([]) == ""

    def test_three_segments(self) -> None:
        """3セグメントの結合"""
        segs = [
            statusline.Segment(text="X"),
            statusline.Segment(text="Y"),
            statusline.Segment(text="Z"),
        ]
        result = statusline._render_line(segs)
        assert result == "X \u2502 Y \u2502 Z"


class TestSegProject:
    """_seg_project のテスト"""

    def test_displays_project_name(self) -> None:
        """cwdからプロジェクト名を表示する"""
        data = {"cwd": "/home/user/myproject"}
        seg = statusline._seg_project(data)
        assert seg is not None
        assert "myproject" in seg.text

    def test_with_remote_url_creates_link(self) -> None:
        """リモートURLがある場合はOSC 8リンクを含む"""
        data = {
            "cwd": "/home/user/myproject",
            "_git": {"remote_url": "git@github.com:user/myproject.git"},
        }
        seg = statusline._seg_project(data)
        assert seg is not None
        assert "myproject" in seg.text
        # OSC 8リンクのエスケープシーケンスを含む
        assert "\033]8;;" in seg.text

    def test_without_git_info(self) -> None:
        """git情報がなくてもセグメントは返る"""
        data = {"cwd": "/home/user/myproject"}
        seg = statusline._seg_project(data)
        assert seg is not None
        assert "myproject" in seg.text
        # OSC 8リンクは含まない
        assert "\033]8;;" not in seg.text

    def test_empty_cwd_shows_unknown(self) -> None:
        """cwdが空の場合は"unknown"を表示する"""
        data: dict[str, Any] = {}
        seg = statusline._seg_project(data)
        assert seg is not None
        assert "unknown" in seg.text


class TestSegBranch:
    """_seg_branch のテスト"""

    def test_displays_branch_name(self) -> None:
        """ブランチ名を表示する"""
        data = {"_git": {"branch": "main"}}
        seg = statusline._seg_branch(data)
        assert seg is not None
        assert "main" in seg.text

    def test_no_git_info_returns_none(self) -> None:
        """git情報がない場合はNone"""
        assert statusline._seg_branch({}) is None

    def test_git_info_not_dict_returns_none(self) -> None:
        """_gitがdictでない場合はNone"""
        assert statusline._seg_branch({"_git": "not-a-dict"}) is None

    def test_no_branch_returns_none(self) -> None:
        """branchキーがない場合はNone"""
        assert statusline._seg_branch({"_git": {}}) is None

    def test_with_remote_url_creates_link(self) -> None:
        """リモートURLがある場合はOSC 8リンクを含む"""
        data = {
            "_git": {
                "branch": "feature/test",
                "remote_url": "https://github.com/user/repo.git",
            },
        }
        seg = statusline._seg_branch(data)
        assert seg is not None
        assert "feature/test" in seg.text
        assert "\033]8;;" in seg.text

    def test_without_remote_url_no_link(self) -> None:
        """リモートURLがない場合はリンクなし"""
        data = {"_git": {"branch": "main"}}
        seg = statusline._seg_branch(data)
        assert seg is not None
        assert "\033]8;;" not in seg.text


class TestSegModel:
    """_seg_model のテスト"""

    def test_displays_name_with_version(self) -> None:
        """display_nameとバージョンを表示する"""
        data = {"model": {"display_name": "Opus", "id": "claude-opus-4-6"}}
        seg = statusline._seg_model(data)
        assert seg is not None
        assert "Opus 4.6" in seg.text

    def test_no_model_returns_none(self) -> None:
        """modelキーがない場合はNone"""
        assert statusline._seg_model({}) is None

    def test_model_not_dict_returns_none(self) -> None:
        """modelがdictでない場合はNone"""
        assert statusline._seg_model({"model": "string"}) is None

    def test_no_display_name_returns_none(self) -> None:
        """display_nameがない場合はNone"""
        assert statusline._seg_model({"model": {"id": "claude-opus-4-6"}}) is None

    def test_version_already_in_name_no_duplicate(self) -> None:
        """display_nameにバージョンが含まれる場合は重複しない"""
        data = {"model": {"display_name": "Opus 4.6", "id": "claude-opus-4-6"}}
        seg = statusline._seg_model(data)
        assert seg is not None
        # "Opus 4.6"が1回だけ含まれ、"Opus 4.6 4.6"にはならない
        assert "4.6 4.6" not in seg.text
        assert "Opus 4.6" in seg.text

    def test_no_version_extracted(self) -> None:
        """バージョン抽出できない場合はdisplay_nameのみ"""
        data = {"model": {"display_name": "CustomModel", "id": "custom"}}
        seg = statusline._seg_model(data)
        assert seg is not None
        assert "CustomModel" in seg.text


class TestSegContext:
    """_seg_context のテスト"""

    def test_displays_percentage(self) -> None:
        """使用率をパーセント表示する"""
        data = {"context_window": {"used_percentage": 45}}
        seg = statusline._seg_context(data)
        assert seg is not None
        assert "45%" in seg.text

    def test_no_context_window_returns_none(self) -> None:
        """context_windowがない場合はNone"""
        assert statusline._seg_context({}) is None

    def test_no_used_percentage_returns_none(self) -> None:
        """used_percentageがない場合はNone"""
        assert statusline._seg_context({"context_window": {}}) is None

    def test_high_utilization_uses_red(self) -> None:
        """80%以上はREDカラーを使用する"""
        data = {"context_window": {"used_percentage": 85}}
        seg = statusline._seg_context(data)
        assert seg is not None
        # RED(31)のANSIエスケープを含む
        assert "\033[31m" in seg.text

    def test_medium_utilization_uses_yellow(self) -> None:
        """60-79%はYELLOWカラーを使用する"""
        data = {"context_window": {"used_percentage": 65}}
        seg = statusline._seg_context(data)
        assert seg is not None
        assert "\033[33m" in seg.text

    def test_low_utilization_uses_green(self) -> None:
        """60%未満はGREENカラーを使用する"""
        data = {"context_window": {"used_percentage": 30}}
        seg = statusline._seg_context(data)
        assert seg is not None
        assert "\033[32m" in seg.text


class TestSegLines:
    """_seg_lines のテスト"""

    def test_displays_added_and_removed(self) -> None:
        """追加行数と削除行数を表示する"""
        data = {"cost": {"total_lines_added": 10, "total_lines_removed": 5}}
        seg = statusline._seg_lines(data)
        assert seg is not None
        assert "+10" in seg.text
        assert "-5" in seg.text

    def test_zero_changes_returns_none(self) -> None:
        """変更がない場合はNone"""
        data = {"cost": {"total_lines_added": 0, "total_lines_removed": 0}}
        assert statusline._seg_lines(data) is None

    def test_no_cost_returns_none(self) -> None:
        """costキーがない場合はNone"""
        assert statusline._seg_lines({}) is None

    def test_added_only(self) -> None:
        """追加のみの場合"""
        data = {"cost": {"total_lines_added": 20, "total_lines_removed": 0}}
        seg = statusline._seg_lines(data)
        assert seg is not None
        assert "+20" in seg.text

    def test_added_green_removed_red(self) -> None:
        """追加はGREEN、削除はREDで色付け"""
        data = {"cost": {"total_lines_added": 1, "total_lines_removed": 1}}
        seg = statusline._seg_lines(data)
        assert seg is not None
        assert "\033[32m+1\033[0m" in seg.text
        assert "\033[31m-1\033[0m" in seg.text


class TestSegRateCommon:
    """_seg_rate_common のテスト"""

    def test_displays_rate_info(self) -> None:
        """レートリミット情報を表示する"""
        data = {
            "_usage": {
                "five_hour": {
                    "utilization": 45.0,
                    "resets_at": "2025-01-15T14:30:00Z",
                },
            },
        }
        with patch("statusline._format_reset_time_short", return_value="14:30"):
            seg = statusline._seg_rate_common(
                data,
                "five_hour",
                "5h",
                "\u23f0",
                statusline._format_reset_time_short,
            )
        assert seg is not None
        assert "5h" in seg.text
        assert "45%" in seg.text
        assert "14:30" in seg.text

    def test_no_usage_returns_none(self) -> None:
        """_usageがない場合はNone"""
        seg = statusline._seg_rate_common(
            {}, "five_hour", "5h", "\u23f0", statusline._format_reset_time_short
        )
        assert seg is None

    def test_no_bucket_returns_none(self) -> None:
        """指定のバケットがない場合はNone"""
        data: dict[str, Any] = {"_usage": {}}
        seg = statusline._seg_rate_common(
            data, "five_hour", "5h", "\u23f0", statusline._format_reset_time_short
        )
        assert seg is None

    def test_missing_utilization_returns_none(self) -> None:
        """utilizationがない場合はNone"""
        data = {"_usage": {"five_hour": {"resets_at": "2025-01-15T14:30:00Z"}}}
        seg = statusline._seg_rate_common(
            data, "five_hour", "5h", "\u23f0", statusline._format_reset_time_short
        )
        assert seg is None

    def test_high_utilization_uses_red(self) -> None:
        """80%以上はREDカラー"""
        data = {
            "_usage": {
                "five_hour": {
                    "utilization": 90.0,
                    "resets_at": "2025-01-15T14:30:00Z",
                },
            },
        }
        with patch("statusline._format_reset_time_short", return_value="14:30"):
            seg = statusline._seg_rate_common(
                data,
                "five_hour",
                "5h",
                "\u23f0",
                statusline._format_reset_time_short,
            )
        assert seg is not None
        assert "\033[31m" in seg.text


class TestSegRate5hAnd7d:
    """_seg_rate_5h / _seg_rate_7d の統合テスト"""

    def test_seg_rate_5h_returns_segment(self) -> None:
        """5hレートリミットセグメントを返す"""
        data = {
            "_usage": {
                "five_hour": {
                    "utilization": 30.0,
                    "resets_at": "2025-01-15T14:30:00Z",
                },
            },
        }
        with patch("statusline._format_reset_time_short", return_value="14:30"):
            seg = statusline._seg_rate_5h(data)
        assert seg is not None
        assert "5h" in seg.text
        assert "30%" in seg.text

    def test_seg_rate_7d_returns_segment(self) -> None:
        """7dレートリミットセグメントを返す"""
        data = {
            "_usage": {
                "seven_day": {
                    "utilization": 50.0,
                    "resets_at": "2025-01-20T00:00:00Z",
                },
            },
        }
        with patch("statusline._format_reset_date", return_value="1/20 0:00"):
            seg = statusline._seg_rate_7d(data)
        assert seg is not None
        assert "7d" in seg.text
        assert "50%" in seg.text

    def test_seg_rate_5h_no_data_returns_none(self) -> None:
        """データなしの場合はNone"""
        assert statusline._seg_rate_5h({}) is None

    def test_seg_rate_7d_no_data_returns_none(self) -> None:
        """データなしの場合はNone"""
        assert statusline._seg_rate_7d({}) is None


class TestBuildLines:
    """_build_lines のテスト"""

    def test_full_data_returns_three_lines(self) -> None:
        """全データがある場合は3行を返す"""
        data = {
            "cwd": "/home/user/project",
            "_git": {
                "branch": "main",
                "remote_url": "https://github.com/user/project.git",
            },
            "model": {"display_name": "Opus", "id": "claude-opus-4-6"},
            "context_window": {"used_percentage": 45},
            "_usage": {
                "five_hour": {
                    "utilization": 30.0,
                    "resets_at": "2025-01-15T14:30:00Z",
                },
                "seven_day": {
                    "utilization": 50.0,
                    "resets_at": "2025-01-20T00:00:00Z",
                },
            },
            "cost": {"total_cost_usd": 1.23},
        }
        with (
            patch.object(statusline, "_currency", "USD"),
            patch("statusline._format_reset_time_short", return_value="14:30"),
            patch("statusline._format_reset_date", return_value="1/20 0:00"),
        ):
            lines = statusline._build_lines(data)
        assert len(lines) == 3

    def test_minimal_data_returns_project_line(self) -> None:
        """最小データでもプロジェクト行は返る"""
        lines = statusline._build_lines({"cwd": "/home/user/project"})
        assert len(lines) >= 1
        assert "project" in lines[0]

    def test_empty_data_returns_project_unknown(self) -> None:
        """空データでも"unknown"プロジェクト行は返る"""
        lines = statusline._build_lines({})
        assert len(lines) >= 1
        assert "unknown" in lines[0]

    def test_segments_joined_with_separator(self) -> None:
        """同一行の複数セグメントはセパレータで結合される"""
        data = {
            "cwd": "/home/user/project",
            "_git": {"branch": "main"},
        }
        lines = statusline._build_lines(data)
        # 1行目: project | branch
        assert "\u2502" in lines[0]


class TestGetOauthToken:
    """_get_oauth_token のテスト"""

    def test_reads_from_credentials_file(self, tmp_path: Path) -> None:
        """クレデンシャルファイルからトークンを読み取る"""
        cred_dir = tmp_path / ".claude"
        cred_dir.mkdir()
        cred_file = cred_dir / ".credentials.json"
        cred_file.write_text(
            json.dumps({"claudeAiOauth": {"accessToken": "test-token-123"}})
        )
        with patch("statusline.Path.home", return_value=tmp_path):
            result = statusline._get_oauth_token()
        assert result == "test-token-123"

    def test_no_credentials_file_returns_none(self, tmp_path: Path) -> None:
        """クレデンシャルファイルが存在しない場合はNone(非macOS)"""
        with (
            patch("statusline.Path.home", return_value=tmp_path),
            patch("statusline.platform.system", return_value="Windows"),
        ):
            result = statusline._get_oauth_token()
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """JSONパース失敗時はNone(非macOS)"""
        cred_dir = tmp_path / ".claude"
        cred_dir.mkdir()
        cred_file = cred_dir / ".credentials.json"
        cred_file.write_text("not-json")
        with (
            patch("statusline.Path.home", return_value=tmp_path),
            patch("statusline.platform.system", return_value="Windows"),
        ):
            result = statusline._get_oauth_token()
        assert result is None

    def test_missing_access_token_returns_none(self, tmp_path: Path) -> None:
        """accessTokenがない場合はNone(非macOS)"""
        cred_dir = tmp_path / ".claude"
        cred_dir.mkdir()
        cred_file = cred_dir / ".credentials.json"
        cred_file.write_text(json.dumps({"claudeAiOauth": {}}))
        with (
            patch("statusline.Path.home", return_value=tmp_path),
            patch("statusline.platform.system", return_value="Windows"),
        ):
            result = statusline._get_oauth_token()
        assert result is None

    def test_keychain_fallback_on_darwin(self, tmp_path: Path) -> None:
        """macOSではKeychainにフォールバックする"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "claudeAiOauth": {"accessToken": "keychain-token"}
        })
        with (
            patch("statusline.Path.home", return_value=tmp_path),
            patch("statusline.platform.system", return_value="Darwin"),
            patch("statusline.subprocess.run", return_value=mock_result),
        ):
            result = statusline._get_oauth_token()
        assert result == "keychain-token"


class TestFetchUsage:
    """_fetch_usage のテスト"""

    def test_fetches_from_api(self) -> None:
        """APIからレスポンスを取得しパースする"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"five_hour":{"utilization":30}}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch("statusline.urlopen", return_value=mock_resp):
            result = statusline._fetch_usage("test-token")
        assert result == {"five_hour": {"utilization": 30}}

    def test_sets_authorization_header(self) -> None:
        """Authorizationヘッダーを設定する"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}"
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None

        with patch("statusline.urlopen", return_value=mock_resp) as mock_urlopen:
            statusline._fetch_usage("my-secret-token")

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer my-secret-token"

    def test_network_error_raises(self) -> None:
        """ネットワークエラー時は例外を送出する"""
        with (
            patch("statusline.urlopen", side_effect=URLError("fail")),
            pytest.raises(URLError),  # pyright: ignore[reportUnknownMemberType]
        ):
            statusline._fetch_usage("token")


class TestGetUsage:
    """_get_usage のテスト"""

    def test_returns_data_from_api(self, tmp_path: Path) -> None:
        """APIからデータを取得して返す"""
        cache_file = tmp_path / "usage-cache.json"
        with (
            patch.object(statusline, "_CACHE_PATH", cache_file),
            patch("statusline._get_oauth_token", return_value="test-token"),
            patch(
                "statusline._fetch_usage",
                return_value={"five_hour": {"utilization": 30}},
            ),
        ):
            result = statusline._get_usage()
        assert result == {"five_hour": {"utilization": 30}}

    def test_returns_none_when_no_token(self, tmp_path: Path) -> None:
        """トークン取得失敗時はNone"""
        cache_file = tmp_path / "nonexistent.json"
        with (
            patch.object(statusline, "_CACHE_PATH", cache_file),
            patch("statusline._get_oauth_token", return_value=None),
        ):
            result = statusline._get_usage()
        assert result is None

    def test_returns_cached_data(self, tmp_path: Path) -> None:
        """有効なキャッシュがあればAPIを呼ばず返す"""
        cache_file = tmp_path / "usage-cache.json"
        cache_data = {
            "_cached_at": time.time(),
            "data": {"five_hour": {"utilization": 25}},
        }
        cache_file.write_text(json.dumps(cache_data))
        with patch.object(statusline, "_CACHE_PATH", cache_file):
            result = statusline._get_usage()
        assert result == {"five_hour": {"utilization": 25}}


class TestFetchGitInfo:
    """_fetch_git_info のテスト"""

    def test_returns_branch_and_remote(self) -> None:
        """ブランチ名とリモートURLを返す"""

        def mock_run(cmd: list[str], **_kwargs: object) -> MagicMock:
            if "--abbrev-ref" in cmd:
                return MagicMock(returncode=0, stdout="main\n")
            if "get-url" in cmd:
                return MagicMock(
                    returncode=0, stdout="https://github.com/user/repo.git\n"
                )
            return MagicMock(returncode=1, stdout="")

        with patch("statusline.subprocess.run", side_effect=mock_run):
            result = statusline._fetch_git_info("/some/path")
        assert result["branch"] == "main"
        assert result["remote_url"] == "https://github.com/user/repo.git"

    def test_detached_head_uses_short_hash(self) -> None:
        """Detached HEAD時は短縮コミットハッシュを使用する"""

        def mock_run(cmd: list[str], **_kwargs: object) -> MagicMock:
            if "--abbrev-ref" in cmd:
                return MagicMock(returncode=0, stdout="HEAD\n")
            if "--short" in cmd:
                return MagicMock(returncode=0, stdout="abc1234\n")
            if "get-url" in cmd:
                return MagicMock(returncode=1, stdout="")
            return MagicMock(returncode=1, stdout="")

        with patch("statusline.subprocess.run", side_effect=mock_run):
            result = statusline._fetch_git_info("/some/path")
        assert result["branch"] == "abc1234"

    def test_no_branch_raises_runtime_error(self) -> None:
        """ブランチ取得失敗時はRuntimeErrorを送出する"""
        mock_result = MagicMock(returncode=1, stdout="")
        with (
            patch("statusline.subprocess.run", return_value=mock_result),
            pytest.raises(RuntimeError),  # pyright: ignore[reportUnknownMemberType]
        ):
            statusline._fetch_git_info("/some/path")

    def test_no_remote_url(self) -> None:
        """リモートURLが取得できない場合はremote_urlキーなし"""

        def mock_run(cmd: list[str], **_kwargs: object) -> MagicMock:
            if "--abbrev-ref" in cmd:
                return MagicMock(returncode=0, stdout="feature\n")
            if "get-url" in cmd:
                return MagicMock(returncode=1, stdout="")
            return MagicMock(returncode=1, stdout="")

        with patch("statusline.subprocess.run", side_effect=mock_run):
            result = statusline._fetch_git_info("/some/path")
        assert result["branch"] == "feature"
        assert "remote_url" not in result


class TestGetGitInfo:
    """_get_git_info のテスト"""

    def test_fetches_and_returns_data(self, tmp_path: Path) -> None:
        """_fetch_git_infoを呼びデータを返す"""
        cache_file = tmp_path / "git-cache.json"
        with (
            patch.object(statusline, "_GIT_CACHE_PATH", cache_file),
            patch(
                "statusline._fetch_git_info",
                return_value={"branch": "main", "remote_url": "https://example.com"},
            ),
        ):
            result = statusline._get_git_info("/some/path")
        assert result == {"branch": "main", "remote_url": "https://example.com"}

    def test_returns_cached_data(self, tmp_path: Path) -> None:
        """有効なキャッシュがあればAPIを呼ばず返す"""
        cache_file = tmp_path / "git-cache.json"
        cache_data = {
            "_cached_at": time.time(),
            "data": {"branch": "cached-branch"},
            "cwd": "/some/path",
        }
        cache_file.write_text(json.dumps(cache_data))
        with patch.object(statusline, "_GIT_CACHE_PATH", cache_file):
            result = statusline._get_git_info("/some/path")
        assert result == {"branch": "cached-branch"}

    def test_different_cwd_invalidates_cache(self, tmp_path: Path) -> None:
        """cwdが異なる場合はキャッシュを無効化する"""
        cache_file = tmp_path / "git-cache.json"
        cache_data = {
            "_cached_at": time.time(),
            "data": {"branch": "old-branch"},
            "cwd": "/old/path",
        }
        cache_file.write_text(json.dumps(cache_data))
        with (
            patch.object(statusline, "_GIT_CACHE_PATH", cache_file),
            patch(
                "statusline._fetch_git_info",
                return_value={"branch": "new-branch"},
            ),
        ):
            result = statusline._get_git_info("/new/path")
        assert result == {"branch": "new-branch"}
