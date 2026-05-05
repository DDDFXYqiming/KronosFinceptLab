from __future__ import annotations

import json as jsonlib
from types import SimpleNamespace


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or jsonlib.dumps(self._payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


def _settings(*, openrouter_configured: bool = True, deepseek_configured: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(
            openrouter=SimpleNamespace(
                is_configured=openrouter_configured,
                api_key="sk-or-test",
                base_url="https://openrouter.ai/api/v1",
                model="openrouter/free",
            ),
            deepseek=SimpleNamespace(
                is_configured=deepseek_configured,
                api_key="sk-deepseek-test",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-v4-flash",
            ),
        )
    )


def _chat_payload(content: dict) -> dict:
    return {"choices": [{"message": {"content": jsonlib.dumps(content, ensure_ascii=False)}, "finish_reason": "stop"}]}


def test_v107_llm_provider_chain_prefers_openrouter_free(monkeypatch):
    from kronos_fincept import agent

    monkeypatch.setattr(agent, "settings", _settings())

    providers = agent._llm_provider_chain()

    assert [item.name for item in providers] == ["openrouter", "deepseek"]
    assert providers[0].model == "openrouter/free"


def test_v107_stock_router_falls_back_from_openrouter_to_deepseek(monkeypatch):
    import requests

    from kronos_fincept import agent

    calls: list[dict] = []
    monkeypatch.setattr(agent, "settings", _settings())

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if "openrouter.ai" in url:
            return FakeResponse(429, {"error": {"message": "rate limit"}}, "rate limit")
        return FakeResponse(
            200,
            _chat_payload(
                {
                    "allowed": True,
                    "needs_clarification": False,
                    "symbols": [{"symbol": "600036", "market": "cn", "name": "招商银行"}],
                }
            ),
        )

    monkeypatch.setattr(requests, "post", fake_post)

    decision = agent._call_deepseek_router("招商银行现在还能买吗")

    assert decision is not None
    assert decision.source == "deepseek_router"
    assert decision.metadata["provider"] == "deepseek"
    assert [(item.symbol, item.market, item.name) for item in decision.symbols] == [("600036", "cn", "招商银行")]
    assert [call["json"]["model"] for call in calls] == ["openrouter/free", "deepseek-v4-flash"]
    assert calls[0]["headers"]["HTTP-Referer"].endswith("KronosFinceptLab")
    assert "thinking" not in calls[0]["json"]
    assert calls[1]["json"]["thinking"] == {"type": "disabled"}


def test_v107_macro_router_uses_openrouter_free_when_it_returns_valid_json(monkeypatch):
    import requests

    from kronos_fincept import agent

    calls: list[dict] = []
    monkeypatch.setattr(agent, "settings", _settings())

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "json": json})
        return FakeResponse(
            200,
            _chat_payload(
                {
                    "allowed": True,
                    "needs_clarification": False,
                    "symbols": ["A股"],
                    "market": "cn",
                    "provider_ids": ["web_search", "shell", "us_treasury"],
                }
            ),
        )

    monkeypatch.setattr(requests, "post", fake_post)

    decision = agent._call_deepseek_macro_router("A股现在位置怎么样")

    assert decision is not None
    assert decision.source == "openrouter_macro_router"
    assert decision.metadata["provider"] == "openrouter"
    assert decision.symbols == ["A股"]
    assert decision.provider_ids == ["web_search", "us_treasury"]
    assert len(calls) == 1
    assert calls[0]["json"]["model"] == "openrouter/free"


def test_v107_report_uses_openrouter_metadata_when_free_model_succeeds(monkeypatch):
    import requests

    from kronos_fincept import agent

    calls: list[dict] = []
    monkeypatch.setattr(agent, "settings", _settings())

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "json": json})
        return FakeResponse(
            200,
            _chat_payload(
                {
                    "conclusion": "OpenRouter 已完成低成本汇总。",
                    "short_term_prediction": "短期中性。",
                    "technical": "技术面中性。",
                    "fundamentals": "基本面需继续跟踪。",
                    "risk": "风险中等。",
                    "uncertainties": "存在模型与数据时效不确定性。",
                    "recommendation": "持有",
                    "confidence": 0.6,
                    "risk_level": "中",
                    "disclaimer": "仅供研究。",
                }
            ),
        )

    monkeypatch.setattr(requests, "post", fake_post)

    report, tool_call = agent._generate_report("招商银行现在还能买吗", {"assets": []})

    assert report["conclusion"] == "OpenRouter 已完成低成本汇总。"
    assert tool_call.status == "completed"
    assert tool_call.metadata["provider"] == "openrouter"
    assert tool_call.metadata["model"] == "openrouter/free"
    assert "OpenRouter Free" in tool_call.summary
    assert len(calls) == 1


def test_v107_report_falls_back_to_deepseek_when_openrouter_content_is_not_json(monkeypatch):
    import requests

    from kronos_fincept import agent

    calls: list[dict] = []
    monkeypatch.setattr(agent, "settings", _settings())

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "json": json})
        if "openrouter.ai" in url:
            return FakeResponse(200, {"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]})
        return FakeResponse(
            200,
            _chat_payload(
                {
                    "conclusion": "DeepSeek 兜底汇总完成。",
                    "short_term_prediction": "短期中性。",
                    "technical": "技术面中性。",
                    "fundamentals": "基本面需继续跟踪。",
                    "risk": "风险中等。",
                    "uncertainties": "存在模型与数据时效不确定性。",
                    "recommendation": "持有",
                    "confidence": 0.6,
                    "risk_level": "中",
                    "disclaimer": "仅供研究。",
                }
            ),
        )

    monkeypatch.setattr(requests, "post", fake_post)

    report, tool_call = agent._generate_report("招商银行现在还能买吗", {"assets": []})

    assert report["conclusion"] == "DeepSeek 兜底汇总完成。"
    assert tool_call.metadata["provider"] == "deepseek"
    assert tool_call.metadata["model"] == "deepseek-v4-flash"
    assert [call["json"]["model"] for call in calls] == ["openrouter/free", "deepseek-v4-flash"]


def test_v107_web_report_uses_short_provider_budgets(monkeypatch):
    import requests

    from kronos_fincept import agent

    calls: list[dict] = []
    monkeypatch.setattr(agent, "settings", _settings())

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        if "openrouter.ai" in url:
            return FakeResponse(200, {"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]})
        return FakeResponse(
            200,
            _chat_payload(
                {
                    "conclusion": "DeepSeek 在 Web 短预算内完成兜底。",
                    "short_term_prediction": "短期中性。",
                    "technical": "技术面中性。",
                    "fundamentals": "基本面需继续跟踪。",
                    "risk": "风险中等。",
                    "uncertainties": "存在模型与数据时效不确定性。",
                    "recommendation": "持有",
                    "confidence": 0.6,
                    "risk_level": "中",
                    "disclaimer": "仅供研究。",
                }
            ),
        )

    monkeypatch.setattr(requests, "post", fake_post)

    report = agent._call_deepseek_report(
        "帮我看看招商银行现在还能买吗",
        {"assets": [{"symbol": "600036", "market": "cn"}], "page_context": {"entry": "web-analysis"}},
    )

    assert report is not None
    assert report["conclusion"] == "DeepSeek 在 Web 短预算内完成兜底。"
    assert [call["timeout"] for call in calls] == [8, 14]
