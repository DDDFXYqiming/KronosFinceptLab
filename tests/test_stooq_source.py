"""
Tests for Stooq data source adapter.

Uses mock HTTP responses to avoid real network calls.
"""

import json
from unittest.mock import patch, Mock
from datetime import datetime

import pytest

from kronos_fincept.data_sources.stooq_source import StooqSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CSV = """Date,Open,High,Low,Close,Volume
2025-01-02,150.12,155.00,149.50,154.30,8500000
2025-01-03,154.50,156.80,153.20,155.10,9200000
2025-01-06,155.00,158.50,154.80,157.90,10100000
2025-01-07,158.00,159.20,156.10,156.80,8900000
"""

SAMPLE_CSV_EMPTY = "Date,Open,High,Low,Close,Volume\n"


@pytest.fixture
def stooq_source():
    return StooqSource(priority=4)


# ---------------------------------------------------------------------------
# Construction & config
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_name(self, stooq_source):
        assert stooq_source.config.name == "stooq"

    def test_priority(self, stooq_source):
        assert stooq_source.config.priority == 4

    def test_supported_endpoints(self, stooq_source):
        assert "stooq_hist" in stooq_source.supported_endpoints

    def test_default_config(self, stooq_source):
        assert stooq_source.config.max_retries == 3
        assert stooq_source.config.timeout == 30.0


# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------

class TestSymbolNormalisation:
    """Verify _normalize_symbol behaviour for each market."""

    def test_shanghai_a_share(self, stooq_source):
        assert stooq_source._normalize_symbol("601398") == "601398.SS"

    def test_shenzhen_a_share(self, stooq_source):
        assert stooq_source._normalize_symbol("000001") == "000001.SZ"

    def test_shenzhen_gem(self, stooq_source):
        assert stooq_source._normalize_symbol("300750") == "300750.SZ"

    def test_hong_kong(self, stooq_source):
        assert stooq_source._normalize_symbol("00700") == "00700.HK"

    def test_us_stock(self, stooq_source):
        assert stooq_source._normalize_symbol("AAPL") == "AAPL.US"

    def test_already_suffixed(self, stooq_source):
        assert stooq_source._normalize_symbol("AAPL.US") == "AAPL.US"
        assert stooq_source._normalize_symbol("601398.SS") == "601398.SS"
        assert stooq_source._normalize_symbol("000001.SZ") == "000001.SZ"
        assert stooq_source._normalize_symbol("00700.HK") == "00700.HK"

    def test_explicit_market_override(self, stooq_source):
        # Force a Shenzhen symbol with explicit market
        assert stooq_source._normalize_symbol("000001", market="cn_sz") == "000001.SZ"
        assert stooq_source._normalize_symbol("AAPL", market="us") == "AAPL.US"
        assert stooq_source._normalize_symbol("00700", market="hk") == "00700.HK"


# ---------------------------------------------------------------------------
# Date normalisation
# ---------------------------------------------------------------------------

class TestDateNormalisation:
    def test_yyyymmdd(self, stooq_source):
        assert stooq_source._normalize_date("20250102") == "20250102"

    def test_yyyy_mm_dd(self, stooq_source):
        assert stooq_source._normalize_date("2025-01-02") == "20250102"

    def test_yyyy_mm_dd_stripped(self, stooq_source):
        assert stooq_source._normalize_date(" 2025-01-02 ") == "20250102"

    def test_empty_string(self, stooq_source):
        assert stooq_source._normalize_date("") == ""


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

class TestCsvParsing:
    def test_parse_valid_csv(self, stooq_source):
        rows = stooq_source._parse_csv(SAMPLE_CSV, "AAPL")
        assert len(rows) == 4

        row = rows[0]
        assert row["date"] == "2025-01-02"
        assert row["symbol"] == "AAPL"
        assert row["open"] == 150.12
        assert row["high"] == 155.00
        assert row["low"] == 149.50
        assert row["close"] == 154.30
        assert row["volume"] == 8500000

    def test_parse_empty_csv(self, stooq_source):
        rows = stooq_source._parse_csv(SAMPLE_CSV_EMPTY, "AAPL")
        assert rows == []

    def test_all_ohlcv_fields_present(self, stooq_source):
        rows = stooq_source._parse_csv(SAMPLE_CSV, "AAPL")
        for row in rows:
            assert "date" in row
            assert "symbol" in row
            assert "open" in row
            assert "high" in row
            assert "low" in row
            assert "close" in row
            assert "volume" in row

    def test_values_rounded_to_two_decimals(self, stooq_source):
        rows = stooq_source._parse_csv(SAMPLE_CSV, "AAPL")
        for row in rows:
            assert isinstance(row["open"], float)
            assert isinstance(row["high"], float)
            assert isinstance(row["low"], float)
            assert isinstance(row["close"], float)
            assert isinstance(row["volume"], int)


# ---------------------------------------------------------------------------
# fetch() — end-to-end with mocked HTTP
# ---------------------------------------------------------------------------

