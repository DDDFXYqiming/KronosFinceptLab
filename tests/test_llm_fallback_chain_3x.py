"""Verify the LLM fallback chain returns all configured providers in order.

User contract: the chain is configured by
  LLM_API_KEY  + LLM_BASE_URL  + LLM_MODEL           (primary)
  LLM_FALLBACK_{N}_API_KEY / _BASE_URL / _MODEL     (N = 1..9)
  LLM_FALLBACK_ORDER  = primary,fallback_1,...
  LLM_ENABLE_FALLBACK_CHAIN = 1
  KRONOS_LLM_MAX_PROVIDER_ATTEMPTS  (runtime budget; must be >= chain size)
and the user must be able to keep a single `LLM_API_KEY` shared across
all providers — the chain entries inherit `LLM_API_KEY` when their
own `LLM_FALLBACK_{N}_API_KEY` is blank.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest


def _clear_chain_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every LLM_* / KRONOS_LLM_* var so the test starts clean."""
    keys = [
        "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
        "LLM_ENABLE_FALLBACK_CHAIN", "LLM_FALLBACK_ORDER",
        "LLM_MAX_PROVIDER_ATTEMPTS", "KRONOS_LLM_MAX_PROVIDER_ATTEMPTS",
        "KRONOS_LLM_CIRCUIT_FAILURES", "KRONOS_LLM_CIRCUIT_COOLDOWN_SECONDS",
    ] + [f"LLM_FALLBACK_{i}_{suffix}" for i in range(1, 10) for suffix in ("API_KEY", "BASE_URL", "MODEL")]
    for k in keys:
        monkeypatch.delenv(k, raising=False)


def test_fallback_chain_returns_three_providers_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    # Build a fully isolated env mapping (no leakage from the developer-
    # machine `.env` that ``_load_dotenv()`` already loaded into ``os.environ``).
    env = {
        "LLM_API_KEY": "sk-shared",
        "LLM_BASE_URL": "https://api.minimaxi.com/v1",
        "LLM_MODEL": "MiniMax-M3",
        "LLM_ENABLE_FALLBACK_CHAIN": "1",
        "LLM_FALLBACK_ORDER": "primary,fallback_1,fallback_2",
        # N=1 and N=2 inherit the shared LLM_API_KEY — user wants a single K.
        "LLM_FALLBACK_1_BASE_URL": "https://api.moonshot.cn/v1",
        "LLM_FALLBACK_1_MODEL": "kimi-k2-5",
        "LLM_FALLBACK_2_BASE_URL": "https://api.xiaomimimo.com/v1",
        "LLM_FALLBACK_2_MODEL": "mimo-v2-5",
        "KRONOS_LLM_MAX_PROVIDER_ATTEMPTS": "3",
    }

    import importlib
    from kronos_fincept import config as _config
    importlib.reload(_config)

    # Assert against the lower-level config primitive so the test stays
    # deterministic regardless of the developer-machine ``.env`` that
    # ``_load_dotenv()`` already loaded into ``os.environ`` at import time.
    from kronos_fincept.config import LLMFallbackChainConfig
    chain = LLMFallbackChainConfig.from_env(env=env).get_ordered_providers()
    assert [p.name for p in chain] == ["primary", "fallback_1", "fallback_2"], (
        f"expected primary -> fallback_1 -> fallback_2, got {[p.name for p in chain]}"
    )
    assert [p.model for p in chain] == ["MiniMax-M3", "kimi-k2-5", "mimo-v2-5"]
    assert [p.base_url for p in chain] == [
        "https://api.minimaxi.com/v1",
        "https://api.moonshot.cn/v1",
        "https://api.xiaomimimo.com/v1",
    ]
    # Shared K rule: every provider reuses LLM_API_KEY when its own
    # LLM_FALLBACK_{N}_API_KEY is blank.
    assert all(p.api_key == "sk-shared" for p in chain), (
        f"all providers should inherit the shared LLM_API_KEY, "
        f"got api_keys={[p.api_key for p in chain]}"
    )


def test_fallback_chain_legacy_single_provider_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the unified-K contract (June 2026) fallback slots are surfaced
    purely by their BASE_URL / MODEL — ``LLM_ENABLE_FALLBACK_CHAIN`` is no
    longer a gate. This test pins that contract: with no fallback slots
    configured, the chain collapses to a single 'primary' entry. v107 tests
    stay unaffected because they build their own SimpleNamespace settings
    fixture rather than reading the real config object."""
    # Build a fully isolated env mapping (no leakage from the developer-
    # machine `.env` that ``_load_dotenv()`` already loaded into ``os.environ``).
    env = {
        "LLM_API_KEY": "sk-test",
        "LLM_BASE_URL": "https://llm.example/v1",
        "LLM_MODEL": "test-model",
    }
    # No LLM_FALLBACK_N_BASE_URL / LLM_FALLBACK_N_MODEL set anywhere.

    import importlib
    from kronos_fincept import config as _config
    importlib.reload(_config)
    from kronos_fincept import agent as _agent
    importlib.reload(_agent)

    # The agent's _llm_provider_chain() reads the real Settings singleton
    # which is built from os.environ. We assert against the same env via
    # the lower-level config primitive so the test stays deterministic.
    from kronos_fincept.config import LLMFallbackChainConfig
    chain_cfg = LLMFallbackChainConfig.from_env(env=env)
    ordered = chain_cfg.get_ordered_providers()
    assert [p.name for p in ordered] == ["primary"], (
        f"expected only primary (no fallback slots configured), "
        f"got {[p.name for p in ordered]}"
    )
    assert ordered[0].model == "test-model"
