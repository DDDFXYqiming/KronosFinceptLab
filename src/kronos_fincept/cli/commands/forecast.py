"""kronos forecast — Single-asset OHLCV prediction.

Examples:
    kronos forecast --symbol 600519 --pred-len 5
    kronos forecast --symbol 600519 --pred-len 5 --dry-run
    kronos forecast --symbol 600519 --pred-len 5 --output table
    kronos forecast --input request.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from kronos_fincept.cli.output import (
    format_forecast_table,
    output_json,
    output_table,
)


@click.command("forecast")
@click.option("--symbol", "-s", type=str, help="A-stock symbol, e.g. 600519")
@click.option("--pred-len", "-p", type=int, default=5, help="Prediction length (bars)")
@click.option("--start", type=str, default=None, help="Start date YYYYMMDD (optional)")
@click.option("--end", type=str, default=None, help="End date YYYYMMDD (optional)")
@click.option("--dry-run", is_flag=True, default=False, help="Use mock predictor")
@click.option("--input", "input_file", type=click.Path(exists=True),
              help="Read request from JSON file instead of fetching data")
@click.option("--temperature", type=float, default=1.0, help="Sampling temperature")
@click.option("--top-k", type=int, default=0, help="Top-K sampling")
@click.option("--top-p", type=float, default=0.9, help="Top-P sampling")
@click.pass_context
def forecast_cmd(
    ctx: click.Context,
    symbol: str | None,
    pred_len: int,
    start: str | None,
    end: str | None,
    dry_run: bool,
    input_file: str | None,
    temperature: float,
    top_k: int,
    top_p: float,
) -> None:
    """Run single-asset OHLCV forecast."""
    output_format = ctx.obj.get("output_format", "json")

    # Load request from file or build from symbol
    if input_file:
        with open(input_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        if not symbol:
            click.echo("Error: --symbol is required (or use --input)", err=True)
            raise SystemExit(1)

        # Fetch data via AkShare
        rows = _fetch_a_stock_data(symbol, start, end)
        if not rows:
            click.echo(f"Error: No data fetched for {symbol}", err=True)
            raise SystemExit(1)

        payload = {
            "symbol": symbol,
            "timeframe": "1d",
            "pred_len": pred_len,
            "rows": rows,
            "dry_run": dry_run,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p,
        }

    # Run forecast
    from kronos_fincept.schemas import ForecastRequest
    from kronos_fincept.service import forecast_from_request

    try:
        request = ForecastRequest.from_dict(payload)
        result = forecast_from_request(request)
    except Exception as exc:
        error_result = {"ok": False, "error": str(exc)}
        if output_format == "json":
            output_json(error_result)
        else:
            click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    # Output
    if output_format == "json":
        output_json(result)
    else:
        title, headers, rows_data = format_forecast_table(result)
        output_table(title, headers, rows_data)
        # Print metadata
        meta = result.get("metadata", {})
        click.echo(f"⏱  {meta.get('elapsed_ms', 0)}ms | "
                    f"Device: {meta.get('device', 'unknown')} | "
                    f"Backend: {meta.get('backend', 'unknown')}")
        click.echo(f"⚠️  {meta.get('warning', '')}")


def _fetch_a_stock_data(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch A-stock data via AkShare. Returns OHLCV rows."""
    try:
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
        return fetch_a_stock_ohlcv(
            symbol=symbol,
            start_date=start_date or "20250101",
            end_date=end_date or "20261231",
        )
    except Exception as exc:
        click.echo(f"Warning: Failed to fetch data via AkShare: {exc}", err=True)
        return []
