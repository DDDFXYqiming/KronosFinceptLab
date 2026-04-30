"""kronos data — Data fetching and search commands.

Examples:
    kronos data fetch --symbol 600519 --start 20240101 --end 20260430
    kronos data search --q 茅台
"""

from __future__ import annotations

import json

import click

from kronos_fincept.cli.output import (
    format_data_table,
    output_json,
    output_table,
)


@click.group("data")
def data_group() -> None:
    """Data fetching and search commands."""
    pass


@data_group.command("fetch")
@click.option("--symbol", "-s", type=str, required=True, help="A-stock symbol")
@click.option("--start", type=str, required=True, help="Start date YYYYMMDD")
@click.option("--end", type=str, required=True, help="End date YYYYMMDD")
@click.option("--adjust", type=str, default="qfq",
              help="Price adjustment: qfq (forward), hfq (backward), '' (none)")
@click.pass_context
def data_fetch(ctx: click.Context, symbol: str, start: str, end: str, adjust: str) -> None:
    """Fetch A-stock historical OHLCV data."""
    output_format = ctx.obj.get("output_format", "json")

    from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv

    try:
        rows = fetch_a_stock_ohlcv(symbol, start, end, adjust)
    except Exception as exc:
        error = {"ok": False, "symbol": symbol, "error": str(exc)}
        if output_format == "json":
            output_json(error)
        else:
            click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    result = {"ok": True, "symbol": symbol, "count": len(rows), "rows": rows}

    if output_format == "json":
        output_json(result)
    else:
        title, headers, rows_data = format_data_table(result)
        output_table(title, headers, rows_data)


@data_group.command("search")
@click.option("--q", "query", type=str, required=True, help="Search keyword")
@click.pass_context
def data_search(ctx: click.Context, query: str) -> None:
    """Search A-stock by code or name."""
    output_format = ctx.obj.get("output_format", "json")

    from kronos_fincept.akshare_adapter import search_stocks

    try:
        results = search_stocks(query)
        result = {"ok": True, "results": results}
    except Exception as exc:
        result = {"ok": True, "results": []}
        click.echo(f"Warning: Search failed: {exc}", err=True)

    if output_format == "json":
        output_json(result)
    else:
        from kronos_fincept.cli.output import output_table as _ot
        headers = ["Code", "Name", "Market"]
        rows_data = [[r["code"], r["name"], r["market"]] for r in result["results"]]
        _ot(f"[search] {query}", headers, rows_data)
