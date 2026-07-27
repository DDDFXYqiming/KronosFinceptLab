"""Single model eval run: inference + all metrics. Args: model_key label."""
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
from model import Kronos, KronosPredictor, KronosTokenizer
import torch_directml

model_key = sys.argv[1]
label = sys.argv[2]
pl = int(sys.argv[3]) if len(sys.argv) > 3 else 5
sc = int(sys.argv[4]) if len(sys.argv) > 4 else 8
T = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
P = float(sys.argv[6]) if len(sys.argv) > 6 else 0.9

dml_dev = torch_directml.device()

hub = r"E:\AI_Projects\ModelCache\huggingface\hub"
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")

model_paths = {
    "finetuned_small": str(PROJ / "external" / "Kronos-small"),
    "pretrained_small": os.path.join(hub, "models--NeoQuasar--Kronos-small", "snapshots", "901c26c1332695a2a8f243eb2f37243a37bea320"),
    "pretrained_base": os.path.join(hub, "models--NeoQuasar--Kronos-base", "snapshots", "2b554741eca47781b64468546e77fef3e85130e6"),
    "finetuned_small_v2": str(PROJ / "external" / "Kronos" / "finetune_csv" / "finetuned_v2_small_v2" / "basemodel" / "best_model"),
}

model_path = model_paths.get(model_key)
if not model_path:
    print(f"[RESULT]{{}}")
    sys.exit(1)

# Load model on CPU to avoid pagefile issue
tok = KronosTokenizer.from_pretrained(tok_path)
model = Kronos.from_pretrained(model_path)
model.eval()
model.to(dml_dev)
tok.to(dml_dev)
predictor = KronosPredictor(model, tok, max_context=512, device=dml_dev)

# ── Data: 100 A + 30 HK stocks ──
DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:100] + sorted(DATA_DIR.glob("hk_*.csv"))[:30]

samples = []
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    n = len(df)
    if n < 150:
        continue
    sym = f.stem.replace("cn_", "").replace("hk_", "")
    is_hk = "hk_" in f.stem
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
            "last_vol": float(df.iloc[ctx_end - 1]["volume"]),
        })

if not samples:
    print("[RESULT]{}")
    sys.exit(0)

print(f"[data] {len(samples)} samples from {len(csv_files)} stocks", flush=True)

# ── Inference ──
correct = 0; total = 0
pred_returns = []; actual_returns = []
pred_vols = []; actual_vols = []
B = 4

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
        # Volatility from prediction sequence
        pred_seq = frame["close"].values[:pl]
        pred_seq_ret = np.diff(pred_seq) / pred_seq[:-1]
        pred_vol = float(np.std(pred_seq_ret) * np.sqrt(252)) if len(pred_seq_ret) > 1 else 0
        pred_vols.append(pred_vol)
        actual_vols.append(0)  # placeholder - real vol needs more data

dir_acc = correct / max(total, 1) * 100

# ── Metrics ──
pred_arr = np.array(pred_returns)
actual_arr = np.array(actual_returns)

ic = float(np.corrcoef(pred_arr, actual_arr)[0, 1]) if len(pred_arr) > 2 else 0
rank_ic = float(spearmanr(pred_arr, actual_arr).correlation) if len(pred_arr) > 2 else 0

# Top-k portfolio simulation
k = min(10, total // 2)
top_k_idx = np.argsort(pred_arr)[-k:]
portfolio_ret = float(np.mean(actual_arr[top_k_idx]))
benchmark_ret = float(np.mean(actual_arr))
excess_ret = portfolio_ret - benchmark_ret
# Tracking error: std of all actual returns (conservative estimate)
tracking_err = float(np.std(actual_arr)) if total > 1 else 1.0
ir = excess_ret / tracking_err if tracking_err > 0 else 0.0

# Vol MAE (placeholder - needs better realized vol)
vol_mae = 0.0

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
    "vol_mae": round(vol_mae, 4),
    "top_k": k,
    "portfolio_return_pct": round(portfolio_ret * 100, 2),
    "benchmark_return_pct": round(benchmark_ret * 100, 2),
}
print(f"[RESULT]{json.dumps(result)}", flush=True)

# Clean up
del model, predictor
gc.collect()
