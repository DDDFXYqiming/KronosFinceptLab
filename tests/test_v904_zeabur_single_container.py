from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re

import pandas as pd

from kronos_fincept.schemas import ForecastRequest, ForecastRow


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"open": 10.0, "high": 11.0, "low": 9.5, "close": 10.4, "volume": 1000.0, "amount": 10000.0},
            {"open": 10.4, "high": 11.2, "low": 10.0, "close": 10.8, "volume": 1000.0, "amount": 10000.0},
            {"open": 10.8, "high": 11.5, "low": 10.2, "close": 11.1, "volume": 1000.0, "amount": 10000.0},
        ],
        index=pd.date_range("2026-01-01", periods=3, freq="D"),
    )


def _request() -> ForecastRequest:
    return ForecastRequest(
        symbol="600036",
        timeframe="1d",
        pred_len=2,
        rows=[
            ForecastRow("2026-01-01", 10.0, 11.0, 9.0, 10.0),
            ForecastRow("2026-01-02", 10.0, 11.0, 9.0, 10.2),
            ForecastRow("2026-01-03", 10.0, 11.0, 9.0, 10.4),
        ],
        dry_run=False,
        sample_count=1,
    )


class FakePredictor:
    def __init__(self, delay: float = 0.0, active: dict[str, int] | None = None) -> None:
        self.delay = delay
        self.active = active

    def predict(self, **kwargs):
        if self.active is not None:
            self.active["current"] += 1
            self.active["max"] = max(self.active["max"], self.active["current"])
        try:
            if self.delay:
                time.sleep(self.delay)
            return pd.DataFrame(
                [
                    {"timestamp": "D1", "open": 10.5, "high": 11.0, "low": 10.0, "close": 10.7},
                    {"timestamp": "D2", "open": 10.7, "high": 11.2, "low": 10.2, "close": 10.9},
                ]
            )
        finally:
            if self.active is not None:
                self.active["current"] -= 1


def test_kronos_predictor_cache_reuses_loaded_model_across_wrappers(monkeypatch):
    from kronos_fincept import predictor

    predictor.clear_predictor_cache()
    load_count = {"value": 0}

    def fake_load_uncached(self):
        load_count["value"] += 1
        return FakePredictor(), "cpu"

    monkeypatch.setattr(predictor.KronosPredictorWrapper, "_load_uncached", fake_load_uncached)

    first = predictor.KronosPredictorWrapper(model_id="NeoQuasar/Kronos-small")
    second = predictor.KronosPredictorWrapper(model_id="NeoQuasar/Kronos-small")
    timestamps = pd.Series(pd.date_range("2026-01-01", periods=3, freq="D"))

    first_result = first.predict(df=_frame(), x_timestamp=timestamps, pred_len=2)
    second_result = second.predict(df=_frame(), x_timestamp=timestamps, pred_len=2)

    assert load_count["value"] == 1
    assert first_result.model_cached is False
    assert second_result.model_cached is True
    assert first_result.cache_key == second_result.cache_key
    assert predictor.predictor_cache_stats()["size"] == 1


def test_kronos_predictor_cache_serializes_concurrent_loads(monkeypatch):
    from kronos_fincept import predictor

    predictor.clear_predictor_cache()
    load_count = {"value": 0}

    def fake_load_uncached(self):
        time.sleep(0.05)
        load_count["value"] += 1
        return FakePredictor(), "cpu"

    monkeypatch.setattr(predictor.KronosPredictorWrapper, "_load_uncached", fake_load_uncached)

    def load_once():
        return predictor.KronosPredictorWrapper(model_id="NeoQuasar/Kronos-small")._load()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: load_once(), range(4)))

    assert load_count["value"] == 1
    assert predictor.predictor_cache_stats()["size"] == 1


def test_real_inference_calls_are_serialized(monkeypatch):
    from kronos_fincept import predictor

    predictor.clear_predictor_cache()
    active = {"current": 0, "max": 0}

    def fake_load_uncached(self):
        return FakePredictor(delay=0.05, active=active), "cpu"

    monkeypatch.setattr(predictor.KronosPredictorWrapper, "_load_uncached", fake_load_uncached)
    timestamps = pd.Series(pd.date_range("2026-01-01", periods=3, freq="D"))

    def run_prediction():
        wrapper = predictor.KronosPredictorWrapper(model_id="NeoQuasar/Kronos-small")
        return wrapper.predict(df=_frame(), x_timestamp=timestamps, pred_len=2)

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: run_prediction(), range(3)))

    assert active["max"] == 1
    assert all(result.inference_wait_ms >= 0 for result in results)
    assert any(result.model_cached for result in results)


