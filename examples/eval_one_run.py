"""Single eval run, called as subprocess by eval_final.py.
Args: model_key pred_len sample_count temperature top_p label
Prints [RESULT]{json} as last stdout line.
"""
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

model_key = sys.argv[1]
pred_len = int(sys.argv[2])
sc = int(sys.argv[3])
T = float(sys.argv[4])
P = float(sys.argv[5])
label = sys.argv[6]

cpu_dev = torch.device("cpu")
import torch_directml
dml_dev = torch_directml.device()

hub = r"E:\AI_Projects\ModelCache\huggingface\hub"
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")

model_paths = {
    "finetuned_small": str(PROJ / "external" / "Kronos-small"),
    "pretrained_small": os.path.join(hub, "models--NeoQuasar--Kronos-small", "snapshots", "901c26c1332695a2a8f243eb2f37243a37bea320"),
    "pretrained_base": os.path.join(hub, "models--NeoQuasar--Kronos-base", "snapshots", "2b554741eca47781b64468546e77fef3e85130e6"),
}

model_path = model_paths.get(model_key)
if not model_path:
    print(f"[RESULT]{{}}"); sys.exit(1)

# Load model on CPU, move to DML for inference
tok = KronosTokenizer.from_pretrained(tok_path).to(cpu_dev)
model = Kronos.from_pretrained(model_path).to(cpu_dev)
model.eval()
model.to(dml_dev)
tok.to(dml_dev)
predictor = KronosPredictor(model, tok, max_context=512, device=dml_dev)

# Load data: 30 stocks, last 200 days (to allow multi-window sliding)
DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:30]

samples = []
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    n = len(df)
    if n < 150:
        continue
    # Take last 150 days for testing
    for start in range(n - 150, n - 100, 3):
        yf = df.iloc[start+90:start+100]
        samples.append({
            "x_df": df.iloc[start:start+90],
            "x_ts": pd.Series(pd.to_datetime(df.iloc[start:start+90]["timestamp"], utc=True)),
            "y_ts": pd.Series(pd.to_datetime(yf["timestamp"], utc=True)),
            "last_c": float(df.iloc[start+89]["close"]),
            "true_10": float(yf.iloc[9]["close"]),
        })

if not samples:
    print(f"[RESULT]{{}}")
    sys.exit(0)

correct = 0; total = 0; mse = 0.0; B = 4
for i in range(0, len(samples), B):
    batch = samples[i:i+B]
    try:
        frames = predictor.predict_batch(
            [s["x_df"] for s in batch],
            [s["x_ts"] for s in batch],
            [s["y_ts"].iloc[:pred_len] for s in batch],
            pred_len,
            T=T, top_k=0, top_p=P,
            sample_count=sc, verbose=False,
        )
    except Exception as e:
        print(f"  [batch fail {i}] {e}", file=sys.stderr, flush=True)
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

result = {
    "dir_accuracy": round(acc * 100, 1),
    "loss": round(float(loss), 4),
    "perplexity": round(ppl, 2),
    "n_samples": total,
    "n_stocks": len(csv_files),
}
print(f"[RESULT]{json.dumps(result)}", flush=True)

# Clean up
try:
    model.to(cpu_dev); tok.to(cpu_dev)
except Exception:
    pass
gc.collect()
