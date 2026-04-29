# Installing KronosFinceptLab in FinceptTerminal

This document describes the current v0.1 bridge path. It does not require C++ UI changes.

## 1. Install the integration package

From this repository:

```bash
python -m pip install -e .
```

For contract testing only, use `dry_run: true` in request JSON. For real Kronos inference, install upstream Kronos and its model dependencies separately, and make the upstream `model` package importable through `PYTHONPATH`.

## 2. Add the bridge script to FinceptTerminal

Copy or symlink:

```text
integrations/fincept_terminal/scripts/kronos_forecast.py
```

into:

```text
FinceptTerminal/fincept-qt/scripts/kronos_forecast.py
```

## 3. Call contract

The script accepts request JSON from stdin or `--input` and writes response JSON to stdout or `--output`.

```bash
python kronos_forecast.py --input examples/request.forecast.json --output forecast.json
```

## 4. Safety boundary

All outputs are research forecasts only. Do not wire this directly to real trading without a separate manual confirmation layer.
