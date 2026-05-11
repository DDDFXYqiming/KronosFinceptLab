from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v90_react_query_provider_is_global():
    package_json = read("web/package.json")
    layout = read("web/src/app/layout.tsx")
    provider = read("web/src/components/providers/AppProviders.tsx")

    assert '"@tanstack/react-query"' in package_json
    assert "AppProviders" in layout
    assert "QueryClientProvider" in provider
    assert "staleTime" in provider
    assert "gcTime" in provider
    assert "refetchOnWindowFocus: false" in provider


def test_v90_query_keys_cover_core_web_requests():
    query_keys = read("web/src/lib/queryKeys.ts")
    symbols = read("web/src/lib/symbols.ts")

    for key in [
        "health",
        "search",
        "data",
        "forecast",
        "batch",
        "backtest",
        "agent",
    ]:
        assert f"{key}:" in query_keys

    assert "normalizeSymbols" in query_keys
    assert "normalizeSymbol" in query_keys
    assert "trim().toUpperCase()" in symbols


def test_v90_api_errors_include_request_id_and_path():
    api_client = read("web/src/lib/api.ts")

    assert "class ApiError" in api_client
    assert "requestId" in api_client
    assert "path: string" in api_client
    assert "formatApiError" in api_client
    assert 'res.headers.get("X-Request-ID")' in api_client
    assert "err.request_id" in api_client


def test_v90_pages_use_query_cache_and_manual_refresh():
    pages = {
        "forecast": read("web/src/app/forecast/page.tsx"),
        "analysis": read("web/src/app/analysis/page.tsx"),
        "batch": read("web/src/app/batch/page.tsx"),
        "backtest": read("web/src/app/backtest/page.tsx"),
        "data": read("web/src/app/data/page.tsx"),
    }

    for name, text in pages.items():
        assert "useQueryClient" in text, name
        assert "queryClient.getQueryData" in text, name
        assert "queryClient.fetchQuery" in text, name
        assert "queryKeys." in text, name
        assert "formatApiError" in text, name

    assert "刷新数据" in pages["forecast"]
    assert "重新预测" in pages["forecast"]
    assert "重新分析" in pages["analysis"]
    assert "刷新对比" in pages["batch"]
    assert "刷新回测" in pages["backtest"]
    assert "刷新数据" in pages["data"]


def test_v90_route_switch_state_still_uses_session_storage():
    pages = [
        "web/src/app/forecast/page.tsx",
        "web/src/app/analysis/page.tsx",
        "web/src/app/batch/page.tsx",
        "web/src/app/backtest/page.tsx",
        "web/src/app/data/page.tsx",
        "web/src/app/watchlist/page.tsx",
    ]

    for path in pages:
        text = read(path)
        assert "useSessionState" in text, path

    assert "kronos-watchlist-symbol" in read("web/src/app/watchlist/page.tsx")
    assert "kronos-watchlist-market" in read("web/src/app/watchlist/page.tsx")


def test_v90_long_running_analysis_and_macro_runs_survive_route_switch():
    pages = {
        "analysis": read("web/src/app/analysis/page.tsx"),
        "macro": read("web/src/app/macro/page.tsx"),
    }

    for name, text in pages.items():
        assert "useIsFetching" in text, name
        assert "ActiveAnalysisRun" in text or "ActiveMacroRun" in text, name
        assert f"kronos-{name}-active-run" in text, name
        assert "queryClient.getQueryState" in text, name
        assert "resumeActiveRun" in text, name
        assert "activeRunFetching" in text, name
        assert "displayLoading" in text, name
        assert "Boolean(activeRun && !error)" in text, name
        assert "if (!activeRun) return" in text, name
        assert "if (!activeRun || result) return" not in text, name
        assert "setActiveRun(null)" in text, name


def test_v90_next_data_route_is_not_ignored_as_local_data():
    gitignore = read(".gitignore")

    assert "/data/" in gitignore
    assert "\ndata/\n" not in gitignore
    assert (ROOT / "web/src/app/data/page.tsx").exists()


def test_v90_version_markers_are_updated():
    readme = read("README.md")
    sidebar = read("web/src/components/layout/Sidebar.tsx")

    assert "Version: v10." in readme
    assert "v10." in sidebar
