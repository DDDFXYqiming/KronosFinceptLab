"""POST /api/backtest/ranking -- Ranking-based strategy backtest."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException

from kronos_fincept import native
from kronos_fincept.api.models import (
    BacktestMetricsOut,
    BacktestRequestIn,
    BacktestResponseOut,
    BacktestReportRequestIn,
    BacktestReportResponseOut,
    ForecastMetadataOut,
)
from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
from kronos_fincept.predictor import DryRunPredictor
from kronos_fincept.schemas import RESEARCH_WARNING

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_BACKTEST_RANGE_DAYS = 800
MAX_BACKTEST_WORK_UNITS = 5000


def _validate_backtest_request(req: BacktestRequestIn | BacktestReportRequestIn) -> None:
    try:
        start = datetime.strptime(req.start_date, "%Y%m%d")
        end = datetime.strptime(req.end_date, "%Y%m%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Dates must use YYYYMMDD format") from exc
    if end < start:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    span_days = (end - start).days
    if span_days > MAX_BACKTEST_RANGE_DAYS:
        raise HTTPException(status_code=422, detail=f"Backtest date range exceeds {MAX_BACKTEST_RANGE_DAYS} days")
    estimated_iterations = max(1, span_days // max(1, req.step))
    work_units = estimated_iterations * len(req.symbols)
    if work_units > MAX_BACKTEST_WORK_UNITS:
        raise HTTPException(status_code=422, detail="Backtest request is too large")


def _fetch_and_prepare_data(
    symbols: list[str],
    start_date: str,
    end_date: str,
    window_size: int,
    pred_len: int,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Fetch OHLCV data, build DataFrames, and align to common date range.

    Returns (dfs, valid_symbols). Raises HTTPException if no valid data.
    """
    all_data: dict[str, list[dict[str, Any]]] = {}
    for sym in symbols:
        try:
            rows = fetch_a_stock_ohlcv(sym, start_date, end_date)
            if len(rows) < window_size + pred_len:
                logger.warning("Insufficient data for %s: %d rows (need %d)",
                               sym, len(rows), window_size + pred_len)
                continue
            all_data[sym] = rows
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", sym, exc)

    if not all_data:
        raise HTTPException(status_code=400, detail="No valid data for any symbol")

    valid_symbols = list(all_data.keys())

    dfs: dict[str, pd.DataFrame] = {}
    for sym in valid_symbols:
        df = pd.DataFrame(all_data[sym])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        dfs[sym] = df

    common_start = max(df["timestamp"].min() for df in dfs.values())
    common_end = min(df["timestamp"].max() for df in dfs.values())
    for sym in valid_symbols:
        mask = (dfs[sym]["timestamp"] >= common_start) & (dfs[sym]["timestamp"] <= common_end)
        dfs[sym] = dfs[sym][mask].reset_index(drop=True)

    return dfs, valid_symbols


