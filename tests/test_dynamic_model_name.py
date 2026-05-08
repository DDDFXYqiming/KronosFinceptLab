from kronos_fincept.agent import (
    AgentRouteDecision,
    AgentToolCall,
    ResolvedSymbol,
    _generate_report,
    _set_last_report_llm_metadata,
    LLMChatProvider,
)


def _make_provider(
    name: str = "deepseek",
    display_name: str = "DeepSeek",
    model: str = "deepseek-chat",
) -> LLMChatProvider:
    return LLMChatProvider(
        name=name,
        display_name=display_name,
        api_key="sk-test",
        base_url="https://api.deepseek.com/v1",
        model=model,
    )


def _fake_call_deepseek_report_with_provider(provider):
    fake_report = {
        "conclusion": "test",
        "recommendation": "持有",
        "confidence": 0.6,
        "risk_level": "中",
        "disclaimer": "test",
    }

    def _inner(question, context):
        _set_last_report_llm_metadata(provider)
        return fake_report

    return _inner


def test_generate_report_success_uses_provider_display_in_tool_call_name(monkeypatch):
    provider = _make_provider(
        name="openrouter",
        display_name="OpenRouter Free",
        model="nvidia/nemotron-3-super-120b-a12b:free",
    )
    monkeypatch.setattr(
        "kronos_fincept.agent._call_deepseek_report",
        _fake_call_deepseek_report_with_provider(provider),
    )

    report, tool_call = _generate_report("test question", {})
    assert tool_call.name == "OpenRouter Free 汇总"
    assert tool_call.status == "completed"
    assert "OpenRouter Free" in tool_call.summary
    assert tool_call.metadata.get("model") == "nvidia/nemotron-3-super-120b-a12b:free"


def test_generate_report_success_deepseek_provider(monkeypatch):
    provider = _make_provider(
        name="deepseek",
        display_name="DeepSeek",
        model="deepseek-chat",
    )
    monkeypatch.setattr(
        "kronos_fincept.agent._call_deepseek_report",
        _fake_call_deepseek_report_with_provider(provider),
    )

    report, tool_call = _generate_report("test question", {})
    assert tool_call.name == "DeepSeek 汇总"
    assert tool_call.status == "completed"
    assert "DeepSeek" in tool_call.summary


def test_generate_report_fallback_uses_llm_summary_name(monkeypatch):
    monkeypatch.setattr(
        "kronos_fincept.agent._call_deepseek_report",
        lambda question, context: None,
    )

    report, tool_call = _generate_report("test question", {})
    assert tool_call.name == "LLM 汇总"
    assert tool_call.status == "fallback"
    assert "DeepSeek" not in tool_call.summary
    assert "OpenRouter" not in tool_call.summary
    assert "LLM" in tool_call.summary


def test_step_name_inherits_tool_call_name(monkeypatch):
    from kronos_fincept import agent

    def fake_router(*args, **kwargs):
        return AgentRouteDecision(
            allowed=True,
            symbols=[ResolvedSymbol("600036", "cn", "招商银行")],
            source="test",
        )

    def fake_asset_context(item, *, question, dry_run, search_query_limit=3, include_prediction=True):
        return (
            {
                "symbol": item.symbol,
                "market": item.market,
                "name": item.name,
                "market_data": {"current_price": 38.0, "data_points": 40},
                "risk_metrics": {"volatility": 0.2},
                "kronos_prediction": None,
                "online_research": None,
            },
            [],
        )

    def fake_generate_report(question, context):
        return (
            {
                "conclusion": "test",
                "recommendation": "持有",
                "confidence": 0.6,
                "risk_level": "中",
                "disclaimer": "test",
            },
            AgentToolCall(
                name="OpenRouter Free 汇总",
                status="completed",
                summary="OpenRouter Free 已基于项目工具结果生成结构化报告。",
                elapsed_ms=100,
                metadata={"model": "nvidia/nemotron-3-super-120b-a12b:free"},
            ),
        )

    monkeypatch.setattr(agent, "_call_deepseek_router", fake_router)
    monkeypatch.setattr(agent, "_build_asset_context", fake_asset_context)
    monkeypatch.setattr(agent, "_generate_report", fake_generate_report)

    result = agent.analyze_investment_question("帮我看看招商银行现在能不能买", dry_run=True)
    synthesis_steps = [s for s in result.steps if s.name.endswith("汇总")]
    assert len(synthesis_steps) >= 1
    assert synthesis_steps[0].name == "OpenRouter Free 汇总"
