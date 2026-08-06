"""Summarize upstream-aligned periodic Top-K diagnostics from evaluation JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.topk import periodic_topk_metrics  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-fraction", type=float, default=0.20)
    parser.add_argument("--baseline", default="official_kronos_small")
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--signal-mode",
        choices=("project_return", "upstream_normalized_last"),
        default="project_return",
    )
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--samples-file", type=Path, default=None)
    args = parser.parse_args()

    signal_scales = None
    if args.signal_mode == "upstream_normalized_last":
        if args.manifest is None or args.samples_file is None:
            raise ValueError("upstream_normalized_last requires --manifest and --samples-file")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        fixture = json.loads(args.samples_file.read_text(encoding="utf-8"))["samples"]
        data_dir = Path(manifest["data_dir"])
        frames: dict[str, pd.DataFrame] = {}
        signal_scales = {}
        for item in fixture:
            file_name = str(item["file"])
            if file_name not in frames:
                frames[file_name] = pd.read_csv(data_dir / file_name, usecols=["close"])
            close = frames[file_name]["close"].astype(float)
            context = close.iloc[int(item["input_start_row"]):int(item["input_end_row"])]
            key = tuple(str(item[field]) for field in ("market", "symbol", "target_start", "target_end"))
            signal_scales[key] = float(np.std(context.to_numpy(dtype=float), ddof=0)) + 1e-5

    models = {}
    hashes = set()
    for path in sorted(args.input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        hashes.add(payload["selection"]["sample_hash"])
        rows = [dict(row) for row in payload["rows"]]
        if signal_scales is not None:
            for row in rows:
                key = tuple(str(row[field]) for field in ("market", "symbol", "target_start", "target_end"))
                row["signal"] = (float(row["pred_close"]) - float(row["last_close"])) / signal_scales[key]
        models[path.stem] = periodic_topk_metrics(
            rows,
            top_fraction=args.top_fraction,
        )
    if len(hashes) != 1:
        raise ValueError(f"sample hashes differ: {sorted(hashes)}")
    if args.baseline not in models:
        raise ValueError(f"missing baseline: {args.baseline}")

    baseline_periods = {
        (item["market"], item["target_end"]): item["net_excess_return"]
        for item in models[args.baseline]["periods"]
    }
    paired = {}
    for name, result in models.items():
        if name == args.baseline:
            paired[name] = None
            continue
        candidate_periods = {
            (item["market"], item["target_end"]): item["net_excess_return"]
            for item in result["periods"]
        }
        keys = sorted(baseline_periods)
        deltas = np.asarray(
            [candidate_periods[key] - baseline_periods[key] for key in keys],
            dtype=float,
        )
        rng = np.random.default_rng(args.seed)
        bootstrap = np.asarray(
            [
                float(np.mean(deltas[rng.integers(0, len(deltas), len(deltas))]))
                for _ in range(args.bootstrap_replicates)
            ],
            dtype=float,
        )
        paired[name] = {
            "mean_net_excess_delta": float(np.mean(deltas)),
            "ci95": {
                "lower": float(np.quantile(bootstrap, 0.025)),
                "upper": float(np.quantile(bootstrap, 0.975)),
            },
            "bootstrap_replicates": args.bootstrap_replicates,
            "n_periods": len(deltas),
        }

    report = {
        "standard": "KRONOS_UPSTREAM_ALIGNED_PERIODIC_TOPK_V1",
        "signal_mode": args.signal_mode,
        "sample_hash": next(iter(hashes)),
        "baseline": args.baseline,
        "models": models,
        "paired_vs_baseline": paired,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("model\tmean_net_excess\twin_rate\tcumulative_net")
    for name, result in sorted(
        models.items(),
        key=lambda item: item[1]["overall"]["mean_net_excess_return"],
        reverse=True,
    ):
        overall = result["overall"]
        print(
            f"{name}\t{overall['mean_net_excess_return']:.6f}\t"
            f"{overall['excess_win_rate']:.3f}\t{overall['cumulative_net_return']:.6f}"
        )
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
