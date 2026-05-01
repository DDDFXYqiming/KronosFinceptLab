# KronosFinceptLab CLI Guide

## Installation
```bash
pip install -e ".[api,astock,cli]"
```

## Commands

### Forecast
```bash
kronos forecast --symbol 600036 --pred-len 5 --dry-run
kronos --output table forecast --symbol 600036 --pred-len 5
kronos forecast --input request.json
```

### Batch
```bash
kronos batch --symbols 600036,000858 --pred-len 5 --dry-run
kronos --output table batch --symbols 600036,000858
```

### Data
```bash
kronos data fetch --symbol 600036 --start 20240101 --end 20260430
kronos data search --q 招商银行
```

### Backtest
```bash
kronos backtest ranking --symbols 600036,000858 --start 20250101 --end 20260430 --top-k 1
kronos --output table backtest ranking --symbols 600036,000858 --dry-run
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
kronos --output json forecast --symbol 600036 --pred-len 5
```
