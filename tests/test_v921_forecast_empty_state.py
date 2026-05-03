from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v921_forecast_formats_no_data_errors_with_actionable_hint():
    page = read("web/src/app/forecast/page.tsx")

    assert "formatForecastDataError" in page
    assert "error instanceof ApiError && error.status === 404" in page
    assert "未找到" in page
    assert "请确认代码、市场和日期范围" in page
    assert "DEFAULT_SYMBOL_NAME" in page
    assert "DEFAULT_SYMBOL" in page
    assert "request_id=" in page


def test_v921_forecast_hides_blank_chart_when_rows_are_empty():
    page = read("web/src/app/forecast/page.tsx")

    assert "ForecastEmptyState" in page
    assert "未加载行情" in page
    assert "当前没有可显示的 K 线数据" in page
    assert "hasChartData ? (" in page
    assert "{symbol} — {data.length} 根K线" in page


def test_v921_forecast_clears_prediction_and_chart_state_on_empty_data():
    page = read("web/src/app/forecast/page.tsx")

    assert "clearForecastState" in page
    assert "setPrediction(null)" in page
    assert "setPredResult(null)" in page
    assert "candlestickSeriesRef.current.setData([])" in page
    assert "lineSeriesRef.current?.setData([])" in page
    assert "[hasChartData]" in page


def test_v921_version_labels_are_updated():
    assert "Version: v9.5" in read("README.md")
    assert "v9.5" in read("web/src/components/layout/Sidebar.tsx")
