from __future__ import annotations


def test_forecast_batch_responses_uses_one_predict_batch_call(monkeypatch):
    import pandas as pd
    from types import SimpleNamespace

    from kronos_fincept import service
    from kronos_fincept.predictor import ForecastResult
    from kronos_fincept.schemas import ForecastRequest, ForecastRow

    calls = []

    class FakeWrapper:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def predict_batch(self, dfs, timestamps, pred_len):
            calls.append(("batch", len(dfs), pred_len))
            return [
                ForecastResult(
                    frame=pd.DataFrame(
                        [{"timestamp": "D1", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5}]
                    ),
                    device="dml",
                    elapsed_ms=25,
                    backend="kronos",
                )
                for _ in dfs
            ]

    rows = [
        ForecastRow(
            timestamp=f"2026-01-{index + 1:02d}",
            open=10 + index,
            high=11 + index,
            low=9 + index,
            close=10.5 + index,
            volume=1000,
        )
        for index in range(5)
    ]
    requests = [
        ForecastRequest(symbol=symbol, timeframe="1d", rows=rows, pred_len=1, sample_count=8)
        for symbol in ("600036", "600519")
    ]
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(
            kronos=SimpleNamespace(
                enable_real_model=True,
                allow_dry_run=False,
                model_id="NeoQuasar/Kronos-small",
                device="dml",
            )
        ),
    )
    monkeypatch.setattr(service, "KronosPredictorWrapper", FakeWrapper)

    responses = service.forecast_batch_responses(requests)

    assert [call[0] for call in calls].count("batch") == 1
    assert calls[0][1]["device"] == "dml"
    assert len(responses) == 2
    assert all(response["metadata"]["device"] == "dml" for response in responses)
    assert all(response["metadata"]["batch_size"] == 2 for response in responses)
    assert all(response["metadata"]["sample_count"] == 8 for response in responses)


def test_macro_manager_is_reused_and_complete_timeout_is_longer_than_fast(monkeypatch):
    from kronos_fincept import agent

    created = []

    class FakeManager:
        def __init__(self, **kwargs):
            created.append(kwargs)
            self.per_provider_timeout_seconds = kwargs["per_provider_timeout_seconds"]

    monkeypatch.setattr(agent, "MacroDataManager", FakeManager)
    agent._shared_macro_data_manager.cache_clear()
    first = agent._create_macro_data_manager(fast_mode=False)
    second = agent._create_macro_data_manager(fast_mode=False)

    assert first is second
    assert len(created) == 1
    assert first.per_provider_timeout_seconds == agent.COMPLETE_MACRO_PER_PROVIDER_TIMEOUT_SECONDS
    assert first.per_provider_timeout_seconds > agent.WEB_MACRO_PER_PROVIDER_TIMEOUT_SECONDS


def test_shallow_model_info_reports_configured_directml_device(monkeypatch):
    from kronos_fincept.api import deps

    monkeypatch.setenv("KRONOS_DEVICE", "dml")
    deps.get_model_info.cache_clear()
    try:
        info = deps.get_model_info(deep=False)
    finally:
        deps.get_model_info.cache_clear()

    assert info["device"] == "dml"


def test_api_defaults_to_one_worker_for_single_model_runtime(monkeypatch):
    from kronos_fincept.api import app

    monkeypatch.delenv("KRONOS_WORKERS", raising=False)
    monkeypatch.setattr(app.os, "cpu_count", lambda: 32)

    assert app._api_worker_count(reload_enabled=False) == 1

    monkeypatch.setenv("KRONOS_WORKERS", "3")
    assert app._api_worker_count(reload_enabled=False) == 3


def test_health_merges_live_predictor_cache_state(monkeypatch):
    from kronos_fincept.api.routes import health

    monkeypatch.setattr(
        "kronos_fincept.predictor.predictor_cache_stats",
        lambda: {"size": 1, "devices": ["dml"], "keys": ["model|tokenizer|512|dml"]},
    )

    merged = health._merge_runtime_model_info({"model_loaded": False, "device": "cpu"})

    assert merged["model_loaded"] is True
    assert merged["device"] == "dml"


def test_asset_workers_include_macro_slot_without_serializing_an_asset():
    from kronos_fincept import agent

    assert agent._analysis_worker_count(asset_count=3, needs_macro=True) == 4
    assert agent._analysis_worker_count(asset_count=3, needs_macro=False) == 3


def test_asset_data_wave_returns_defaults_at_one_shared_deadline():
    import concurrent.futures
    import time

    from kronos_fincept import agent

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    try:
        futures = {
            "fast": pool.submit(lambda: "ok"),
            "slow": pool.submit(lambda: (time.sleep(0.2), "late")[1]),
        }
        started = time.perf_counter()
        results = agent._collect_futures_with_deadline(
            futures,
            defaults={"fast": "missing", "slow": "timed-out"},
            timeout_seconds=0.02,
        )
        elapsed = time.perf_counter() - started
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    assert results == {"fast": "ok", "slow": "timed-out"}
    assert elapsed < 0.1
