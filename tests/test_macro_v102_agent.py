from __future__ import annotations

import json

from click.testing import CliRunner
from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app
from kronos_fincept.cli.main import cli
from kronos_fincept.macro import MacroGatherResult, MacroProviderResult, MacroSignal


def _macro_result(provider_ids: list[str]) -> MacroGatherResult:
    signals = [
        MacroSignal(
            source=provider_ids[0],
            signal_type="prediction_market_probability",
            value=0.38,
            interpretation="预测市场对地缘冲突升级的定价偏中性。",
            time_horizon="event",
            confidence=0.68,
            source_url="https://example.com/polymarket",
        ),
        MacroSignal(
            source=provider_ids[1] if len(provider_ids) > 1 else provider_ids[0],
            signal_type="market_sentiment",
            value=42,
            interpretation="市场情绪偏谨慎。",
            time_horizon="short",
            confidence=0.61,
        ),
    ]
    return MacroGatherResult(
        signals=signals,
        provider_results={
            provider_id: MacroProviderResult(
                provider_id=provider_id,
                status="completed" if index < 2 else "empty",
                signals=signals[index : index + 1] if index < 2 else [],
                elapsed_ms=5,
            )
            for index, provider_id in enumerate(provider_ids)
        },
    )


class FakeMacroManager:
    def __init__(self) -> None:
        self.last_provider_ids: list[str] = []

    def gather(self, query, *, provider_ids=None):
        self.last_query = query
        self.last_provider_ids = list(provider_ids or [])
        return _macro_result(self.last_provider_ids)


def _patch_macro_tools(monkeypatch):
    from kronos_fincept import agent

    manager = FakeMacroManager()
    monkeypatch.setattr(agent, "_create_macro_data_manager", lambda: manager)
    monkeypatch.setattr(
        agent,
        "_call_deepseek_report",
        lambda question, context: {
            "conclusion": "宏观信号显示需要保持谨慎观察。",
            "short_term_prediction": "宏观链路不直接调用 Kronos K 线预测。",
            "technical": "不适用。",
            "fundamentals": "不适用。",
            "risk": "尾部风险存在。",
            "uncertainties": "provider 覆盖和事件时效会影响结论。",
            "recommendation": "观察",
            "confidence": 0.64,
            "risk_level": "中",
            "disclaimer": "仅供研究。",
            "macro_analysis": "预测市场和情绪信号未形成强共振。",
            "macro_signals": context["macro"]["signals"],
            "cross_validation": "预测市场、情绪和利率维度需要交叉验证。",
            "contradictions": "不同市场信号可能滞后。",
            "probability_scenarios": [
                {"scenario": "基准情形", "probability": 0.55, "basis": "多数信号中性。"},
                {"scenario": "尾部风险", "probability": 0.2, "basis": "地缘事件可能突发。"},
            ],
        },
    )
    return manager


def _rows(n: int = 40) -> list[dict]:
    return [
        {
            "timestamp": f"2026-03-{(i % 28) + 1:02d}",
            "open": 30 + i,
            "high": 31 + i,
            "low": 29 + i,
            "close": 30.5 + i,
            "volume": 100000 + i,
            "amount": 3000000 + i,
        }
        for i in range(n)
    ]


def test_v102_selects_macro_providers_for_geopolitical_question():
    from kronos_fincept.agent import select_macro_provider_ids

    providers = select_macro_provider_ids("WW3 概率是多少，黄金该不该买")
    gold_providers = select_macro_provider_ids("黄金该不该买")

    assert providers[:2] == ["polymarket", "kalshi"]
    assert 3 <= len(providers) <= 5
    assert {"cftc_cot", "fear_greed", "us_treasury"} <= set(gold_providers)


def test_v102_macro_agent_returns_macro_report(monkeypatch):
    from kronos_fincept.agent import analyze_macro_question

    manager = _patch_macro_tools(monkeypatch)
    result = analyze_macro_question("WW3 概率是多少，黄金该不该买")

    assert result.ok is True
    assert result.symbol is None
    assert result.report["macro_signals"]
    assert result.report["cross_validation"]
    assert result.report["probability_scenarios"]
    assert "宏观信号" in result.final_report
    assert "macro_signal" in {call.name for call in result.tool_calls}
    assert manager.last_provider_ids[:2] == ["polymarket", "kalshi"]


def test_v102_existing_stock_agent_does_not_auto_call_macro(monkeypatch):
    from kronos_fincept import agent

    monkeypatch.setattr(
        agent,
        "_create_macro_data_manager",
        lambda: (_ for _ in ()).throw(AssertionError("stock agent must not call macro providers")),
    )
    monkeypatch.setattr(
        agent,
        "_call_deepseek_router",
        lambda question, explicit_symbol=None, explicit_market=None: agent.AgentRouteDecision(
            allowed=True,
            symbols=[agent.ResolvedSymbol("600036", "cn", "招商银行")],
            source="deepseek_router",
        ),
    )
    monkeypatch.setattr(agent, "_fetch_price_data", lambda symbol, market: _rows())
    monkeypatch.setattr(agent, "_fetch_financial_summary", lambda symbol, market: {"symbol": symbol})
    monkeypatch.setattr(agent, "_build_technical_indicators", lambda rows: {"rsi": {"current": 52.0}})
    monkeypatch.setattr(agent, "_build_risk_metrics", lambda symbol, rows: {"volatility": 0.2})
    monkeypatch.setattr(
        agent,
        "_build_prediction",
        lambda symbol, rows, dry_run: {"model": "Kronos", "prediction_days": 5, "forecast": [{"close": 35.0}]},
    )
    monkeypatch.setattr(agent, "_call_deepseek_report", lambda question, context: None)

    class DisabledSearchClient:
        provider = ""
        is_configured = False

    monkeypatch.setattr(agent, "_create_web_search_client", lambda: DisabledSearchClient())
    monkeypatch.setattr(agent, "_create_cninfo_client", lambda: DisabledSearchClient())

    result = agent.analyze_investment_question("帮我看看招商银行现在能不能买")

    assert result.ok is True
    assert "macro_signal" not in {call.name for call in result.tool_calls}


def test_v102_macro_api_endpoint(monkeypatch):
    _patch_macro_tools(monkeypatch)
    client = TestClient(create_app())

    response = client.post("/api/v1/analyze/macro", json={"question": "黄金该不该买"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["report"]["macro_signals"]
    assert any(step["name"] == "获取宏观信号" for step in payload["steps"])


def test_v102_macro_cli_command(monkeypatch):
    _patch_macro_tools(monkeypatch)
    runner = CliRunner()

    result = runner.invoke(cli, ["analyze", "macro", "--question", "WW3 概率", "--output", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["report"]["macro_signals"]
    assert "macro_signal" in {call["name"] for call in payload["tool_calls"]}
