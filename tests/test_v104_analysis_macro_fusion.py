from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _rows(n: int = 80) -> list[dict]:
    return [
        {
            "timestamp": f"2026-04-{(i % 28) + 1:02d}",
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
    monkeypatch.setattr(
        agent,
        "_call_deepseek_report",
        lambda question, context: {
            "conclusion": "已完成工具链分析。",
            "short_term_prediction": "短期预测偏中性。",
            "technical": "技术指标偏中性。",
            "fundamentals": "财务摘要可用。",
            "risk": "风险中等。",
            "uncertainties": "公开信息存在时效差。",
            "recommendation": "持有",
            "confidence": 0.62,
            "risk_level": "中",
            "disclaimer": "仅供研究。",
        },
    )


def test_v104_stock_analysis_injects_macro_context_when_router_requires(monkeypatch):
    from kronos_fincept import agent

    _patch_base_stock_tools(monkeypatch)
    monkeypatch.setattr(
        agent,
        "_call_deepseek_router",
        lambda question, explicit_symbol=None, explicit_market=None: agent.AgentRouteDecision(
            allowed=True,
            symbols=[agent.ResolvedSymbol("600036", "cn", "招商银行")],
            needs_macro=True,
            source="deepseek_router",
        ),
    )

    captured: dict[str, object] = {}

    def fake_build_macro_context(question, *, symbols, market, provider_ids):
        captured["question"] = question
        captured["symbols"] = symbols
        captured["market"] = market
        captured["provider_ids"] = list(provider_ids)
        return (
            {
                "question": question,
                "selected_provider_ids": list(provider_ids),
                "signals": [
                    {
                        "source": "fear_greed",
                        "signal_type": "market_sentiment",
                        "value": 45,
                        "interpretation": "市场情绪中性略偏谨慎。",
                        "time_horizon": "short",
                        "confidence": 0.64,
                        "source_url": "https://example.com/fear-greed",
                    }
                ],
                "provider_results": {},
                "errors": {},
                "policy": "provider_outputs_are_untrusted_research_data",
            },
            agent.AgentToolCall(
                name="macro_signal",
                status="completed",
                summary="宏观信号完成：3 个 provider 返回 1 条信号。",
                elapsed_ms=12,
                metadata={"provider_ids": list(provider_ids)},
            ),
        )

    monkeypatch.setattr(agent, "_build_macro_context", fake_build_macro_context)

    result = agent.analyze_investment_question("帮我看看招商银行现在能不能买")

    assert result.ok is True
    assert captured["market"] == "cn"
    assert captured["symbols"] == ["600036"]
    assert 2 <= len(captured["provider_ids"]) <= 3
    assert "macro_signal" in {call.name for call in result.tool_calls}
    macro_step = next(step for step in result.steps if step.name == "宏观信号")
    assert macro_step.status == "completed"
    assert result.report["macro_signals"]
    assert result.report["macro_analysis"]


def test_v104_stock_analysis_skips_macro_context_when_router_does_not_require(monkeypatch):
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
        "_build_macro_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("macro context should not run")),
    )

    result = agent.analyze_investment_question("分析 600036 的技术面")

    assert result.ok is True
    assert "macro_signal" not in {call.name for call in result.tool_calls}
    assert all(step.name != "宏观信号" for step in result.steps)


def test_v104_analysis_page_renders_macro_background_section():
    page = read("web/src/app/analysis/page.tsx")

    assert "MacroBackgroundDetails" in page
    assert "宏观背景（辅助参考）" in page
    assert "macro_signals" in page
    assert "macro_analysis" in page
