# KronosFinceptLab

Integration layer between the Kronos financial K-line foundation model and the FinceptTerminal ecosystem.

## Current status

Version: v0.2

## Implemented

- Python package structure under `src/kronos_fincept/`.
- Forecast request schema validation with sampling parameters (temperature, top_k, top_p, sample_count, max_context).
- OHLCV data adapter for Kronos-compatible DataFrame inputs.
- Deterministic dry-run predictor for integration and contract tests.
- Real Kronos predictor wrapper with `KRONOS_REPO_PATH` env var support.
- HuggingFace cache path detection and offline failure hints.
- JSON CLI bridge (stdin/stdout, `--input`/`--output`).
- FinceptTerminal-compatible PythonRunner bridge script.
- Minimal Qlib-style adapter with predicted-return signal.
- Example request and CSV files.
- Unit tests for schema, adapter, CLI contract, and real Kronos smoke test (auto-skip when deps missing).

## Usage

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run tests:

```bash
PYTHONPATH=src python3 -m pytest tests -v
```

Run the dry-run forecast example:

```bash
PYTHONPATH=src python3 -m kronos_fincept.cli --input examples/request.forecast.json
```

### Real Kronos inference

To use real Kronos models instead of dry-run, ensure:

1. **Upstream Kronos** is available via one of:
   - Set `KRONOS_REPO_PATH=/path/to/Kronos`
   - Place Kronos at `external/Kronos` in the project root
   - Add the Kronos root to `PYTHONPATH`
2. **PyTorch** and **huggingface-hub** are installed:
   ```bash
   python3 -m pip install -e ".[kronos]"
   ```
3. Set `dry_run: false` in the request JSON (or omit it).

Example real request:

```bash
PYTHONPATH=src:external/Kronos python3 -m kronos_fincept.cli --input examples/request.forecast.json
# (set "dry_run": false in the JSON first)
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

Successful responses contain: `ok`, `symbol`, `timeframe`, `model_id`, `tokenizer_id`, `pred_len`, `forecast`, `metadata`.

All outputs are research forecasts only and are not trading advice.