def _run_ranking_backtest(
    dfs: dict[str, pd.DataFrame],
    valid_symbols: list[str],
    predictor: DryRunPredictor,
    window_size: int,
    pred_len: int,
    step: int,
    top_k: int,
    initial_equity: float = 100000.0,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> tuple[list[dict[str, Any]], int, int]:
    """Run the ranking backtest loop.

    Returns (equity_curve, total_trades, winning_trades).
    """
    equity = initial_equity
    equity_curve: list[dict[str, Any]] = []
    total_trades = 0
    winning_trades = 0
    min_len = min(len(df) for df in dfs.values())

    i = window_size
    while i + step <= min_len:
        predictions: list[tuple[str, float]] = []
        for sym in valid_symbols:
            df = dfs[sym]
            window = df.iloc[i - window_size: i]
            last_close = float(window.iloc[-1]["close"])
            ohlcv_df = window[["open", "high", "low", "close"]].astype(float)
            timestamps = pd.Series(pd.to_datetime(window["timestamp"]))
            try:
                result = predictor.predict(
                    df=ohlcv_df,
                    x_timestamp=timestamps,
                    pred_len=pred_len,
                )
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
            trading_cost = 2 * (fee_bps + slippage_bps) / 10000.0
            ret -= trading_cost
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

    return equity_curve, total_trades, winning_trades


def _calculate_metrics(
    equity_curve: list[dict[str, Any]],
    total_trades: int,
    winning_trades: int,
) -> BacktestMetricsOut:
    """Calculate backtest performance metrics from equity curve."""
    if not equity_curve or len(equity_curve) < 2:
        return BacktestMetricsOut(
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            total_trades=total_trades,
            win_rate=0.0,
            avg_holding_days=0,
        )

    rust_metrics = native.calculate_backtest_metrics(
        [float(entry["equity"]) for entry in equity_curve],
        total_trades,
        winning_trades,
    )
    if rust_metrics is not None:
        return BacktestMetricsOut(
            total_return=float(rust_metrics["total_return"]),
            annualized_return=float(rust_metrics["annualized_return"]),
            sharpe_ratio=float(rust_metrics["sharpe_ratio"]),
            max_drawdown=float(rust_metrics["max_drawdown"]),
            total_trades=int(rust_metrics["total_trades"]),
            win_rate=float(rust_metrics["win_rate"]),
            avg_holding_days=int(rust_metrics["avg_holding_days"]),
        )

    # Total return
    initial = equity_curve[0]["equity"]
    final = equity_curve[-1]["equity"]
    total_return = (final / initial - 1.0) if initial > 0 else 0.0

    # Annualized return (assume 252 trading days/year)
    n_days = len(equity_curve)
    years = n_days / 252.0
    if years > 0 and total_return > -1:
        annualized_return = (1 + total_return) ** (1 / years) - 1
    else:
        annualized_return = -1.0

    # Daily returns for Sharpe
    equities = [e["equity"] for e in equity_curve]
    daily_returns = [
        (equities[i] / equities[i - 1] - 1) if equities[i - 1] > 0 else 0.0
        for i in range(1, len(equities))
    ]

    if daily_returns:
        mean_ret = sum(daily_returns) / len(daily_returns)
        std_ret = (sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
        sharpe_ratio = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0
    else:
        sharpe_ratio = 0.0

    # Max drawdown
    peak = equities[0]
    max_dd = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
    avg_holding_days = max(1, n_days // max(total_trades, 1))

    return BacktestMetricsOut(
        total_return=round(total_return, 6),
        annualized_return=round(annualized_return, 6),
        sharpe_ratio=round(sharpe_ratio, 4),
        max_drawdown=round(max_dd, 6),
        total_trades=total_trades,
        win_rate=round(win_rate, 4),
        avg_holding_days=avg_holding_days,
    )


@router.post("/backtest/ranking", response_model=BacktestResponseOut)
async def backtest_ranking(req: BacktestRequestIn) -> BacktestResponseOut:
    """Run a ranking-based strategy backtest.

    Strategy: At each rebalance step, predict each stock's return over the next
    `pred_len` days using the last `window_size` days of data. Buy the top_k
    stocks with the highest predicted return. Hold for `step` days, then rebalance.
    """
    _validate_backtest_request(req)
    started = time.perf_counter()
    predictor = DryRunPredictor() if req.dry_run else None

    def _run():
        dfs, symbols = _fetch_and_prepare_data(
            req.symbols, req.start_date, req.end_date, req.window_size, req.pred_len,
        )
        curve, trades, wins = _run_ranking_backtest(
            dfs,
            symbols,
            predictor,
            req.window_size,
            req.pred_len,
            req.step,
            req.top_k,
            req.initial_equity,
            req.fee_bps,
            req.slippage_bps,
        )
        return dfs, symbols, curve, trades, wins

    dfs, valid_symbols, equity_curve, total_trades, winning_trades = await asyncio.to_thread(_run)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    metrics = _calculate_metrics(equity_curve, total_trades, winning_trades)

    return BacktestResponseOut(
        ok=True,
        symbols=valid_symbols,
        start_date=req.start_date,
        end_date=req.end_date,
        top_k=req.top_k,
        metrics=metrics,
        equity_curve=equity_curve,
        metadata=ForecastMetadataOut(
            device="cpu",
            elapsed_ms=elapsed_ms,
            backend="ranking_backtest",
            warning=RESEARCH_WARNING,
        ),
    )


@router.post("/backtest/report", response_model=BacktestReportResponseOut)
async def backtest_report(req: BacktestReportRequestIn) -> BacktestReportResponseOut:
    """Run backtest and return HTML report string for frontend display."""
    _validate_backtest_request(req)
    from kronos_fincept.backtest_report import BacktestReportGenerator

    started = time.perf_counter()
    predictor = DryRunPredictor() if req.dry_run else None

    def _run():
        dfs, symbols = _fetch_and_prepare_data(
            req.symbols, req.start_date, req.end_date, req.window_size, req.pred_len,
        )
        curve, trades, wins = _run_ranking_backtest(
            dfs,
            symbols,
            predictor,
            req.window_size,
            req.pred_len,
            req.step,
            req.top_k,
            req.initial_equity,
            req.fee_bps,
            req.slippage_bps,
        )
        return dfs, symbols, curve, trades, wins

    dfs, valid_symbols, equity_curve, total_trades, winning_trades = await asyncio.to_thread(_run)

    metrics = _calculate_metrics(equity_curve, total_trades, winning_trades)
    metrics_dict = metrics.model_dump()

    # Fetch benchmark data if requested
    benchmark_data = None
    if req.benchmark:
        try:
            bench_rows = await asyncio.to_thread(
                fetch_a_stock_ohlcv, req.benchmark, req.start_date, req.end_date,
            )
            if bench_rows:
                benchmark_data = bench_rows
        except Exception as exc:
            logger.warning("Failed to fetch benchmark %s: %s", req.benchmark, exc)

    # Generate HTML report
    gen = BacktestReportGenerator()
    html = gen.generate_html(
        symbol=", ".join(req.symbols),
        metrics=metrics_dict,
        equity_curve=equity_curve,
        benchmark_data=benchmark_data,
        strategy_name=req.strategy_name,
    )

    # Save a copy to disk
    safe_name = "_".join(req.symbols[:3])
    filename = f"backtest_{safe_name}_{req.start_date}_{req.end_date}.html"

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("Backtest report generated in %d ms — %d symbols, %d trades",
                elapsed_ms, len(valid_symbols), total_trades)

    return BacktestReportResponseOut(ok=True, html=html, filename=filename)
