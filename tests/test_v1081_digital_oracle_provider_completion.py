from __future__ import annotations

import pytest

from kronos_fincept.macro import MacroDataManager, MacroProviderUnavailable, MacroQuery
from kronos_fincept.macro.providers import digital_oracle


def test_v1081_edgar_provider_returns_recent_official_filings(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_json(url: str, **kwargs):
        if url == digital_oracle.SEC_COMPANY_TICKERS_URL:
            return {
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            }
        if url == digital_oracle.SEC_SUBMISSIONS_URL.format(cik="0000320193"):
            return {
                "name": "Apple Inc.",
                "filings": {
                    "recent": {
                        "form": ["10-Q", "8-K", "SD"],
                        "filingDate": ["2026-04-30", "2026-04-01", "2026-03-01"],
                        "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002", "x"],
                        "primaryDocument": ["aapl-20260328.htm", "aapl-8k.htm", "x.htm"],
                        "acceptanceDateTime": ["2026-04-30T18:00:00", "2026-04-01T18:00:00", ""],
                    }
                },
            }
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(digital_oracle, "_get_json", fake_get_json)

    signals = digital_oracle.EdgarProvider().fetch_signals(MacroQuery("AAPL filings", symbols=("AAPL",), limit=2))

    assert [item.value for item in signals] == ["10-Q", "8-K"]
    assert signals[0].metadata["cik"] == "0000320193"
    assert signals[0].metadata["data_quality"] == "official_sec_filing"
    assert "sec.gov/Archives/edgar/data/320193" in str(signals[0].source_url)


def test_v1081_bis_provider_reads_official_bulk_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows_by_topic = {
        digital_oracle.BIS_BULK_DOWNLOADS["policy_rates"]: [
            {"REF_AREA": "US", "TIME_PERIOD": "2025-Q4", "OBS_VALUE": "4.50", "series_name": "Policy rate"},
            {"REF_AREA": "US", "TIME_PERIOD": "2026-Q1", "OBS_VALUE": "4.25", "series_name": "Policy rate"},
        ],
        digital_oracle.BIS_BULK_DOWNLOADS["credit_gap"]: [
            {"REF_AREA": "US", "TIME_PERIOD": "2026-Q1", "OBS_VALUE": "-1.2", "series_name": "Credit-to-GDP gap"},
        ],
        digital_oracle.BIS_BULK_DOWNLOADS["global_liquidity"]: [],
    }

    monkeypatch.setattr(digital_oracle, "_get_zip_csv_rows", lambda url, **kwargs: rows_by_topic[url])

    signals = digital_oracle.BisProvider().fetch_signals(MacroQuery("美国信用和利率", limit=3))

    assert [item.signal_type for item in signals] == ["bis_policy_rates", "bis_credit_gap"]
    assert signals[0].value == 4.25
    assert signals[0].observed_at == "2026-Q1"
    assert signals[0].metadata["data_quality"] == "official_bis_statistics"


