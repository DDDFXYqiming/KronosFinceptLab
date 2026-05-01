"""kronos backtest — Strategy backtest commands.

Examples:
    kronos backtest ranking --symbols 600036,000858 --start 20250101 --end 20260430 --top-k 1
    kronos --output table backtest ranking --symbols 600036,000858 --start 20250101 --end 20260430 --dry-run
    kronos backtest ranking --symbols 600036,000858 --start 20250101 --end 20260430 --report
    kronos backtest report ./backtest_report.html
"""

from __future__ import annotations

import json
import os

import click

from kronos_fincept.cli.output import (
    format_backtest_table,
    output_json,
    output_table,
)


@click.group("backtest")
def backtest_group() -> None:
    """Strategy backtest commands."""
    pass


DEFAULT_REPORT_DIR = os.path.join(os.getcwd(), "backtest_reports")


@backtest_group.command("ranking")
@click.option("--symbols", "-s", type=str, required=True,
              help="Comma-separated stock symbols")
@click.option("--start", type=str, required=True, help="Start date YYYYMMDD")
@click.option("--end", type=str, required=True, help="End date YYYYMMDD")
@click.option("--top-k", type=int, default=3, help="Top K stocks to hold")
@click.option("--pred-len", type=int, default=5, help="Prediction length")
@click.option("--window-size", type=int, default=60, help="Lookback window size")
@click.option("--step", type=int, default=5, help="Rebalance step (trading days)")
@click.option("--dry-run", is_flag=True, default=True, help="Use mock predictor")
@click.option("--report", is_flag=True, default=False, help="Generate HTML report")
@click.pass_context
def backtest_ranking(
    ctx: click.Context,
    symbols: str,
    start: str,
    end: str,
    top_k: int,
    pred_len: int,
    window_size: int,
    step: int,
    dry_run: bool,
    report: bool,
) -> None:
    """Run ranking-based strategy backtest."""
    output_format = ctx.obj.get("output_format", "json")
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]

    if not symbol_list:
        click.echo("Error: --symbols cannot be empty", err=True)
        raise SystemExit(1)

    # Fetch data and run backtest
    import time
    import math
    import pandas as pd

    from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
    from kronos_fincept.predictor import DryRunPredictor
    from kronos_fincept.schemas import RESEARCH_WARNING

    started = time.perf_counter()
    predictor = DryRunPredictor() if dry_run else None

    # Fetch data
    all_data = {}
    for sym in symbol_list:
        try:
            rows = fetch_a_stock_ohlcv(sym, start, end)
            if len(rows) < window_size + pred_len:
                click.echo(f"Warning: Insufficient data for {sym} ({len(rows)} rows)", err=True)
                continue
            all_data[sym] = rows
        except Exception as exc:
            click.echo(f"Warning: Failed to fetch {sym}: {exc}", err=True)

    if not all_data:
        error = {"ok": False, "error": "No valid data for any symbol"}
        if output_format == "json":
            output_json(error)
        else:
            click.echo(f"Error: {error['error']}", err=True)
        raise SystemExit(1)

    valid_symbols = list(all_data.keys())
    dfs = {}
    for sym in valid_symbols:
        df = pd.DataFrame(all_data[sym])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        dfs[sym] = df

    # Run backtest
    equity = 100000.0
    equity_curve = []
    total_trades = 0
    winning_trades = 0
    min_len = min(len(df) for df in dfs.values())

    i = window_size
    while i + step <= min_len:
        predictions = []
        for sym in valid_symbols:
            df = dfs[sym]
            window = df.iloc[i - window_size:i]
            last_close = float(window.iloc[-1]["close"])
            ohlcv_df = window[["open", "high", "low", "close"]].astype(float)
            timestamps = pd.Series(pd.to_datetime(window["timestamp"]))
            try:
                result = predictor.predict(df=ohlcv_df, x_timestamp=timestamps, pred_len=pred_len)
                pred_close = float(result.frame.iloc[-1]["close"])
                predictions.append((sym, pred_close / last_close - 1.0))
            except Exception:
                continue

        if not predictions:
            i += step
            continue

        predictions.sort(key=lambda x: x[1], reverse=True)
        selected = predictions[:top_k]
        end_idx = min(i + step, min_len)
        portfolio_return = 0.0
        for sym, _ in selected:
            df = dfs[sym]
            entry_price = float(df.iloc[i]["close"])
            exit_price = float(df.iloc[end_idx - 1]["close"])
            ret = (exit_price / entry_price - 1.0) if entry_price > 0 else 0.0
            portfolio_return += ret / len(selected)
            total_trades += 1
            if ret > 0:
                winning_trades += 1

        equity *= (1 + portfolio_return)
        equity_curve.append({
            "date": str(dfs[valid_symbols[0]].iloc[i]["timestamp"]),
            "equity": round(equity, 2),
            "return": round(portfolio_return, 6),
            "selected": [s[0] for s in selected],
        })
        i += step

    # Calculate metrics
    if len(equity_curve) >= 2:
        initial = equity_curve[0]["equity"]
        final = equity_curve[-1]["equity"]
        total_return = (final / initial - 1.0) if initial > 0 else 0.0
        years = len(equity_curve) / 252.0
        annualized = ((1 + total_return) ** (1 / years) - 1) if years > 0 and total_return > -1 else -1.0
        equities = [e["equity"] for e in equity_curve]
        daily_rets = [(equities[j] / equities[j-1] - 1) if equities[j-1] > 0 else 0.0
                      for j in range(1, len(equities))]
        mean_r = sum(daily_rets) / len(daily_rets) if daily_rets else 0
        std_r = (sum((r - mean_r)**2 for r in daily_rets) / len(daily_rets))**0.5 if daily_rets else 1
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
        peak = equities[0]
        max_dd = 0.0
        for eq in equities:
            if eq > peak: peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd: max_dd = dd
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
    else:
        total_return = annualized = sharpe = max_dd = win_rate = 0.0

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    metrics = {
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized, 6),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown": round(max_dd, 6),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "avg_holding_days": max(1, len(equity_curve) // max(total_trades, 1)),
    }

    result = {
        "ok": True,
        "symbols": valid_symbols,
        "start_date": start,
        "end_date": end,
        "top_k": top_k,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "metadata": {"device": "cpu", "elapsed_ms": elapsed_ms, "backend": "ranking_backtest",
                      "warning": RESEARCH_WARNING},
    }

    if output_format == "json":
        output_json(result)
    else:
        title, headers, rows_data = format_backtest_table(result)
        output_table(title, headers, rows_data)
        click.echo(f"[warn]  {RESEARCH_WARNING}")

    # Generate HTML report if --report flag is set
    if report:
        _generate_report(result, symbol_list, start, end)


