# KronosFinceptLab

Integration layer between the Kronos financial K-line foundation model and the FinceptTerminal ecosystem.

## Upstream projects

- **Kronos**: https://github.com/shiyu-coder/Kronos — Foundation model for financial K-line prediction.
- **FinceptTerminal**: https://github.com/Fincept-Corporation/FinceptTerminal — Full-featured financial terminal with data connectors, AI Quant Lab, and PythonRunner.

## Current status

Version: v0.5 (in progress)

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
- Qlib-style adapter with predicted-return signal + batch_predict ranking.
- AkShare data adapter for A-stock OHLCV (`fetch_a_stock_ohlcv`, `fetch_multi_stock_ohlcv`).
- A-stock ranking backtest demo (`examples/backtest_a_stock_ranking.py`).
- Real Kronos-small CPU inference verified (PyTorch 2.11.0, Python 3.13.6, Windows).
- MCP server (`kronos_mcp/kronos_mcp_server.py`) — exposes `forecast_ohlcv`, `batch_forecast_ohlcv`, `fetch_a_stock` as MCP tools for AI Agents.

## MCP Server

```bash
# Install MCP dependencies
pip install -e ".[mcp]"

# Run the MCP server (stdio transport)
PYTHONPATH=src python3 kronos_mcp/kronos_mcp_server.py
```

MCP client config (Claude Desktop, Cursor, etc.):

```json
{
  "mcpServers": {
    "kronos-fincept": {
      "command": "python3",
      "args": ["kronos_mcp/kronos_mcp_server.py"],
      "cwd": "/path/to/KronosFinceptLab",
      "env": {
        "PYTHONPATH": "src",
        "KRONOS_REPO_PATH": "external/Kronos",
        "HF_HOME": "external"
      }
    }
  }
}
```

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

### Windows setup (with GPU-capable PyTorch)

```powershell
# Install PyTorch (CPU version, Windows Python 3.13+)
pip install torch torchvision torchaudio

# Install project dependencies
cd E:\AI_Projects\KronosFinceptLab
pip install -e .
pip install transformers huggingface-hub einops

# Download models via HuggingFace mirror (faster in China)
python -c "from huggingface_hub import snapshot_download; import os; os.environ['HF_ENDPOINT']='https://hf-mirror.com'; snapshot_download('NeoQuasar/Kronos-small', local_dir='external/Kronos-small'); snapshot_download('NeoQuasar/Kronos-Tokenizer-base', local_dir='external/Kronos-Tokenizer-base')"
```

### Install bridge into FinceptTerminal

```bash
./scripts/install_bridge.sh /path/to/FinceptTerminal          # copy mode
./scripts/install_bridge.sh /path/to/FinceptTerminal --symlink # symlink mode
```

### Real Kronos inference

```bash
# Dry-run (no model needed)
python3 -m kronos_fincept.cli --input examples/request.forecast.json

# Real inference (CPU)
export KRONOS_REPO_PATH=external/Kronos
export HF_HOME=external
PYTHONPATH=src python3 -m kronos_fincept.cli --input examples/request.real.json

# Windows real inference
set PYTHONPATH=src
set KRONOS_REPO_PATH=E:\AI_Projects\KronosFinceptLab\external\Kronos
set HF_HOME=E:\AI_Projects\KronosFinceptLab\external
python -m kronos_fincept.cli --input examples\request.real.json
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
