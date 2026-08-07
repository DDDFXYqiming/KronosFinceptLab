from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _rows(count: int) -> list[dict[str, float | str]]:
    return [
        {
            "timestamp": f"2026-01-{index + 1:03d}",
            "open": 10.0 + index,
            "high": 11.0 + index,
            "low": 9.0 + index,
            "close": 10.5 + index,
            "volume": 1000.0 + index,
            "amount": 10000.0 + index,
        }
        for index in range(count)
    ]


def test_agent_kronos_request_uses_last_90_rows():
    from kronos_fincept.config import settings
    from kronos_fincept.agent import _forecast_request_for_rows

    request = _forecast_request_for_rows("300308", _rows(240), dry_run=True)

    assert len(request.rows) == 90
    assert request.pred_len == settings.runtime.pred_len
    assert request.temperature == settings.runtime.temperature
    assert request.rows[0].timestamp == "2026-01-151"
    assert request.rows[-1].timestamp == "2026-01-240"


def test_forecast_page_reads_lookback_from_runtime_config():
    source = (ROOT / "web/src/app/forecast/page.tsx").read_text(encoding="utf-8")

    assert "const KRONOS_RUNTIME_LOOKBACK = 90;" not in source
    assert "api.forecastConfig" in source
    assert "const forecastRows = data.slice(-runtimeLookback);" in source
    assert "rows: forecastRows" in source
