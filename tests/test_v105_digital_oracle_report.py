from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _rows(n: int = 80) -> list[dict]:
    return [
        {
            "timestamp": f"2026-05-{(i % 28) + 1:02d}",
            "open": 30.0 + i * 0.1,
            "high": 30.3 + i * 0.1,
            "low": 29.7 + i * 0.1,
            "close": 30.1 + i * 0.1,
            "volume": 1000000 + i,
            "amount": 30000000 + i,
        }
        for i in range(n)
    ]


def _patch_base_stock_tools(monkeypatch):
    from kronos_fincept import agent

    class DisabledSearchClient:
        provider = ""
        is_configured = False

    monkeypatch.setattr(agent, "_fetch_price_data", lambda symbol, market: _rows())
    monkeypatch.setattr(agent, "_fetch_financial_summary", lambda symbol, market: {"symbol": symbol, "market": market})
    monkeypatch.setattr(agent, "_build_technical_indicators", lambda rows: {"rsi": {"current": 48.5}})
    monkeypatch.setattr(
        agent,
        "_build_risk_metrics",
        lambda symbol, rows: {"var_95": -0.02, "sharpe_ratio": 0.9, "max_drawdown": -0.1, "volatility": 0.24},
    )
    monkeypatch.setattr(
        agent,
        "_build_prediction",
        lambda symbol, rows, dry_run: {
            "model": "NeoQuasar/Kronos-small",
            "prediction_days": 5,
            "forecast": [
                {"timestamp": "D1", "open": 38.2, "high": 38.7, "low": 38.0, "close": 38.4},
                {"timestamp": "D2", "open": 38.4, "high": 38.9, "low": 38.2, "close": 38.6},
            ],
            "probabilistic": None,
        },
    )
    monkeypatch.setattr(agent, "_create_web_search_client", lambda: DisabledSearchClient())
    monkeypatch.setattr(agent, "_create_cninfo_client", lambda: DisabledSearchClient())


def test_v105_deepseek_prompt_includes_digital_oracle_rules(monkeypatch):
    import requests

    from kronos_fincept import agent

    captured: dict[str, object] = {}
    fake_settings = SimpleNamespace(
        llm=SimpleNamespace(
            deepseek=SimpleNamespace(
                api_key="sk-test",
                base_url="https://api.deepseek.com",
                model="deepseek-v4-flash",
                is_configured=True,
            )
        )
    )

    class FakeResponse:
        status_code = 200
        text = '{"choices":[]}'

        def json(self):
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": (
                                '{"conclusion":"ok","short_term_prediction":"ok",'
                                '"technical":"ok","fundamentals":"ok","risk":"ok",'
                                '"uncertainties":"ok","recommendation":"持有",'
                                '"confidence":0.7,"risk_level":"中","disclaimer":"仅供研究"}'
                            )
                        },
                    }
                ]
            }

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(agent, "settings", fake_settings)
    monkeypatch.setattr(requests, "post", fake_post)

    report = agent._call_deepseek_report("黄金该不该买", {"assets": [], "macro": {"signals": []}})
    request_json = captured["json"]
    assert isinstance(request_json, dict)
    system_prompt = request_json["messages"][0]["content"]
    assert "Digital Oracle 5 条铁规则" in system_prompt
    assert "交易数据优先" in system_prompt
    assert "显式推理" in system_prompt
    assert "多信号交叉验证" in system_prompt
    assert "时间维度标注" in system_prompt
    assert "结构化输出" in system_prompt
    assert "信号一致性评估" in system_prompt
    assert report is not None
    assert report["conclusion"] == "ok"


