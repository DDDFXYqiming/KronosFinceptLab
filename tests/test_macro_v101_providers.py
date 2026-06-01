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


class SourceCacheProvider(StaticProvider):
    provider_id = "source_project_macro_cache"
    display_name = "Source Cache Provider"

    def fetch_signals(self, query):
        from kronos_fincept.macro import MacroSignal

        self.calls += 1
        return [
            MacroSignal(
                source=self.provider_id,
                signal_type="growth",
                value=50.1,
                interpretation=f"local cache query={query.question}",
                time_horizon="mixed",
                confidence=0.74,
                observed_at="2026-05-01",
                source_url="external/stock-analysis-system/data/macro/china_pmi.parquet",
                metadata={
                    "series_id": "china_pmi",
                    "label": "China PMI",
                    "market": "cn",
                    "data_quality": "source_project_verified_cache",
                },
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
    assert len(providers) >= 23
    assert {
        "polymarket",
        "kalshi",
        "fred",
        "source_project_macro_cache",
        "china_macro_akshare",
        "china_macro_chinalive",
        "china_nbs_live",
        "us_treasury",
        "cftc_cot",
        "coingecko",
        "edgar",
        "bis",
        "worldbank",
        "yfinance_options",
        "fear_greed",
        "cme_fedwatch",
        "rss_news",
        "web_search",
        "anysearch",
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


def test_v101_macro_manager_prioritizes_verified_source_cache_signals():
    from kronos_fincept.macro import MacroDataManager

    manager = MacroDataManager(
        providers=[StaticProvider(), SourceCacheProvider()],
        cache_ttl_seconds=0,
        timeout_seconds=5,
    )

    result = manager.gather("中国PMI和A股流动性")

    assert [signal.source for signal in result.signals][:2] == ["source_project_macro_cache", "static"]


def test_v101_macro_router_prefers_local_cache_for_china_questions():
    from kronos_fincept.agent import select_macro_provider_ids

    provider_ids = select_macro_provider_ids("中国A股流动性、PMI和社融现在怎么样")

    assert provider_ids[:3] == ["source_project_macro_cache", "china_macro_akshare", "china_macro_chinalive"]


def test_v101_macro_context_summarizes_local_cache_assets():
    from kronos_fincept.agent import _macro_context_from_gather
    from kronos_fincept.macro import MacroGatherResult, MacroProviderResult

    signal = SourceCacheProvider().fetch_signals(type("Query", (), {"question": "中国PMI"})())[0]
    result = MacroGatherResult(
        signals=[signal],
        provider_results={
            "source_project_macro_cache": MacroProviderResult(
                provider_id="source_project_macro_cache",
                status="completed",
                signals=[signal],
            )
        },
    )

    context = _macro_context_from_gather("中国PMI", ["source_project_macro_cache"], result)

    assert context["local_data_assets"]["available"] is True
    assert context["local_data_assets"]["series"][0]["series_id"] == "china_pmi"


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


def test_v101_generic_macro_theme_symbol_is_not_used_as_market_ticker(monkeypatch):
    from kronos_fincept.macro import MacroQuery
    from kronos_fincept.macro.providers import digital_oracle as providers

    assert providers._infer_yahoo_symbol(MacroQuery("AI硬件泡沫了吗", symbols=("AI硬件",))) == ("SPY", "SPY")

    captured: dict[str, str] = {}

    def fake_get_text(url: str, *, params=None, timeout=8, accept="application/json") -> str:
        captured["url"] = url
        return "Symbol,Date,Time,Open,High,Low,Close,Volume\n^SPX,2026-05-15,22:00:00,100,101,99,100.5,1000\n"

    monkeypatch.setattr(providers, "_get_text", fake_get_text)

    signals = providers.StooqProvider().fetch_signals(MacroQuery("AI硬件泡沫了吗", symbols=("AI硬件",)))

    assert signals
    assert "AI" not in captured["url"]
    assert "%5Espx" in captured["url"] or "%5ESPX" in captured["url"] or "^SPX" in captured["url"]


def test_v101_readme_and_version_label_is_removed():
    assert "Version:" not in read("README.md")
    assert "v10." in read("web/src/components/layout/Sidebar.tsx")
    assert "v10." in read("web/src/components/layout/Header.tsx")


def test_v101_anysearch_provider_emits_public_web_signals():
    from kronos_fincept.macro import AnySearchProvider, MacroQuery
    from kronos_fincept.web_search import WebSearchResponse, WebSearchResult

    class Client:
        is_configured = True

        def search(self, query):
            return WebSearchResponse(
                enabled=True,
                status="completed",
                provider="anysearch",
                query=query,
                results=[WebSearchResult("Macro news", "https://example.com/macro", "Macro signal")],
                elapsed_ms=1,
            )

    signals = AnySearchProvider(search_client_factory=lambda: Client()).fetch_signals(MacroQuery("黄金宏观风险"))

    assert len(signals) == 1
    assert signals[0].source == "anysearch"
    assert signals[0].metadata["search_provider"] == "anysearch"


def test_v101_rss_news_provider_uses_configured_feeds(monkeypatch):
    from kronos_fincept.macro import MacroQuery, RssNewsProvider

    monkeypatch.setenv("KRONOS_RSS_VALIDATE_DNS", "0")
    xml = (
        "<rss><channel><title>Macro Feed</title>"
        "<item><title>Fed cuts rates</title><link>https://example.com/fed</link>"
        "<pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>"
        "<description>Policy update.</description></item>"
        "</channel></rss>"
    )
    monkeypatch.setattr("kronos_fincept.api.routes.news._fetch_text", lambda url: xml)

    signals = RssNewsProvider().fetch_signals(
        MacroQuery(
            "美联储降息影响",
            limit=2,
            metadata={"rss_feeds": [{"id": "fed", "title": "Fed", "url": "https://example.com/rss.xml"}]},
        )
    )

    assert len(signals) == 1
    assert signals[0].source == "rss_news"
    assert signals[0].signal_type == "rss_news_item"
    assert signals[0].value == "Fed cuts rates"
    assert signals[0].metadata["feed_id"] == "fed"




def test_v101_us_treasury_retries_nominal_curve_before_degrading(monkeypatch):
    from kronos_fincept.macro.providers import digital_oracle as providers

    attempts = {"nominal": 0, "real": 0}

    def fake_latest_curve_row(year, curve_kind, *, timeout=8):
        attempts[curve_kind] += 1
        if curve_kind == "nominal" and attempts[curve_kind] == 1:
            raise TimeoutError("temporary nominal timeout")
        if curve_kind == "nominal":
            return {"Date": "05/15/2026", "2 Yr": "4.09", "10 Yr": "4.59"}
        return {"Date": "05/15/2026", "10 YR": "2.10"}

    monkeypatch.setattr(providers, "_latest_curve_row", fake_latest_curve_row)
    monkeypatch.setattr(providers.USTreasuryProvider, "_fetch_exchange_rate_rows", lambda self, query: [])

    signals = providers.USTreasuryProvider().fetch_signals(providers.MacroQuery("黄金该不该买"))
    by_type = {signal.signal_type: signal for signal in signals}

    assert attempts["nominal"] == 2
    assert by_type["yield_curve_10y_2y_spread"].metadata["10y"] == 4.59
    assert by_type["real_yield_10y"].value == 2.1
    assert by_type["breakeven_10y"].value == 2.49
    assert by_type["real_yield_10y"].metadata["degraded_errors"] == {}


def test_v101_us_treasury_real_yield_signal_uses_tips_label(monkeypatch):
    from kronos_fincept.macro.providers import digital_oracle as providers

    def fake_latest_curve_row(year, curve_kind, *, timeout=8):
        if curve_kind == "nominal":
            raise TimeoutError("nominal unavailable")
        return {"Date": "05/15/2026", "10 YR": "2.10"}

    monkeypatch.setattr(providers, "_latest_curve_row", fake_latest_curve_row)
    monkeypatch.setattr(providers.USTreasuryProvider, "_fetch_exchange_rate_rows", lambda self, query: [])

    signals = providers.USTreasuryProvider().fetch_signals(providers.MacroQuery("黄金该不该买"))

    assert [signal.signal_type for signal in signals] == ["real_yield_10y"]
    assert "TIPS" in signals[0].interpretation
    assert signals[0].metadata["degraded_errors"]["nominal"]


def test_v101_get_text_falls_back_to_urllib_when_requests_times_out(monkeypatch):
    from kronos_fincept.macro.providers import digital_oracle as providers

    class TimedOutRequests:
        @staticmethod
        def get(*args, **kwargs):
            raise TimeoutError("requests read timed out")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"Date,10 Yr\n05/19/2026,4.59\n"

    captured = {}

    def fake_urlopen(request, timeout=8):
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        return FakeResponse()

    monkeypatch.setitem(__import__("sys").modules, "requests", TimedOutRequests)
    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)

    text = providers._get_text("https://example.com/data.csv", timeout=7)

    assert "05/19/2026" in text
    assert captured["timeout"] == 7
    assert captured["headers"]["Connection"] == "close"


def test_v101_us_treasury_fetches_curves_sequentially_without_shared_timeout_border(monkeypatch):
    from kronos_fincept.macro.providers import digital_oracle as providers

    calls = []

    def fake_latest_curve_row_with_retry(year, curve_kind, *, timeout=8):
        calls.append((curve_kind, timeout))
        if curve_kind == "nominal":
            return {"Date": "05/19/2026", "2 Yr": "4.09", "10 Yr": "4.59"}
        return {"Date": "05/19/2026", "10 YR": "2.10"}

    monkeypatch.setattr(providers, "_latest_curve_row_with_retry", fake_latest_curve_row_with_retry)

    nominal, real, errors = providers.USTreasuryProvider()._fetch_curve_rows(2026, timeout_seconds=30.0)

    assert nominal["10 Yr"] == "4.59"
    assert real["10 YR"] == "2.10"
    assert errors == {}
    assert calls == [("nominal", 30.0), ("real", 30.0)]
