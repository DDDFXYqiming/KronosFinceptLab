from pathlib import Path

from kronos_fincept.api.models import ForecastRequestIn
from kronos_fincept.config import KronosConfig
from kronos_fincept.schemas import DEFAULT_MODEL_ID, DEFAULT_TOKENIZER_ID, ForecastRequest

ROOT = Path(__file__).resolve().parents[1]


def test_default_model_and_tokenizer_are_kronos_base(monkeypatch):
    monkeypatch.delenv("KRONOS_MODEL_ID", raising=False)

    assert DEFAULT_MODEL_ID == "NeoQuasar/Kronos-base"
    assert DEFAULT_TOKENIZER_ID == "NeoQuasar/Kronos-Tokenizer-base"
    assert KronosConfig().model_id == DEFAULT_MODEL_ID
    assert ForecastRequestIn.model_fields["model_id"].default == DEFAULT_MODEL_ID
    assert ForecastRequestIn.model_fields["tokenizer_id"].default == DEFAULT_TOKENIZER_ID

    request = ForecastRequest.from_dict(
        {
            "symbol": "600036",
            "pred_len": 1,
            "rows": [
                {"timestamp": "2026-04-29", "open": 1, "high": 2, "low": 1, "close": 2}
            ],
        }
    )
    assert request.model_id == DEFAULT_MODEL_ID
    assert request.tokenizer_id == DEFAULT_TOKENIZER_ID


def test_web_settings_removed_and_defaults_are_shared():
    defaults = (ROOT / "web/src/lib/defaults.ts").read_text(encoding="utf-8")
    sidebar = (ROOT / "web/src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "web/src/app/settings/page.tsx").read_text(encoding="utf-8")

    assert 'DEFAULT_SYMBOL = "600036"' in defaults
    assert 'DEFAULT_SYMBOL_NAME = "招商银行"' in defaults
    assert 'DEFAULT_MODEL_ID = "NeoQuasar/Kronos-base"' in defaults
    assert 'DEFAULT_TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"' in defaults
    assert 'href: "/settings"' not in sidebar
    assert 'label: "设置"' not in sidebar
    assert 'redirect("/")' in settings
    assert "NeoQuasar/Kronos-small" not in settings


def test_web_pages_preserve_route_switch_state():
    for rel in [
        "web/src/app/forecast/page.tsx",
        "web/src/app/analysis/page.tsx",
        "web/src/app/batch/page.tsx",
        "web/src/app/backtest/page.tsx",
        "web/src/app/data/page.tsx",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "useSessionState" in text, rel

    forecast = (ROOT / "web/src/app/forecast/page.tsx").read_text(encoding="utf-8")
    analysis = (ROOT / "web/src/app/analysis/page.tsx").read_text(encoding="utf-8")
    batch = (ROOT / "web/src/app/batch/page.tsx").read_text(encoding="utf-8")
    backtest = (ROOT / "web/src/app/backtest/page.tsx").read_text(encoding="utf-8")
    data = (ROOT / "web/src/app/data/page.tsx").read_text(encoding="utf-8")

    assert "kronos-forecast-result" in forecast
    assert "kronos-analysis-result" in analysis
    assert "kronos-batch-results" in batch
    assert "kronos-backtest-result" in backtest
    assert "kronos-data-result" in data
