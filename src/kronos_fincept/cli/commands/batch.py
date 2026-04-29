"""kronos batch — Multi-asset batch prediction with ranking.

Examples:
    kronos batch --symbols 600519,000858,000001 --pred-len 5
    kronos batch --symbols 600519,000858 --pred-len 5 --dry-run --output table
"""

from __future__ import annotations

import json
from typing import Any

import click

from kronos_fincept.cli.output import (
    format_batch_table,
    output_json,
    output_table,
)


@click.command("batch")
@click.option("--symbols", "-s", type=str, required=True,
              help="Comma-separated stock symbols, e.g. 600519,000858")
@click.option("--pred-len", "-p", type=int, default=5, help="Prediction length (bars)")
@click.option("--dry-run", is_flag=True, default=False, help="Use mock predictor")
@click.pass_context
def batch_cmd(
    ctx: click.Context,
    symbols: str,
    pred_len: int,
    dry_run: bool,
) -> None:
    """Run batch forecast on multiple assets and rank by predicted return."""
    output_format = ctx.obj.get("output_format", "json")
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]

    if not symbol_list:
        click.echo("Error: --symbols cannot be empty", err=True)
        raise SystemExit(1)

    # Fetch data for each symbol
    from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
    from kronos_fincept.schemas import ForecastRequest
    from kronos_fincept.service import batch_forecast_from_requests

    requests = []
    for sym in symbol_list:
        try:
            rows = fetch_a_stock_ohlcv(sym, "20250101", "20261231")
        except Exception as exc:
            click.echo(f"Warning: Failed to fetch {sym}: {exc}", err=True)
            continue

        req = ForecastRequest(
            symbol=sym,
            timeframe="1d",
            pred_len=pred_len,
            rows=[],
            dry_run=dry_run,
        )
        # Build rows from dicts
        from kronos_fincept.schemas import ForecastRow
        req_rows = [ForecastRow.from_dict(r) for r in rows]
        req = ForecastRequest(
            symbol=sym,
            timeframe="1d",
            pred_len=pred_len,
            rows=req_rows,
            dry_run=dry_run,
        )
        requests.append(req)

    if not requests:
        click.echo("Error: No valid data for any symbol", err=True)
        raise SystemExit(1)

    signals = batch_forecast_from_requests(requests)

    # Build result
    result = {
        "ok": True,
        "rankings": [
            {
                "rank": sig.rank,
                "symbol": sig.symbol,
                "last_close": sig.last_close,
                "predicted_close": sig.predicted_close,
                "predicted_return": sig.predicted_return,
                "elapsed_ms": sig.elapsed_ms,
            }
            for sig in signals
        ],
        "metadata": {
            "device": "cpu",
            "elapsed_ms": sum(s.elapsed_ms for s in signals),
            "backend": "batch",
            "warning": "Research forecast only; not trading advice.",
        },
    }

    if output_format == "json":
        output_json(result)
    else:
        title, headers, rows_data = format_batch_table(result)
        output_table(title, headers, rows_data)
        click.echo(f"⚠️  {result['metadata']['warning']}")
