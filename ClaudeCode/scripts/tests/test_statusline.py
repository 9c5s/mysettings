"""statusline.pyのテスト"""

# テストではプライベートメンバーへのアクセスが必要である
# pyright: reportPrivateUsage=false

import sys
from pathlib import Path
from unittest.mock import patch

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
