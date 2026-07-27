"""Evaluate fine-tuned Kronos-small through the full production inference pipeline.

Uses KronosPredictor.predict() — the exact same code path as the API server —
instead of calling the model directly in normalized space like eval_full.py.
"""

from __future__ import annotations

import json
import os
import sys
import time
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("KRONOS_REPO_PATH", str(PROJECT_ROOT / "external" / "Kronos"))
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from kronos_fincept.predictor import _ensure_kronos_on_syspath
_ensure_kronos_on_syspath()

import torch
from model import Kronos, KronosPredictor, KronosTokenizer

# ── Model paths ──
HF_HUB = r"E:\AI_Projects\ModelCache\huggingface\hub"

# Cache directory naming: models--NeoQuasar--Kronos-small (ONE dir name, not joined by / or \)
SNAPSHOTS = os.path.join(HF_HUB, "models--NeoQuasar--Kronos-small", "snapshots", "901c26c1332695a2a8f243eb2f37243a37bea320")
SNAPSHOTS_BASE = os.path.join(HF_HUB, "models--NeoQuasar--Kronos-base", "snapshots", "2b554741eca47781b64468546e77fef3e85130e6")
TOKENIZER_SNAPSHOTS = os.path.join(HF_HUB, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")

MODEL_PATHS = {
    "pretrained_small": {
        "path": SNAPSHOTS,
        "label": "Kronos-small (pretrained, 24.7M)",
    },
    "finetuned_small": {
        "path": str(PROJECT_ROOT / "external" / "Kronos-small"),
        "label": "Kronos-small (finetuned, 24.7M)",
    },
    "pretrained_base": {
        "path": SNAPSHOTS_BASE,
        "label": "Kronos-base (pretrained, 102.3M)",
    },
}

TOKENIZER_PATH = TOKENIZER_SNAPSHOTS

DATA_DIR = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv" / "data_v2"
LOOKBACK = 90
PRED_LEN = 10
BATCH_SIZE = 32
MAX_STOCKS = 200


@dataclass
class EvalResult:
    label: str
    loss: float
    perplexity: float
    dir_accuracy: float
    total: int
    elapsed_s: float
    n_stocks: int


def load_data(data_dir: Path, max_stocks: int = MAX_STOCKS) -> dict[str, pd.DataFrame]:
    csv_files = sorted(data_dir.glob("cn_*.csv"))
    if len(csv_files) > max_stocks:
        csv_files = csv_files[:max_stocks]

    stocks = {}
    for f in csv_files:
        df = pd.read_csv(f, parse_dates=["timestamp"])
        df.sort_values("timestamp", inplace=True)
        symbol = f.stem.replace("cn_", "")
        stocks[symbol] = df
    return stocks


def extract_test_samples(stocks: dict[str, pd.DataFrame], lookback: int, pred_len: int) -> list[dict]:
    """Extract test samples: consecutive 101-day windows from the last 10% of each stock."""
    samples = []
    for symbol, df in stocks.items():
        n = len(df)
        test_start = int(n * 0.9)
        window = lookback + pred_len
        if n - test_start < window:
            continue
        last_start = n - window
        for start in range(test_start, last_start + 1):
            samples.append({
                "symbol": symbol,
                "df": df.iloc[start:start + lookback],
                "x_timestamp": pd.to_datetime(df.iloc[start:start + lookback]["timestamp"], utc=True),
                "y_timestamp": pd.to_datetime(df.iloc[start + lookback:start + window]["timestamp"], utc=True),
                "true_close_final": float(df.iloc[start + window - 1]["close"]),
                "last_close": float(df.iloc[start + lookback - 1]["close"]),
            })
    return samples


def evaluate_model(
    model_key: str,
    stocks: dict[str, pd.DataFrame],
    samples: list[dict],
    device: torch.device,
) -> EvalResult:
    cfg = MODEL_PATHS[model_key]
    t0 = time.perf_counter()
    print(f"\n  Loading {cfg['label']}...", end=" ", flush=True)

    model = Kronos.from_pretrained(cfg["path"]).to(device)
    model.eval()
    tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_PATH).to(device)
    predictor = KronosPredictor(model, tokenizer, max_context=512, device=device)

    print(f"done ({time.perf_counter() - t0:.1f}s)  Running inference...", flush=True)

    total = 0
    correct_dir = 0
    total_mse = 0.0

    batch_start = 0
    while batch_start < len(samples):
        batch = samples[batch_start:batch_start + BATCH_SIZE]
        batch_start += BATCH_SIZE
        n_batch = len(batch)

        dfs = [s["df"] for s in batch]
        x_ts = [s["x_timestamp"] for s in batch]
        y_ts = [s["y_timestamp"] for s in batch]

        try:
            results = predictor.predict_batch(dfs, x_ts, y_ts, PRED_LEN, T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False)
        except Exception as e:
            print(f"    batch failed at {batch_start}: {e}")
            for i in range(n_batch):
                try:
                    frame = predictor.predict(batch[i]["df"], batch[i]["x_timestamp"], batch[i]["y_timestamp"], PRED_LEN, T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False)
                except Exception:
                    continue
                pred_close = float(frame.iloc[-1]["close"])
                true_close = batch[i]["true_close_final"]
                last_close = batch[i]["last_close"]
                total += 1
                if (pred_close > last_close) == (true_close > last_close):
                    correct_dir += 1
                total_mse += (pred_close - true_close) ** 2
            continue

        for i in range(n_batch):
            frame = results[i]
            pred_close = float(frame.iloc[-1]["close"])
            true_close = batch[i]["true_close_final"]
            last_close = batch[i]["last_close"]
            total += 1
            if (pred_close > last_close) == (true_close > last_close):
                correct_dir += 1
            total_mse += (pred_close - true_close) ** 2

        if batch_start % (BATCH_SIZE * 10) == 0:
            pct = total / max(len(samples), 1) * 100
            acc = correct_dir / max(total, 1) * 100
            print(f"    {pct:.0f}%  ({total}/{len(samples)})  curr_acc={acc:.1f}%")

    elapsed = time.perf_counter() - t0
    loss = total_mse / max(total, 1)
    dir_acc = correct_dir / max(total, 1)
    perplexity = float(np.exp(loss))

    print(f"  ✅ done: acc={dir_acc*100:.1f}%  loss={loss:.4f}  ppl={perplexity:.2f}  ({elapsed:.0f}s)")
    return EvalResult(
        label=cfg["label"],
        loss=loss,
        perplexity=perplexity,
        dir_accuracy=dir_acc,
        total=total,
        elapsed_s=elapsed,
        n_stocks=len(stocks),
    )


