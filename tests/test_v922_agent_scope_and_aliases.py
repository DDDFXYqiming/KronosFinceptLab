from __future__ import annotations


def _rows(n: int = 40) -> list[dict]:
    data = []
    for i in range(n):
        close = 20.0 + i * 0.2
        data.append(
            {
                "timestamp": f"2026-02-{(i % 28) + 1:02d}",
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1000000 + i,
                "amount": 20000000 + i,
            }
        )
    return data


def _patch_agent_tools(monkeypatch):
    from kronos_fincept import agent

    class DisabledSearchClient:
        provider = ""
        is_configured = False

    monkeypatch.setattr(
        agent,
        "_call_deepseek_router",
        lambda question, explicit_symbol=None, explicit_market=None: agent._local_route_decision(
            question,
            explicit_symbol=explicit_symbol,
            explicit_market=explicit_market,
        ),
    )
    monkeypatch.setattr(agent, "_fetch_price_data", lambda symbol, market: _rows())
    monkeypatch.setattr(agent, "_fetch_financial_summary", lambda symbol, market: None)
    monkeypatch.setattr(agent, "_build_technical_indicators", lambda rows: {"rsi": {"current": 50.0}})
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
            "forecast": [{"timestamp": "D1", "open": 22.0, "high": 23.0, "low": 21.5, "close": 22.8}],
            "probabilistic": None,
        },
    )
    monkeypatch.setattr(
        agent,
        "_call_deepseek_report",
        lambda question, context: {
            "conclusion": f"已分析 {context['assets'][0]['symbol']}",
            "short_term_prediction": "短期预测偏中性。",
            "technical": "技术指标处于中性区间。",
            "fundamentals": "财务数据未返回，不编造基本面。",
            "risk": "风险中等。",
            "uncertainties": "数据源延迟和模型误差。",
            "recommendation": "持有",
            "confidence": 0.62,
            "risk_level": "中",
            "disclaimer": "仅供研究。",
        },
    )
    monkeypatch.setattr(agent, "_create_web_search_client", lambda: DisabledSearchClient())
    monkeypatch.setattr(agent, "_create_cninfo_client", lambda: DisabledSearchClient())


def test_agent_safety_allows_common_stock_price_questions():
    from kronos_fincept.agent import evaluate_agent_safety

    allowed_questions = [
        "帮我看看小米的股价还有救吗",
        "分析预测诺基亚未来的股价走势",
    ]

    for question in allowed_questions:
        decision = evaluate_agent_safety(question)
        assert decision["allowed"] is True, question


def test_agent_safety_still_rejects_non_financial_common_phrasing():
    from kronos_fincept.agent import evaluate_agent_safety

    decision = evaluate_agent_safety("我的感情还有救吗")

    assert decision["allowed"] is False
    assert "超出 KronosFinceptLab 当前能力范围" in decision["reason"]


def test_agent_resolves_common_chinese_company_aliases():
    from kronos_fincept.agent import resolve_symbols

    assert [(item.symbol, item.market, item.name) for item in resolve_symbols("帮我看看小米的股价还有救吗")] == [
        ("1810", "hk", "小米集团")
    ]
    assert [(item.symbol, item.market, item.name) for item in resolve_symbols("分析预测诺基亚未来的股价走势")] == [
        ("NOK", "us", "Nokia")
    ]


def test_agent_analyzes_xiaomi_question_without_rejection_or_clarification(monkeypatch):
    from kronos_fincept.agent import analyze_investment_question

    _patch_agent_tools(monkeypatch)
    result = analyze_investment_question("帮我看看小米的股价还有救吗")

    assert result.ok is True
    assert result.rejected is False
    assert result.clarification_required is False
    assert result.symbol == "1810"
    assert result.market == "hk"
    assert result.report["recommendation"] == "持有"


def test_agent_analyzes_nokia_question_without_clarification(monkeypatch):
    from kronos_fincept.agent import analyze_investment_question

    _patch_agent_tools(monkeypatch)
    result = analyze_investment_question("分析预测诺基亚未来的股价走势")

    assert result.ok is True
    assert result.rejected is False
    assert result.clarification_required is False
    assert result.symbol == "NOK"
    assert result.market == "us"
