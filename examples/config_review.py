"""Config review chain: verify all settings align between training and production."""
import os, sys
sys.path.insert(0, "src")

from kronos_fincept.config import settings, _resolve_kronos_model_id
from kronos_fincept.schemas import DEFAULT_MODEL_ID, SUPPORTED_MODEL_IDS
from kronos_fincept.predictor import _resolve_pretrained_source, _resolve_kronos_repo
from kronos_fincept.schemas import resolve_tokenizer_id
from pathlib import Path

print("=== Config Review ===\n")

# 1. Model ID
print(f"KRONOS_MODEL_ID (env):  {os.environ.get('KRONOS_MODEL_ID', 'NOT SET')}")
print(f"Resolved model_id:      {_resolve_kronos_model_id()}")
model_path, model_src = _resolve_pretrained_source(_resolve_kronos_model_id())
print(f"Model source:           {model_src}")
print(f"Model path:             {model_path}")
print(f"Model path exists:      {os.path.isdir(str(model_path)) if model_path else False}")

# 2. Config details
print(f"\nKRONOS_DEVICE:          {os.environ.get('KRONOS_DEVICE', 'NOT SET')}")
print(f"enable_real_model:      {settings.kronos.enable_real_model}")
print(f"prewarm_on_startup:     {settings.kronos.prewarm_on_startup}")
print(f"DEFAULT_MODEL_ID:       {DEFAULT_MODEL_ID}")
print(f"SUPPORTED_MODEL_IDS:    {SUPPORTED_MODEL_IDS}")

# 3. Normalization fix check
repo = _resolve_kronos_repo()
if repo:
    model_py = repo / "model" / "kronos.py"
    content = open(model_py, encoding="utf-8").read()
    has_fix = "norm_window = min" in content
    print(f"\nNorm fix applied:       {has_fix}")

# 4. Data paths
proj = Path(__file__).resolve().parents[1]
train_data = proj / "external" / "Kronos" / "finetune_csv" / "data_v2"
print(f"\nTraining data:          {train_data}")
print(f"Training data exists:   {train_data.is_dir()}")
csv_count = len(list(train_data.glob("cn_*.csv")))
print(f"Training CSV count:     {csv_count}")

# 5. Frontend vs Backend defaults
fe_file = proj / "web" / "src" / "lib" / "defaults.ts"
if fe_file.is_file():
    for line in open(fe_file, encoding="utf-8"):
        if "DEFAULT_MODEL_ID" in line and "export" in line and "=" in line:
            print(f"\nFrontend DEFAULT:       {line.strip()}")

print("\n=== Config Review Complete ===")
