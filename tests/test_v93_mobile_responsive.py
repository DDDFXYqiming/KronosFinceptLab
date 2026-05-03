from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v93_layout_uses_mobile_shell_without_desktop_sidebar_flow():
    layout = read("web/src/app/layout.tsx")
    shell = read("web/src/components/layout/AppShell.tsx")
    sidebar = read("web/src/components/layout/Sidebar.tsx")
    header = read("web/src/components/layout/Header.tsx")

    assert "AppShell" in layout
    assert "overflow-x-hidden" in layout
    assert "md:ml-60" in shell
    assert "md:ml-16" in shell
    assert "min-w-0" in shell
    assert "hidden h-screen" in sidebar
    assert "md:block" in sidebar
    assert "mobileMenuOpen" in header
    assert "role=\"dialog\"" in header
    assert "mobile-safe-top" in header
    assert "mobile-safe-bottom" in header


def test_v93_core_pages_use_mobile_safe_primitives():
    pages = [
        "web/src/app/page.tsx",
        "web/src/app/forecast/page.tsx",
        "web/src/app/analysis/page.tsx",
        "web/src/app/watchlist/page.tsx",
        "web/src/app/batch/page.tsx",
        "web/src/app/backtest/page.tsx",
        "web/src/app/data/page.tsx",
    ]

    for path in pages:
        source = read(path)
        assert "page-shell" in source, path
        assert "page-title" in source, path
        assert "text-3xl font-display" not in source, path


def test_v93_tables_charts_and_inputs_have_mobile_bounds():
    forecast = read("web/src/app/forecast/page.tsx")
    analysis = read("web/src/app/analysis/page.tsx")
    batch = read("web/src/app/batch/page.tsx")
    backtest = read("web/src/app/backtest/page.tsx")
    data = read("web/src/app/data/page.tsx")
    globals_css = read("web/src/app/globals.css")
    return_chart = read("web/src/components/charts/ReturnComparisonChart.tsx")
    equity_chart = read("web/src/components/charts/BacktestEquityChart.tsx")

    assert "app-input" in globals_css
    assert "min-height: 44px" in globals_css
    assert "table-scroll" in globals_css
    assert "chart-frame" in globals_css
    assert "formatDuration" in read("web/src/lib/utils.ts")

    assert "chart-frame h-[360px] md:h-[500px]" in forecast
    assert "window.innerWidth < 768 ? 360 : 500" in forecast
    assert "min-w-[42rem]" in forecast
    assert "Agent 执行时间线" in analysis
    assert "table-scroll" in analysis
    assert "ReturnComparisonChart" in batch
    assert "chart-frame h-72" in return_chart
    assert "min-w-[44rem]" in batch
    assert "BacktestEquityChart" in backtest
    assert "chart-frame h-72 md:h-80" in equity_chart
    assert "table-scroll" in data


def test_v93_version_label_is_updated():
    assert "Version: v9.5" in read("README.md")
    assert "v9.5" in read("web/src/components/layout/Sidebar.tsx")
    assert "v9.5" in read("web/src/components/layout/Header.tsx")