def test_service_metadata_exposes_cache_and_lock_diagnostics(monkeypatch):
    from kronos_fincept import service
    from kronos_fincept.predictor import ForecastResult

    class FakeWrapper:
        def __init__(self, **kwargs):
            pass

        def predict(self, df, x_timestamp, pred_len):
            return ForecastResult(
                frame=pd.DataFrame(
                    [{"timestamp": "D1", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5}]
                ),
                device="cpu",
                elapsed_ms=12,
                backend="kronos",
                model_cached=True,
                cache_key="NeoQuasar/Kronos-small|tokenizer|512|auto",
                load_wait_ms=3,
                inference_wait_ms=4,
            )

    monkeypatch.setattr(service, "KronosPredictorWrapper", FakeWrapper)

    result = service.forecast_from_request(_request())

    assert result["ok"] is True
    assert result["metadata"]["model_cached"] is True
    assert result["metadata"]["cache_key"]
    assert result["metadata"]["load_wait_ms"] == 3
    assert result["metadata"]["inference_wait_ms"] == 4


def test_agent_kronos_failure_keeps_clear_error_without_mock(monkeypatch):
    from kronos_fincept import agent

    rows = [
        {
            "timestamp": f"2026-01-{(i % 28) + 1:02d}",
            "open": 30.0 + i * 0.1,
            "high": 30.2 + i * 0.1,
            "low": 29.8 + i * 0.1,
            "close": 30.1 + i * 0.1,
            "volume": 1000000 + i,
            "amount": 30000000 + i,
        }
        for i in range(40)
    ]

    monkeypatch.setattr(agent, "_fetch_price_data", lambda symbol, market: rows)
    monkeypatch.setattr(agent, "_fetch_financial_summary", lambda symbol, market: {"symbol": symbol})
    monkeypatch.setattr(agent, "_build_technical_indicators", lambda input_rows: {"rsi": {"current": 52.0}})
    monkeypatch.setattr(
        agent,
        "_build_risk_metrics",
        lambda symbol, input_rows: {"var_95": -0.02, "sharpe_ratio": 1.1, "max_drawdown": -0.08, "volatility": 0.2},
    )
    monkeypatch.setattr(
        agent,
        "_call_deepseek_router",
        lambda question, explicit_symbol=None, explicit_market=None: agent._local_route_decision(
            question,
            explicit_symbol=explicit_symbol,
            explicit_market=explicit_market,
        ),
    )
    monkeypatch.setattr(agent, "_call_deepseek_report", lambda question, context: None)
    monkeypatch.setattr(
        agent,
        "_build_prediction",
        lambda symbol, rows, dry_run: (_ for _ in ()).throw(RuntimeError("model load failed")),
    )
    monkeypatch.setattr(
        agent,
        "_create_web_search_client",
        lambda: type("DisabledSearchClient", (), {"provider": "", "is_configured": False})(),
    )

    result = agent.analyze_investment_question("帮我看看招商银行现在能不能买")
    prediction_call = next(call for call in result.tool_calls if call.name == "kronos_prediction")

    assert result.kronos_prediction is None
    assert prediction_call.status == "failed"
    assert "model load failed" in prediction_call.summary
    assert "真实 Kronos 未返回预测" in result.report["short_term_prediction"]


def test_web_api_client_adds_zeabur_gateway_diagnostics():
    api_client = read("web/src/lib/api.ts")

    assert "502, 503, 504" in api_client
    assert "Zeabur 网关" in api_client
    assert "容器重启" in api_client
    assert "推理超时" in api_client
    assert "内存压力" in api_client


def test_legacy_ai_analyze_no_longer_uses_high_sample_count():
    legacy_route = read("src/kronos_fincept/api/routes/ai_analyze.py")

    assert "sample_count=100" not in legacy_route
    assert "sample_count=1" in legacy_route


def test_v904_version_labels_are_updated():
    assert re.search(r"Version: v10\.2", read("README.md"))
    assert re.search(r"v10\.2.*— 仅供研究", read("web/src/components/layout/Sidebar.tsx"))
