"""v10.9 Web/API/CLI page-completion contract tests.

These tests encode docs/spec_web_page_completion.md so every UI feature added for the
web app has a matching API/CLI surface where possible.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v109_spec_file_is_present_and_covers_all_requested_pages() -> None:
    spec_path = ROOT / "docs/spec_web_page_completion.md"
    if spec_path.exists():
        spec = spec_path.read_text(encoding="utf-8")
        markers = [
            "回测页增强",
            "数据页增强",
            "自选股增强",
            "批量对比增强",
            "仪表盘增强",
            "设置/诊断页",
            "新增告警/监控入口",
            "Web、API、CLI",
        ]
    else:
        # docs/spec*.md is intentionally ignored in this repository.
        spec = read("SPEC.md")
        markers = ["回测", "数据", "自选股", "批量", "告警", "Web", "API", "CLI"]
    for marker in markers:
        assert marker in spec


def test_v109_backtest_web_api_cli_share_report_and_parameter_contracts() -> None:
    page = read("web/src/app/backtest/page.tsx")
    api = read("web/src/lib/api.ts")
    types = read("web/src/types/api.ts")
    models = read("src/kronos_fincept/api/models.py")
    route = read("src/kronos_fincept/api/routes/backtest.py")
    cli = read("src/kronos_fincept/cli/commands/backtest.py")

    for token in ["predLen", "windowSize", "step", "initialEquity", "benchmark", "feeBps", "slippageBps"]:
        assert token in page
    assert "api.backtestReport" in page
    assert "downloadBacktestCsv" in page
    assert "date,equity,return,selected" in page
    assert "持仓明细" in page
    assert "BacktestReportResponse" in types
    assert "backtestReport" in api
    assert "initial_equity" in models
    assert "req.initial_equity" in route
    for token in ["--initial-equity", "--benchmark", "--fee-bps", "--slippage-bps"]:
        assert token in cli


def test_v109_data_page_supports_multi_market_indicators_actions_and_export() -> None:
    page = read("web/src/app/data/page.tsx")
    api = read("web/src/lib/api.ts")
    cli = read("src/kronos_fincept/cli/commands/data.py")

    for token in [
        "MARKET_OPTIONS",
        "adjust",
        "rangePreset",
        "api.getGlobalData",
        "api.getIndicators",
        "PriceLineChart",
        "downloadDataCsv",
        "数据摘要",
        "技术指标",
        "/forecast?symbol=",
        "/analysis?symbol=",
        "addToWatchlist",
    ]:
        assert token in page
    assert "api.getData(requestSymbol, startDate, endDate, adjust" in page
    assert "adjust=" in api
    for token in ["--market", "--csv", "indicator", "GlobalMarketSource"]:
        assert token in cli


def test_v109_watchlist_is_research_workbench_with_metadata_batch_actions_and_import_export() -> None:
    page = read("web/src/app/watchlist/page.tsx")
    store = read("web/src/stores/app.ts")

    for token in ["name?", "note?", "tags?", "replaceWatchlist", "updateWatchlistItem"]:
        assert token in store
    for token in [
        "quoteSummaries",
        "api.getIndicators",
        "api.getGlobalData",
        "selectedSymbols",
        "handleExportWatchlist",
        "handleImportWatchlist",
        "/batch?symbols=",
        "/backtest?symbols=",
        "批量预测",
        "批量分析",
        "最新价",
        "RSI",
        "MACD",
    ]:
        assert token in page


def test_v109_batch_page_supports_pools_sorting_export_actions_and_retry_failed() -> None:
    page = read("web/src/app/batch/page.tsx")
    cli = read("src/kronos_fincept/cli/commands/batch.py")

    for token in [
        "useSearchParams",
        "poolPreset",
        "自选股",
        "常用A股组合",
        "downloadBatchCsv",
        "sortKey",
        "retryFailed",
        "addToWatchlist",
        "风险",
        "/analysis?symbol=",
        "/forecast?symbol=",
        "/backtest?symbols=",
    ]:
        assert token in page
    for token in ["--market", "--csv", "risk_label", "failures"]:
        assert token in cli


def test_v109_dashboard_settings_alerts_are_reachable_and_safe() -> None:
    dashboard = read("web/src/app/page.tsx")
    settings = read("web/src/app/settings/page.tsx")
    alerts = read("web/src/app/alerts/page.tsx")
    sidebar = read("web/src/components/layout/Sidebar.tsx")
    api = read("web/src/lib/api.ts")
    alert_route = read("src/kronos_fincept/api/routes/alert.py")

    for href in ["/forecast", "/analysis", "/macro", "/watchlist", "/batch", "/backtest", "/data", "/settings", "/alerts"]:
        assert href in dashboard
        assert href in sidebar
    assert "recentResults" in dashboard
    assert "watchlistQuotes" in dashboard
    assert "api.health" in settings
    assert "clearLocalCaches" in settings
    assert "exportLocalState" in settings
    assert "redirect" not in settings
    for token in ["alertList", "alertCreate", "alertDelete", "alertCheck"]:
        assert token in api
        assert token in alerts
    assert "showSensitiveFields" in alerts
    assert "maskContactValue" in alerts
    assert "_mask_contact_value" in alert_route


def test_v109_alert_contact_masking_helper_never_returns_full_secret() -> None:
    from kronos_fincept.api.routes.alert import _mask_contact_value

    assert _mask_contact_value(None) is None
    assert _mask_contact_value("short") == "[REDACTED]"
    masked = _mask_contact_value("https://open.feishu.cn/open-apis/bot/v2/hook/abcdef123456")
    assert masked.startswith("https")
    assert masked.endswith("3456")
    assert "abcdef12" not in masked
