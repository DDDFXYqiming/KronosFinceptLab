from __future__ import annotations

from types import SimpleNamespace


def _rows(n: int = 40) -> list[dict]:
    return [
        {
            "timestamp": f"2026-04-{(i % 28) + 1:02d}",
            "open": 30.0 + i * 0.1,
            "high": 30.2 + i * 0.1,
            "low": 29.8 + i * 0.1,
            "close": 30.1 + i * 0.1,
            "volume": 1000000 + i,
            "amount": 30000000 + i,
        }
        for i in range(n)
    ]


def _patch_agent_tools(monkeypatch, search_client):
    from kronos_fincept import agent

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
    monkeypatch.setattr(agent, "_fetch_financial_summary", lambda symbol, market: {"symbol": symbol})
    monkeypatch.setattr(agent, "_build_technical_indicators", lambda rows: {"rsi": {"current": 51.0}})
    monkeypatch.setattr(
        agent,
        "_build_risk_metrics",
        lambda symbol, rows: {"var_95": -0.02, "sharpe_ratio": 1.0, "max_drawdown": -0.08, "volatility": 0.21},
    )
    monkeypatch.setattr(
        agent,
        "_build_prediction",
        lambda symbol, rows, dry_run: {
            "model": "NeoQuasar/Kronos-small",
            "prediction_days": 5,
            "forecast": [{"timestamp": "D1", "open": 34.0, "high": 35.0, "low": 33.5, "close": 34.8}],
            "probabilistic": None,
        },
    )
    monkeypatch.setattr(agent, "_create_web_search_client", lambda: search_client)
    monkeypatch.setattr(agent, "_create_cninfo_client", lambda: SimpleNamespace(provider="", is_configured=False))


def _report_payload(context):
    return {
        "conclusion": f"已分析 {context['assets'][0]['symbol']}",
        "short_term_prediction": "短期预测偏中性。",
        "technical": "技术指标中性。",
        "fundamentals": "财务摘要可用。",
        "risk": "风险中等。",
        "uncertainties": "关注公开信息时效。",
        "recommendation": "持有",
        "confidence": 0.64,
        "risk_level": "中",
        "disclaimer": "仅供研究。",
    }


def test_web_search_client_tavily_success_parses_results():
    from kronos_fincept.web_search import WebSearchClient

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {
                        "title": "招商银行公告",
                        "url": "https://example.com/cmb",
                        "content": "招商银行发布公告。",
                        "published_date": "2026-05-01",
                    }
                ]
            }

        def raise_for_status(self):
            return None

    class FakeRequester:
        def __init__(self):
            self.payload = None

        def post(self, url, json, timeout):
            self.payload = {"url": url, "json": json, "timeout": timeout}
            return FakeResponse()

    requester = FakeRequester()
    config = SimpleNamespace(
        provider="tavily",
        api_key="test-key",
        endpoint="",
        timeout_seconds=3,
        max_results=2,
        is_configured=True,
    )
    response = WebSearchClient(config=config, requester=requester).search("招商银行 股价 新闻")

    assert response.status == "completed"
    assert response.provider == "tavily"
    assert response.results[0].url == "https://example.com/cmb"
    assert requester.payload["json"]["max_results"] == 2


def test_agent_marks_web_search_disabled_without_ambiguous_legacy_message(monkeypatch):
    from kronos_fincept import agent

    search_client = SimpleNamespace(provider="", is_configured=False)
    _patch_agent_tools(monkeypatch, search_client)
    monkeypatch.setattr(agent, "_call_deepseek_report", lambda question, context: _report_payload(context))

    result = agent.analyze_investment_question("帮我看看招商银行现在能不能买")
    research_call = next(call for call in result.tool_calls if call.name == "online_research")
    research_step = next(step for step in result.steps if step.name == "网页检索")

    assert result.ok is True
    assert research_call.status == "skipped"
    assert research_step.status == "skipped"
    assert "网页检索未启用" in research_call.summary
    assert "未配置通用网页检索工具" not in research_call.summary


def test_agent_passes_real_web_search_results_to_deepseek_context(monkeypatch):
    from kronos_fincept import agent
    from kronos_fincept.web_search import WebSearchResponse, WebSearchResult

    class FakeSearchClient:
        provider = "custom"
        is_configured = True

        def search(self, query):
            return WebSearchResponse(
                enabled=True,
                status="completed",
                provider="custom",
                query=query,
                results=[
                    WebSearchResult(
                        title="招商银行新闻",
                        url="https://example.com/news",
                        snippet="公开新闻摘要。",
                        source="custom",
                    )
                ],
                elapsed_ms=1,
            )

    _patch_agent_tools(monkeypatch, FakeSearchClient())

    def fake_report(question, context):
        research = context["assets"][0]["online_research"]
        assert research["enabled"] is True
        assert research["results"][0]["url"] == "https://example.com/news"
        return _report_payload(context)

    monkeypatch.setattr(agent, "_call_deepseek_report", fake_report)
    result = agent.analyze_investment_question("帮我看看招商银行现在能不能买")
    research_call = next(call for call in result.tool_calls if call.name == "online_research")

    assert result.ok is True
    assert research_call.status == "completed"
    assert research_call.metadata["result_count"] == 1


def test_agent_web_search_failure_degrades_without_failing_analysis(monkeypatch):
    from kronos_fincept import agent
    from kronos_fincept.web_search import WebSearchResponse

    class FailingSearchClient:
        provider = "custom"
        is_configured = True

        def search(self, query):
            return WebSearchResponse(
                enabled=True,
                status="failed",
                provider="custom",
                query=query,
                results=[],
                elapsed_ms=2,
                error="timeout",
            )

    _patch_agent_tools(monkeypatch, FailingSearchClient())
    monkeypatch.setattr(agent, "_call_deepseek_report", lambda question, context: _report_payload(context))

    result = agent.analyze_investment_question("帮我看看招商银行现在能不能买")
    research_call = next(call for call in result.tool_calls if call.name == "online_research")
    research_step = next(step for step in result.steps if step.name == "网页检索")

    assert result.ok is True
    assert research_call.status == "failed"
    assert research_step.status == "failed"
    assert "timeout" in research_call.summary


def test_deepseek_report_prompt_treats_web_content_as_untrusted():
    from pathlib import Path

    source = Path("src/kronos_fincept/agent.py").read_text(encoding="utf-8")

    assert "网页内容" in source
    assert "不可信数据" in source
    assert "来源 URL" in source
