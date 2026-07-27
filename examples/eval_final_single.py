"""Final eval: single process, sequential runs, clean GPU memory between combos."""

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
import torch_directml

dml_dev = torch_directml.device()
print(f"Device: DirectML", flush=True)

# ── Paths ──
hub = r"E:\AI_Projects\ModelCache\huggingface\hub"
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")

model_paths = {
    "finetuned_small": str(PROJ / "external" / "Kronos-small"),
    "pretrained_small": os.path.join(hub, "models--NeoQuasar--Kronos-small", "snapshots", "901c26c1332695a2a8f243eb2f37243a37bea320"),
    "pretrained_base": os.path.join(hub, "models--NeoQuasar--Kronos-base", "snapshots", "2b554741eca47781b64468546e77fef3e85130e6"),
}

# ── Tokenizer (load once) ──
print("Loading tokenizer...", end=" ", flush=True)
tok = KronosTokenizer.from_pretrained(tok_path)
print("done", flush=True)

# ── Data ──
DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:30]
samples = []
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    n = len(df)
    if n < 150:
        continue
    for start in range(n - 150, n - 100, 3):
        yf = df.iloc[start+90:start+100]
        samples.append({
            "x_df": df.iloc[start:start+90],
            "x_ts": pd.Series(pd.to_datetime(df.iloc[start:start+90]["timestamp"], utc=True)),
            "y_ts": pd.Series(pd.to_datetime(yf["timestamp"], utc=True)),
            "last_c": float(df.iloc[start+89]["close"]),
            "true_10": float(yf.iloc[9]["close"]),
        })
print(f"{len(samples)} samples from {len(csv_files)} stocks", flush=True)

# ── Grid ──
grid = [
    ("finetuned_small",   5, 8,  0.5, 0.9, "FT best"),
    ("finetuned_small",   5, 1,  1.0, 0.9, "FT baseline"),
    ("pretrained_small",  5, 8,  0.5, 0.9, "Pre best"),
    ("pretrained_small",  5, 1,  1.0, 0.9, "Pre baseline"),
    ("pretrained_base",   5, 8,  0.5, 0.9, "Base best"),
    ("pretrained_base",   5, 1,  1.0, 0.9, "Base baseline"),
]

OUT = PROJ / "output"
OUT.mkdir(exist_ok=True)
out_path = OUT / "eval_final_results.json"
results = []

for model_key, pl, sc, T, P, label in grid:
    print(f"\n{'='*50}", flush=True)
    print(f"{label}: {model_key}  pl={pl} sc={sc} T={T} P={P}", flush=True)

    # Load model on CPU, move to DML
    t0 = time.perf_counter()
    print("  loading model...", end=" ", flush=True)
    model = Kronos.from_pretrained(model_paths[model_key])
    model.eval()
    model.to(dml_dev)
    predictor = KronosPredictor(model, tok, max_context=512, device=dml_dev)
    print(f"done ({time.perf_counter()-t0:.1f}s)", flush=True)

    correct = 0; total = 0; mse = 0.0; B = 4
    for i in range(0, len(samples), B):
        batch = samples[i:i+B]
        try:
            frames = predictor.predict_batch(
                [s["x_df"] for s in batch],
                [s["x_ts"] for s in batch],
                [s["y_ts"].iloc[:pl] for s in batch],
                pl, T=T, top_k=0, top_p=P,
                sample_count=sc, verbose=False,
            )
        except Exception as e:
            print(f"  batch fail {i}: {e}", flush=True)
            continue
        for j, frame in enumerate(frames):
            try:
                pc = float(frame.iloc[-1]["close"])
            except (IndexError, KeyError):
                continue
            total += 1
            if (pc > batch[j]["last_c"]) == (batch[j]["true_10"] > batch[j]["last_c"]):
                correct += 1
            mse += (pc - batch[j]["true_10"]) ** 2

    loss = mse / max(total, 1)
    acc = correct / max(total, 1)
    ppl = float(np.exp(loss)) if loss < 30 else float("inf")
    elapsed = time.perf_counter() - t0

    print(f"  acc={acc*100:.1f}%  loss={loss:.4f}  ppl={ppl:.2f}  ({total} samples, {elapsed:.0f}s)", flush=True)

    results.append({
        "label": label, "model": model_key,
        "pred_len": pl, "sample_count": sc,
        "temperature": T, "top_p": P,
        "dir_accuracy": round(acc*100, 1),
        "loss": round(float(loss), 4),
        "perplexity": round(ppl, 2),
        "n_samples": total,
        "elapsed_s": round(elapsed, 1),
    })
    json.dump(results, open(out_path, "w", encoding="utf-8"), indent=2)

    # Free GPU memory
    del model, predictor
    gc.collect()
    gc.collect()

# ── Print summary ──
print(f"\n{'='*70}")
print("FINAL RESULTS (single process)")
print(f"{'='*70}")
print(f"{'Label':<20} {'Acc%':>6} {'Loss':>8} {'PPL':>10} {'Samples':>7} {'Time':>6}")
print("-" * 70)
for r in results:
    ppl_s = f"{r['perplexity']:.1f}" if r['perplexity'] < 1e6 else f"{r['perplexity']:.2e}"
    print(f"{r['label']:<20} {r['dir_accuracy']:>5.1f}% {r['loss']:>8.4f} {ppl_s:>10} {r['n_samples']:>5} {r['elapsed_s']:>5.0f}s")

# Comparison
ft_best = next((r for r in results if r["label"] == "FT best"), None)
ft_base = next((r for r in results if r["label"] == "FT baseline"), None)
pre_best = next((r for r in results if r["label"] == "Pre best"), None)
base_best = next((r for r in results if r["label"] == "Base best"), None)

if ft_best and pre_best:
    print(f"\nFT best vs Pre best:   {ft_best['dir_accuracy']}% vs {pre_best['dir_accuracy']}%  Δ={ft_best['dir_accuracy']-pre_best['dir_accuracy']:+.1f}pp")
if ft_best and ft_base:
    print(f"FT best vs FT baseline: {ft_best['dir_accuracy']}% vs {ft_base['dir_accuracy']}%  Δ={ft_best['dir_accuracy']-ft_base['dir_accuracy']:+.1f}pp")
if ft_best:
    print(f"FT best vs Random (50%): {ft_best['dir_accuracy']}% vs 50%  Δ={ft_best['dir_accuracy']-50:+.1f}pp")
if ft_best and base_best:
    print(f"FT best vs Base best:   {ft_best['dir_accuracy']}% vs {base_best['dir_accuracy']}%  Δ={ft_best['dir_accuracy']-base_best['dir_accuracy']:+.1f}pp")

print(f"\nSaved to {out_path}")