def main():
    print("=" * 70)
    print("Production-path evaluation: KronosPredictor.predict() full pipeline")
    print("=" * 70)

    # Device
    import torch_directml
    device = torch_directml.device()
    print(f"Device: DirectML (AMD RX 7800 XT)")

    # Load data
    print(f"\nLoading data from {DATA_DIR}...")
    stocks = load_data(DATA_DIR, MAX_STOCKS)
    print(f"  {len(stocks)} stocks loaded")

    samples = extract_test_samples(stocks, LOOKBACK, PRED_LEN)
    print(f"  {len(samples)} test samples extracted (last 10% of each stock)")

    # Evaluate
    results: list[EvalResult] = []
    for model_key in ["pretrained_small", "finetuned_small", "pretrained_base"]:
        result = evaluate_model(model_key, stocks, samples, device)
        results.append(result)

    # Print comparison
    print("\n" + "=" * 70)
    print("Results (production path — KronosPredictor.predict() pipeline)")
    print("=" * 70)
    print(f"{'Model':<40} {'Loss':>8} {'PPL':>8} {'DirAcc':>8} {'Samples':>8} {'Time':>8}")
    print("-" * 70)
    for r in results:
        print(f"{r.label:<40} {r.loss:>8.4f} {r.perplexity:>8.2f} {r.dir_accuracy*100:>7.1f}% {r.total:>8} {r.elapsed_s:>7.0f}s")

    print("\n" + "=" * 70)
    if len(results) >= 2:
        ft = results[1]
        pre = results[0]
        delta_acc = (ft.dir_accuracy - pre.dir_accuracy) * 100
        delta_ppl = pre.perplexity / ft.perplexity - 1 if ft.perplexity > 0 else 0
        print(f"Improvement: DirAcc +{delta_acc:.1f}pp  PPL -{delta_ppl*100:.1f}%")

    # Save results
    out_path = PROJECT_ROOT / "output" / "eval_production_results.json"
    out_path.parent.mkdir(exist_ok=True)
    json.dump([asdict(r) for r in results], open(out_path, "w", encoding="utf-8"), indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
