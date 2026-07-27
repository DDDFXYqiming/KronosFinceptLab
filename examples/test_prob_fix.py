"""Test the probabilistic prediction fix with DML."""
import sys, os, time
from pathlib import Path
import pandas as pd

PROJ = Path(__file__).resolve().parents[1]
os.environ.setdefault("KRONOS_REPO_PATH", str(PROJ / "external" / "Kronos"))
sys.path.insert(0, str(PROJ / "src"))
sys.path.insert(0, str(PROJ / "external" / "Kronos"))

import torch
from model import Kronos, KronosPredictor, KronosTokenizer
import torch_directml

dml_dev = torch_directml.device()
cpu_dev = torch.device("cpu")

hub = r"E:\AI_Projects\ModelCache\huggingface\hub"
tok_path = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")
ft_path = str(PROJ / "external" / "Kronos-small")

print("Loading model on CPU...", end=" ", flush=True)
tok = KronosTokenizer.from_pretrained(tok_path).to(cpu_dev)
model = Kronos.from_pretrained(ft_path).to(cpu_dev)
model.eval()
print("done")

model.to(dml_dev)
tok.to(dml_dev)

from kronos_fincept.predictor import KronosPredictorWrapper
from model import KronosPredictor as UpKronosPredictor

up_pred = UpKronosPredictor(model, tok, max_context=512, device=dml_dev)
wrapper = KronosPredictorWrapper(
    model_id="NeoQuasar/Kronos-small",
    tokenizer_id="NeoQuasar/Kronos-Tokenizer-base",
    max_context=512, temperature=1.0, sample_count=8,
)
wrapper._predictor = up_pred
wrapper._resolved_device = "dml"

# Test data
file = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2" / "cn_000001.csv"
df = pd.read_csv(file, parse_dates=["timestamp"]).tail(90)
df.sort_values("timestamp", inplace=True)
ts = pd.to_datetime(df["timestamp"], utc=True)
feat = df[["open","high","low","close","volume","amount"]].astype(float)

t0 = time.perf_counter()
result = wrapper.predict_probabilistic(df=feat, x_timestamp=ts, pred_len=5)
elapsed = time.perf_counter() - t0

print(f"\n{'='*50}")
print("Probabilistic Prediction Test Results")
print(f"{'='*50}")
print(f"sample_count:     {result.sample_count}")
print(f"samples count:    {len(result.samples)}")
print(f"final_closes:     {[round(float(s.iloc[-1]['close']),2) for s in result.samples]}")
print(f"upside_prob:      {result.upside_probability:.4f}")
print(f"forecast_range:   [{result.forecast_range[0]:.2f}, {result.forecast_range[1]:.2f}]")
print(f"mean_final_close: {result.mean_final_close:.2f}")
print(f"vol_amplif:       {result.volatility_amplification:.4f}")
print(f"elapsed_ms:       {result.elapsed_ms}")
print(f"device:           {result.device}")
print(f"backend:          {result.backend}")

# Validation
assert result.sample_count == 8, f"Expected 8 samples, got {result.sample_count}"
assert len(result.samples) == 8, f"Expected 8 sample paths, got {len(result.samples)}"
assert 0 <= result.upside_probability <= 1, f"unexpected upside_prob: {result.upside_probability}"
assert result.forecast_range[0] <= result.mean_final_close <= result.forecast_range[1], "mean not in range"
print("\n✅ All assertions passed!")
