"""Compare aligned Kronos evaluation outputs under evaluation standard v2.

The input files must contain predictions for exactly the same samples.  Statistical
uncertainty is estimated by paired resampling of (market, target_end) groups, so a
candidate and the baseline always see the same realised returns in each replicate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats


ROW_KEY = ("market", "symbol", "target_start", "target_end")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[field]) for field in ROW_KEY)


def _aligned_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(payload["rows"], key=_key)


def _returns(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    last = np.asarray([row["last_close"] for row in rows], dtype=float)
    pred = np.asarray([row["pred_close"] for row in rows], dtype=float) / last - 1.0
    true = np.asarray([row["true_close"] for row in rows], dtype=float) / last - 1.0
    return pred, true


def _safe_corr(pred: np.ndarray, true: np.ndarray, *, rank: bool) -> float | None:
    if len(pred) < 3 or np.std(pred) == 0 or np.std(true) == 0:
        return None
    value = stats.spearmanr(pred, true).statistic if rank else stats.pearsonr(pred, true).statistic
    return float(value) if np.isfinite(value) else None


def _groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str], np.ndarray]:
    grouped: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault((row["market"], row["target_end"]), []).append(index)
    return {key: np.asarray(indices, dtype=int) for key, indices in grouped.items()}


def _daily_rankic(
    pred: np.ndarray, true: np.ndarray, groups: dict[tuple[str, str], np.ndarray]
) -> dict[tuple[str, str], float]:
    result: dict[tuple[str, str], float] = {}
    for key, indices in groups.items():
        value = _safe_corr(pred[indices], true[indices], rank=True)
        if value is not None:
            result[key] = value
    return result


def _topk_diagnostic(
    pred: np.ndarray,
    true: np.ndarray,
    groups: dict[tuple[str, str], np.ndarray],
    k: int = 5,
) -> dict[str, float | int | None]:
    excess = []
    for indices in groups.values():
        chosen = indices[np.argsort(pred[indices])[-min(k, len(indices)) :]]
        excess.append(float(np.mean(true[chosen]) - np.mean(true[indices])))
    values = np.asarray(excess, dtype=float)
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    return {
        "n_periods": int(len(values)),
        "mean_excess": float(np.mean(values)) if len(values) else None,
        "diagnostic_ir": float(np.mean(values) / std * np.sqrt(len(values))) if std > 0 else None,
        "win_rate": float(np.mean(values > 0)) if len(values) else None,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pred, true = _returns(rows)
    grouped = _groups(rows)
    daily = _daily_rankic(pred, true, grouped)
    return {
        "n": len(rows),
        "n_periods": len(daily),
        "pooled_rankic": _safe_corr(pred, true, rank=True),
        "pooled_ic": _safe_corr(pred, true, rank=False),
        "mean_daily_rankic": float(np.mean(list(daily.values()))) if daily else None,
        "direction_accuracy": float(np.mean((pred > 0) == (true > 0))),
        "endpoint_return_mae": float(np.mean(np.abs(pred - true))),
        "top5_diagnostic": _topk_diagnostic(pred, true, grouped),
    }


def _paired_tests(
    candidate_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    *,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    candidate_pred, true = _returns(candidate_rows)
    baseline_pred, baseline_true = _returns(baseline_rows)
    if not np.allclose(true, baseline_true, rtol=0, atol=1e-12):
        raise ValueError("candidate and baseline true returns are not aligned")

    grouped = _groups(candidate_rows)
    keys = sorted(grouped)
    candidate_daily = _daily_rankic(candidate_pred, true, grouped)
    baseline_daily = _daily_rankic(baseline_pred, true, grouped)
    paired_keys = sorted(set(candidate_daily) & set(baseline_daily))
    daily_test = stats.ttest_rel(
        [candidate_daily[key] for key in paired_keys],
        [baseline_daily[key] for key in paired_keys],
    ) if len(paired_keys) >= 2 else None

    rng = np.random.default_rng(seed)
    rankic_deltas = []
    direction_deltas = []
    mae_deltas = []
    for _ in range(replicates):
        sampled = rng.integers(0, len(keys), size=len(keys))
        indices = np.concatenate([grouped[keys[index]] for index in sampled])
        candidate_rankic = _safe_corr(candidate_pred[indices], true[indices], rank=True)
        baseline_rankic = _safe_corr(baseline_pred[indices], true[indices], rank=True)
        if candidate_rankic is not None and baseline_rankic is not None:
            rankic_deltas.append(candidate_rankic - baseline_rankic)
        direction_deltas.append(
            np.mean((candidate_pred[indices] > 0) == (true[indices] > 0))
            - np.mean((baseline_pred[indices] > 0) == (true[indices] > 0))
        )
        mae_deltas.append(
            np.mean(np.abs(candidate_pred[indices] - true[indices]))
            - np.mean(np.abs(baseline_pred[indices] - true[indices]))
        )

    def interval(values: list[float]) -> dict[str, float]:
        array = np.asarray(values, dtype=float)
        return {
            "lower": float(np.quantile(array, 0.025)),
            "upper": float(np.quantile(array, 0.975)),
        }

    rankic_array = np.asarray(rankic_deltas, dtype=float)
    two_sided_p = float(
        min(1.0, 2 * min((np.sum(rankic_array <= 0) + 1) / (len(rankic_array) + 1),
                         (np.sum(rankic_array >= 0) + 1) / (len(rankic_array) + 1)))
    )
    return {
        "cluster": "market_target_end",
        "bootstrap_replicates": replicates,
        "pooled_rankic_delta_ci95": interval(rankic_deltas),
        "pooled_rankic_delta_p_two_sided": two_sided_p,
        "direction_accuracy_delta_ci95": interval(direction_deltas),
        "endpoint_return_mae_delta_ci95": interval(mae_deltas),
        "daily_rankic_paired_t_p_two_sided": float(daily_test.pvalue) if daily_test else None,
        "daily_rankic_paired_periods": len(paired_keys),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--baseline", default="pretrained_small")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    payloads = {
        path.stem: _load(path)
        for path in sorted(args.input_dir.glob("*.json"))
        if path.name not in {"summary.json", "comparison_report.json"}
    }
    if args.baseline not in payloads:
        raise ValueError(f"missing baseline: {args.baseline}")
    hashes = {name: payload["selection"]["sample_hash"] for name, payload in payloads.items()}
    if len(set(hashes.values())) != 1:
        raise ValueError(f"sample hashes differ: {hashes}")

    rows_by_model = {name: _aligned_rows(payload) for name, payload in payloads.items()}
    baseline_rows = rows_by_model[args.baseline]
    baseline_keys = [_key(row) for row in baseline_rows]
    for name, rows in rows_by_model.items():
        if [_key(row) for row in rows] != baseline_keys:
            raise ValueError(f"row keys differ for model: {name}")

    models: dict[str, Any] = {}
    baseline_metrics = _metrics(baseline_rows)
    for name, rows in rows_by_model.items():
        overall = _metrics(rows)
        by_market = {
            market: _metrics([row for row in rows if row["market"] == market])
            for market in sorted({row["market"] for row in rows})
        }
        comparison = None if name == args.baseline else _paired_tests(
            rows,
            baseline_rows,
            replicates=args.bootstrap_replicates,
            seed=args.seed,
        )
        delta = overall["pooled_rankic"] - baseline_metrics["pooled_rankic"]
        passes = None
        if comparison is not None:
            statistical_evidence = (
                comparison["pooled_rankic_delta_p_two_sided"] < 0.10
                or comparison["daily_rankic_paired_t_p_two_sided"] < 0.10
            )
            passes = {
                "rankic_delta_at_least_0_02": delta >= 0.02,
                "paired_statistical_evidence_p_lt_0_10": statistical_evidence,
                "direction_within_0_02": overall["direction_accuracy"] >= baseline_metrics["direction_accuracy"] - 0.02,
                "endpoint_mae_not_worse": overall["endpoint_return_mae"] <= baseline_metrics["endpoint_return_mae"],
                "top5_mean_excess_positive": overall["top5_diagnostic"]["mean_excess"] > 0,
            }
            passes["all"] = all(passes.values())
        models[name] = {
            "model_path": payloads[name]["model_path"],
            "overall": overall,
            "by_market": by_market,
            "delta_vs_baseline": {
                "pooled_rankic": delta,
                "direction_accuracy": overall["direction_accuracy"] - baseline_metrics["direction_accuracy"],
                "endpoint_return_mae": overall["endpoint_return_mae"] - baseline_metrics["endpoint_return_mae"],
            },
            "paired_tests_vs_baseline": comparison,
            "v2_gates": passes,
        }

    ranking = sorted(models, key=lambda name: models[name]["overall"]["pooled_rankic"], reverse=True)
    report = {
        "standard": "FINETUNE_EVALUATION_STANDARD_v3_PRODUCTION_PARAMETERS",
        "evaluation_status": "development_confirm_not_strict_oos",
        "sample_hash": next(iter(hashes.values())),
        "baseline": args.baseline,
        "ranking_by_pooled_rankic": ranking,
        "models": models,
        "notes": {
            "endpoint_return_mae": "Terminal five-day return error; not full OHLC path MAE.",
            "top5_diagnostic": "Equal-weight, no-cost grouped diagnostic; not a Qlib backtest or annualised production IR.",
            "paired_inference": "Paired resampling by market and target_end; Fisher-z independence approximation is not used.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("model\tpooled_rankic\tdaily_rankic\tdir_acc\tendpoint_mae\ttop5_excess\tpass")
    for name in ranking:
        item = models[name]
        metrics = item["overall"]
        passed = "BASE" if name == args.baseline else str(item["v2_gates"]["all"])
        print(
            f"{name}\t{metrics['pooled_rankic']:.6f}\t{metrics['mean_daily_rankic']:.6f}\t"
            f"{metrics['direction_accuracy']:.6f}\t{metrics['endpoint_return_mae']:.6f}\t"
            f"{metrics['top5_diagnostic']['mean_excess']:.6f}\t{passed}"
        )
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
