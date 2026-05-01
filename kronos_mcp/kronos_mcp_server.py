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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — these are heavy (torch, akshare) so we defer until first use
# ---------------------------------------------------------------------------
_service = None
_akshare_adapter = None


def _get_service():
    global _service
    if _service is None:
        # Ensure kronos_fincept is importable
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))
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
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))
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
        else:
            return [TextContent(type="text", text=json.dumps({"ok": False, "error": f"Unknown tool: {name}"}))]
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"ok": False, "error": str(e)}))]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

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
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


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
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


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
    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
