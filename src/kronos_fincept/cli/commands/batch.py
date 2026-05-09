"""kronos batch — Multi-asset batch prediction with ranking.

Examples:
    kronos batch --symbols 600036,000858,000001 --market cn --pred-len 5 --csv batch.csv
    kronos --output table batch --symbols AAPL,MSFT --market us --pred-len 5 --dry-run
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import click

from kronos_fincept.cli.output import format_batch_table, output_json, output_table


def _risk_label(predicted_return: float) -> str:
    if predicted_return < -0.03:
        return "high"
    if abs(predicted_return) > 0.05:
        return "medium"
    return "low"


def _fetch_rows(symbol: str, market: str) -> list[dict[str, Any]]:
    if market == "cn":
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
        return fetch_a_stock_ohlcv(symbol, "20250101", "20261231")
    from kronos_fincept.financial import GlobalMarketSource
    return GlobalMarketSource().fetch_data(symbol, "20250101", "20261231", market=market)


def _write_csv(path: str, rankings: list[dict[str, Any]], failures: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["rank", "symbol", "market", "last_close", "predicted_close", "predicted_return", "risk_label", "failure_reason"])
        writer.writeheader()
        for row in rankings:
            writer.writerow(row | {"failure_reason": ""})
        for failure in failures:
            writer.writerow({"rank": "", "symbol": failure["symbol"], "market": failure.get("market", ""), "last_close": "", "predicted_close": "", "predicted_return": "", "risk_label": "", "failure_reason": failure["error"]})


@click.command("batch")
@click.option("--symbols", "-s", type=str, required=True, help="Comma-separated stock symbols, e.g. 600036,000858")
@click.option("--market", type=click.Choice(["cn", "us", "hk", "commodity"]), default="cn", help="Market")
@click.option("--pred-len", "-p", type=int, default=5, help="Prediction length (bars)")
@click.option("--csv", "csv_path", type=str, default=None, help="Write rankings and failures to CSV")
@click.option("--dry-run", is_flag=True, default=False, help="Use mock predictor")
@click.pass_context
def batch_cmd(ctx: click.Context, symbols: str, market: str, pred_len: int, csv_path: str | None, dry_run: bool) -> None:
    """Run batch forecast on multiple assets and rank by predicted return."""
    output_format = ctx.obj.get("output_format", "json")
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        click.echo("Error: --symbols cannot be empty", err=True)
        raise SystemExit(1)

    from kronos_fincept.schemas import ForecastRequest, ForecastRow
    from kronos_fincept.service import batch_forecast_from_requests

    requests: list[ForecastRequest] = []
    failures: list[dict[str, Any]] = []
    for sym in symbol_list:
        try:
            rows = _fetch_rows(sym, market)
            if not rows:
                raise ValueError("no OHLCV rows returned")
            req_rows = [ForecastRow.from_dict(r) for r in rows]
            requests.append(ForecastRequest(symbol=sym, timeframe="1d", pred_len=pred_len, rows=req_rows, dry_run=dry_run))
        except Exception as exc:
            failures.append({"symbol": sym, "market": market, "stage": "data", "error": str(exc)})
            click.echo(f"Warning: Failed to fetch {sym}: {exc}", err=True)

    rankings: list[dict[str, Any]] = []
    if requests:
        try:
            signals = batch_forecast_from_requests(requests)
            rankings = [
                {
                    "rank": sig.rank,
                    "symbol": sig.symbol,
                    "market": market,
                    "last_close": sig.last_close,
                    "predicted_close": sig.predicted_close,
                    "predicted_return": sig.predicted_return,
                    "risk_label": _risk_label(sig.predicted_return),
                    "elapsed_ms": sig.elapsed_ms,
                }
                for sig in signals
            ]
        except Exception as exc:
            failures.extend({"symbol": req.symbol, "market": market, "stage": "forecast", "error": str(exc)} for req in requests)

    result = {
        "ok": bool(rankings),
        "rankings": rankings,
        "failures": failures,
        "metadata": {"device": "cpu", "elapsed_ms": sum(row.get("elapsed_ms", 0) for row in rankings), "backend": "batch", "warning": "Research forecast only; not trading advice."},
    }
    if csv_path:
        _write_csv(csv_path, rankings, failures)
        result["csv"] = csv_path

    if output_format == "json":
        output_json(result)
    else:
        title, headers, rows_data = format_batch_table(result)
        output_table(title, headers, rows_data)
        if failures:
            click.echo(f"[failures] {len(failures)}")
        if csv_path:
            click.echo(f"[csv] {csv_path}")
        click.echo(f"[warn]  {result['metadata']['warning']}")
