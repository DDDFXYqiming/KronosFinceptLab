"""DML grid eval — safe VRAM usage. Load on CPU, infer on DML, clear GPU between groups."""

import json, os, sys, time, gc
from pathlib import Path
import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parents[1]
os.environ.setdefault("KRONOS_REPO_PATH", str(PROJ / "external" / "Kronos"))
sys.path.insert(0, str(PROJ / "src"))
sys.path.insert(0, str(PROJ / "external" / "Kronos"))

import torch
from model import Kronos, KronosPredictor, KronosTokenizer

cpu_dev = torch.device("cpu")
import torch_directml
dml_dev = torch_directml.device()

hub = r"E:\AI_Projects\ModelCache\huggingface\hub"
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")
ft_path = str(PROJ / "external" / "Kronos-small")

# ── Data (30 stocks, last 5%) ──
DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:30]
samples = []
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    n = len(df); test_start = max(int(n * 0.95), n - 150)
    if test_start <= 0: continue
    for start in range(test_start, n - 100, 3):
        y_df = df.iloc[start+90:start+100]
        samples.append({
            "x_df": df.iloc[start:start+90],
            "x_ts": pd.Series(pd.to_datetime(df.iloc[start:start+90]["timestamp"], utc=True)),
            "y_ts": pd.Series(pd.to_datetime(y_df["timestamp"], utc=True)),
            "last_c": float(df.iloc[start+89]["close"]),
            "true_10": float(y_df.iloc[9]["close"]),
        })
print(f"{len(samples)} samples from {len(csv_files)} stocks")

# ── Load tokenizer on CPU ──
print("Loading tokenizer on CPU...", end=" ", flush=True)
tok = KronosTokenizer.from_pretrained(tok_path).to(cpu_dev)
print("done")

# ── Load model on CPU to avoid pagefile issue ──
print("Loading model on CPU...", end=" ", flush=True)
t0 = time.perf_counter()
model = Kronos.from_pretrained(ft_path).to(cpu_dev)
model.eval()
print(f"done ({time.perf_counter()-t0:.1f}s)")

out_path = PROJ / "output" / "eval_grid_results.json"
results = []
B = 4  # small batch to keep VRAM low
seen_notes = set()

grid = [
    (10, 1, 1.0, 0.9, "A: baseline"),
    (10, 8, 1.0, 0.9, "D: sample_count=8"),
    (10, 1, 0.5, 0.9, "J: pl10+T0.5"),
    (10, 8, 0.5, 0.9, "K: pl10+sc8+T0.5"),
    (5,  1, 1.0, 0.9, "B: pred_len=5"),
    (5,  8, 1.0, 0.9, "F: pl5+sc8"),
    (5,  8, 0.5, 0.9, "G: +T0.5"),
    (5,  8, 0.3, 0.9, "I: +T0.3"),
]

for pred_len, sc, T, p, note in grid:
    print(f"\n{'─'*50}")
    print(f"{note}: pl={pred_len} sc={sc} T={T} P={p}")
    print(f"{'─'*50}")

    # Move model + tok to DML
    t_start = time.perf_counter()
    print("  moving to DML...", end=" ", flush=True)
    model.to(dml_dev)
    tok.to(dml_dev)
    predictor = KronosPredictor(model, tok, max_context=512, device=dml_dev)
    print("done", flush=True)

    correct = 0; total = 0; mse = 0.0

    for i in range(0, len(samples), B):
        batch = samples[i:i+B]
        try:
            frames = predictor.predict_batch(
                [s["x_df"] for s in batch],
                [s["x_ts"] for s in batch],
                [s["y_ts"].iloc[:pred_len] for s in batch],
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
            total += 1
            if (pred_c > batch[j]["last_c"]) == (batch[j]["true_10"] > batch[j]["last_c"]):
                correct += 1
            mse += (pred_c - batch[j]["true_10"]) ** 2

    loss = mse / max(total, 1)
    acc = correct / max(total, 1)
    ppl = float(np.exp(loss)) if loss < 30 else float("inf")
    elapsed = time.perf_counter() - t_start

    print(f"  acc={acc*100:.1f}%  loss={loss:.4f}  ppl={ppl:.2f}  ({total} samples, {elapsed:.1f}s)", flush=True)

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

    # Move model back to CPU to free GPU memory
    model.to(cpu_dev)
    tok.to(cpu_dev)
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

# ── Print ──
print(f"\n{'='*55}")
print("RESULTS (DML - safe mode)")
print(f"{'='*55}")
print(f"{'Note':<28} {'PL':>3} {'SC':>3} {'T':>4} {'P':>4} {'Acc%':>6} {'Loss':>8} {'PPL':>10} {'N':>5}")
print("-" * 55)
for r in results:
    ppl_s = f"{r['perplexity']:.1f}" if r['perplexity'] < 1e6 else f"{r['perplexity']:.2e}"
    print(f"{r['note']:<28} {r['pred_len']:>3} {r['sample_count']:>3} {r['temperature']:>4.1f} {r['top_p']:>4.1f} {r['dir_accuracy']:>5.1f}% {r['loss']:>8.4f} {ppl_s:>10} {r['n_samples']:>5}")

print(f"\nSaved to {out_path}")
