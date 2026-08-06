"""Qlib-style periodic Top-K diagnostics for fixed Kronos evaluation rows."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


def periodic_topk_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    top_fraction: float = 0.20,
    open_cost: float = 0.001,
    close_cost: float = 0.0015,
) -> dict[str, Any]:
    """Evaluate non-overlapping five-day Top-K portfolios with round-trip costs."""

    frame = pd.DataFrame(rows).copy()
    frame["pred_return"] = frame["pred_close"].astype(float) / frame["last_close"].astype(float) - 1.0
    frame["actual_return"] = frame["true_close"].astype(float) / frame["last_close"].astype(float) - 1.0
    score_column = "signal" if "signal" in frame.columns else "pred_return"

    periods: list[dict[str, Any]] = []
    for (market, target_end), group in frame.groupby(["market", "target_end"], sort=True):
        topk = max(1, int(math.ceil(len(group) * top_fraction)))
        selected = group.nlargest(topk, score_column)
        gross_return = float(selected["actual_return"].mean())
        benchmark_return = float(group["actual_return"].mean())
        net_return = gross_return - open_cost - close_cost
        periods.append(
            {
                "market": str(market),
                "target_end": str(target_end),
                "universe_size": int(len(group)),
                "topk": topk,
                "gross_return": gross_return,
                "net_return": net_return,
                "benchmark_return": benchmark_return,
                "net_excess_return": net_return - benchmark_return,
            }
        )

    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        net = np.asarray([item["net_return"] for item in items], dtype=float)
        benchmark = np.asarray([item["benchmark_return"] for item in items], dtype=float)
        excess = net - benchmark
        std = float(np.std(excess, ddof=1)) if len(excess) > 1 else 0.0
        return {
            "n_periods": len(items),
            "mean_net_return": float(np.mean(net)),
            "mean_benchmark_return": float(np.mean(benchmark)),
            "mean_net_excess_return": float(np.mean(excess)),
            "excess_win_rate": float(np.mean(excess > 0)),
            "cumulative_net_return": float(np.prod(1.0 + net) - 1.0),
            "cumulative_benchmark_return": float(np.prod(1.0 + benchmark) - 1.0),
            "diagnostic_excess_t_stat": float(np.mean(excess) / std * np.sqrt(len(excess))) if std > 0 else None,
        }

    markets = sorted({item["market"] for item in periods})
    return {
        "method": "fixed_non_overlapping_top_fraction_hold_5d",
        "signal": "provided_upstream_normalized_last" if score_column == "signal" else "predicted_endpoint_return",
        "top_fraction": top_fraction,
        "open_cost": open_cost,
        "close_cost": close_cost,
        "overall": aggregate(periods),
        "by_market": {
            market: aggregate([item for item in periods if item["market"] == market])
            for market in markets
        },
        "periods": periods,
        "limitations": (
            "Qlib-style economic diagnostic only; fixed non-overlapping periods, "
            "no TopkDropout carry-over, slippage, limit-up/down execution, or market impact."
        ),
    }
