"""kronos data — Data fetching, export, indicators, and search commands.

Examples:
    kronos data fetch --symbol 600036 --market cn --start 20240101 --end 20260430 --csv out.csv
    kronos data fetch --symbol AAPL --market us --start 20240101 --end 20260430
    kronos data indicator --symbol 600036 --market cn
    kronos data search --q 招商银行
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import click

from kronos_fincept.cli.output import format_data_table, output_json, output_table


@click.group("data")
def data_group() -> None:
    """Data fetching, export, indicators, and search commands."""
    pass


def _write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["timestamp", "open", "high", "low", "close", "volume", "amount"]
    with target.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _fetch_market_rows(symbol: str, market: str, start: str, end: str, adjust: str) -> list[dict[str, Any]]:
    if market == "cn":
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
        return fetch_a_stock_ohlcv(symbol, start, end, adjust)
    from kronos_fincept.financial import GlobalMarketSource
    source = GlobalMarketSource()
    return source.fetch_data(symbol, start, end, market=market)


@data_group.command("fetch")
@click.option("--symbol", "-s", type=str, required=True, help="Symbol (e.g., 600036, AAPL, 00700)")
@click.option("--market", type=click.Choice(["cn", "us", "hk", "commodity"]), default="cn", help="Market")
@click.option("--type", "asset_type", type=click.Choice(["stock", "crypto"]), default="stock", help="Legacy asset type")
@click.option("--start", type=str, default=None, help="Start date YYYYMMDD")
@click.option("--end", type=str, default=None, help="End date YYYYMMDD")
@click.option("--timeframe", type=str, default="1d", help="Timeframe for crypto: 1m, 5m, 15m, 1h, 4h, 1d")
@click.option("--limit", type=int, default=100, help="Number of bars for crypto")
@click.option("--adjust", type=str, default="qfq", help="A-stock price adjustment: qfq, hfq, or ''")
@click.option("--csv", "csv_path", type=str, default=None, help="Write OHLCV rows to CSV path")
@click.pass_context
def data_fetch(ctx: click.Context, symbol: str, market: str, asset_type: str, start: str | None, end: str | None, timeframe: str, limit: int, adjust: str, csv_path: str | None) -> None:
    """Fetch historical OHLCV data."""
    output_format = ctx.obj.get("output_format", "json")
    try:
        if asset_type == "crypto":
            from kronos_fincept.akshare_adapter import fetch_crypto_ohlcv
            rows = fetch_crypto_ohlcv(symbol, timeframe, limit)
            market_out = "crypto"
        else:
            start = start or "20250101"
            end = end or "20261231"
            rows = _fetch_market_rows(symbol, market, start, end, adjust)
            market_out = market
        if csv_path:
            _write_csv(csv_path, rows)
    except Exception as exc:
        error = {"ok": False, "symbol": symbol, "market": market, "error": str(exc)}
        if output_format == "json":
            output_json(error)
        else:
            click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    result = {"ok": True, "symbol": symbol, "market": market_out, "count": len(rows), "rows": rows}
    if csv_path:
        result["csv"] = csv_path
    if output_format == "json":
        output_json(result)
    else:
        title, headers, rows_data = format_data_table(result)
        output_table(title, headers, rows_data)
        if csv_path:
            click.echo(f"[csv] {csv_path}")


@data_group.command("indicator")
@click.option("--symbol", "-s", type=str, required=True, help="Symbol to calculate indicators for")
@click.option("--market", type=click.Choice(["cn", "us", "hk", "commodity"]), default="cn", help="Market")
@click.option("--start", type=str, default="20250101", help="Start date YYYYMMDD")
@click.option("--end", type=str, default="20260430", help="End date YYYYMMDD")
@click.pass_context
def data_indicator(ctx: click.Context, symbol: str, market: str, start: str, end: str) -> None:
    """Calculate technical indicators for fetched market data."""
    output_format = ctx.obj.get("output_format", "json")
    try:
        from kronos_fincept.financial import TechnicalIndicators
        rows = _fetch_market_rows(symbol, market, start, end, "qfq")
        if len(rows) < 30:
            raise ValueError(f"Insufficient data for indicators: {len(rows)} rows")
        closes = [row["close"] for row in rows]
        highs = [row["high"] for row in rows]
        lows = [row["low"] for row in rows]
        volumes = [row.get("volume", 0) for row in rows]
        ti = TechnicalIndicators()
        indicators = ti.calculate_all_indicators(closes, highs, lows, volumes)
        result = {"ok": True, "symbol": symbol, "market": market, "current_price": rows[-1]["close"], "indicators": {name: obj.__dict__ if hasattr(obj, "__dict__") else obj for name, obj in indicators.items()}, "data_points": len(rows)}
    except Exception as exc:
        result = {"ok": False, "symbol": symbol, "market": market, "error": str(exc)}
        if output_format == "json":
            output_json(result)
        else:
            click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    if output_format == "json":
        output_json(result)
    else:
        rows_data = [[name, str(value)] for name, value in result["indicators"].items()]
        output_table(f"[indicator] {symbol} ({market})", ["Indicator", "Value"], rows_data)


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
        headers = ["Code", "Name", "Market"]
        rows_data = [[r["code"], r["name"], r["market"]] for r in result["results"]]
        output_table(f"[search] {query}", headers, rows_data)
