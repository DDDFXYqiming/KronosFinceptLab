"""Fast production-path evaluation: 30 stocks, reduced samples."""

import json, os, sys, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJ = Path(__file__).resolve().parents[1]
os.environ.setdefault("KRONOS_REPO_PATH", str(PROJ / "external" / "Kronos"))
sys.path.insert(0, str(PROJ / "src"))
sys.path.insert(0, str(PROJ / "external" / "Kronos"))

from model import Kronos, KronosPredictor, KronosTokenizer
import torch_directml

device = torch_directml.device()
print(f"Device: DirectML")

DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
N_STOCKS = 30

csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:N_STOCKS]
stocks = {}
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["timestamp"])
    df.sort_values("timestamp", inplace=True)
    stocks[f.stem.replace("cn_", "")] = df
print(f"{len(stocks)} stocks loaded")

samples = []
for symbol, df in stocks.items():
    n = len(df)
    test_start = int(n * 0.9)
    window = 100
    if n - test_start < window:
        continue
    for start in range(test_start, n - window, 5):
        samples.append({
            "symbol": symbol,
            "df": df.iloc[start:start+90],
            "x_ts": pd.to_datetime(df.iloc[start:start+90]["timestamp"], utc=True),
            "y_ts": pd.to_datetime(df.iloc[start+90:start+100]["timestamp"], utc=True),
            "true_c": float(df.iloc[start+99]["close"]),
            "last_c": float(df.iloc[start+89]["close"]),
        })
print(f"{len(samples)} test samples")

hub = r"E:\AI_Projects\ModelCache\huggingface\hub"
models_cfg = {
    "pretrained_small": {
        "path": os.path.join(hub, "models--NeoQuasar--Kronos-small", "snapshots", "901c26c1332695a2a8f243eb2f37243a37bea320"),
        "label": "Kronos-small pretrained",
    },
    "finetuned_small": {
        "path": str(PROJ / "external" / "Kronos-small"),
        "label": "Kronos-small finetuned",
    },
    "pretrained_base": {
        "path": os.path.join(hub, "models--NeoQuasar--Kronos-base", "snapshots", "2b554741eca47781b64468546e77fef3e85130e6"),
        "label": "Kronos-base pretrained",
    },
}
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")
tok = KronosTokenizer.from_pretrained(tok_path).to(device)

results = []
for key, cfg in models_cfg.items():
    t0 = time.perf_counter()
    print(f"\nLoading {cfg['label']}...", end=" ", flush=True)
    model = Kronos.from_pretrained(cfg["path"]).to(device)
    model.eval()
    predictor = KronosPredictor(model, tok, max_context=512, device=device)
    print(f"done ({time.perf_counter()-t0:.1f}s)", flush=True)

    correct = 0
    total = 0
    mse = 0.0
    for i in range(0, len(samples), 32):
        batch = samples[i:i+32]
        try:
            frames = predictor.predict_batch(
                [s["df"] for s in batch],
                [s["x_ts"] for s in batch],
                [s["y_ts"] for s in batch],
                10, T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False,
            )
        except Exception:
            continue
        for j, frame in enumerate(frames):
            pred_c = float(frame.iloc[-1]["close"])
            total += 1
            if (pred_c > batch[j]["last_c"]) == (batch[j]["true_c"] > batch[j]["last_c"]):
                correct += 1
            mse += (pred_c - batch[j]["true_c"]) ** 2

    loss = mse / max(total, 1)
    acc = correct / max(total, 1)
    elapsed = time.perf_counter() - t0
    print(f"  acc={acc*100:.1f}%  loss={loss:.4f}  ppl={np.exp(loss):.2f}  ({elapsed:.0f}s)  {total} samples")
    results.append({
        "model": cfg["label"],
        "acc_pct": round(acc * 100, 1),
        "loss": round(float(loss), 4),
        "ppl": round(float(np.exp(loss)), 2),
        "samples": total,
        "time_s": round(elapsed, 0),
    })

print("\n" + "=" * 60)
print("RESULTS (production path — KronosPredictor.predict() pipeline)")
print("=" * 60)
for r in results:
    print(f"  {r['model']:<30}  acc={r['acc_pct']}%  loss={r['loss']}  ppl={r['ppl']}  ({r['samples']} samples)")

out = PROJ / "output" / "eval_production_results.json"
out.parent.mkdir(exist_ok=True)
json.dump(results, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"\nSaved to {out}")
