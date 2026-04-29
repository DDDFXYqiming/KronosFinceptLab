# KronosFinceptLab CLI Guide

## Installation
```bash
pip install -e ".[api,astock,cli]"
```

## Commands

### Forecast
```bash
kronos forecast --symbol 600519 --pred-len 5 --dry-run
kronos forecast --symbol 600519 --pred-len 5 --output table
kronos forecast --input request.json
```

### Batch
```bash
kronos batch --symbols 600519,000858 --pred-len 5 --dry-run
kronos batch --symbols 600519,000858 --output table
```

### Data
```bash
kronos data fetch --symbol 600519 --start 20240101 --end 20260430
kronos data search --q 茅台
```

### Backtest
```bash
kronos backtest ranking --symbols 600519,000858 --start 20250101 --end 20260430 --top-k 1
kronos backtest ranking --symbols 600519,000858 --dry-run --output table
```

### Serve
```bash
kronos serve --host 0.0.0.0 --port 8000
kronos serve --host 0.0.0.0 --port 8000 --workers 4
```

## Output Format
- `--output json` (default): Machine-readable JSON
- `--output table`: Human-readable rich table

## Hermes Agent Integration
```bash
# Via terminal command in Feishu
kronos forecast --symbol 600519 --pred-len 5 --output json
```
