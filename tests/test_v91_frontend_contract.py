from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v91_frontend_domain_modules_exist_and_own_defaults():
    markets = read("web/src/lib/markets.ts")
    symbols = read("web/src/lib/symbols.ts")
    defaults = read("web/src/lib/defaults.ts")

    assert 'export type Market = "cn" | "us" | "hk" | "commodity"' in markets
    assert "MARKET_OPTIONS" in markets
    assert "normalizeMarket" in markets
    assert "toBackendMarket" in markets

    assert 'DEFAULT_SYMBOL = "600036"' in symbols
    assert "normalizeSymbol" in symbols
    assert "normalizeSymbols" in symbols
    assert "detectSymbolKind" in symbols
    assert "inferMarketFromSymbol" in symbols

    assert "from \"@/lib/markets\"" in defaults
    assert "from \"@/lib/symbols\"" in defaults


def test_v91_api_types_are_not_owned_by_api_client():
    api_types = read("web/src/types/api.ts")
    api_client = read("web/src/lib/api.ts")

    for name in [
        "ForecastRequest",
        "ForecastResponse",
        "DataResponse",
        "BacktestResponse",
        "AgentAnalyzeResponse",
        "HealthResponse",
    ]:
        assert f"interface {name}" in api_types

    assert "from \"@/types/api\"" in api_client
    assert "interface ForecastResponse" not in api_client
    assert "interface AgentAnalyzeResponse" not in api_client


def test_v91_api_client_has_request_layer_timeout_abort_and_request_id():
    api_client = read("web/src/lib/api.ts")

    assert "DEFAULT_TIMEOUT_MS" in api_client
    assert "AbortController" in api_client
    assert "timeoutMs" in api_client
    assert "ApiClientOptions" in api_client
    assert "function get<T>" in api_client
    assert "function post<T>" in api_client
    assert 'res.headers.get("X-Request-ID")' in api_client
    assert "err.request_id" in api_client


def test_v91_core_pages_use_shared_market_symbol_and_api_types():
    pages = {
        "forecast": read("web/src/app/forecast/page.tsx"),
        "analysis": read("web/src/app/analysis/page.tsx"),
        "batch": read("web/src/app/batch/page.tsx"),
        "backtest": read("web/src/app/backtest/page.tsx"),
        "data": read("web/src/app/data/page.tsx"),
    }

    assert "from \"@/lib/defaults\"" not in "\n".join(pages.values())
    assert "from \"@/types/api\"" in pages["forecast"]
    assert "from \"@/types/api\"" in pages["analysis"]
    assert "from \"@/types/api\"" in pages["batch"]
    assert "from \"@/types/api\"" in pages["backtest"]
    assert "from \"@/types/api\"" in pages["data"]

    assert "normalizeSymbol(symbol)" in pages["forecast"]
    assert "normalizeSymbols(input)" in pages["batch"]
    assert "normalizeSymbols(symbols)" in pages["backtest"]
    assert "normalizeSymbol(symbol)" in pages["data"]


def test_v91_react_list_keys_no_longer_use_array_index_for_changed_paths():
    analysis = read("web/src/app/analysis/page.tsx")
    batch = read("web/src/app/batch/page.tsx")

    assert "key={`${call.name}-${index}`}" not in analysis
    assert "key={`cell-${index}`}" not in batch
    assert "ReturnComparisonChart" in batch
    assert 'from "recharts"' not in batch
