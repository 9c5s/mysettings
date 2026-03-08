"""statusline.pyのテスト"""

# テストではプライベートメンバーへのアクセスが必要である
# pyright: reportPrivateUsage=false

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "ClaudeCode" / "scripts")
)
import statusline


class TestGetCurrencyFromLocale:
    """_get_currency_from_locale のテスト"""

    def test_japanese_locale(self):
        with patch("statusline.locale.getlocale", return_value=("ja_JP", "utf-8")):
            assert statusline._get_currency_from_locale() == "JPY"

    def test_us_locale(self):
        with patch("statusline.locale.getlocale", return_value=("en_US", "utf-8")):
            assert statusline._get_currency_from_locale() == "USD"

    def test_uk_locale(self):
        with patch("statusline.locale.getlocale", return_value=("en_GB", "utf-8")):
            assert statusline._get_currency_from_locale() == "GBP"

    def test_german_locale(self):
        with patch("statusline.locale.getlocale", return_value=("de_DE", "utf-8")):
            assert statusline._get_currency_from_locale() == "EUR"

    def test_unknown_locale_falls_back_to_usd(self):
        with patch("statusline.locale.getlocale", return_value=("xx_XX", "utf-8")):
            assert statusline._get_currency_from_locale() == "USD"

    def test_none_locale_falls_back_to_usd(self):
        with patch("statusline.locale.getlocale", return_value=(None, None)):
            assert statusline._get_currency_from_locale() == "USD"

    def test_value_error_falls_back_to_usd(self):
        with patch("statusline.locale.getlocale", side_effect=ValueError):
            assert statusline._get_currency_from_locale() == "USD"

    def test_locale_without_country(self):
        with patch("statusline.locale.getlocale", return_value=("ja", "utf-8")):
            assert statusline._get_currency_from_locale() == "USD"


class TestCurrencyData:
    """通貨データのテスト"""

    def test_currencies_has_usd(self):
        assert "USD" in statusline._CURRENCIES

    def test_currencies_has_jpy(self):
        info = statusline._CURRENCIES["JPY"]
        assert info.symbol == "\u00a5"
        assert info.decimals == 0

    def test_currencies_has_thb(self):
        """新規追加通貨THBのテスト"""
        info = statusline._CURRENCIES["THB"]
        assert info.symbol == "\u0e3f"
        assert info.decimals == 2

    def test_currencies_has_try(self):
        """新規追加通貨TRYのテスト"""
        info = statusline._CURRENCIES["TRY"]
        assert info.symbol == "\u20ba"
        assert info.decimals == 2

    def test_twd_removed(self):
        """TWDはAPI非対応のため削除されている"""
        assert "TWD" not in statusline._CURRENCIES

    def test_locale_to_currency_has_jp(self):
        assert statusline._LOCALE_TO_CURRENCY["JP"] == "JPY"

    def test_locale_to_currency_has_us(self):
        assert statusline._LOCALE_TO_CURRENCY["US"] == "USD"

    def test_locale_to_currency_tw_removed(self):
        """TWはAPI非対応のため削除されている"""
        assert "TW" not in statusline._LOCALE_TO_CURRENCY


