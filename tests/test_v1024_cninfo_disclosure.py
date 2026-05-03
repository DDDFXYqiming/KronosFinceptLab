from __future__ import annotations


def _rows(n: int = 40) -> list[dict]:
    return [
        {
            "timestamp": f"2026-05-{(i % 28) + 1:02d}",
            "open": 30.0 + i * 0.1,
            "high": 30.2 + i * 0.1,
            "low": 29.8 + i * 0.1,
            "close": 30.1 + i * 0.1,
            "volume": 1000000 + i,
            "amount": 30000000 + i,
        }
        for i in range(n)
    ]


def test_cninfo_client_parses_official_disclosures():
    from kronos_fincept.cninfo import CninfoDisclosureClient

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "announcements": [
                    {
                        "secCode": "600036",
                        "secName": "招商银行",
                        "orgId": "gssh0600036",
                        "announcementId": "1225272642",
                        "announcementTitle": "<em>招商银行</em>：<em>招商银行股份有限公司</em>董事会决议公告",
                        "announcementTime": 1777564800000,
                        "adjunctUrl": "finalpage/2026-05-01/1225272642.PDF",
                        "shortTitle": "<em>招商银行股份有限公司</em>董事会决议公告",
                    }
                ]
            }

        def raise_for_status(self):
            return None

    class FakeRequester:
        def __init__(self):
            self.calls = []

        def get(self, url, params, timeout, headers):
            self.calls.append({"url": url, "params": params, "timeout": timeout, "headers": headers})
            return FakeResponse()

    requester = FakeRequester()
    response = CninfoDisclosureClient(requester=requester).search("600036")

    assert response.status == "completed"
    assert response.provider == "cninfo"
    assert response.results[0].source == "cninfo"
    assert response.results[0].url == "https://static.cninfo.com.cn/finalpage/2026-05-01/1225272642.PDF"
    assert response.results[0].title.startswith("招商银行")
    assert response.results[0].published_at is not None
    assert response.results[0].published_at.endswith("Z")
    assert requester.calls[0]["params"]["searchkey"] == "600036"
    assert requester.calls[0]["headers"]["User-Agent"].startswith("KronosFinceptLab/10.2.4")


def test_agent_uses_cninfo_official_disclosure_when_web_search_is_disabled(monkeypatch):
    from kronos_fincept import agent
    from kronos_fincept.web_search import WebSearchResponse, WebSearchResult

    class DisabledSearchClient:
        provider = ""
        is_configured = False

    class FakeCninfoClient:
        provider = "cninfo"
        is_configured = True

        def search(self, query):
            return WebSearchResponse(
                enabled=True,
                status="completed",
                provider="cninfo",
                query=query,
                results=[
                    WebSearchResult(
                        title="招商银行：董事会决议公告",
                        url="https://static.cninfo.com.cn/finalpage/2026-05-01/1225272642.PDF",
                        snippet="招商银行 | 董事会决议公告 | 2026-05-01T00:00:00Z",
                        source="cninfo",
                        published_at="2026-05-01T00:00:00Z",
                    )
                ],
                elapsed_ms=7,
            )

    captured: dict[str, object] = {}

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
    def fake_report(question, context):
        captured["research"] = context["assets"][0]["online_research"]
        return {
            "conclusion": "已完成公开信息分析。",
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

    monkeypatch.setattr(agent, "_call_deepseek_report", fake_report)
    monkeypatch.setattr(agent, "_create_web_search_client", lambda: DisabledSearchClient())
    monkeypatch.setattr(agent, "_create_cninfo_client", lambda: FakeCninfoClient())

    result = agent.analyze_investment_question("帮我看看招商银行现在能不能买")
    research_call = next(call for call in result.tool_calls if call.name == "online_research")
    research = captured["research"]

    assert result.ok is True
    assert research_call.status == "completed"
    assert research_call.metadata["providers"] == ["cninfo"]
    assert research_call.summary.startswith("官方披露检索完成")
    assert research["enabled"] is True
    assert research["results"][0]["source"] == "cninfo"
