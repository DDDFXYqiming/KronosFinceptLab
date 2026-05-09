from __future__ import annotations

import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class StaticProvider:
    provider_id = "static"
    display_name = "Static Provider"
    capabilities = ("test",)
    requires_api_key = False

    def __init__(self) -> None:
        self.calls = 0

    def describe(self):
        from kronos_fincept.macro import MacroProviderResult  # noqa: F401
        from kronos_fincept.macro.schemas import MacroProviderMetadata

        return MacroProviderMetadata(self.provider_id, self.display_name, self.capabilities)

    def fetch_signals(self, query):
        from kronos_fincept.macro import MacroSignal

        self.calls += 1
        return [
            MacroSignal(
                source=self.provider_id,
                signal_type="test_signal",
                value=1.0,
                interpretation=f"query={query.question}",
                time_horizon="short",
                confidence=0.8,
            )
        ]


class EmptyProvider:
    provider_id = "empty"
    display_name = "Empty Provider"
    capabilities = ("test",)
    requires_api_key = False

    def describe(self):
        from kronos_fincept.macro.schemas import MacroProviderMetadata

        return MacroProviderMetadata(self.provider_id, self.display_name, self.capabilities)

    def fetch_signals(self, query):
        return []


class FailingProvider:
    provider_id = "failing"
    display_name = "Failing Provider"
    capabilities = ("test",)
    requires_api_key = False

    def describe(self):
        from kronos_fincept.macro.schemas import MacroProviderMetadata

        return MacroProviderMetadata(self.provider_id, self.display_name, self.capabilities)

    def fetch_signals(self, query):
        raise RuntimeError("boom")


class SlowProvider:
    provider_id = "slow"
    display_name = "Slow Provider"
    capabilities = ("test",)
    requires_api_key = False

    def describe(self):
        from kronos_fincept.macro.schemas import MacroProviderMetadata

        return MacroProviderMetadata(self.provider_id, self.display_name, self.capabilities)

    def fetch_signals(self, query):
        time.sleep(0.3)
        return []


def test_v101_macro_manager_imports_and_registers_digital_oracle_providers():
    from kronos_fincept.macro import MacroDataManager, create_default_providers

    providers = create_default_providers()
    provider_ids = {item.provider_id for item in providers}

    assert MacroDataManager
    assert len(providers) == 17
    assert {
        "polymarket",
        "kalshi",
        "us_treasury",
        "cftc_cot",
        "coingecko",
        "edgar",
        "bis",
        "worldbank",
        "yfinance_options",
        "fear_greed",
        "cme_fedwatch",
        "web_search",
        "yahoo_price",
        "deribit",
        "currency",
        "dbnomics",
        "stooq",
    } <= provider_ids


def test_v101_macro_manager_gather_keeps_partial_results_when_provider_fails():
    from kronos_fincept.macro import MacroDataManager

    manager = MacroDataManager(
        providers=[StaticProvider(), EmptyProvider(), FailingProvider()],
        cache_ttl_seconds=0,
        timeout_seconds=5,
    )
    result = manager.gather("gold macro risk")

    assert result.ok is False
    assert len(result.signals) == 1
    assert result.provider_results["static"].status == "completed"
    assert result.provider_results["empty"].status == "empty"
    assert result.provider_results["failing"].status == "failed"
    assert "boom" in result.errors["failing"]


def test_v101_macro_manager_caches_provider_results():
    from kronos_fincept.macro import MacroDataManager

    provider = StaticProvider()
    manager = MacroDataManager(providers=[provider], cache_ttl_seconds=60)

    first = manager.gather("same query")
    second = manager.gather("same query")

    assert len(first.signals) == 1
    assert len(second.signals) == 1
    assert provider.calls == 1


def test_v101_macro_manager_times_out_slow_provider_without_blocking_result():
    from kronos_fincept.macro import MacroDataManager

    manager = MacroDataManager(providers=[SlowProvider()], cache_ttl_seconds=0, timeout_seconds=0.01)

    started = time.perf_counter()
    result = manager.gather("slow query")
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert result.provider_results["slow"].status == "failed"
    assert "timed out" in result.errors["slow"]


def test_v101_optional_providers_degrade_without_configuration_or_dependency():
    from kronos_fincept.macro import MacroQuery, WebSearchProvider, YFinanceProvider, YahooPriceProvider

    assert WebSearchProvider(search_client_factory=lambda: None).fetch_signals(MacroQuery("VIX")) == []
    assert YFinanceProvider(yfinance_loader=lambda: None).fetch_signals(MacroQuery("AAPL", symbols=("AAPL",))) == []
    assert YahooPriceProvider(yfinance_loader=lambda: None).fetch_signals(MacroQuery("SPY", symbols=("SPY",))) == []


def test_v101_readme_and_version_labels_are_current():
    assert "Version: v10." in read("README.md")
    assert "MacroDataManager" in read("README.md")
    assert "v10." in read("web/src/components/layout/Sidebar.tsx")
    assert "v10." in read("web/src/components/layout/Header.tsx")
