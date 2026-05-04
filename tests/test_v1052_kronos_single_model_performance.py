from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _rows(n: int = 40) -> list[dict]:
    return [
        {
            "timestamp": f"2026-04-{(i % 28) + 1:02d}",
            "open": 30 + i * 0.1,
            "high": 30.3 + i * 0.1,
            "low": 29.7 + i * 0.1,
            "close": 30.1 + i * 0.1,
            "volume": 100000 + i,
            "amount": 1000000 + i,
        }
        for i in range(n)
    ]


def test_v1052_zeabur_uses_single_kronos_base_with_startup_prewarm():
    dockerfile = read("Dockerfile")

    assert "KRONOS_MODEL_ID=NeoQuasar/Kronos-base" in dockerfile
    assert "KRONOS_PREWARM_ON_STARTUP=1" in dockerfile
    assert "KRONOS_AGENT_MODEL_ID" not in dockerfile
    assert "Kronos-small" not in dockerfile


def test_v1052_default_predictor_prewarm_uses_shared_configured_model(monkeypatch):
    from kronos_fincept import service

    captured = {}

    def fake_prewarm_predictor(**kwargs):
        captured.update(kwargs)
        return {"model_id": kwargs["model_id"], "cache_key": "cached"}

    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(kronos=SimpleNamespace(model_id="NeoQuasar/Kronos-base", tokenizer_id="tokenizer")),
    )
    monkeypatch.setattr(service, "prewarm_predictor", fake_prewarm_predictor)

    result = service.prewarm_default_predictor()

    assert result["model_id"] == "NeoQuasar/Kronos-base"
    assert captured == {"model_id": "NeoQuasar/Kronos-base", "tokenizer_id": "tokenizer"}


def test_v1052_multi_asset_agent_defers_to_shared_batch_prediction(monkeypatch):
    from kronos_fincept import agent

    include_prediction_values = []
    batch_called = {"value": False}

    monkeypatch.setattr(
        agent,
        "_call_deepseek_router",
        lambda question, explicit_symbol=None, explicit_market=None: agent.AgentRouteDecision(
            allowed=True,
            symbols=[
                agent.ResolvedSymbol("600036", "cn", "招商银行"),
                agent.ResolvedSymbol("600519", "cn", "贵州茅台"),
            ],
            source="deepseek_router",
        ),
    )

    def fake_asset_context(item, *, question, dry_run, search_query_limit=3, include_prediction=True):
        include_prediction_values.append(include_prediction)
        return (
            {
                "symbol": item.symbol,
                "market": item.market,
                "name": item.name,
                "market_data": {"rows": _rows(), "current_price": 34.0},
            },
            [agent.AgentToolCall(name="market_data", status="completed", summary="ok")],
        )

    def fake_batch_predictions(items, asset_contexts, *, dry_run):
        batch_called["value"] = True
        for item, asset in zip(items, asset_contexts):
            asset["kronos_prediction"] = {
                "model": "NeoQuasar/Kronos-base",
                "prediction_days": 5,
                "forecast": [{"timestamp": "D1", "open": 34, "high": 35, "low": 33, "close": 34.8}],
                "probabilistic": None,
            }
        return [
            agent.AgentToolCall(
                name="kronos_prediction",
                status="completed",
                summary="已通过批量模式调用 NeoQuasar/Kronos-base 生成真实短期预测。",
            )
        ]

    monkeypatch.setattr(agent, "_build_asset_context", fake_asset_context)
    monkeypatch.setattr(agent, "_build_batch_predictions", fake_batch_predictions)
    monkeypatch.setattr(agent, "_call_deepseek_report", lambda question, context: None)

    result = agent.analyze_investment_question("比较招商银行和贵州茅台的中短期风险")

    assert include_prediction_values == [False, False]
    assert batch_called["value"] is True
    assert result.ok is True
    assert [item["kronos_prediction"]["model"] for item in result.asset_results] == [
        "NeoQuasar/Kronos-base",
        "NeoQuasar/Kronos-base",
    ]


def test_v1052_agent_multi_asset_predictions_reuse_single_forecast_path(monkeypatch):
    from kronos_fincept import agent

    calls = []
    items = [
        agent.ResolvedSymbol("600036", "cn", "招商银行"),
        agent.ResolvedSymbol("600519", "cn", "贵州茅台"),
    ]
    asset_contexts = [
        {"symbol": item.symbol, "market": item.market, "market_data": {"rows": _rows(), "current_price": 34.0}}
        for item in items
    ]

    def fake_prediction(symbol, rows, *, dry_run):
        calls.append({"symbol": symbol, "rows": len(rows), "dry_run": dry_run})
        return {
            "model": "NeoQuasar/Kronos-base",
            "prediction_days": 5,
            "forecast": [{"timestamp": "D1", "open": 34, "high": 35, "low": 33, "close": 34.8}],
            "probabilistic": None,
            "metadata": {"backend": "kronos"},
        }

    monkeypatch.setattr(agent, "_build_prediction", fake_prediction)

    tool_calls = agent._build_batch_predictions(items, asset_contexts, dry_run=False)

    assert [item["symbol"] for item in calls] == ["600036", "600519"]
    assert all(item["rows"] == 40 for item in calls)
    assert all(call.status == "completed" for call in tool_calls)
    assert all(asset["kronos_prediction"]["metadata"]["backend"] == "kronos" for asset in asset_contexts)
