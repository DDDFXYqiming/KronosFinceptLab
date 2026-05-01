# Installing KronosFinceptLab in FinceptTerminal

This document describes the v0.2 bridge path. It does not require C++ UI changes.

## 1. Install the integration package

From this repository:

```bash
python3 -m pip install -e .
```

For real Kronos inference, also install model dependencies:

```bash
python3 -m pip install -e ".[kronos]"
```

## 2. Configure upstream Kronos

Point to the upstream Kronos repo via one of:

```bash
# Option A: environment variable
export KRONOS_REPO_PATH=/path/to/Kronos

# Option B: place Kronos at external/Kronos in this project
cp -r /path/to/Kronos external/Kronos
```

The resolution order is: `KRONOS_REPO_PATH` → `external/Kronos` → `PYTHONPATH`.

## 3. Add the bridge script to FinceptTerminal

Copy or symlink:

```text
integrations/fincept_terminal/scripts/kronos_forecast.py
```

into:

```text
FinceptTerminal/fincept-qt/scripts/kronos_forecast.py
```

## 4. Call contract

```bash
# Dry-run (no model needed)
python3 kronos_forecast.py --input request.forecast.json --output forecast.json

# Real inference
KRONOS_REPO_PATH=/path/to/Kronos python3 kronos_forecast.py --input request.real.json --output forecast.json
```

## 5. JSON fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| symbol | string | required | Asset identifier |
| timeframe | string | "unknown" | Candle interval |
| pred_len | int | required | Number of future candles to predict |
| dry_run | bool | false | Use deterministic dry-run predictor |
| model_id | string | NeoQuasar/Kronos-base | HuggingFace model ID or local path |
| tokenizer_id | string | NeoQuasar/Kronos-Tokenizer-base | HuggingFace tokenizer ID or local path |
| max_context | int | 512 | Max context length for Kronos |
| temperature | float | 1.0 | Sampling temperature |
| top_k | int | 0 | Top-k filtering (0 = disabled) |
| top_p | float | 0.9 | Nucleus sampling threshold |
| sample_count | int | 1 | Number of parallel samples (averaged) |

## 6. Safety boundary

All outputs are research forecasts only. Do not wire this directly to real trading without a separate manual confirmation layer.
