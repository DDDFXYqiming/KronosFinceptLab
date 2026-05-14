from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _rows(n: int = 40) -> list[dict]:
    return [
        {
            "timestamp": f"2026-04-{(i % 28) + 1:02d}",
            "open": 10 + i * 0.1,
            "high": 10.2 + i * 0.1,
            "low": 9.8 + i * 0.1,
            "close": 10.1 + i * 0.1,
            "volume": 100000 + i,
            "amount": 1000000 + i,
        }
        for i in range(n)
    ]


def _patch_agent_tools(monkeypatch):
    from kronos_fincept import agent

    class DisabledSearchClient:
        provider = ""
        is_configured = False

    monkeypatch.setattr(agent, "_call_deepseek_router", lambda question, explicit_symbol=None, explicit_market=None: None)
    monkeypatch.setattr(agent, "_fetch_price_data", lambda symbol, market: _rows())
    monkeypatch.setattr(agent, "_fetch_financial_summary", lambda symbol, market: {"revenue": 1})
    monkeypatch.setattr(agent, "_build_technical_indicators", lambda rows: {"rsi": {"current": 52}})
    monkeypatch.setattr(
        agent,
        "_build_risk_metrics",
        lambda symbol, rows: {"var_95": -0.02, "sharpe_ratio": 0.8, "max_drawdown": -0.1, "volatility": 0.22},
    )
    monkeypatch.setattr(
        agent,
        "_build_prediction",
        lambda symbol, rows, dry_run: {
            "model": "NeoQuasar/Kronos-small",
            "prediction_days": 5,
            "forecast": [{"timestamp": "D1", "open": 10, "high": 10.5, "low": 9.8, "close": 10.3}],
            "probabilistic": None,
        },
    )
    monkeypatch.setattr(
        agent,
        "_call_deepseek_report",
        lambda question, context: {
            "conclusion": "可以进入正常金融研究链路。",
            "short_term_prediction": "短期预测偏中性。",
            "technical": "技术指标中性。",
            "fundamentals": "财务摘要可用。",
            "risk": "风险中等。",
            "uncertainties": "数据源延迟。",
            "recommendation": "持有",
            "confidence": 0.6,
            "risk_level": "中",
            "disclaimer": "仅供研究。",
        },
    )
    monkeypatch.setattr(agent, "_create_web_search_client", lambda: DisabledSearchClient())
    monkeypatch.setattr(agent, "_create_cninfo_client", lambda: DisabledSearchClient())


def test_v95_agent_steps_are_traceable_for_web_api_cli(monkeypatch):
    from kronos_fincept.agent import analyze_investment_question
    from kronos_fincept.logging_config import reset_request_id, set_request_id

    _patch_agent_tools(monkeypatch)
    token = set_request_id("req-v95")
    try:
        result = analyze_investment_question("帮我看看招商银行现在能不能买")
    finally:
        reset_request_id(token)

    assert result.ok is True
    step_names = [step.name for step in result.steps]
    assert step_names[:6] == [
        "理解问题",
        "范围/安全检查",
        "解析标的",
        "获取行情",
        "调用 Kronos",
        "网页检索",
    ]
    assert step_names[6].endswith("汇总"), f"Expected synthesis step, got: {step_names[6]}"
    assert step_names[7] == "生成报告"
    assert all("request_id" in call.metadata for call in result.tool_calls)
    assert any(call.metadata["request_id"] == "req-v95" for call in result.tool_calls)


def test_v95_web_analysis_page_has_agent_workspace_controls():
    page = read("web/src/app/analysis/page.tsx")

    assert "新建对话/清空本轮" in page
    assert "Agent 执行进度" in page or "Agent 执行时间线" in page
    assert "ToolCallList" in page
    assert "<details" in page
    assert "cleanUserVisibleText" in page
    assert "依据与工具调用" in page
    assert "buildEvidenceSummary" in page
    assert 'ReportSection title="依据"' in page
    assert page.index("汇总研究报告") < page.index("依据与工具调用")
    assert "request_id" not in page
    assert "JSON.stringify(call.metadata" not in page
    assert "queryClient.removeQueries" in page


def test_v95_version_labels_are_current():
    assert "Version: v10." in read("README.md")
    assert "v10." in read("web/src/components/layout/Sidebar.tsx")
    assert "v10." in read("web/src/components/layout/Header.tsx")
