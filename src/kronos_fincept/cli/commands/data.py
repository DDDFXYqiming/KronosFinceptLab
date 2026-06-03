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


def _data_manager_fetch(endpoint: str, cache_ttl: int, **kwargs: Any) -> dict[str, Any]:
    from kronos_fincept.data_sources.init import init_data_sources

    return init_data_sources().fetch(endpoint, use_cache=True, cache_ttl=cache_ttl, **kwargs)


def _result_or_exit(ctx: click.Context, result: dict[str, Any], *, default_error: str = "Data source error") -> dict[str, Any]:
    if result.get("success"):
        return result

    payload = {
        "ok": False,
        "source": result.get("source", "none"),
        "error": result.get("error") or default_error,
    }
    if ctx.obj.get("output_format", "json") == "json":
        output_json(payload)
    else:
        click.echo(f"Error: {payload['error']}", err=True)
    raise SystemExit(1)


def _render_rows_result(ctx: click.Context, payload: dict[str, Any], *, title: str, headers: list[str], keys: list[str]) -> None:
    if ctx.obj.get("output_format", "json") == "json":
        output_json(payload)
        return

    rows = payload.get("rows") or payload.get("data") or []
    if isinstance(rows, list):
        rows_data = [[str(row.get(key, "")) for key in keys] for row in rows[:20] if isinstance(row, dict)]
        output_table(title, headers, rows_data)
    else:
        output_json(payload)


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
@click.option("--start", type=str, default="", help="Start date YYYYMMDD (default: 1 year ago)")
@click.option("--end", type=str, default="", help="End date YYYYMMDD (default: today)")
@click.pass_context
def data_indicator(ctx: click.Context, symbol: str, market: str, start: str, end: str) -> None:
    """Calculate technical indicators for fetched market data."""
    output_format = ctx.obj.get("output_format", "json")
    # Default dates: last 1 year if not specified
    if not start or not end:
        from datetime import datetime, timedelta
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=365)
        start = start or start_dt.strftime("%Y%m%d")
        end = end or end_dt.strftime("%Y%m%d")
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
        # Serialize including @property values
        ind_result = {}
        for name, obj in indicators.items():
            if hasattr(obj, "__dict__"):
                row_d = {k: round(float(v), 4) if isinstance(v, (int, float)) else v
                         for k, v in obj.__dict__.items()}
                for attr in dir(obj):
                    if attr.startswith("_") or attr in row_d:
                        continue
                    try:
                        val = getattr(obj, attr)
                        if not callable(val) and isinstance(val, (int, float)):
                            row_d[attr] = round(float(val), 4)
                    except Exception:
                        pass
                ind_result[name] = row_d
            else:
                ind_result[name] = str(obj)
        result = {"ok": True, "symbol": symbol, "market": market, "current_price": rows[-1]["close"], "indicators": ind_result, "data_points": len(rows)}
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


@data_group.command("money-flow")
@click.option("--symbol", "-s", type=str, required=True, help="A-share/ETF symbol, e.g. 600036")
@click.option("--start", "start_date", type=str, default=None, help="Optional start date YYYYMMDD")
@click.option("--end", "end_date", type=str, default=None, help="Optional end date YYYYMMDD")
@click.option("--limit", type=int, default=60, show_default=True, help="Maximum rows")
@click.pass_context
def data_money_flow(ctx: click.Context, symbol: str, start_date: str | None, end_date: str | None, limit: int) -> None:
    """Fetch EastMoney main-money-flow rows."""
    raw = _result_or_exit(
        ctx,
        _data_manager_fetch(
            "eastmoney_money_flow",
            300,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        ),
    )
    rows = raw.get("data") or []
    payload = {
        "ok": True,
        "symbol": symbol,
        "market": "cn",
        "count": len(rows) if isinstance(rows, list) else raw.get("count", 0),
        "source": raw.get("source"),
        "from_cache": raw.get("from_cache", False),
        "from_stale_cache": raw.get("from_stale_cache", False),
        "rows": rows,
    }
    _render_rows_result(
        ctx,
        payload,
        title=f"[money-flow] {symbol}",
        headers=["Date", "Main Net", "Super Net", "Large Net", "Close", "Change"],
        keys=["date", "main_net_amount", "super_net_amount", "large_net_amount", "close", "change_pct"],
    )


