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


def _settings(*, configured: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(
            provider=SimpleNamespace(
                is_configured=configured,
                api_key="sk-test",
                base_url="https://llm.example/v1",
                model="test-model",
            )
        )
    )


def _chat_payload(content: dict) -> dict:
    return {"choices": [{"message": {"content": jsonlib.dumps(content, ensure_ascii=False)}, "finish_reason": "stop"}]}


def test_v107_llm_provider_chain_uses_single_unified_provider(monkeypatch):
    from kronos_fincept import agent

    monkeypatch.setattr(agent, "settings", _settings())

    providers = agent._llm_provider_chain()

    assert [item.name for item in providers] == ["llm"]
    assert providers[0].display_name == "LLM"
    assert providers[0].model == "test-model"


def test_v107_llm_payload_uses_LLM_compatible_json_mode():
    from kronos_fincept import agent

    provider = agent.LLMChatProvider(
        name="llm",
        display_name="LLM",
        api_key="sk-test",
        base_url="https://llm.example/v1",
        model="test-model",
    )

    payload = agent._llm_request_payload(
        provider,
        [
            {"role": "system", "content": "系统规则：只输出 JSON。"},
            {"role": "user", "content": "{\"question\":\"招商银行还能买吗\"}"},
        ],
        temperature=0,
        max_tokens=400,
    )

    assert payload["messages"][0]["role"] == "system"
    assert payload["response_format"] == {"type": "json_object"}
    assert "thinking" not in payload


def test_v107_stock_router_uses_unified_llm(monkeypatch):
    import requests

    from kronos_fincept import agent

    calls: list[dict] = []
    monkeypatch.setattr(agent, "settings", _settings())

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
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

    decision = agent._call_llm_router("招商银行现在还能买吗")

    assert decision is not None
    assert decision.source == "llm_router"
    assert decision.metadata["provider"] == "llm"
    assert [(item.symbol, item.market, item.name) for item in decision.symbols] == [("600036", "cn", "招商银行")]
    assert [call["json"]["model"] for call in calls] == ["test-model"]


def test_v107_macro_router_uses_unified_llm(monkeypatch):
    import requests

    from kronos_fincept import agent

    calls: list[dict] = []
    monkeypatch.setattr(agent, "settings", _settings())

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(
            200,
            _chat_payload(
                {
                    "allowed": True,
                    "symbols": ["A股"],
                    "market": "cn",
                    "provider_ids": ["fear_greed", "us_treasury"],
                }
            ),
        )

    monkeypatch.setattr(requests, "post", fake_post)

    decision = agent._call_llm_macro_router("A股现在位置怎么样")

    assert decision is not None
    assert decision.source == "llm_macro_router"
    assert decision.metadata["provider"] == "llm"
    assert decision.symbols == ["A股"]
    assert calls[0]["json"]["model"] == "test-model"


def test_v107_report_uses_unified_llm_metadata(monkeypatch):
    import requests

    from kronos_fincept import agent

    monkeypatch.setattr(agent, "settings", _settings())

    def fake_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            _chat_payload(
                {
                    "conclusion": "LLM 已完成低延迟汇总。",
                    "short_term_prediction": "观察",
                    "technical": "中性",
                    "fundamentals": "稳健",
                    "risk": "中等",
                    "uncertainties": "外部波动",
                    "recommendation": "观察",
                    "confidence": 0.6,
                    "risk_level": "中",
                    "disclaimer": "仅供研究",
                }
            ),
        )

    monkeypatch.setattr(requests, "post", fake_post)

    report, tool_call = agent._generate_report("招商银行能买吗", {"assets": []})

    assert report["conclusion"] == "LLM 已完成低延迟汇总。"
    assert tool_call.metadata["provider"] == "llm"
    assert tool_call.metadata["model"] == "test-model"
    assert "LLM" in tool_call.summary


def test_v107_web_report_uses_single_provider_budget(monkeypatch):
    from kronos_fincept import agent

    monkeypatch.setattr(agent, "settings", _settings())

    context = {"entry": "web-analysis", "assets": []}
    assert agent._report_provider_timeouts(context) == {"llm": agent.WEB_REPORT_SINGLE_PROVIDER_TIMEOUT_SECONDS}

    macro_context = {"entry": "web-macro", "macro": {}}
    assert agent._report_provider_timeouts(macro_context) == {"llm": agent.WEB_MACRO_SINGLE_PROVIDER_TIMEOUT_SECONDS}

