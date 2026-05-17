#!/usr/bin/env python3
"""KronosFinceptLab MCP Server.

Exposes Kronos financial K-line forecasting as MCP tools for AI Agents.

Tools:
  - forecast_ohlcv:       Single-asset OHLCV K-line forecast
  - batch_forecast_ohlcv: Multi-asset batch forecast with predicted_return ranking
  - fetch_a_stock:        Fetch real A-share daily OHLCV data via AkShare

Usage:
  # stdio transport (default, for local MCP clients)
  python mcp/kronos_mcp_server.py

  # or via module
  python -m mcp.kronos_mcp_server
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from kronos_fincept.logging_config import configure_logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — these are heavy (torch, akshare) so we defer until first use
# ---------------------------------------------------------------------------
_service = None
_akshare_adapter = None


def _ensure_src_path() -> None:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))


def _get_service():
    global _service
    if _service is None:
        # Ensure kronos_fincept is importable
        _ensure_src_path()
        from kronos_fincept.service import batch_forecast_from_requests, forecast_from_request
        from kronos_fincept.schemas import ForecastRequest

        _service = {
            "forecast": forecast_from_request,
            "batch_forecast": batch_forecast_from_requests,
            "ForecastRequest": ForecastRequest,
        }
    return _service


def _get_akshare_adapter():
    global _akshare_adapter
    if _akshare_adapter is None:
        _ensure_src_path()
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv

        _akshare_adapter = {"fetch": fetch_a_stock_ohlcv}
    return _akshare_adapter


# ---------------------------------------------------------------------------
# MCP Server definition
# ---------------------------------------------------------------------------
app = Server("kronos-fincept-lab")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="forecast_ohlcv",
            description=(
                "Forecast future OHLCV K-line data for a single financial asset using the Kronos "
                "time-series foundation model. Accepts historical candlestick data and returns "
                "predicted future candles. Research use only — not trading advice."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Asset symbol, e.g. '600036' (A-share), 'BTC/USDT' (crypto)",
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Data timeframe, e.g. '1d', '1h', '15m'",
                        "default": "1d",
                    },
                    "pred_len": {
                        "type": "integer",
                        "description": "Number of future candles to predict",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 120,
                    },
                    "rows": {
                        "type": "array",
                        "description": "Historical OHLCV candles, sorted by time ascending",
                        "items": {
                            "type": "object",
                            "properties": {
                                "timestamp": {"type": "string", "description": "ISO 8601 timestamp"},
                                "open": {"type": "number"},
                                "high": {"type": "number"},
                                "low": {"type": "number"},
                                "close": {"type": "number"},
                                "volume": {"type": "number", "default": 0},
                                "amount": {"type": "number", "default": 0},
                            },
                            "required": ["timestamp", "open", "high", "low", "close"],
                        },
                        "minItems": 10,
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, use deterministic mock predictor (no model loading)",
                        "default": False,
                    },
                    "model_id": {
                        "type": "string",
                        "description": "HuggingFace model ID",
                        "default": "NeoQuasar/Kronos-base",
                    },
                },
                "required": ["symbol", "rows", "pred_len"],
            },
        ),
        Tool(
            name="batch_forecast_ohlcv",
            description=(
                "Batch forecast multiple financial assets and rank them by predicted return. "
                "Returns a ranked table of assets sorted by expected return (best first). "
                "Useful for portfolio screening and Top-K strategy. Research use only."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "assets": {
                        "type": "array",
                        "description": "List of assets to forecast",
                        "items": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"},
                                "rows": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "timestamp": {"type": "string"},
                                            "open": {"type": "number"},
                                            "high": {"type": "number"},
                                            "low": {"type": "number"},
                                            "close": {"type": "number"},
                                            "volume": {"type": "number", "default": 0},
                                            "amount": {"type": "number", "default": 0},
                                        },
                                        "required": ["timestamp", "open", "high", "low", "close"],
                                    },
                                    "minItems": 10,
                                },
                            },
                            "required": ["symbol", "rows"],
                        },
                        "minItems": 1,
                    },
                    "pred_len": {
                        "type": "integer",
                        "description": "Number of future candles per asset",
                        "default": 5,
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": False,
                    },
                    "model_id": {
                        "type": "string",
                        "default": "NeoQuasar/Kronos-base",
                    },
                },
                "required": ["assets", "pred_len"],
            },
        ),
        Tool(
            name="fetch_a_stock",
            description=(
                "Fetch real A-share (Chinese stock market) daily OHLCV data via AkShare. "
                "Returns historical candlestick data suitable for Kronos forecasting. "
                "Symbol format: 6-digit code, e.g. '600036' (China Merchants Bank), '000858' (Wuliangye)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "6-digit A-share stock code, e.g. '600036'",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYYMMDD format, e.g. '20240101'",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYYMMDD format, e.g. '20260429'",
                    },
                },
                "required": ["symbol", "start_date", "end_date"],
            },
        ),
        Tool(
            name="search_stocks",
            description="Search A-share stocks by code or Chinese name, aligned with GET /api/data/search.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Stock code or name keyword"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="calculate_indicators",
            description="Calculate technical indicators for a stock, aligned with GET /api/data/indicator/{symbol}.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "market": {"type": "string", "default": "cn"},
                    "start_date": {"type": "string", "default": "20250101"},
                    "end_date": {"type": "string", "default": "20260430"},
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="run_ranking_backtest",
            description="Run ranking strategy backtest, aligned with POST /api/backtest/ranking.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "top_k": {"type": "integer", "default": 3},
                    "pred_len": {"type": "integer", "default": 5},
                    "window_size": {"type": "integer", "default": 60},
                    "step": {"type": "integer", "default": 5},
                    "dry_run": {"type": "boolean", "default": True},
                },
                "required": ["symbols", "start_date", "end_date"],
            },
        ),
        Tool(
            name="generate_backtest_report",
            description="Generate HTML backtest report, aligned with POST /api/backtest/report.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "strategy_name": {"type": "string", "default": "Ranking Strategy"},
                    "top_k": {"type": "integer", "default": 3},
                    "dry_run": {"type": "boolean", "default": True},
                },
                "required": ["symbols", "start_date", "end_date"],
            },
        ),
        Tool(
            name="analyze_agent",
            description="Run agent-style stock analysis, aligned with POST /api/v1/analyze/agent.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "language": {"type": "string", "default": "zh"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="analyze_macro",
            description="Run macro/cross-market analysis, aligned with POST /api/v1/analyze/macro.",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "language": {"type": "string", "default": "zh"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="generate_suggestions",
            description="Generate analysis or macro question suggestions, aligned with GET /api/v1/suggestions.",
            inputSchema={
                "type": "object",
                "properties": {"type": {"type": "string", "enum": ["analysis", "macro"], "default": "analysis"}},
            },
        ),
        Tool(
            name="health_check",
            description="Return service health diagnostics, aligned with GET /api/health.",
            inputSchema={
                "type": "object",
                "properties": {"deep": {"type": "boolean", "default": False}},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "forecast_ohlcv":
            return _handle_forecast(arguments)
        elif name == "batch_forecast_ohlcv":
            return _handle_batch_forecast(arguments)
        elif name == "fetch_a_stock":
            return _handle_fetch_a_stock(arguments)
        elif name == "search_stocks":
            return _handle_search_stocks(arguments)
        elif name == "calculate_indicators":
            return _handle_calculate_indicators(arguments)
        elif name == "run_ranking_backtest":
            return await _handle_run_ranking_backtest(arguments)
        elif name == "generate_backtest_report":
            return await _handle_generate_backtest_report(arguments)
        elif name == "analyze_agent":
            return await _handle_analyze_agent(arguments)
        elif name == "analyze_macro":
            return await _handle_analyze_macro(arguments)
        elif name == "generate_suggestions":
            return await _handle_generate_suggestions(arguments)
        elif name == "health_check":
            return _handle_health_check(arguments)
        else:
            return _json_text({"ok": False, "error": f"Unknown tool: {name}"})
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return _json_text({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _json_text(result: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2, default=str))]

def _handle_forecast(args: dict[str, Any]) -> list[TextContent]:
    svc = _get_service()
    req = svc["ForecastRequest"].from_dict({
        "symbol": args["symbol"],
        "timeframe": args.get("timeframe", "1d"),
        "pred_len": args["pred_len"],
        "rows": args["rows"],
        "dry_run": args.get("dry_run", False),
        "model_id": args.get("model_id", "NeoQuasar/Kronos-base"),
    })
    result = svc["forecast"](req)
    return _json_text(result)


def _handle_batch_forecast(args: dict[str, Any]) -> list[TextContent]:
    svc = _get_service()
    assets = args["assets"]
    pred_len = args["pred_len"]
    dry_run = args.get("dry_run", False)
    model_id = args.get("model_id", "NeoQuasar/Kronos-base")

    requests = []
    for asset in assets:
        req = svc["ForecastRequest"].from_dict({
            "symbol": asset["symbol"],
            "timeframe": asset.get("timeframe", "1d"),
            "pred_len": pred_len,
            "rows": asset["rows"],
            "dry_run": dry_run,
            "model_id": model_id,
        })
        requests.append(req)

    signals = svc["batch_forecast"](requests)
    result = {
        "ok": True,
        "count": len(signals),
        "rankings": [
            {
                "rank": s.rank,
                "symbol": s.symbol,
                "last_close": s.last_close,
                "predicted_close": s.predicted_close,
                "predicted_return_pct": round(s.predicted_return * 100, 3),
                "signal": "BUY" if s.predicted_return > 0.001 else ("SELL" if s.predicted_return < -0.001 else "HOLD"),
                "elapsed_ms": s.elapsed_ms,
            }
            for s in signals
        ],
        "metadata": {"warning": "Research forecast only; not trading advice."},
    }
    return _json_text(result)


def _handle_fetch_a_stock(args: dict[str, Any]) -> list[TextContent]:
    adapter = _get_akshare_adapter()
    symbol = args["symbol"]
    start_date = args["start_date"]
    end_date = args["end_date"]

    rows = adapter["fetch"](symbol=symbol, start_date=start_date, end_date=end_date)
    result = {
        "ok": True,
        "symbol": symbol,
        "count": len(rows),
        "rows": rows,
    }
    return _json_text(result)



def _model_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def _handle_search_stocks(args: dict[str, Any]) -> list[TextContent]:
    _ensure_src_path()
    from kronos_fincept.akshare_adapter import search_stocks

    results = search_stocks(args["query"])
    return _json_text({"ok": True, "results": results})


def _handle_calculate_indicators(args: dict[str, Any]) -> list[TextContent]:
    _ensure_src_path()
    from kronos_fincept.cli.commands.data import _fetch_market_rows
    from kronos_fincept.financial import TechnicalIndicators

    symbol = args["symbol"]
    market = args.get("market", "cn")
    start_date = args.get("start_date", "20250101")
    end_date = args.get("end_date", "20260430")
    rows = _fetch_market_rows(symbol, market, start_date, end_date, "qfq")
    if len(rows) < 30:
        raise ValueError(f"Insufficient data for indicators: {len(rows)} rows")
    closes = [row["close"] for row in rows]
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    volumes = [row.get("volume", 0) for row in rows]
    indicators = TechnicalIndicators().calculate_all_indicators(closes, highs, lows, volumes)
    return _json_text({
        "ok": True,
        "symbol": symbol,
        "market": market,
        "current_price": rows[-1]["close"],
        "indicators": {name: obj.__dict__ if hasattr(obj, "__dict__") else obj for name, obj in indicators.items()},
        "data_points": len(rows),
    })


async def _handle_run_ranking_backtest(args: dict[str, Any]) -> list[TextContent]:
    _ensure_src_path()
    from kronos_fincept.api.models import BacktestRequestIn
    from kronos_fincept.api.routes.backtest import backtest_ranking

    req = BacktestRequestIn(**{
        "symbols": args["symbols"],
        "start_date": args["start_date"],
        "end_date": args["end_date"],
        "top_k": args.get("top_k", 3),
        "pred_len": args.get("pred_len", 5),
        "window_size": args.get("window_size", 60),
        "step": args.get("step", 5),
        "initial_equity": args.get("initial_equity", 100000.0),
        "benchmark": args.get("benchmark"),
        "fee_bps": args.get("fee_bps", 0.0),
        "slippage_bps": args.get("slippage_bps", 0.0),
        "dry_run": args.get("dry_run", True),
    })
    return _json_text(_model_to_dict(await backtest_ranking(req)))


async def _handle_generate_backtest_report(args: dict[str, Any]) -> list[TextContent]:
    _ensure_src_path()
    from kronos_fincept.api.models import BacktestReportRequestIn
    from kronos_fincept.api.routes.backtest import backtest_report

    req = BacktestReportRequestIn(**{
        "symbols": args["symbols"],
        "start_date": args["start_date"],
        "end_date": args["end_date"],
        "top_k": args.get("top_k", 3),
        "pred_len": args.get("pred_len", 5),
        "window_size": args.get("window_size", 60),
        "step": args.get("step", 5),
        "initial_equity": args.get("initial_equity", 100000.0),
        "fee_bps": args.get("fee_bps", 0.0),
        "slippage_bps": args.get("slippage_bps", 0.0),
        "dry_run": args.get("dry_run", True),
        "benchmark": args.get("benchmark"),
        "strategy_name": args.get("strategy_name", "Ranking Strategy"),
    })
    return _json_text(_model_to_dict(await backtest_report(req)))


async def _handle_analyze_agent(args: dict[str, Any]) -> list[TextContent]:
    _ensure_src_path()
    from kronos_fincept.api.routes.ai_analyze import AgentAnalyzeRequest, agent_analyze

    req = AgentAnalyzeRequest(
        question=args["query"],
        symbol=args.get("symbol"),
        market=args.get("market"),
        context=args.get("context"),
        dry_run=args.get("dry_run", False),
    )
    return _json_text(_model_to_dict(await agent_analyze(req)))


async def _handle_analyze_macro(args: dict[str, Any]) -> list[TextContent]:
    _ensure_src_path()
    from kronos_fincept.api.routes.ai_analyze import MacroAnalyzeRequest, macro_analyze

    req = MacroAnalyzeRequest(
        question=args["query"],
        symbols=args.get("symbols", []),
        market=args.get("market"),
        provider_ids=args.get("provider_ids"),
        context=args.get("context"),
    )
    return _json_text(_model_to_dict(await macro_analyze(req)))


async def _handle_generate_suggestions(args: dict[str, Any]) -> list[TextContent]:
    _ensure_src_path()
    from kronos_fincept.api.routes.suggestions import get_suggestions

    suggestion_type = args.get("type", "analysis")
    result = await get_suggestions(type=suggestion_type)
    return _json_text({"ok": True, "type": suggestion_type, **result})


def _handle_health_check(args: dict[str, Any]) -> list[TextContent]:
    _ensure_src_path()
    from kronos_fincept.api.deps import get_model_info
    from kronos_fincept.build_info import get_build_info

    model_info = get_model_info(deep=args.get("deep", False))
    build_info = get_build_info()
    return _json_text({
        "status": model_info["status"],
        "version": "2.0.0",
        "app_version": build_info.app_version,
        "build_commit": build_info.build_commit,
        "build_ref": build_info.build_ref,
        "build_source": build_info.build_source,
        "model_loaded": model_info["model_loaded"],
        "model_id": model_info["model_id"],
        "tokenizer_id": model_info["tokenizer_id"],
        "device": model_info["device"],
        "uptime_seconds": 0.0,
        "runtime_mode": model_info["runtime_mode"],
        "model_enabled": model_info["model_enabled"],
        "deep_check": model_info["deep_check"],
        "capabilities": model_info["capabilities"],
        "model_error": model_info["model_error"],
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
