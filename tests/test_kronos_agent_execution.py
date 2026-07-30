from __future__ import annotations

import threading


def test_single_asset_kronos_does_not_run_in_compute_pool(monkeypatch):
    from kronos_fincept import agent

    rows = [
        {
            "timestamp": f"2026-07-{index:02d}",
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "volume": 1000.0 + index,
            "amount": 100000.0 + index,
        }
        for index in range(1, 11)
    ]
    prediction_threads: list[str] = []

    monkeypatch.setattr(agent, "_fetch_price_data", lambda symbol, market: rows)
    monkeypatch.setattr(agent, "_fetch_financial_summary", lambda symbol, market: {})
    monkeypatch.setattr(
        agent,
        "_build_local_market_review_context",
        lambda symbol, market: {"available": False},
    )
    monkeypatch.setattr(
        agent,
        "_build_online_research",
        lambda item, *, question, query_limit: (
            {"enabled": False, "results": []},
            agent.AgentToolCall(
                name="online_research",
                status="skipped",
                summary="disabled",
            ),
        ),
    )
    monkeypatch.setattr(agent, "_build_technical_indicators", lambda rows: {"ok": True})
    monkeypatch.setattr(agent, "_build_risk_metrics", lambda symbol, rows: {"volatility": 0.1})

    def fake_prediction(symbol, rows, *, dry_run):
        prediction_threads.append(threading.current_thread().name)
        return {
            "model": "NeoQuasar/Kronos-small",
            "prediction_days": 5,
            "forecast": [{"close": 101.0}],
            "metadata": {"device": "dml"},
        }

    monkeypatch.setattr(agent, "_build_prediction", fake_prediction)

    asset, calls = agent._build_asset_context(
        agent.ResolvedSymbol(symbol="300308", market="cn", name="中际旭创"),
        question="中际旭创能买吗现在",
        dry_run=False,
        include_prediction=True,
    )

    assert asset["kronos_prediction"]["forecast"]
    assert any(call.name == "kronos_prediction" and call.status == "completed" for call in calls)
    assert prediction_threads
    assert not prediction_threads[0].startswith("kronos-compute")