class TestGetExchangeRate:
    """_get_exchange_rate のテスト"""

    def test_usd_returns_none(self):
        """USDの場合は変換不要なのでNoneを返す"""
        assert statusline._get_exchange_rate("USD") is None

    def test_fetches_rate_from_api(self, tmp_path: Path):
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

    def test_returns_cached_rate(self, tmp_path: Path):
        """有効なキャッシュからレートを返す"""
        cache_file = tmp_path / "exchange-cache.json"
        cache_data = {"_cached_at": time.time(), "data": 149.0, "currency": "JPY"}
        cache_file.write_text(json.dumps(cache_data))

        with patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file):
            rate = statusline._get_exchange_rate("JPY")
        assert rate == 149.0

    def test_api_failure_returns_expired_cache(self, tmp_path: Path):
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

    def test_api_failure_no_cache_returns_none(self, tmp_path: Path):
        """API失敗かつキャッシュなしの場合はNoneを返す"""
        # 存在しないキャッシュファイルを指定する
        cache_file = tmp_path / "nonexistent-cache.json"

        with (
            patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file),
            patch("statusline.urlopen", side_effect=URLError("fail")),
        ):
            rate = statusline._get_exchange_rate("JPY")
        assert rate is None

    def test_different_currency_invalidates_cache(self, tmp_path: Path):
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

    def test_usd_display(self):
        """USDの場合は$表示"""
        with patch.object(statusline, "_currency", "USD"):
            assert statusline._format_cost(1.23) == "$1.23"

    def test_jpy_display(self):
        """JPYの場合は¥表示(小数なし)"""
        with (
            patch.object(statusline, "_currency", "JPY"),
            patch("statusline._get_exchange_rate", return_value=150.0),
        ):
            # 1.23 * 150.0 = 184.5 -> :.0fの偶数丸めで184
            assert statusline._format_cost(1.23) == "¥184"

    def test_eur_display(self):
        """EURの場合はユーロ表示(小数2桁)"""
        with (
            patch.object(statusline, "_currency", "EUR"),
            patch("statusline._get_exchange_rate", return_value=0.92),
        ):
            assert statusline._format_cost(1.00) == "€0.92"

    def test_exchange_rate_failure_falls_back_to_usd(self):
        """為替レート取得失敗時はUSDフォールバック"""
        with (
            patch.object(statusline, "_currency", "JPY"),
            patch("statusline._get_exchange_rate", return_value=None),
        ):
            assert statusline._format_cost(1.23) == "$1.23"

    def test_unknown_currency_falls_back_to_usd(self):
        """_CURRENCIESに存在しない通貨はUSDフォールバック"""
        with (
            patch.object(statusline, "_currency", "XYZ"),
            patch("statusline._get_exchange_rate", return_value=1.5),
        ):
            assert statusline._format_cost(1.23) == "$1.23"


class TestSegCost:
    """_seg_cost のテスト"""

    def test_returns_segment_with_cost(self):
        """コストデータがある場合はSegmentを返す"""
        with patch.object(statusline, "_currency", "USD"):
            data = {"cost": {"total_cost_usd": 1.23}}
            seg = statusline._seg_cost(data)
            assert seg is not None
            assert "$1.23" in seg.text

    def test_jpy_cost_display(self):
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

    def test_no_cost_data_returns_none(self):
        """コストデータがない場合はNone"""
        seg = statusline._seg_cost({})
        assert seg is None

    def test_no_total_cost_returns_none(self):
        """total_cost_usdがない場合はNone"""
        seg = statusline._seg_cost({"cost": {}})
        assert seg is None