def _generate_report(result: dict, symbols: list[str], start: str, end: str) -> None:
    """Generate HTML report from backtest result and print file path."""
    from kronos_fincept.backtest_report import BacktestReportGenerator

    gen = BacktestReportGenerator()
    symbol_str = "_".join(symbols[:3])
    if len(symbols) > 3:
        symbol_str += f"_+{len(symbols) - 3}"
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in symbol_str)
    filename = f"backtest_{safe_name}_{start}_{end}.html"
    os.makedirs(DEFAULT_REPORT_DIR, exist_ok=True)
    output_path = os.path.join(DEFAULT_REPORT_DIR, filename)

    metrics = result.get("metrics", {})
    equity_curve = result.get("equity_curve", [])
    html = gen.generate_html(
        symbol=", ".join(symbols),
        metrics=metrics,
        equity_curve=equity_curve,
        strategy_name="Ranking Strategy",
    )
    gen.export_html(html, output_path)
    click.echo(f"")
    click.echo(f"Report saved to: {output_path}")


@backtest_group.command("report")
@click.argument("filepath", type=str)
def open_report(filepath: str) -> None:
    """Open a generated backtest HTML report in the browser."""
    import subprocess
    import sys

    if not os.path.exists(filepath):
        click.echo(f"Error: File not found: {filepath}", err=True)
        raise SystemExit(1)

    abs_path = os.path.abspath(filepath)

    # Determine platform and open
    if sys.platform == "win32":
        os.startfile(abs_path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", abs_path], check=False)
    else:
        # Linux / WSL
        try:
            subprocess.run(["xdg-open", abs_path], check=False)
        except FileNotFoundError:
            click.echo(f"Report ready at: {abs_path}")
