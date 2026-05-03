from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _rows(n: int = 40) -> list[dict]:
    return [
        {
            "timestamp": f"2026-04-{(i % 28) + 1:02d}",
            "open": 10 + i * 0.1,
            "high": 10.3 + i * 0.1,
            "low": 9.7 + i * 0.1,
            "close": 10.1 + i * 0.1,
            "volume": 100000 + i,
            "amount": 1000000 + i,
        }
        for i in range(n)
    ]


def _patch_multi_asset_tools(monkeypatch, *, deepseek_report=True):
    from kronos_fincept import agent

    class DisabledSearchClient:
        provider = ""
        is_configured = False

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
    monkeypatch.setattr(agent, "_create_web_search_client", lambda: DisabledSearchClient())

    if deepseek_report:
        monkeypatch.setattr(
            agent,
            "_call_deepseek_report",
            lambda question, context: {
                "conclusion": "招商银行与贵州茅台需要分开看风险。",
                "short_term_prediction": "两个标的均已调用 Kronos。",
                "technical": "技术面分别评估。",
                "fundamentals": "财务摘要分别获取。",
                "risk": "招商银行风险中，贵州茅台风险中。",
                "uncertainties": "关注行情和财务数据时效。",
                "recommendation": "分标的查看",
                "confidence": 0.62,
                "risk_level": "中",
                "disclaimer": "仅供研究。",
                "asset_reports": [
                    {
                        "symbol": "600036",
                        "market": "cn",
                        "name": "招商银行",
                        "conclusion": "招商银行单独结论。",
                        "short_term_prediction": "招商银行短期预测。",
                        "technical": "招商银行技术面。",
                        "fundamentals": "招商银行基本面。",
                        "risk": "招商银行风险。",
                        "uncertainties": "招商银行不确定性。",
                        "recommendation": "持有",
                        "confidence": 0.6,
                        "risk_level": "中",
                        "disclaimer": "仅供研究。",
                    },
                    {
                        "symbol": "600519",
                        "market": "cn",
                        "name": "贵州茅台",
                        "conclusion": "贵州茅台单独结论。",
                        "short_term_prediction": "贵州茅台短期预测。",
                        "technical": "贵州茅台技术面。",
                        "fundamentals": "贵州茅台基本面。",
                        "risk": "贵州茅台风险。",
                        "uncertainties": "贵州茅台不确定性。",
                        "recommendation": "持有",
                        "confidence": 0.61,
                        "risk_level": "中",
                        "disclaimer": "仅供研究。",
                    },
                ],
            },
        )
    else:
        monkeypatch.setattr(agent, "_call_deepseek_report", lambda question, context: None)


def test_v971_agent_returns_per_asset_results_for_multi_symbol_question(monkeypatch):
    from kronos_fincept.agent import analyze_investment_question

    _patch_multi_asset_tools(monkeypatch)
    result = analyze_investment_question("比较招商银行和贵州茅台的中短期风险")

    assert result.ok is True
    assert result.symbols == ["600036", "600519"]
    assert len(result.asset_results) == 2
    assert [item["symbol"] for item in result.asset_results] == ["600036", "600519"]
    assert result.report["conclusion"].startswith("招商银行与贵州茅台")
    assert result.asset_results[0]["report"]["conclusion"] == "招商银行单独结论。"
    assert result.asset_results[1]["kronos_prediction"]["model"] == "NeoQuasar/Kronos-small"


def test_v971_fallback_report_still_returns_real_tool_derived_asset_cards(monkeypatch):
    from kronos_fincept.agent import analyze_investment_question

    _patch_multi_asset_tools(monkeypatch, deepseek_report=False)
    result = analyze_investment_question("比较招商银行和贵州茅台的中短期风险")

    assert result.ok is True
    assert len(result.asset_results) == 2
    assert "各标的独立卡片" in result.report["conclusion"]
    assert all(item["kronos_prediction"] for item in result.asset_results)
    assert all("工具链分析已完成" in item["report"]["conclusion"] for item in result.asset_results)


def test_v971_web_analysis_page_renders_summary_and_per_asset_cards():
    page = read("web/src/app/analysis/page.tsx")
    types = read("web/src/types/api.ts")

    assert "AgentAssetResult" in types
    assert "asset_results: AgentAssetResult[]" in types
    assert "汇总结论" in page
    assert "各标的分析" in page
    assert "AssetAnalysisCard" in page
    assert "getAssetResults(result)" in page