class TestCachedFetch:
    """_cached_fetch のテスト"""

    def test_returns_fresh_data_on_cache_miss(self, tmp_path: Path):
        """キャッシュミス時はfetch_fnからデータを取得する"""
        cache_file = tmp_path / "test-cache.json"
        result = statusline._cached_fetch(cache_file, 60, lambda: {"key": "value"})
        assert result == {"key": "value"}

    def test_returns_cached_data_within_ttl(self, tmp_path: Path):
        """TTL内のキャッシュを返す"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {"_cached_at": time.time(), "data": {"cached": True}}
        cache_file.write_text(json.dumps(cache_data))
        result = statusline._cached_fetch(cache_file, 60, lambda: {"fresh": True})
        assert result == {"cached": True}

    def test_refetches_on_expired_cache(self, tmp_path: Path):
        """TTL切れキャッシュは再取得する"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {"_cached_at": 0, "data": {"old": True}}
        cache_file.write_text(json.dumps(cache_data))
        result = statusline._cached_fetch(cache_file, 60, lambda: {"new": True})
        assert result == {"new": True}

    def test_returns_expired_cache_on_fetch_failure(self, tmp_path: Path):
        """fetch失敗時は期限切れキャッシュを返す"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {"_cached_at": 0, "data": {"expired": True}}
        cache_file.write_text(json.dumps(cache_data))

        def failing_fetch():
            raise URLError("fail")

        result = statusline._cached_fetch(cache_file, 60, failing_fetch)
        assert result == {"expired": True}

    def test_returns_none_on_fetch_failure_no_cache(self, tmp_path: Path):
        """fetch失敗かつキャッシュなしの場合はNoneを返す"""
        cache_file = tmp_path / "nonexistent.json"

        def failing_fetch():
            raise URLError("fail")

        result = statusline._cached_fetch(cache_file, 60, failing_fetch)
        assert result is None

    def test_cache_key_mismatch_refetches(self, tmp_path: Path):
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

    def test_cache_key_match_returns_cache(self, tmp_path: Path):
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

    def test_writes_cache_file(self, tmp_path: Path):
        """取得後にキャッシュファイルが書き込まれる"""
        cache_file = tmp_path / "test-cache.json"
        statusline._cached_fetch(cache_file, 60, lambda: {"written": True})
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["data"] == {"written": True}
        assert "_cached_at" in data

    def test_fetch_returning_none_returns_expired(self, tmp_path: Path):
        """fetch_fnがNoneを返した場合は期限切れキャッシュを返す"""
        cache_file = tmp_path / "test-cache.json"
        cache_data = {"_cached_at": 0, "data": {"expired": True}}
        cache_file.write_text(json.dumps(cache_data))
        result = statusline._cached_fetch(cache_file, 60, lambda: None)
        assert result == {"expired": True}


class TestGetSupportedCurrencies:
    """_get_supported_currencies のテスト"""

    def test_fetches_from_api(self, tmp_path: Path):
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

    def test_returns_cached_currencies(self, tmp_path: Path):
        """キャッシュから通貨リストを返す"""
        cache_file = tmp_path / "currencies-cache.json"
        cache_data = {"_cached_at": time.time(), "data": ["JPY", "USD", "EUR"]}
        cache_file.write_text(json.dumps(cache_data))
        with patch.object(statusline, "_CURRENCIES_CACHE_PATH", cache_file):
            result = statusline._get_supported_currencies()
        assert result is not None
        assert "JPY" in result

    def test_api_failure_returns_none(self, tmp_path: Path):
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

    def test_no_args(self):
        """引数なしの場合はデフォルト値"""
        args = statusline._parse_args([])
        assert args.icons is None
        assert args.currency is None

    def test_icons_nerd(self):
        """--icons nerd"""
        args = statusline._parse_args(["--icons", "nerd"])
        assert args.icons == "nerd"

    def test_icons_invalid(self):
        """--icons xxx は無効だがエラーにはならない"""
        args = statusline._parse_args(["--icons", "xxx"])
        assert args.icons == "xxx"

    def test_currency_jpy(self):
        """--currency jpy は大文字化される"""
        args = statusline._parse_args(["--currency", "jpy"])
        assert args.currency == "JPY"

    def test_currency_and_icons(self):
        """両方指定"""
        args = statusline._parse_args(["--icons", "nerd", "--currency", "EUR"])
        assert args.icons == "nerd"
        assert args.currency == "EUR"


class TestResolveCurrency:
    """_resolve_currency のテスト"""

    def test_valid_currency_from_arg(self):
        """CLI引数の通貨がAPI対応なら採用"""
        with patch(
            "statusline._get_supported_currencies", return_value=["JPY", "USD", "EUR"]
        ):
            assert statusline._resolve_currency("JPY") == "JPY"

    def test_invalid_currency_from_arg_falls_back_to_locale(self):
        """CLI引数の通貨がAPI非対応ならロケール判定"""
        with (
            patch("statusline._get_supported_currencies", return_value=["JPY", "USD"]),
            patch("statusline._get_currency_from_locale", return_value="JPY"),
        ):
            assert statusline._resolve_currency("XYZ") == "JPY"

    def test_none_currency_uses_locale(self):
        """通貨未指定ならロケール判定"""
        with (
            patch("statusline._get_supported_currencies", return_value=["JPY", "USD"]),
            patch("statusline._get_currency_from_locale", return_value="JPY"),
        ):
            assert statusline._resolve_currency(None) == "JPY"

    def test_locale_currency_not_supported_falls_back_to_usd(self):
        """ロケール通貨がAPI非対応ならUSD"""
        with (
            patch("statusline._get_supported_currencies", return_value=["USD", "EUR"]),
            patch("statusline._get_currency_from_locale", return_value="XYZ"),
        ):
            assert statusline._resolve_currency(None) == "USD"

    def test_api_failure_falls_back_to_usd(self):
        """API対応通貨リスト取得失敗時はUSD"""
        with patch("statusline._get_supported_currencies", return_value=None):
            assert statusline._resolve_currency("JPY") == "USD"
