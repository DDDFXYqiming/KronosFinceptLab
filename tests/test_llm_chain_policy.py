from __future__ import annotations

import ast
from pathlib import Path

from kronos_fincept import agent
from kronos_fincept.agent import AgentRouteDecision, AgentToolCall, ResolvedSymbol
from kronos_fincept.config import LLMProviderConfig


ROOT = Path(__file__).resolve().parents[1]


def test_llm_default_model_uses_LLM_compatible_default(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)

    assert LLMProviderConfig().model == "gpt-4o-mini"


def test_legacy_ai_advisor_module_is_not_exported():
    package_init = (ROOT / "src/kronos_fincept/financial/__init__.py").read_text(encoding="utf-8")

    assert "AIInvestmentAdvisor" not in package_init
    assert "AIAnalysisResult" not in package_init
    assert ".ai_advisor" not in package_init
    assert not (ROOT / "src/kronos_fincept/financial/ai_advisor.py").exists()


def test_ai_analyze_api_uses_agent_chain_not_legacy_advisor():
    route_source = (ROOT / "src/kronos_fincept/api/routes/ai_analyze.py").read_text(encoding="utf-8")
    tree = ast.parse(route_source)

    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)

    assert "AIInvestmentAdvisor" not in imported_names
    assert "analyze_investment_question" in route_source


def test_multi_asset_agent_context_build_is_parallel_and_capped_at_five(monkeypatch):
    max_workers_seen: list[int] = []
    symbols = [ResolvedSymbol(f"00000{i}", "cn", f"测试{i}") for i in range(6)]

    class FakeExecutor:
        def __init__(self, max_workers: int, thread_name_prefix: str):
            max_workers_seen.append(max_workers)
            self.thread_name_prefix = thread_name_prefix

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def map(self, fn, items):
            return [fn(item) for item in items]

    monkeypatch.setattr("concurrent.futures.ThreadPoolExecutor", FakeExecutor)
    monkeypatch.setattr(
        agent,
        "_call_llm_router",
        lambda *args, **kwargs: AgentRouteDecision(allowed=True, symbols=symbols, source="test"),
    )
    monkeypatch.setattr(
        agent,
        "_build_asset_context",
        lambda item, **kwargs: (
            {"symbol": item.symbol, "market": item.market, "market_data": {"current_price": 1.0}},
            [AgentToolCall(name="行情", status="completed", summary=item.symbol)],
        ),
    )
    monkeypatch.setattr(agent, "_build_batch_predictions", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        agent,
        "_generate_report",
        lambda question, context: (
            {"conclusion": "ok", "recommendation": "持有", "confidence": 0.5, "risk_level": "中"},
            AgentToolCall(name="LLM 汇总", status="completed", summary="ok"),
        ),
    )

    result = agent.analyze_investment_question("比较多只股票", dry_run=True)

    assert result.ok is True
    assert result.symbols == [item.symbol for item in symbols]
    assert max_workers_seen == [5]
