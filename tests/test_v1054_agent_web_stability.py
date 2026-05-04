from __future__ import annotations

import json
from types import SimpleNamespace


def _rows(n: int = 40) -> list[dict]:
    return [
        {
            "timestamp": f"2026-04-{(i % 28) + 1:02d}",
            "open": 30.0 + i * 0.1,
            "high": 30.2 + i * 0.1,
            "low": 29.8 + i * 0.1,
            "close": 30.1 + i * 0.1,
            "volume": 1_000_000 + i,
            "amount": 30_000_000 + i,
        }
        for i in range(n)
    ]


class DisabledSearchClient:
    provider = ""
    is_configured = False


class FakeMacroFailure(AssertionError):
    pass


def _report_payload(context: dict) -> dict:
    return {
        "conclusion": f"已分析 {context['assets'][0]['symbol']}",
        "short_term_prediction": "短期预测偏中性。",
        "technical": "技术指标中性。",
        "fundamentals": "财务摘要可用。",
        "risk": "风险中等。",
        "uncertainties": "关注外部服务时效。",
        "recommendation": "持有",
        "confidence": 0.62,
        "risk_level": "中",
        "disclaimer": "仅供研究。",
    }


def _patch_fast_agent_tools(monkeypatch):
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
            "model": "NeoQuasar/Kronos-base",
            "prediction_days": 5,
            "forecast": [{"timestamp": "D1", "open": 34.0, "high": 35.0, "low": 33.5, "close": 34.8}],
            "probabilistic": None,
        },
    )
    monkeypatch.setattr(agent, "_create_web_search_client", lambda: DisabledSearchClient())
    monkeypatch.setattr(agent, "_create_cninfo_client", lambda: DisabledSearchClient())
    monkeypatch.setattr(agent, "_call_deepseek_report", lambda question, context: _report_payload(context))


WEB_CONTEXT = {"entry": "web-analysis", "turn_index": 1, "max_turns": 5}


def test_v1054_web_analysis_plain_stock_buy_question_does_not_trigger_embedded_macro(monkeypatch):
    from kronos_fincept import agent

    _patch_fast_agent_tools(monkeypatch)

    def fail_macro(*args, **kwargs):
        raise FakeMacroFailure("plain web-analysis stock question must not trigger macro providers")

    monkeypatch.setattr(agent, "_build_macro_context", fail_macro)

    result = agent.analyze_investment_question(
        "帮我看看招商银行现在能不能买",
        context=WEB_CONTEXT,
        dry_run=True,
    )

    assert result.ok is True
    assert result.symbol == "600036"
    assert all(call.name != "macro_signal" for call in result.tool_calls)


def test_v1054_web_analysis_explicit_macro_question_still_runs_macro(monkeypatch):
    from kronos_fincept import agent

    _patch_fast_agent_tools(monkeypatch)
    macro_calls = []

    def fake_macro(question, *, symbols, market, provider_ids):
        macro_calls.append({"question": question, "symbols": symbols, "market": market, "provider_ids": provider_ids})
        context = {
            "question": question,
            "selected_provider_ids": provider_ids,
            "signals": [
                {
                    "source": "us_treasury",
                    "signal_type": "rates",
                    "value": 1.9,
                    "interpretation": "利率信号仅用于显式宏观问题。",
                    "time_horizon": "short",
                    "confidence": 0.6,
                }
            ],
            "errors": {},
            "provider_results": {},
        }
        return context, agent.AgentToolCall(
            name="macro_signal",
            status="completed",
            summary="宏观信号完成：1 个 provider 返回 1 条信号。",
            elapsed_ms=1,
            metadata={"provider_ids": provider_ids},
        )

    monkeypatch.setattr(agent, "_build_macro_context", fake_macro)

    result = agent.analyze_investment_question(
        "从宏观利率和美元角度看招商银行现在能不能买",
        context=WEB_CONTEXT,
        dry_run=True,
    )

    assert result.ok is True
    assert macro_calls
    assert any(call.name == "macro_signal" for call in result.tool_calls)


def test_v1054_web_analysis_deepseek_report_uses_short_timeout(monkeypatch):
    from kronos_fincept import agent
    import requests

    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "conclusion": "快速汇总完成。",
                                    "recommendation": "持有",
                                    "confidence": 0.6,
                                    "risk_level": "中",
                                },
                                ensure_ascii=False,
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured["timeout"] = timeout
        return FakeResponse()

    deepseek = SimpleNamespace(
        is_configured=True,
        api_key="test-key",
        base_url="https://example.com/v1",
        model="deepseek-chat",
    )
    monkeypatch.setattr(agent, "settings", SimpleNamespace(llm=SimpleNamespace(deepseek=deepseek)))
    monkeypatch.setattr(requests, "post", fake_post)

    report = agent._call_deepseek_report(
        "帮我看看招商银行现在能不能买",
        {"assets": [{"symbol": "600036", "market": "cn"}], "page_context": WEB_CONTEXT},
    )

    assert report is not None
    assert report["conclusion"] == "快速汇总完成。"
    assert captured["timeout"] <= 15


def test_v1054_cninfo_referer_encodes_chinese_query_as_ascii_safe_header():
    from kronos_fincept.cninfo import CninfoDisclosureClient

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "announcements": [
                    {
                        "announcementTitle": "招商银行年度报告",
                        "adjunctUrl": "finalpage/2026-04-30/test.pdf",
                        "announcementTime": 1777507200000,
                        "secName": "招商银行",
                        "shortTitle": "招商银行",
                        "announcementTypeName": "年度报告",
                    }
                ]
            }

        def raise_for_status(self):
            return None

    class FakeRequester:
        def __init__(self):
            self.headers = None

        def get(self, url, params, headers, timeout):
            headers["Referer"].encode("latin-1")
            self.headers = headers
            return FakeResponse()

    requester = FakeRequester()
    result = CninfoDisclosureClient(requester=requester, timeout_seconds=1, max_results=1).search("招商银行 公告")

    assert result.status == "completed"
    assert requester.headers is not None
    assert "%E6%8B%9B%E5%95%86%E9%93%B6%E8%A1%8C" in requester.headers["Referer"]


def test_v1054_agent_api_returns_ok_for_web_analysis_plain_stock_question(monkeypatch):
    from fastapi.testclient import TestClient

    from kronos_fincept import agent
    from kronos_fincept.api.app import app

    _patch_fast_agent_tools(monkeypatch)

    def fail_macro(*args, **kwargs):
        raise FakeMacroFailure("API web-analysis path must not call macro providers for plain stock buy questions")

    monkeypatch.setattr(agent, "_build_macro_context", fail_macro)

    response = TestClient(app).post(
        "/api/v1/analyze/agent",
        json={"question": "帮我看看招商银行现在能不能买", "dry_run": True, "context": WEB_CONTEXT},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["symbol"] == "600036"
    assert all(call["name"] != "macro_signal" for call in payload["tool_calls"])
