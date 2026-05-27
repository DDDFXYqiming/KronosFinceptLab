"""Tests for the standalone DBnomicsProvider.

Relies on monkeypatch to avoid hitting the live DBnomics API.
"""

from __future__ import annotations

from typing import Any

from kronos_fincept.macro import MacroQuery
from kronos_fincept.macro.providers.dbnomics import (
    DBnomicsProvider,
    SERIES_CATALOG,
    _CAPABILITY_KEYWORDS,
    _COUNTRY_KEYWORDS,
    _infer_capabilities,
    _infer_countries,
    _query_text,
    _to_float,
)


# ---------------------------------------------------------------------------
# Unit: helper functions
# ---------------------------------------------------------------------------


def test_to_float_converts_valid_values():
    assert _to_float(3.14) == 3.14
    assert _to_float("2.5") == 2.5
    assert _to_float(0) == 0.0
    assert _to_float(None) is None
    assert _to_float("") is None
    assert _to_float("n/a") is None
    assert _to_float("N/A") is None
    assert _to_float({}) is None


def test_query_text_combines_question_market_and_symbols():
    q = MacroQuery(question="GDP growth", market="US", symbols=("2025",))
    text = _query_text(q)
    assert "gdp" in text
    assert "growth" in text
    assert "us" in text
    assert "2025" in text


def test_query_text_lowercases_everything():
    q = MacroQuery(question="USA Inflation Rate")
    assert _query_text(q) == "usa inflation rate"


def test_infer_capabilities_returns_relevant_capabilities():
    assert "gdp" in _infer_capabilities("gdp growth united states")
    assert "inflation" in _infer_capabilities("cpi inflation price")
    assert "interest_rates" in _infer_capabilities("fed interest rate")
    assert "employment" in _infer_capabilities("unemployment job labor")
    assert "trade_balance" in _infer_capabilities("trade balance exports")
    assert "debt" in _infer_capabilities("government debt fiscal deficit")


def test_infer_capabilities_empty_when_no_keywords():
    assert _infer_capabilities("hello world") == set()


def test_infer_capabilities_multiple_capabilities():
    caps = _infer_capabilities("gdp growth and inflation and debt")
    assert "gdp" in caps
    assert "inflation" in caps
    assert "debt" in caps


def test_infer_countries_returns_country_codes():
    assert "US" in _infer_countries("united states economy")
    assert "CN" in _infer_countries("china gdp")
    assert "JP" in _infer_countries("japan cpi")
    assert "DE" in _infer_countries("germany unemployment")
    assert "GB" in _infer_countries("uk trade balance")
    assert "FR" in _infer_countries("france debt")
    assert "IN" in _infer_countries("india")
    assert "EU" in _infer_countries("eurozone interest rates")


def test_infer_countries_empty_when_no_keywords():
    assert _infer_countries("gdp growth") == set()


def test_infer_countries_multiple_countries():
    codes = _infer_countries("us and china and japan gdp")
    assert "US" in codes
    assert "CN" in codes
    assert "JP" in codes


# ---------------------------------------------------------------------------
# Unit: DBnomicsProvider
# ---------------------------------------------------------------------------


def test_provider_id_and_capabilities():
    provider = DBnomicsProvider()
    assert provider.provider_id == "dbnomics"
    assert provider.display_name == "DBnomics"
    assert provider.capabilities == (
        "gdp",
        "inflation",
        "interest_rates",
        "employment",
        "trade_balance",
        "debt",
    )


def test_describe_returns_metadata():
    provider = DBnomicsProvider()
    meta = provider.describe()
    assert meta.provider_id == "dbnomics"
    assert meta.display_name == "DBnomics"
    assert "gdp" in meta.capabilities
    assert meta.requires_api_key is False


def test_default_candidates_covers_all_capabilities():
    provider = DBnomicsProvider()
    candidates = provider._default_candidates()
    capabilities_in_defaults = {entry[5] for entry in candidates}
    assert capabilities_in_defaults == {
        "gdp",
        "inflation",
        "interest_rates",
        "employment",
        "trade_balance",
        "debt",
    }
    assert len(candidates) == 6


def test_resolve_candidates_filters_by_capability_and_country():
    provider = DBnomicsProvider()
    candidates = provider._resolve_candidates("gdp germany")
    assert candidates
    for entry in candidates:
        assert entry[5] == "gdp"  # capability
        assert "DE" in entry[6]  # countries_str contains DE


def test_resolve_candidates_returns_all_for_capability_when_no_country_match():
    provider = DBnomicsProvider()
    candidates = provider._resolve_candidates("inflation")
    assert candidates
    for entry in candidates:
        assert entry[5] == "inflation"


def test_resolve_candidates_empty_when_no_keywords():
    provider = DBnomicsProvider()
    candidates = provider._resolve_candidates("random unrelated text")
    assert candidates == []


def test_resolve_candidates_multi_country_and_capability():
    provider = DBnomicsProvider()
    candidates = provider._resolve_candidates("gdp us and japan")
    assert candidates
    for entry in candidates:
        assert entry[5] == "gdp"
        entry_countries = entry[6].split(",")
        # Should include US or JP entries
        assert "US" in entry[6] or "JP" in entry[6]


