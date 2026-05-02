from pathlib import Path
from types import SimpleNamespace

from kronos_fincept.schemas import ForecastRequest, ForecastRow


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_zeabur_production_disables_dry_run_and_installs_real_kronos_runtime():
    dockerfile = read("Dockerfile")

    assert "KRONOS_MODEL_ID=NeoQuasar/Kronos-base" in dockerfile
    assert "KRONOS_ENABLE_REAL_MODEL=1" in dockerfile
    assert "KRONOS_ALLOW_DRY_RUN=0" in dockerfile
    assert "ARG INSTALL_KRONOS_RUNTIME=1" in dockerfile
    assert 'pip install --no-cache-dir -e ".[kronos]"' in dockerfile


def test_web_forecast_and_backtest_do_not_request_dry_run():
    forecast_page = read("web/src/app/forecast/page.tsx")
    backtest_page = read("web/src/app/backtest/page.tsx")

    assert "dry_run: true" not in forecast_page
    assert "dryRun: true" not in forecast_page
    assert "dry_run: false" in forecast_page
    assert "dryRun: false" in forecast_page
    assert "dry_run: true" not in backtest_page
    assert "dry_run: false" in backtest_page


def test_service_rejects_dry_run_when_environment_disallows_it(monkeypatch):
    from kronos_fincept import service

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(
            kronos=SimpleNamespace(
                allow_dry_run=False,
                enable_real_model=True,
                model_id="NeoQuasar/Kronos-small",
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "DryRunPredictor",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dry-run predictor should not load")),
    )

    req = ForecastRequest(
        symbol="600036",
        timeframe="1d",
        pred_len=2,
        rows=[
            ForecastRow("2026-01-01", 10, 11, 9, 10),
            ForecastRow("2026-01-02", 10, 12, 9, 11),
        ],
        dry_run=True,
    )

    result = service.forecast_from_request(req)

    assert result["ok"] is False
    assert "Dry-run/mock predictor is disabled" in result["error"]
