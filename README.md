# KronosFinceptLab

KronosFinceptLab is an integration layer for connecting Kronos financial K-line forecasting with the FinceptTerminal ecosystem.

## Current status

Version: v0.1 scaffold and bridge contract.

## Implemented

- Python package structure under `src/kronos_fincept/`.
- Forecast request schema validation.
- OHLCV data adapter for Kronos-compatible DataFrame inputs.
- Deterministic dry-run predictor for integration and contract tests.
- JSON CLI bridge:
  - stdin / stdout mode
  - `--input` / `--output` file mode
- FinceptTerminal-compatible bridge script:
  - `integrations/fincept_terminal/scripts/kronos_forecast.py`
- Minimal Qlib-style adapter:
  - `integrations/fincept_terminal/qlib_adapter/kronos_model_adapter.py`
- Example request and CSV files.
- Unit tests for schema, adapter, and CLI contract.

## Usage

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run tests:

```bash
PYTHONPATH=src python3 -m pytest tests -q
```

Run the dry-run forecast example:

```bash
PYTHONPATH=src python3 -m kronos_fincept.cli --input examples/request.forecast.json
```

Run the FinceptTerminal bridge script directly:

```bash
PYTHONPATH=src python3 integrations/fincept_terminal/scripts/kronos_forecast.py --input examples/request.forecast.json
```

## Output contract

The CLI returns JSON. Successful responses contain:

- `ok`
- `symbol`
- `timeframe`
- `model_id`
- `tokenizer_id`
- `pred_len`
- `forecast`
- `metadata`

All outputs are research forecasts only and are not trading advice.

## Real Kronos inference

The current default test path uses `dry_run: true`. Real Kronos inference requires upstream Kronos and model dependencies to be installed and importable.