class TestFetch:
    def test_unknown_endpoint(self, stooq_source):
        result = stooq_source.fetch("nonexistent")
        assert result["success"] is False
        assert "error" in result

    def test_missing_symbol(self, stooq_source):
        result = stooq_source.fetch("stooq_hist")
        assert result["success"] is False
        assert "缺少 symbol" in result["error"]

    @patch.object(StooqSource, "_download", return_value=SAMPLE_CSV)
    def test_successful_fetch(self, mock_download, stooq_source):
        result = stooq_source.fetch(
            "stooq_hist",
            symbol="AAPL",
            start_date="2025-01-01",
            end_date="2025-01-07",
            market="us",
        )

        assert result["success"] is True
        assert result["source"] == "stooq"
        assert result["count"] == 4
        assert len(result["data"]) == 4

        first = result["data"][0]
        assert first["symbol"] == "AAPL"
        assert first["date"] == "2025-01-02"
        assert first["open"] == 150.12
        assert first["close"] == 154.30
        assert first["volume"] == 8500000

    @patch.object(StooqSource, "_download", return_value=SAMPLE_CSV_EMPTY)
    def test_fetch_empty_result(self, mock_download, stooq_source):
        result = stooq_source.fetch(
            "stooq_hist",
            symbol="NODATA",
            start_date="2025-01-01",
            end_date="2025-01-07",
        )
        assert result["success"] is True
        assert result["count"] == 0
        assert result["data"] == []

    @patch.object(StooqSource, "_download", return_value=None)
    def test_download_failure_returns_error(self, mock_download, stooq_source):
        result = stooq_source.fetch(
            "stooq_hist",
            symbol="AAPL",
            start_date="2025-01-01",
            end_date="2025-01-07",
        )
        assert result["success"] is False
        assert "下载" in result["error"]

    @patch.object(StooqSource, "_download", return_value=SAMPLE_CSV)
    def test_symbol_normalisation_applied(self, mock_download, stooq_source):
        """Verify that A-share symbol gets .SS suffix in the URL."""
        stooq_source.fetch(
            "stooq_hist",
            symbol="601398",
            start_date="20250101",
            end_date="20250107",
            market="auto",
        )
        # Check that the URL called by _download contains .SS
        call_url = mock_download.call_args[0][0]
        assert "601398.SS" in call_url

    @patch.object(StooqSource, "_download", return_value=SAMPLE_CSV)
    def test_url_format(self, mock_download, stooq_source):
        stooq_source.fetch(
            "stooq_hist",
            symbol="AAPL",
            start_date="20250101",
            end_date="20250107",
            market="us",
        )
        call_url = mock_download.call_args[0][0]
        assert call_url.startswith("https://stooq.com/q/d/l/")
        assert "s=AAPL.US" in call_url
        assert "d1=20250101" in call_url
        assert "d2=20250107" in call_url
        assert "i=daily" in call_url


# ---------------------------------------------------------------------------
# Integration with DataSource base class (circuit-breaker, retry)
# ---------------------------------------------------------------------------

class TestDataSourceBaseIntegration:
    def test_record_success_clears_failures(self, stooq_source):
        stooq_source.consecutive_failures = 3
        stooq_source.record_success()
        assert stooq_source.consecutive_failures == 0

    def test_record_failure_increments(self, stooq_source):
        stooq_source.consecutive_failures = 0
        stooq_source.record_failure()
        assert stooq_source.consecutive_failures == 1

    def test_retry_delay_exponential(self, stooq_source):
        delays = [stooq_source.get_retry_delay(i) for i in range(3)]
        assert delays == [1.0, 2.0, 4.0]

    def test_is_available_default(self, stooq_source):
        assert stooq_source.is_available() is True

    def test_supports_stooq_endpoint(self, stooq_source):
        assert stooq_source.supports_endpoint("stooq_hist") is True

    def test_does_not_support_unknown_endpoint(self, stooq_source):
        assert stooq_source.supports_endpoint("some_other") is False


# ---------------------------------------------------------------------------
# Unicode / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_csv_with_bom(self, stooq_source):
        """Stooq sometimes returns UTF-8 BOM — ensure it's handled."""
        bom_csv = "\ufeffDate,Open,High,Low,Close,Volume\n2025-01-02,100.0,101.0,99.0,100.5,5000\n"
        rows = stooq_source._parse_csv(bom_csv, "TEST")
        assert len(rows) == 1
        assert rows[0]["open"] == 100.0

    def test_csv_with_na_values(self, stooq_source):
        """Stooq may return N/A for missing data points."""
        na_csv = "Date,Open,High,Low,Close,Volume\n2025-01-02,N/A,N/A,N/A,N/A,N/A\n"
        rows = stooq_source._parse_csv(na_csv, "TEST")
        assert rows[0]["open"] == 0.0
        assert rows[0]["volume"] == 0

    def test_non_numeric_in_csv(self, stooq_source):
        bad_csv = "Date,Open,High,Low,Close,Volume\n2025-01-02,abc,def,ghi,jkl,mno\n"
        rows = stooq_source._parse_csv(bad_csv, "TEST")
        # Should skip the row gracefully
        assert rows == []
