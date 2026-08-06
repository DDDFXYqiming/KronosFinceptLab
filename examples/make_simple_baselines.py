"""Build momentum / volatility reference predictions for the fixed Confirm fixture.

These baselines are computed purely from the pre-window market data (no model
inference) so they can be compared side by side with Kronos checkpoints as
reference rows.  They are NOT part of the promotion gates.

Signals:
  - momentum_5d: predicted return = past 5 trading-day return (persistence);
  - vol_low_90d: predicted return = -past 90-bar realised volatility (low-vol tilt).

Usage (from the repository root):

    .\\.venv311\\Scripts\\python.exe examples\\make_simple_baselines.py \
        --reference output\\evaluation_v8_recent\\confirm\\pretrained_small.json \
        --samples-file configs\\evaluation\\evaluation_samples_v4.json \
        --data-dir external\\Kronos\\finetune_csv\\clean_v8_largecap_recent \
        --output-dir output\\evaluation_batch1\\confirm
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _compute_signals(
    frame: pd.DataFrame,
    sample: dict[str, Any],
) -> dict[str, float]:
    start = int(sample["input_start_row"])
    end = int(sample["input_end_row"])
    closes = frame.iloc[start:end]["close"].to_numpy(dtype=float)
    if len(closes) < 7:
        raise ValueError(f"input window too short for {sample['file']}: {len(closes)}")
    log_returns = np.diff(np.log(closes))
    momentum = closes[-1] / closes[-6] - 1.0
    volatility = float(np.std(log_returns, ddof=1)) if len(log_returns) > 1 else 0.0
    return {
        "momentum_5d": float(momentum),
        "vol_low_90d": -volatility,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--samples-file", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    reference = _load(args.reference)
    samples = _load(args.samples_file)["samples"]
    rows = sorted(reference["rows"], key=lambda row: (
        row["market"], row["symbol"], row["target_start"], row["target_end"]
    ))

    by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        by_key[(row["market"], row["symbol"], row["target_start"], row["target_end"])] = row

    frames: dict[str, pd.DataFrame] = {}
    signal_rows: dict[str, list[dict[str, Any]]] = {
        "momentum_5d": [],
        "vol_low_90d": [],
    }

    for sample in samples:
        key = (sample["market"], sample["symbol"], sample["target_start"], sample["target_end"])
        row = by_key.get(key)
        if row is None:
            continue
        data_dir = args.data_dir.resolve()
        frame = frames.get(sample["file"])
        if frame is None:
            frame = pd.read_csv(data_dir / sample["file"])
            frames[sample["file"]] = frame
        signals = _compute_signals(frame, sample)
        last_close = float(frame.iloc[int(sample["input_end_row"]) - 1]["close"])
        true_close = float(frame.iloc[int(sample["target_end_row"]) - 1]["close"])
        if not np.isclose(last_close, float(row["last_close"]), rtol=0, atol=1e-6):
            raise ValueError(f"last_close mismatch for {key}: data={last_close} ref={row['last_close']}")
        if not np.isclose(true_close, float(row["true_close"]), rtol=0, atol=1e-6):
            raise ValueError(f"true_close mismatch for {key}: data={true_close} ref={row['true_close']}")
        for name, pred_ret in signals.items():
            out_row = dict(row)
            out_row["pred_close"] = float(last_close * (1.0 + pred_ret))
            signal_rows[name].append(out_row)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, out_rows in signal_rows.items():
        if len(out_rows) != len(rows):
            raise ValueError(f"{name}: produced {len(out_rows)} rows, expected {len(rows)}")
        payload = dict(reference)
        payload["model_path"] = f"baseline:{name}"
        payload["rows"] = sorted(out_rows, key=lambda row: (
            row["market"], row["symbol"], row["target_start"], row["target_end"]
        ))
        destination = args.output_dir / f"{name}.json"
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[baseline] {name}: {len(out_rows)} rows -> {destination}")


if __name__ == "__main__":
    main()
