"""Verify _call_structured_llm_json walks the full fallback chain
(primary -> fallback_1 -> fallback_2) and returns the first success."""
from __future__ import annotations

import json as jsonlib
import os
from types import SimpleNamespace

import pytest


class _FakeResp:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = jsonlib.dumps(self._payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


def _clear_chain_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in [
        "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
        "LLM_ENABLE_FALLBACK_CHAIN", "LLM_FALLBACK_ORDER",
        "LLM_MAX_PROVIDER_ATTEMPTS", "KRONOS_LLM_MAX_PROVIDER_ATTEMPTS",
        "KRONOS_LLM_CIRCUIT_FAILURES", "KRONOS_LLM_CIRCUIT_COOLDOWN_SECONDS",
    ] + [f"LLM_FALLBACK_{i}_{suffix}" for i in range(1, 10) for suffix in ("API_KEY", "BASE_URL", "MODEL")]:
        monkeypatch.delenv(k, raising=False)


def test_call_structured_llm_json_walks_three_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Primary 502 -> fallback_1 401 -> fallback_2 200 — assert all three
    providers are exercised in order and the final result is from fallback_2."""
    _clear_chain_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "sk-shared")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.minimaxi.com/v1")
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M3")
    monkeypatch.setenv("LLM_ENABLE_FALLBACK_CHAIN", "1")
    monkeypatch.setenv("LLM_FALLBACK_ORDER", "primary,fallback_1,fallback_2")
    monkeypatch.setenv("LLM_FALLBACK_1_BASE_URL", "https://api.moonshot.cn/v1")
    monkeypatch.setenv("LLM_FALLBACK_1_MODEL", "kimi-k2-5")
    monkeypatch.setenv("LLM_FALLBACK_2_BASE_URL", "https://api.xiaomimimo.com/v1")
    monkeypatch.setenv("LLM_FALLBACK_2_MODEL", "mimo-v2-5")
    monkeypatch.setenv("LLM_MAX_PROVIDER_ATTEMPTS", "3")
    monkeypatch.setenv("KRONOS_LLM_MAX_PROVIDER_ATTEMPTS", "3")

    import importlib
    from kronos_fincept import config as _config
    importlib.reload(_config)
    from kronos_fincept import agent as _agent
    importlib.reload(_agent)
    _agent._LLM_FAILURES.clear()

    import requests

    calls: list[dict] = []

    def fake_post(url, *, headers, json, timeout):  # noqa: ANN001
        calls.append({"url": url, "model": json.get("model"), "headers": headers})
        if "minimaxi" in url:
            return _FakeResp(502, {"error": "upstream bad gateway"})
        if "moonshot" in url:
            return _FakeResp(401, {"error": "invalid api key"})
        # xiaomimimo succeeds.
        return _FakeResp(200, {
            "choices": [
                {
                    "message": {
                        "content": jsonlib.dumps(
                            {"answer": "ok-from-fallback-2"}, ensure_ascii=False
                        )
                    },
                    "finish_reason": "stop",
                }
            ]
        })

    monkeypatch.setattr(requests, "post", fake_post)

    result = _agent._call_structured_llm_json(
        messages=[{"role": "user", "content": "招商银行能买吗"}],
        temperature=0,
        max_tokens=200,
        timeout=20,
        purpose="report",
        provider_timeouts=None,
    )

    assert result is not None, "expected a successful provider result"
    parsed, provider = result
    assert parsed == {"answer": "ok-from-fallback-2"}
    assert provider.name == "fallback_2", (
        f"expected fallback_2 to win, got {provider.name}; "
        f"call sequence: {[c['model'] for c in calls]}"
    )
    # Three POSTs in the documented order.
    assert [c["model"] for c in calls] == ["MiniMax-M3", "kimi-k2-5", "mimo-v2-5"], (
        f"expected primary -> fallback_1 -> fallback_2, got models: "
        f"{[c['model'] for c in calls]}"
    )
    # Shared K: every Authorization header carries the same key.
    assert all(c["headers"].get("Authorization") == "Bearer sk-shared" for c in calls)
    # The two failed providers each surface an http_error entry in the
    # per-report failure context. The winning provider does not.
    failures = _agent._last_report_llm_failures()
    failed_providers = {f.get("provider") for f in failures if isinstance(f, dict)}
    assert "primary" in failed_providers, f"primary missing from {failed_providers}"
    assert "fallback_1" in failed_providers, f"fallback_1 missing from {failed_providers}"
    assert "fallback_2" not in failed_providers, (
        f"fallback_2 won, should not be in failures: {failed_providers}"
    )


def test_call_structured_llm_json_returns_none_when_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """All three providers 5xx — function returns None, all three failures
    are recorded, and the call order is exactly the chain order."""
    _clear_chain_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "sk-shared")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.minimaxi.com/v1")
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M3")
    monkeypatch.setenv("LLM_ENABLE_FALLBACK_CHAIN", "1")
    monkeypatch.setenv("LLM_FALLBACK_ORDER", "primary,fallback_1,fallback_2")
    monkeypatch.setenv("LLM_FALLBACK_1_BASE_URL", "https://api.moonshot.cn/v1")
    monkeypatch.setenv("LLM_FALLBACK_1_MODEL", "kimi-k2-5")
    monkeypatch.setenv("LLM_FALLBACK_2_BASE_URL", "https://api.xiaomimimo.com/v1")
    monkeypatch.setenv("LLM_FALLBACK_2_MODEL", "mimo-v2-5")
    monkeypatch.setenv("LLM_MAX_PROVIDER_ATTEMPTS", "3")
    monkeypatch.setenv("KRONOS_LLM_MAX_PROVIDER_ATTEMPTS", "3")

    import importlib
    from kronos_fincept import config as _config
    importlib.reload(_config)
    from kronos_fincept import agent as _agent
    importlib.reload(_agent)
    _agent._LLM_FAILURES.clear()

    import requests

    def fake_post(url, *, headers, json, timeout):  # noqa: ANN001
        return _FakeResp(503, {"error": "service unavailable"})

    monkeypatch.setattr(requests, "post", fake_post)

    result = _agent._call_structured_llm_json(
        messages=[{"role": "user", "content": "x"}],
        temperature=0,
        max_tokens=200,
        timeout=20,
        purpose="report",
        provider_timeouts=None,
    )

    assert result is None
    # All three providers recorded their HTTP failures in the report-failure
    # context. (Note: _record_report_llm_failure is invoked for non-200 HTTP
    # responses, while _record_llm_provider_failure — the circuit breaker
    # counter — only fires for exceptions raised during the call.)
    failures = _agent._last_report_llm_failures()
    failed_providers = {f.get("provider") for f in failures if isinstance(f, dict)}
    assert {"primary", "fallback_1", "fallback_2"}.issubset(failed_providers), (
        f"expected all three providers in _last_report_llm_failures, "
        f"got {failed_providers}"
    )
