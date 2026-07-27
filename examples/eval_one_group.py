"""Evaluate one param group as a standalone process. Args: pred_len sc T P note."""
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

pred_len = int(sys.argv[1])
sc = int(sys.argv[2])
T = float(sys.argv[3])
p = float(sys.argv[4])
note = sys.argv[5]

cpu_dev = torch.device("cpu")
import torch_directml
dml_dev = torch_directml.device()

hub = r"E:\AI_Projects\ModelCache\huggingface\hub"
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")
ft_path = str(PROJ / "external" / "Kronos-small")

# Load data
DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:30]
samples = []
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    n = len(df); ts = max(int(n * 0.95), n - 150)
    if ts <= 0: continue
    for start in range(ts, n - 100, 3):
        yf = df.iloc[start+90:start+100]
        samples.append({
            "x_df": df.iloc[start:start+90],
            "x_ts": pd.Series(pd.to_datetime(df.iloc[start:start+90]["timestamp"], utc=True)),
            "y_ts": pd.Series(pd.to_datetime(yf["timestamp"], utc=True)),
            "last_c": float(df.iloc[start+89]["close"]),
            "true_10": float(yf.iloc[9]["close"]),
        })
print(f"[data] {len(samples)} samples", flush=True)

# Load model on CPU, move to DML for inference
tok = KronosTokenizer.from_pretrained(tok_path).to(cpu_dev)
model = Kronos.from_pretrained(ft_path).to(cpu_dev)
model.eval()
model.to(dml_dev)
tok.to(dml_dev)
predictor = KronosPredictor(model, tok, max_context=512, device=dml_dev)

correct = 0; total = 0; mse = 0.0; B = 4
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
print(f"[result] acc={acc*100:.1f}% loss={loss:.4f} ppl={ppl:.2f} ({total} samples)", flush=True)

# Save incrementally
out_path = PROJ / "output" / "eval_grid_results.json"
results = json.load(open(out_path)) if out_path.exists() else []
results.append({
    "model": "finetuned_small",
    "pred_len": pred_len, "sample_count": sc,
    "temperature": T, "top_p": p, "note": note,
    "dir_accuracy": round(acc*100, 1),
    "loss": round(float(loss), 4),
    "perplexity": round(ppl, 2),
    "n_samples": total,
})
json.dump(results, open(out_path, "w", encoding="utf-8"), indent=2)
print(f"[saved] {out_path}", flush=True)

# Clean up: move to CPU before exit to avoid DML deadlock cascade
try:
    model.to(cpu_dev)
    tok.to(cpu_dev)
except Exception:
    pass  # ignore DML deadlock at exit
gc.collect()