def test_interpretation_contains_label_and_value():
    provider = DBnomicsProvider()
    text = provider._interpretation("gdp_growth", "USA GDP growth", 2.5, "2025-01")
    assert "USA GDP growth" in text
    assert "2.50" in text
    assert "2025-01" in text


def test_interpretation_none_value():
    provider = DBnomicsProvider()
    text = provider._interpretation("inflation", "CPI", None, "")
    assert "N/A" in text


# ---------------------------------------------------------------------------
# Integration-style: monkeypatched HTTP
# ---------------------------------------------------------------------------


def test_fetch_signals_returns_signals_on_success(monkeypatch):
    """Simulate a successful DBnomics API response."""

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {
                    "series": {
                        "docs": [
                            {
                                "period": {
                                    "value": 2.4,
                                    "period": "2025-01-01",
                                },
                            }
                        ]
                    }
                }

        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)

    provider = DBnomicsProvider()
    signals = provider.fetch_signals(MacroQuery("US GDP growth"))

    assert len(signals) >= 1
    signal = signals[0]
    assert signal.source == "dbnomics"
    assert signal.value == 2.4
    assert signal.metadata["period"] == "2025-01-01"
    assert signal.metadata["capability"] == "gdp"


def test_fetch_signals_handles_api_error_gracefully(monkeypatch):
    """When the API fails, the provider should degrade to empty."""

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        raise TimeoutError("API timeout")

    monkeypatch.setattr("requests.get", fake_get)

    provider = DBnomicsProvider()
    signals = provider.fetch_signals(MacroQuery("GDP"))
    # Default candidates will be tried and each will fail
    # So we should get empty list
    assert signals == []


def test_fetch_signals_handles_malformed_response(monkeypatch):
    """Malformed JSON response should not crash the provider."""

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {"series": None}

        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)

    provider = DBnomicsProvider()
    signals = provider.fetch_signals(MacroQuery("inflation"))
    assert signals == []


def test_fetch_signals_honours_query_limit(monkeypatch):
    """The limit parameter should cap the number of returned signals."""

    call_count = 0

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1

        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {
                    "series": {
                        "docs": [
                            {
                                "period": {
                                    "value": 3.1,
                                    "period": "2025-Q1",
                                },
                            }
                        ]
                    }
                }

        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)

    provider = DBnomicsProvider()
    signals = provider.fetch_signals(MacroQuery("gdp growth", limit=3))
    assert len(signals) <= 3


def test_fetch_signals_uses_requests_library(monkeypatch):
    """Verify that requests.get is called with the correct URL pattern."""
    captured_urls: list[str] = []

    def fake_get(url: str, *args: Any, **kwargs: Any) -> Any:
        captured_urls.append(url)

        class FakeResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {
                    "series": {
                        "docs": [
                            {
                                "period": {
                                    "value": 1.5,
                                    "period": "2025-01",
                                },
                            }
                        ]
                    }
                }

        return FakeResponse()

    monkeypatch.setattr("requests.get", fake_get)

    provider = DBnomicsProvider()
    provider.fetch_signals(MacroQuery("fed interest rate"))
    assert captured_urls
    for url in captured_urls:
        assert "api.db.nomics.world/v22/series/" in url


# ---------------------------------------------------------------------------
# Catalog integrity
# ---------------------------------------------------------------------------


def test_series_catalog_has_at_least_one_entry_per_capability():
    capabilities_found: set[str] = set()
    for entry in SERIES_CATALOG:
        capabilities_found.add(entry[5])
    assert capabilities_found == {
        "gdp",
        "inflation",
        "interest_rates",
        "employment",
        "trade_balance",
        "debt",
    }


def test_series_catalog_has_us_entries():
    us_entries = [e for e in SERIES_CATALOG if "US" in e[6]]
    assert len(us_entries) >= 6  # at least one per capability


def test_capability_keywords_cover_all_capabilities():
    keywords_by_cap: dict[str, list[str]] = {}
    for keyword, cap in _CAPABILITY_KEYWORDS.items():
        keywords_by_cap.setdefault(cap, []).append(keyword)
    assert set(keywords_by_cap.keys()) == {
        "gdp",
        "inflation",
        "interest_rates",
        "employment",
        "trade_balance",
        "debt",
    }


# ---------------------------------------------------------------------------
# smoke: create_default_providers includes dbnomics
# ---------------------------------------------------------------------------


def test_dbnomics_in_default_providers():
    from kronos_fincept.macro.providers import create_default_providers

    providers = create_default_providers()
    ids = {p.provider_id for p in providers}
    assert "dbnomics" in ids


def test_dbnomics_provider_is_db_nomics_class():
    from kronos_fincept.macro.providers import DBnomicsProvider
    from kronos_fincept.macro.providers.dbnomics import DBnomicsProvider as Standalone

    assert DBnomicsProvider is Standalone
