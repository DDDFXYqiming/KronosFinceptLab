"""Evaluate multiple Kronos-small models on CPU for fair comparison.
Runs each model sequentially, cleans up between runs.
Usage: python examples/eval_compare_models.py
"""
import os
import json, os, sys, time, gc
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
import pandas as pd

PROJ = Path(__file__).resolve().parents[1]
os.environ.setdefault("KRONOS_REPO_PATH", str(PROJ / "external" / "Kronos"))
sys.path.insert(0, str(PROJ / "src"))
sys.path.insert(0, str(PROJ / "external" / "Kronos"))
import torch
import torch_directml
from model import Kronos, KronosPredictor, KronosTokenizer

DEVICE = torch_directml.device()

hub =  os.environ.get("HF_HUB_CACHE", os.path.expanduser("~/.cache/huggingface/hub"))
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")

BASE = str(PROJ / "external" / "Kronos" / "finetune_csv")

MODEL_PATHS = {
    "pretrained_small": os.path.join(hub, "models--NeoQuasar--Kronos-small", "snapshots", "901c26c1332695a2a8f243eb2f37243a37bea320"),
    "v2_small_v2": os.path.join(BASE, "finetuned_v2_small_v2", "basemodel", "best_model"),
    "full_small_v3": os.path.join(BASE, "finetuned_full_small_v3", "basemodel", "best_model"),
    "v3_best": os.path.join(BASE, "finetuned_v3_fromFTv1", "basemodel", "best_model"),
    "v3_cont_best": os.path.join(BASE, "finetuned_v3_fromFTv1_cont", "basemodel", "best_model"),
    # Extra: v3_cont epoch details (only tested if needed)
    "v3_cont_epoch_1": os.path.join(BASE, "finetuned_v3_fromFTv1_cont", "basemodel", "epoch_1"),
    "v3_cont_epoch_2": os.path.join(BASE, "finetuned_v3_fromFTv1_cont", "basemodel", "epoch_2"),
}

PL = 5
SC = 8
T = 0.3

# ── Data: 20 A-stock + 10 HK stock ──
DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
a_files = sorted(DATA_DIR.glob("cn_*.csv"))[:20]
hk_files = sorted(DATA_DIR.glob("hk_*.csv"))[:10]
csv_files = a_files + hk_files

samples = []
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    n = len(df)
    if n < 150:
        continue
    for offset in range(0, 50, 10):
        ctx_end = n - 60 - offset
        ctx_start = ctx_end - 90
        if ctx_start < 0 or ctx_end + 5 > n:
            continue
        y_df = df.iloc[ctx_start + 90:ctx_end + 90]
        samples.append({
            "x_df": df.iloc[ctx_start:ctx_end],
            "x_ts": pd.Series(pd.to_datetime(df.iloc[ctx_start:ctx_end]["timestamp"], utc=True)),
            "y_ts": pd.Series(pd.to_datetime(y_df["timestamp"], utc=True)),
            "last_c": float(df.iloc[ctx_end - 1]["close"]),
            "true_5": float(df.iloc[ctx_end + 4]["close"]) if ctx_end + 4 < n else float(df.iloc[-1]["close"]),
        })

print(f"[data] {len(samples)} samples from {len(csv_files)} stocks", flush=True)