def test_v105_macro_report_contains_probability_consistency_and_monitoring(monkeypatch):
    from kronos_fincept import agent
    from kronos_fincept.macro import MacroGatherResult, MacroProviderResult, MacroSignal

    class FakeMacroManager:
        def gather(self, query, *, provider_ids=None):
            selected = list(provider_ids or [])
            signals = [
                MacroSignal(
                    source=selected[0] if selected else "polymarket",
                    signal_type="prediction_market_probability",
                    value=0.36,
                    interpretation="预测市场对冲突升级定价偏中性。",
                    time_horizon="event",
                    confidence=0.67,
                    source_url="https://example.com/polymarket",
                ),
                MacroSignal(
                    source=selected[1] if len(selected) > 1 else "us_treasury",
                    signal_type="yield_curve",
                    value=0.12,
                    interpretation="收益率曲线仍偏平坦。",
                    time_horizon="mid",
                    confidence=0.61,
                    source_url="https://example.com/ust",
                ),
                MacroSignal(
                    source=selected[2] if len(selected) > 2 else "fear_greed",
                    signal_type="market_sentiment",
                    value=45,
                    interpretation="市场情绪中性偏谨慎。",
                    time_horizon="short",
                    confidence=0.64,
                    source_url="https://example.com/fng",
                ),
            ]
            provider_results = {
                provider_id: MacroProviderResult(
                    provider_id=provider_id,
                    status="completed",
                    signals=signals[:1],
                    elapsed_ms=5,
                )
                for provider_id in selected
            }
            return MacroGatherResult(signals=signals, provider_results=provider_results, errors={})

    monkeypatch.setattr(agent, "_create_macro_data_manager", lambda: FakeMacroManager())
    monkeypatch.setattr(agent, "_call_deepseek_macro_router", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "_call_deepseek_report", lambda question, context: None)

    result = agent.analyze_macro_question("WW3 概率和黄金该不该买")

    assert result.ok is True
    assert result.report["cross_validation"]
    assert result.report["contradictions"]
    assert isinstance(result.report.get("probability_scenarios"), list)
    assert len(result.report["probability_scenarios"]) >= 1
    assert isinstance(result.report.get("monitoring_signals"), list)
    assert len(result.report["monitoring_signals"]) >= 1
    assert any(step.name == "OpenRouter/DeepSeek 汇总" for step in result.steps)
    assert "信号一致性评估" in result.final_report
    assert "概率估计" in result.final_report
    assert "概率场景" in result.final_report
    assert "待监控信号" in result.final_report


def test_v105_stock_report_shape_stays_stable_when_macro_not_required(monkeypatch):
    from kronos_fincept import agent

    _patch_base_stock_tools(monkeypatch)
    monkeypatch.setattr(
        agent,
        "_call_deepseek_router",
        lambda question, explicit_symbol=None, explicit_market=None: agent.AgentRouteDecision(
            allowed=True,
            symbols=[agent.ResolvedSymbol("600036", "cn", "招商银行")],
            needs_macro=False,
            source="deepseek_router",
        ),
    )
    monkeypatch.setattr(
        agent,
        "_call_deepseek_report",
        lambda question, context: {
            "conclusion": "结论",
            "short_term_prediction": "短期预测",
            "technical": "技术面",
            "fundamentals": "基本面",
            "risk": "风险",
            "uncertainties": "不确定性",
            "recommendation": "持有",
            "confidence": 0.66,
            "risk_level": "中",
            "disclaimer": "仅供研究",
        },
    )

    result = agent.analyze_investment_question("分析 600036 的技术面")

    assert result.ok is True
    assert all(step.name != "宏观信号" for step in result.steps)
    for key in [
        "macro_analysis",
        "macro_signals",
        "cross_validation",
        "contradictions",
        "probability_scenarios",
        "monitoring_signals",
    ]:
        assert key not in result.report


def test_v105_web_api_cli_share_macro_template_contract():
    macro_page = read("web/src/app/macro/page.tsx")
    api_routes = read("src/kronos_fincept/api/routes/ai_analyze.py")
    cli_analyze = read("src/kronos_fincept/cli/commands/analyze.py")

    assert "信号一致性评估" in macro_page
    assert "概率估计" in macro_page
    assert "待监控信号" in macro_page
    assert "analyze_macro_question" in api_routes
    assert "analyze_macro_question" in cli_analyze
