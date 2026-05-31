"""v11.2 watchlist, backtest job, alert preset, and MCP alignment tests."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_fake_mcp(monkeypatch):
    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    stdio_module = types.ModuleType("mcp.server.stdio")
    types_module = types.ModuleType("mcp.types")

    class _FakeServer:
        def __init__(self, name):
            self.name = name

        def list_tools(self):
            def decorator(fn):
                return fn
            return decorator

        def call_tool(self):
            def decorator(fn):
                return fn
            return decorator

    class _FakeTool:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _FakeTextContent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    server_module.Server = _FakeServer
    stdio_module.stdio_server = lambda: None
    types_module.Tool = _FakeTool
    types_module.TextContent = _FakeTextContent

    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.stdio", stdio_module)
    monkeypatch.setitem(sys.modules, "mcp.types", types_module)


def test_watchlist_research_builds_portfolio_summary():
    client = TestClient(create_app())

    resp = client.post("/api/watchlist/research", json={
        "name": "Core A-share watchlist",
        "symbols": ["600036", "000858", "300750"],
        "weights": {"600036": 0.5, "000858": 0.3, "300750": 0.2},
        "rankings": [
            {"symbol": "600036", "predicted_return": 0.03, "last_close": 35.0, "predicted_close": 36.05},
            {"symbol": "000858", "predicted_return": -0.01, "last_close": 140.0, "predicted_close": 138.6},
            {"symbol": "300750", "predicted_return": 0.02, "last_close": 180.0, "predicted_close": 183.6},
        ],
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["symbol_count"] == 3
    assert data["expected_return"] == 0.016
    assert data["top_symbols"] == ["600036", "300750", "000858"]
    assert data["risk_flags"] == []
    assert "Research forecast only" in data["metadata"]["warning"]


def test_backtest_can_be_submitted_as_trackable_job_without_starting_immediately():
    client = TestClient(create_app())

    resp = client.post("/api/jobs/backtest", json={
        "symbols": ["600036", "000858"],
        "start_date": "20250101",
        "end_date": "20260430",
        "top_k": 1,
        "dry_run": True,
        "start_immediately": False,
    })

    assert resp.status_code == 200
    submitted = resp.json()
    assert submitted["status"] == "queued"

    status = client.get(f"/api/jobs/{submitted['job_id']}").json()
    assert status["kind"] == "backtest"
    assert [step["name"] for step in status["steps"]] == ["行情数据", "回测执行", "指标汇总"]


def test_alert_prediction_deviation_preset_registers_rules_for_watchlist():
    client = TestClient(create_app())

    resp = client.post("/api/alert/presets/prediction-deviation", json={
        "symbols": ["600036", "000858"],
        "deviation_pct": 7.5,
        "market": "cn",
        "channel": "feishu",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["created"] == 2
    assert {rule["symbol"] for rule in data["rules"]} == {"600036", "000858"}
    assert all(rule["alert_type"] == "prediction_deviation" for rule in data["rules"])
    assert all(rule["params"]["deviation_pct"] == 7.5 for rule in data["rules"])


def test_mcp_exposes_v112_operations(monkeypatch):
    _install_fake_mcp(monkeypatch)
    module = importlib.import_module("kronos_mcp.kronos_mcp_server")
    module = importlib.reload(module)

    tools = {tool.name for tool in module.asyncio.run(module.list_tools())}

    assert {
        "submit_backtest_job",
        "get_job_status",
        "create_prediction_deviation_alerts",
        "macro_provider_status",
        "watchlist_research",
        "get_money_flow",
        "get_sector_flow",
        "get_hsgt_flow",
        "get_source_market_artifact",
        "fetch_rss_news",
    }.issubset(tools)