def evaluate_model(model_key: str, label: str) -> dict:
    model_path = MODEL_PATHS.get(model_key)
    if not model_path or not os.path.isdir(model_path):
        return {"label": label, "model": model_key, "error": "path not found"}

    print(f"\n=== Evaluating {label} ({model_key}) ===", flush=True)
    t0 = time.time()

    # Load on CPU
    tok = KronosTokenizer.from_pretrained(tok_path)
    model = Kronos.from_pretrained(model_path)
    model.eval()
    model.to(DEVICE)
    tok.to(DEVICE)
    predictor = KronosPredictor(model, tok, max_context=512, device=DEVICE)

    # Inference
    correct = 0
    total = 0
    pred_returns = []
    actual_returns = []
    B = 4

    for i in range(0, len(samples), B):
        batch = samples[i:i+B]
        try:
            frames = predictor.predict_batch(
                [s["x_df"] for s in batch],
                [s["x_ts"] for s in batch],
                [s["y_ts"].iloc[:PL] for s in batch],
                PL, T=T, top_k=0, top_p=0.9,
                sample_count=SC, verbose=False,
            )
        except Exception as e:
            continue
        for j, frame in enumerate(frames):
            try:
                pred_close = float(frame.iloc[-1]["close"])
            except (IndexError, KeyError):
                continue
            last_c = batch[j]["last_c"]
            true_c = batch[j]["true_5"]
            total += 1
            if (pred_close > last_c) == (true_c > last_c):
                correct += 1
            pred_ret = pred_close / last_c - 1
            actual_ret = true_c / last_c - 1
            pred_returns.append(pred_ret)
            actual_returns.append(actual_ret)

    dir_acc = correct / max(total, 1) * 100

    pred_arr = np.array(pred_returns)
    actual_arr = np.array(actual_returns)
    ic = float(np.corrcoef(pred_arr, actual_arr)[0, 1]) if len(pred_arr) > 2 else 0
    rank_ic = float(spearmanr(pred_arr, actual_arr).correlation) if len(pred_arr) > 2 else 0

    k = min(10, total // 2)
    top_k_idx = np.argsort(pred_arr)[-k:]
    portfolio_ret = float(np.mean(actual_arr[top_k_idx]))
    benchmark_ret = float(np.mean(actual_arr))
    excess_ret = portfolio_ret - benchmark_ret
    tracking_err = float(np.std(actual_arr)) if total > 1 else 1.0
    ir = excess_ret / tracking_err if tracking_err > 0 else 0.0

    elapsed = round(time.time() - t0, 1)

    # Clean up
    del model, predictor, tok
    gc.collect()

    result = {
        "label": label,
        "model": model_key,
        "n_stocks": len(csv_files),
        "n_samples": total,
        "dir_accuracy": round(dir_acc, 1),
        "ic": round(ic, 4),
        "rankic": round(rank_ic, 4),
        "aer": round(excess_ret * 100, 2),
        "ir": round(ir, 2),
        "top_k": k,
        "portfolio_return_pct": round(portfolio_ret * 100, 2),
        "benchmark_return_pct": round(benchmark_ret * 100, 2),
        "elapsed_s": elapsed,
    }
    print(f"[RESULT] {json.dumps(result)}", flush=True)
    return result


# ── Run order ──
results = []

# 1. Baseline
results.append(evaluate_model("pretrained_small", "Pretrained baseline"))

# 2. Current best
r = evaluate_model("v2_small_v2", "v2_small_v2 (current best)")
results.append(r)
v2_best = r.get("dir_accuracy", 0)

# 3. full lineage
r = evaluate_model("full_small_v3", "full_small_v3")
results.append(r)

# 4. V3 first round
r = evaluate_model("v3_best", "V3 fromFTv1 best")
results.append(r)
v3_best_acc = r.get("dir_accuracy", 0)

# 5. V3 continuation - only if v3_best beat or matched v2
if v3_best_acc >= v2_best - 2:
    print(f"\n--- v3_best ({v3_best_acc}%) close to v2_best ({v2_best}%), testing v3_cont ---", flush=True)
    r = evaluate_model("v3_cont_best", "V3 cont best")
    results.append(r)
    v3_cont_best_acc = r.get("dir_accuracy", 0)

    # 6. V3 cont epoch details - only if v3_cont_best beat v3_best
    if v3_cont_best_acc >= v3_best_acc:
        print(f"\n--- v3_cont_best ({v3_cont_best_acc}%) beat v3_best ({v3_best_acc}%), testing epochs ---", flush=True)
        r = evaluate_model("v3_cont_epoch_1", "V3 cont epoch_1")
        results.append(r)
        r = evaluate_model("v3_cont_epoch_2", "V3 cont epoch_2")
        results.append(r)
else:
    print(f"\n--- v3_best ({v3_best_acc}%) << v2_best ({v2_best}%), skipping v3_cont ---", flush=True)

# ── Final summary ──
print("\n" + "=" * 70)
print("FINAL COMPARISON")
print("=" * 70)
print(f"{'Model':<25} {'DirAcc%':<8} {'IC':<8} {'RankIC':<8} {'AER%':<8} {'IR':<8} {'Time':<8}")
print("-" * 70)
for r in results:
    if r.get("error"):
        print(f"{r['label']:<25} ERROR: {r['error']}")
    else:
        print(f"{r['label']:<25} {r['dir_accuracy']:<8} {r['ic']:<8} {r['rankic']:<8} {r['aer']:<8} {r['ir']:<8} {r['elapsed_s']:<8}")
print("=" * 70)
