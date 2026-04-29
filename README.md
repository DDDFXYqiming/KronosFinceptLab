# KronosFinceptLab

Integration layer between the Kronos financial K-line foundation model and the FinceptTerminal ecosystem.

## Current status

Version: v0.3

## Implemented

- Python package under `src/kronos_fincept/` with schema validation, data adapter, and service layer.
- Sampling parameters: `temperature`, `top_k`, `top_p`, `sample_count`, `max_context`.
- Deterministic dry-run predictor for contract tests.
- Real Kronos predictor wrapper with `KRONOS_REPO_PATH` / `external/Kronos` / `PYTHONPATH` fallback.
- HuggingFace cache path detection and offline failure hints.
- JSON CLI bridge: stdin/stdout and `--input`/`--output` modes.
- FinceptTerminal PythonRunner bridge script (`kronos_forecast.py`).
- `install_bridge.sh` — one-command bridge installation into FinceptTerminal.
- PythonRunner integration tests (8 tests simulating subprocess + JSON contract).
- Minimal Qlib-style adapter with predicted-return signal.
- Real Kronos smoke test (auto-skip when torch/HuggingFace deps missing).

## Tests

```bash
PYTHONPATH=src python3 -m pytest tests -v
```

Current: 18 passed, 2 skipped (real Kronos tests auto-skip without torch).

## Quick start

```bash
# Install
python3 -m pip install -r requirements.txt

# Dry-run forecast
PYTHONPATH=src python3 -m kronos_fincept.cli --input examples/request.forecast.json
```

### Install bridge into FinceptTerminal

```bash
./scripts/install_bridge.sh /path/to/FinceptTerminal          # copy mode
./scripts/install_bridge.sh /path/to/FinceptTerminal --symlink # symlink mode
```

### Real Kronos inference

```bash
export KRONOS_REPO_PATH=/path/to/Kronos
python3 -m pip install -e ".[kronos]"
# Set "dry_run": false in request JSON, then:
PYTHONPATH=src python3 -m kronos_fincept.cli --input request.json
```

## CLI JSON fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| symbol | string | required | Asset identifier |
| timeframe | string | "unknown" | Candle interval |
| pred_len | int | required | Number of future candles to predict |
| dry_run | bool | false | Use deterministic dry-run predictor |
| model_id | string | NeoQuasar/Kronos-small | HuggingFace model ID or local path |
| tokenizer_id | string | NeoQuasar/Kronos-Tokenizer-base | HuggingFace tokenizer ID or local path |
| max_context | int | 512 | Max context length for Kronos |
| temperature | float | 1.0 | Sampling temperature |
| top_k | int | 0 | Top-k filtering (0 = disabled) |
| top_p | float | 0.9 | Nucleus sampling threshold |
| sample_count | int | 1 | Number of parallel samples (averaged) |

## Output contract

Successful responses: `ok`, `symbol`, `timeframe`, `model_id`, `tokenizer_id`, `pred_len`, `forecast`, `metadata`.

All outputs are research forecasts only and are not trading advice.
