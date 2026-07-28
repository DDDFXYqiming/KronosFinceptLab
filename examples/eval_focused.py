"""Focused param grid: finetuned model, key combos, correct y_timestamp handling."""

import os
import json, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parents[1]
os.environ.setdefault("KRONOS_REPO_PATH", str(PROJ / "external" / "Kronos"))
sys.path.insert(0, str(PROJ / "src"))
sys.path.insert(0, str(PROJ / "external" / "Kronos"))

import torch
from model import Kronos, KronosPredictor, KronosTokenizer

# Use CPU to avoid DirectML page file issues
device = torch.device("cpu")
print(f"Device: CPU")

# ── Data ──
DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
hub =  os.environ.get("HF_HUB_CACHE", os.path.expanduser("~/.cache/huggingface/hub"))
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")
ft_path = str(PROJ / "external" / "Kronos-small")

csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:15]
samples = []
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    sym = f.stem.replace("cn_", "")
    n = len(df)
    test_start = max(int(n * 0.95), n - 150)
    if test_start <= 0:
        continue
    for start in range(test_start, n - 100, 5):
        y_df = df.iloc[start+90:start+100]
        samples.append({
            "x_df": df.iloc[start:start+90],
            "x_ts": pd.Series(pd.to_datetime(df.iloc[start:start+90]["timestamp"], utc=True)),
            "y_ts": pd.Series(pd.to_datetime(y_df["timestamp"], utc=True)),
            "last_c": float(df.iloc[start+89]["close"]),
            "true_5": float(y_df.iloc[4]["close"]),
            "true_10": float(y_df.iloc[9]["close"]),
        })
print(f"{len(samples)} samples from {len(csv_files)} stocks")

tok = KronosTokenizer.from_pretrained(tok_path).to(device)
print("Loading finetuned model...", end=" ", flush=True)
t0 = time.perf_counter()
model = Kronos.from_pretrained(ft_path).to(device)
model.eval()
print(f"done ({time.perf_counter()-t0:.1f}s)")

results = []
out_path = PROJ / "output" / "eval_grid_results.json"

grid = [
    (10, 1, 1.0, 0.9, "A: baseline(pl10,sc1,T1)"),
    (10, 8, 1.0, 0.9, "D: sample_count=8"),
    (10, 32, 1.0, 0.9, "E: sample_count=32"),
    (5,  1, 1.0, 0.9, "B: pred_len=5"),
    (5,  8, 1.0, 0.9, "F: pl5+sc8"),
    (5,  8, 0.5, 0.9, "G: +T0.5"),
    (5,  32, 0.5, 0.8, "H: +sc32+P0.8"),
    (5,  8, 0.3, 0.9, "I: +T0.3"),
    (10, 1, 0.5, 0.9, "J: pl10+T0.5"),
    (10, 8, 0.5, 0.9, "K: pl10+sc8+T0.5"),
]

for pred_len, sc, T, p, note in grid:
    print(f"\n{'─'*50}")
    print(f"{note}: pl={pred_len} sc={sc} T={T} P={p}")
    print(f"{'─'*50}")

    predictor = KronosPredictor(model, tok, max_context=512, device=device)
    correct = 0; total = 0; mse = 0.0
    B = 4

    for i in range(0, len(samples), B):
        batch = samples[i:i+B]

        y_ts_list = [s["y_ts"].iloc[:pred_len] for s in batch]

        try:
            frames = predictor.predict_batch(
                [s["x_df"] for s in batch],
                [s["x_ts"] for s in batch],
                y_ts_list,
                pred_len,
                T=T, top_k=0, top_p=p,
                sample_count=sc, verbose=False,
            )
        except Exception as e:
            print(f"  batch fail {i}: {e}", flush=True)
            continue

        for j, frame in enumerate(frames):
            try:
                pred_c = float(frame.iloc[-1]["close"])
            except (IndexError, KeyError):
                continue

            true_c = batch[j]["true_5"] if pred_len <= 5 else batch[j]["true_10"]
            last_c = batch[j]["last_c"]

            total += 1
            if (pred_c > last_c) == (true_c > last_c):
                correct += 1
            mse += (pred_c - true_c) ** 2

    loss = mse / max(total, 1)
    acc = correct / max(total, 1)
    ppl = float(np.exp(loss)) if loss < 30 else float("inf")
    print(f"  acc={acc*100:.1f}%  loss={loss:.4f}  ppl={ppl:.2f}  ({total} samples)")

    results.append({
        "model": "finetuned_small",
        "pred_len": pred_len,
        "sample_count": sc,
        "temperature": T,
        "top_p": p,
        "note": note,
        "dir_accuracy": round(acc*100, 1),
        "loss": round(float(loss), 4),
        "perplexity": round(ppl, 2),
        "n_samples": total,
    })
    json.dump(results, open(out_path, "w", encoding="utf-8"), indent=2)

print(f"\n{'='*55}")
print("RESULTS — finetuned Kronos-small on production pipeline")
print(f"{'='*55}")
print(f"{'Note':<28} {'PL':>3} {'SC':>3} {'T':>4} {'P':>4} {'Acc%':>6} {'Loss':>8} {'PPL':>8} {'N':>5}")
print("-" * 55)
for r in results:
    print(f"{r['note']:<28} {r['pred_len']:>3} {r['sample_count']:>3} {r['temperature']:>4.1f} {r['top_p']:>4.1f} {r['dir_accuracy']:>5.1f}% {r['loss']:>8.4f} {r['perplexity']:>8.2f} {r['n_samples']:>5}")
print(f"\nSaved to {out_path}")
