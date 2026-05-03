from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v94_shared_chart_data_adapter_exists():
    adapter = read("web/src/lib/chartData.ts")

    assert "toCandlestickSeriesData" in adapter
    assert "toForecastLineData" in adapter
    assert "toEquityAreaData" in adapter
    assert "toReturnBarData" in adapter
    assert "sampleChartRows" in adapter
    assert "maxPoints" in adapter
    assert "normalizeDate" in adapter


def test_v94_backtest_uses_lightweight_equity_chart():
    backtest = read("web/src/app/backtest/page.tsx")
    chart = read("web/src/components/charts/BacktestEquityChart.tsx")

    assert "BacktestEquityChart" in backtest
    assert "items-end gap-1" not in backtest
    assert "createChart" in chart
    assert "addAreaSeries" in chart
    assert "ResizeObserver" in chart
    assert "toEquityAreaData" in chart


def test_v94_forecast_uses_adapter_and_visual_prediction_boundary():
    forecast = read("web/src/app/forecast/page.tsx")

    assert "toCandlestickSeriesData" in forecast
    assert "toForecastLineData" in forecast
    assert "setMarkers" in forecast
    assert "Kronos 预测路径" in forecast
    assert "预测区间" in forecast


def test_v94_batch_removes_recharts_runtime_dependency():
    batch = read("web/src/app/batch/page.tsx")
    chart = read("web/src/components/charts/ReturnComparisonChart.tsx")

    assert 'from "recharts"' not in batch
    assert "ResponsiveContainer" not in batch
    assert "ReturnComparisonChart" in batch
    assert "<svg" in chart
    assert "toReturnBarData" in chart


def test_v94_version_labels_are_current():
    assert "Version: v9.7" in read("README.md")
    assert "v9.7" in read("web/src/components/layout/Sidebar.tsx")
    assert "v9.7" in read("web/src/components/layout/Header.tsx")
