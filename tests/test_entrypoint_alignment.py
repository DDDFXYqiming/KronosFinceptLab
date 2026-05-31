"""Entry-point alignment tests for CLI and MCP surfaces."""

from __future__ import annotations

import importlib
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path

from click.testing import CliRunner

from kronos_fincept.cli.main import cli

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestCLIAlignment:
    def test_cli_exposes_health_and_suggestions(self):
        result = CliRunner().invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "health" in result.output
        assert "suggestions" in result.output

    def test_cli_health_json(self):
        result = CliRunner().invoke(cli, ["health"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] in {"ok", "degraded"}
        assert "model_loaded" in data
        assert "capabilities" in data

    def test_cli_suggestions_uses_route_fallback(self, monkeypatch):
        from kronos_fincept.api.routes import suggestions as suggestions_route

        monkeypatch.setattr(
            suggestions_route,
            "_call_llm_for_suggestions",
            lambda *args, **kwargs: ["帮我看看招商银行现在能不能买", "分析一下 AAPL 和 NVDA 最近表现", "比较腾讯和阿里巴巴走势"],
        )
        suggestions_route._cache.clear()

        result = CliRunner().invoke(cli, ["suggestions", "--type", "analysis"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["questions"]
        assert data["type"] == "analysis"


@dataclass
class _FakeTool:
    name: str
    description: str
    inputSchema: dict


@dataclass
class _FakeTextContent:
    type: str
    text: str


class _FakeServer:
    def __init__(self, name: str):
        self.name = name

    def list_tools(self):
        def decorator(fn):
            return fn
        return decorator

    def call_tool(self):
        def decorator(fn):
            return fn
        return decorator

    def create_initialization_options(self):
        return {}

    async def run(self, *_args, **_kwargs):
        return None


def _install_fake_mcp(monkeypatch):
    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    stdio_module = types.ModuleType("mcp.server.stdio")
    types_module = types.ModuleType("mcp.types")

    server_module.Server = _FakeServer
    stdio_module.stdio_server = lambda: None
    types_module.Tool = _FakeTool
    types_module.TextContent = _FakeTextContent

    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.stdio", stdio_module)
    monkeypatch.setitem(sys.modules, "mcp.types", types_module)


class TestMCPAlignment:
    def test_mcp_exposes_web_api_core_tools(self, monkeypatch):
        _install_fake_mcp(monkeypatch)
        module = importlib.import_module("kronos_mcp.kronos_mcp_server")
        module = importlib.reload(module)

        tools = {tool.name for tool in module.asyncio.run(module.list_tools())}

        assert {
            "forecast_ohlcv",
            "batch_forecast_ohlcv",
            "fetch_a_stock",
            "search_stocks",
            "calculate_indicators",
            "get_money_flow",
            "get_sector_flow",
            "get_hsgt_flow",
            "get_source_market_artifact",
            "run_ranking_backtest",
            "generate_backtest_report",
            "analyze_agent",
            "analyze_macro",
            "generate_suggestions",
            "fetch_rss_news",
            "health_check",
        }.issubset(tools)
