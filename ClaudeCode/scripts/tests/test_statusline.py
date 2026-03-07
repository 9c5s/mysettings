"""statusline.pyのテスト"""

# テストではプライベートメンバーへのアクセスが必要である
# pyright: reportPrivateUsage=false
# pyright: reportUnknownParameterType=false
# pyright: reportMissingParameterType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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

    def test_locale_to_currency_has_jp(self):
        assert statusline._LOCALE_TO_CURRENCY["JP"] == "JPY"

    def test_locale_to_currency_has_us(self):
        assert statusline._LOCALE_TO_CURRENCY["US"] == "USD"


class TestGetExchangeRate:
    """_get_exchange_rate のテスト"""

    def test_usd_returns_none(self):
        """USDの場合は変換不要なのでNoneを返す"""
        assert statusline._get_exchange_rate("USD") is None

    def test_fetches_rate_from_api(self, tmp_path):
        """APIからレートを取得できる"""
        # 存在しないキャッシュファイルを指定してキャッシュミスを発生させる
        cache_file = tmp_path / "nonexistent-cache.json"

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"rates":{"JPY":150.5}}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with (
            patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file),
            patch("statusline.urlopen", return_value=mock_resp),
        ):
            rate = statusline._get_exchange_rate("JPY")
        assert rate == 150.5

    def test_returns_cached_rate(self, tmp_path):
        """有効なキャッシュからレートを返す"""
        cache_file = tmp_path / "exchange-cache.json"
        cache_data = {"_cached_at": time.time(), "currency": "JPY", "rate": 149.0}
        cache_file.write_text(json.dumps(cache_data))

        with patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file):
            rate = statusline._get_exchange_rate("JPY")
        assert rate == 149.0

    def test_api_failure_returns_expired_cache(self, tmp_path):
        """API失敗時は期限切れキャッシュを返す"""
        cache_file = tmp_path / "exchange-cache.json"
        cache_data = {"_cached_at": 0, "currency": "JPY", "rate": 148.0}
        cache_file.write_text(json.dumps(cache_data))

        with (
            patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file),
            patch("statusline.urlopen", side_effect=URLError("fail")),
        ):
            rate = statusline._get_exchange_rate("JPY")
        assert rate == 148.0

    def test_api_failure_no_cache_returns_none(self, tmp_path):
        """API失敗かつキャッシュなしの場合はNoneを返す"""
        # 存在しないキャッシュファイルを指定する
        cache_file = tmp_path / "nonexistent-cache.json"

        with (
            patch.object(statusline, "_EXCHANGE_CACHE_PATH", cache_file),
            patch("statusline.urlopen", side_effect=URLError("fail")),
        ):
            rate = statusline._get_exchange_rate("JPY")
        assert rate is None

    def test_different_currency_invalidates_cache(self, tmp_path):
        """キャッシュの通貨が異なる場合はAPIから取得する"""
        cache_file = tmp_path / "exchange-cache.json"
        cache_data = {"_cached_at": time.time(), "currency": "EUR", "rate": 0.92}
        cache_file.write_text(json.dumps(cache_data))

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"rates":{"JPY":150.0}}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

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
