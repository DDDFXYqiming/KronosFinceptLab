"""Real DeepSeek integration checks for API, CLI, MCP, and concurrency.

These tests intentionally do not mock LLM calls. They are skipped by default
because they require a live DeepSeek-compatible API key and network access.
Kronos model inference is avoided by using macro-analysis flows.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    os.environ.get("KRONOS_RUN_REAL_DEEPSEEK") != "1",
    reason="set KRONOS_RUN_REAL_DEEPSEEK=1 to run live DeepSeek integration tests",
)


def _assert_deepseek_only_payload(payload: dict[str, Any]) -> None:
    assert payload["ok"] is True
    tool_calls = payload.get("tool_calls") or []
    llm_calls = [
        call for call in tool_calls
        if isinstance(call, dict) and str(call.get("name", "")).endswith("汇总")
    ]
    assert llm_calls, payload
    assert any(call.get("status") == "completed" for call in llm_calls), llm_calls
    assert all((call.get("metadata") or {}).get("provider") != "openrouter" for call in llm_calls)
    assert any((call.get("metadata") or {}).get("provider") == "deepseek" for call in llm_calls), llm_calls


def _env_for_subprocess() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "OPENROUTER_API_KEY": "",
            "OPENROUTER_BASE_URL": "",
            "OPENROUTER_MODEL": "",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "KRONOS_LOW_MEMORY_DEFAULTS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_MAX_THREADS": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    return env


def test_real_deepseek_api_macro_path_uses_deepseek_only():
    from kronos_fincept.api.app import create_app
    from kronos_fincept.agent import _llm_provider_chain

    providers = _llm_provider_chain()
    assert [provider.name for provider in providers] == ["deepseek"]
    assert providers[0].model == "deepseek-v4-flash"

    client = TestClient(create_app())
    response = client.post(
        "/api/v1/analyze/macro",
        json={
            "question": "A股现在位置怎么样？请用一句结论加关键依据。",
            "mode": "fast",
            "context": {"entry": "web-macro"},
        },
    )

    assert response.status_code == 200
    _assert_deepseek_only_payload(response.json())


def test_real_deepseek_cli_macro_path_uses_deepseek_only():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "kronos_fincept.cli.main",
            "analyze",
            "macro",
            "--question",
            "黄金和美元目前哪个宏观信号更强？",
            "--output",
            "json",
        ],
        cwd=ROOT,
        env=_env_for_subprocess(),
        capture_output=True,
        text=True,
        timeout=100,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    _assert_deepseek_only_payload(json.loads(proc.stdout))


def test_real_deepseek_mcp_macro_path_uses_deepseek_only():
    import kronos_mcp.kronos_mcp_server as server

    result = asyncio.run(
        server.call_tool(
            "analyze_macro",
            {
                "query": "美债收益率和A股风险偏好现在是否冲突？",
                "language": "zh",
            },
        )
    )
    payload = json.loads(result[0].text)
    _assert_deepseek_only_payload(payload)


def test_real_deepseek_concurrent_macro_requests_do_not_mix_llm_state():
    from kronos_fincept.agent import analyze_macro_question

    questions = [
        "A股现在位置怎么样？",
        "黄金短期风险偏好如何？",
    ]

    def run(question: str) -> dict[str, Any]:
        return analyze_macro_question(question, context={"entry": "web-macro"}).to_dict()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, question) for question in questions]
        payloads = [future.result(timeout=120) for future in futures]

    assert len(payloads) == 2
    for payload in payloads:
        _assert_deepseek_only_payload(payload)