def test_v1081_cme_fedwatch_provider_parses_configured_probability_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CME_FEDWATCH_ENDPOINT", "https://example.test/fedwatch")
    monkeypatch.setenv("CME_FEDWATCH_API_KEY", "secret")
    captured: dict[str, object] = {}

    def fake_get_json(url: str, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return {
            "meetings": [
                {
                    "meetingDate": "2026-06-17",
                    "probabilities": [
                        {"targetRate": "4.25-4.50", "probability": 65.0},
                        {"targetRate": "4.00-4.25", "probability": 35.0},
                    ],
                }
            ]
        }

    monkeypatch.setattr(digital_oracle, "_get_json", fake_get_json)

    signals = digital_oracle.CMEFedWatchProvider().fetch_signals(MacroQuery("FedWatch", limit=1))

    assert captured["url"] == "https://example.test/fedwatch"
    assert captured["params"] == {"apiKey": "secret"}
    assert signals[0].value == 0.65
    assert signals[0].metadata["target_rate"] == "4.25-4.50"
    assert signals[0].metadata["data_quality"] == "cme_fedwatch_api"


def test_v1081_macro_manager_marks_configured_provider_unavailable() -> None:
    class UnavailableProvider:
        provider_id = "needs_key"
        display_name = "Needs Key"
        capabilities = ("test",)
        requires_api_key = True

        def describe(self):
            from kronos_fincept.macro.schemas import MacroProviderMetadata

            return MacroProviderMetadata(self.provider_id, self.display_name, self.capabilities, True)

        def fetch_signals(self, query):
            raise MacroProviderUnavailable("missing endpoint")

    result = MacroDataManager(providers=[UnavailableProvider()], cache_ttl_seconds=0).gather("test")

    assert result.ok is True
    assert result.provider_results["needs_key"].status == "unavailable"
    assert result.provider_results["needs_key"].metadata["reason"] == "unavailable"


def test_us_treasury_provider_adds_fiscaldata_exchange_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_curve_row(year: int, curve_type: str, *, timeout: float):
        if curve_type == "nominal":
            return {"Date": "2026-05-20", "10 Yr": "4.50", "2 Yr": "4.00"}
        return {"Date": "2026-05-20", "10 Yr": "2.00"}

    captured: dict[str, object] = {}

    def fake_get_json(url: str, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return {
            "data": [
                {
                    "record_date": "2026-03-31",
                    "country": "China",
                    "currency": "Yuan",
                    "country_currency_desc": "China-CNY",
                    "exchange_rate": "7.18",
                }
            ]
        }

    monkeypatch.setattr(digital_oracle, "_latest_curve_row_with_retry", fake_curve_row)
    monkeypatch.setattr(digital_oracle, "_get_json", fake_get_json)

    signals = digital_oracle.USTreasuryProvider().fetch_signals(MacroQuery("人民币汇率", limit=4))

    fx = [item for item in signals if item.signal_type == "treasury_fx_exchange_rate"]
    assert fx
    assert fx[0].value == 7.18
    assert fx[0].metadata["data_quality"] == "official_us_treasury_fiscaldata"
    assert str(captured["url"]).endswith("/rates_of_exchange")
    assert captured["params"]["filter"] == "country_currency_desc:eq:China-CNY"


def test_dbnomics_provider_accepts_dict_series_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        digital_oracle.DBnomicsProvider,
        "_DBNOMICS_SERIES",
        (("IMF", "WEO", "USA.NGDP_RPCH.pcent", "IMF 美国 GDP 增速"),),
    )
    monkeypatch.setattr(
        digital_oracle,
        "_get_json",
        lambda *args, **kwargs: {
            "series": {
                "docs": [
                    {
                        "period": {"value": "2.8", "period": "2026"},
                        "period_start_day": "2026-01-01",
                    }
                ]
            }
        },
    )

    signals = digital_oracle.DBnomicsProvider().fetch_signals(MacroQuery("美国 GDP", limit=1))

    assert len(signals) == 1
    assert signals[0].value == 2.8
    assert signals[0].metadata["data_quality"] == "official_imf"


def test_stooq_provider_maps_yfinance_symbols_to_stooq(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_text(url: str, **kwargs) -> str:
        captured["url"] = url
        return "Symbol,Date,Time,Open,High,Low,Close,Volume\nEURUSD,2026-05-20,22:00:00,1.10,1.12,1.09,1.11,1000\n"

    monkeypatch.setattr(digital_oracle, "_get_text", fake_get_text)

    signals = digital_oracle.StooqProvider().fetch_signals(MacroQuery("EURUSD", symbols=("EURUSD=X",), limit=1))

    assert len(signals) == 1
    assert "s=eurusd" in captured["url"]
    assert signals[0].metadata["symbol"] == "eurusd"
    assert signals[0].metadata["source_symbol"] == "EURUSD=X"