@data_group.command("sector-flow")
@click.option(
    "--sector-type",
    type=str,
    default="industry",
    show_default=True,
    help="industry, concept, region, or raw EastMoney market id like m:90+t:2",
)
@click.pass_context
def data_sector_flow(ctx: click.Context, sector_type: str) -> None:
    """Fetch EastMoney sector/concept/region money-flow rankings."""
    raw = _result_or_exit(
        ctx,
        _data_manager_fetch("eastmoney_sector_flow", 300, sector_type=sector_type),
    )
    rows = raw.get("data") or []
    payload = {
        "ok": True,
        "market": "cn",
        "sector_type": sector_type,
        "count": len(rows) if isinstance(rows, list) else raw.get("count", 0),
        "source": raw.get("source"),
        "from_cache": raw.get("from_cache", False),
        "from_stale_cache": raw.get("from_stale_cache", False),
        "rows": rows,
    }
    _render_rows_result(
        ctx,
        payload,
        title=f"[sector-flow] {sector_type}",
        headers=["Name", "Code", "Change", "Main Net", "Rank"],
        keys=["name", "code", "change_pct", "main_net_amount", "rank"],
    )


@data_group.command("hsgt-flow")
@click.option("--start", "start_date", type=str, default=None, help="Optional start date YYYYMMDD")
@click.option("--end", "end_date", type=str, default=None, help="Optional end date YYYYMMDD")
@click.pass_context
def data_hsgt_flow(ctx: click.Context, start_date: str | None, end_date: str | None) -> None:
    """Fetch Stock Connect north/south-bound flow via Tushare when configured."""
    raw = _result_or_exit(
        ctx,
        _data_manager_fetch("tushare_hsgt_flow", 1800, start_date=start_date, end_date=end_date),
        default_error="Tushare is not configured or returned no HSGT data",
    )
    rows = raw.get("data") or []
    payload = {
        "ok": True,
        "market": "cn",
        "count": len(rows) if isinstance(rows, list) else raw.get("count", 0),
        "source": raw.get("source"),
        "from_cache": raw.get("from_cache", False),
        "from_stale_cache": raw.get("from_stale_cache", False),
        "rows": rows,
    }
    _render_rows_result(
        ctx,
        payload,
        title="[hsgt-flow]",
        headers=["Date", "North Net", "South Net", "HK->SH", "HK->SZ"],
        keys=["date", "north_money", "south_money", "ggt_ss", "ggt_sz"],
    )


@data_group.command("source-market")
@click.option("--artifact", type=str, default="summary", show_default=True, help="summary, dragon_tiger, stock_in, stock_out, limit_up, ...")
@click.option("--date", type=str, default=None, help="Review date YYYY-MM-DD; defaults to latest available cache")
@click.option("--limit", type=int, default=500, show_default=True, help="Maximum artifact rows; 0 for metadata-only where supported")
@click.pass_context
def data_source_market(ctx: click.Context, artifact: str, date: str | None, limit: int) -> None:
    """Read source-project market-review cache artifacts when configured."""
    raw = _result_or_exit(
        ctx,
        _data_manager_fetch(
            "source_market_review",
            300,
            artifact=artifact,
            date=date,
            limit=limit,
        ),
        default_error="Source market review cache is not configured",
    )
    metadata = raw.get("metadata") or {}
    data = raw.get("data")
    payload = {
        "ok": True,
        "artifact": metadata.get("artifact", artifact),
        "date": metadata.get("date", date),
        "count": raw.get("count", len(data) if isinstance(data, list) else 0),
        "source": raw.get("source"),
        "from_cache": raw.get("from_cache", False),
        "from_stale_cache": raw.get("from_stale_cache", False),
        "data": data,
        "metadata": metadata,
    }
    if ctx.obj.get("output_format", "json") == "json":
        output_json(payload)
        return

    if isinstance(data, list):
        rows_data = []
        for row in data[:20]:
            if isinstance(row, dict):
                rows_data.append([str(row.get(key, "")) for key in ("date", "symbol", "name", "net_amount", "reason")])
        output_table(f"[source-market] {payload['artifact']}", ["Date", "Symbol", "Name", "Net", "Reason"], rows_data)
    elif isinstance(data, dict):
        rows_data = [[str(key), str(value)] for key, value in data.items() if key != "artifacts"][:20]
        output_table(f"[source-market] {payload['artifact']}", ["Key", "Value"], rows_data)
    else:
        output_json(payload)
