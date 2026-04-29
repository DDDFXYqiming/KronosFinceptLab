"""Quick test: Kronos real inference via Windows Python."""
import sys, os, time
import pandas as pd

project_root = os.path.dirname(os.path.abspath(__file__))
kronos_repo = os.path.join(project_root, "external", "Kronos")
os.environ["KRONOS_REPO_PATH"] = kronos_repo
os.environ["HF_HOME"] = os.path.join(project_root, "external")
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, kronos_repo)

from model import Kronos, KronosPredictor, KronosTokenizer

# Sample data
rows = []
price = 100.0
for i in range(60):
    o = price; c = price * (1 + (i%5-2)*0.002)
    h = max(o,c)*1.005; l = min(o,c)*0.995
    rows.append({"open":o,"high":h,"low":l,"close":c})
    price = c

df = pd.DataFrame(rows)[["open","high","low","close"]].astype(float)
timestamps = pd.Series(pd.date_range("2026-01-01", periods=60, freq="B"))

# Load model
project = os.path.join(project_root, "external")
tokenizer = KronosTokenizer.from_pretrained(os.path.join(project, "Kronos-Tokenizer-base"))
model = Kronos.from_pretrained(os.path.join(project, "Kronos-small"))
model.to("cpu"); model.eval()
predictor = KronosPredictor(model, tokenizer, max_context=512, device="cpu")

# Predict
pred_len = 5
future_ts = pd.Series(pd.date_range(start=timestamps.iloc[-1] + pd.tseries.offsets.BDay(1), periods=pred_len, freq="B"))
started = time.perf_counter()
result = predictor.predict(df=df, x_timestamp=timestamps, y_timestamp=future_ts, pred_len=pred_len, T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False)
elapsed = int((time.perf_counter() - started) * 1000)

last_close = float(df["close"].iloc[-1])
pred_close = float(result["close"].iloc[-1])
ret = (pred_close / last_close - 1) * 100

print(f"=== Kronos Real Inference ===")
print(f"Input: 60 bars, last close = {last_close:.2f}")
print(f"Model: Kronos-small, Device: cpu, Time: {elapsed}ms")
print(f"\nPredicted {pred_len} bars:")
for idx in range(len(result)):
    r = result.iloc[idx]
    print(f"  Bar {idx+1}: O={r['open']:.2f} H={r['high']:.2f} L={r['low']:.2f} C={r['close']:.2f}")
print(f"\nPredicted close: {pred_close:.2f} ({ret:+.2f}%)")
print(f"✅ PASSED")
