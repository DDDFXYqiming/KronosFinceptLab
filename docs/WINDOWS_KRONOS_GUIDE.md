# Kronos Model Service - Windows Guide

## Overview

The Kronos model service is deployed on Windows and can be used via:

1. **FinceptTerminal PythonRunner** - Call directly from FinceptTerminal
2. **Command-line tools** - Via batch scripts
3. **MCP Server** - For AI Agent integration

## Requirements

- **OS**: Windows 10/11
- **Python**: 3.13.6 (pre-installed)
- **PyTorch**: 2.11.0 (pre-installed)
- **Storage**: ~500MB (model files)

## Model Location

```
E:\AI_Projects\KronosFinceptLab\external\
├── Kronos\                    # Kronos upstream source
├── Kronos-base\              # Kronos-base model (98MB)
├── Kronos-Tokenizer-base\     # Tokenizer (15MB)
├── hub\                       # HuggingFace Hub cache
└── xet\                       # Other caches
```

## Quick Start

### Method 1: Using Batch Scripts (Recommended)

```batch
# Enter FinceptTerminal scripts directory
cd E:\FinceptTerminal\scripts

# Run test forecast
run_kronos_forecast.bat --test

# Input from file
run_kronos_forecast.bat --input request.json

# Input from stdin
echo {"symbol":"600036",...} | run_kronos_forecast.bat --stdin
```

### Method 2: Using Project Scripts

```batch
# Enter project directory
cd E:\AI_Projects\KronosFinceptLab

# Run test
kronos_forecast.bat --test

# Run batch forecast
kronos_forecast.bat --batch

# Start MCP server
kronos_forecast.bat --mcp
```

### Method 3: Manual Environment Setup

```batch
# Set environment variables
set KRONOS_REPO_PATH=E:\AI_Projects\KronosFinceptLab\external\Kronos
set HF_HOME=E:\AI_Projects\KronosFinceptLab\external
set PYTHONPATH=E:\AI_Projects\KronosFinceptLab\src

# Enter scripts directory
cd E:\FinceptTerminal\scripts

# Run forecast
python kronos_forecast.py --input request.json
```

## Input Format

### Single-Asset Forecast

```json
{
  "symbol": "600036",
  "timeframe": "1d",
  "pred_len": 5,
  "dry_run": false,
  "rows": [
    {
      "timestamp": "2026-04-01",
      "open": 1400,
      "high": 1420,
      "low": 1390,
      "close": 1410,
      "volume": 1000000,
      "amount": 1400000000
    },
    ...
  ]
}
```

### Batch Forecast

```json
{
  "assets": [
    {
      "symbol": "600036",
      "rows": [...]
    },
    {
      "symbol": "000858",
      "rows": [...]
    }
  ],
  "pred_len": 5,
  "dry_run": false
}
```

## Output Format

```json
{
  "ok": true,
  "symbol": "600036",
  "timeframe": "1d",
  "model_id": "NeoQuasar/Kronos-base",
  "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
  "pred_len": 5,
  "forecast": [
    {
      "timestamp": "2026-04-15 00:00:00+00:00",
      "open": 1500.0,
      "high": 1510.0,
      "low": 1490.0,
      "close": 1505.0,
      "volume": 0.0,
      "amount": 0.0
    },
    ...
  ],
  "metadata": {
    "device": "cpu",
    "elapsed_ms": 1234,
    "warning": "Research forecast only; not trading advice."
  }
}
```

## Usage in FinceptTerminal

### 1. Via PythonRunner

FinceptTerminal's PythonRunner can call `kronos_forecast.py` directly:

```python
# Inside a FinceptTerminal Python script
import subprocess
import json

# Prepare input data
input_data = {
    "symbol": "600036",
    "timeframe": "1d",
    "pred_len": 5,
    "dry_run": False,
    "rows": [...]  # Historical K-line data
}

# Call Kronos forecast
result = subprocess.run(
    ["python", "kronos_forecast.py"],
    input=json.dumps(input_data),
    capture_output=True,
    text=True,
    cwd="E:\\FinceptTerminal\\scripts"
)

# Parse output
if result.returncode == 0:
    forecast = json.loads(result.stdout)
    print(f"Forecast result: {forecast}")
else:
    print(f"Error: {result.stderr}")
```

### 2. Via Agent

FinceptTerminal's Agent can invoke Kronos through the MCP protocol:

```json
{
  "tool": "forecast_ohlcv",
  "arguments": {
    "symbol": "600036",
    "pred_len": 5,
    "rows": [...]
  }
}
```

## Troubleshooting

### 1. Python Not Found

```
Error: Python not found
```

**Solution**: Ensure Python 3.13.6 is installed and added to PATH.

### 2. PyTorch Not Found

```
Error: PyTorch not found
```

**Solution**: Install PyTorch:
```batch
pip install torch torchvision torchaudio
```

### 3. kronos_fincept Package Not Found

```
Error: kronos_fincept package not found
```

**Solution**: Install the package:
```batch
cd E:\AI_Projects\KronosFinceptLab
pip install -e .
```

### 4. Model Loading Failed

```
Error: Unable to load model
```

**Solution**:
1. Check if model files exist
2. Check the `KRONOS_REPO_PATH` environment variable
3. Check network connectivity (first run requires model download)

### 5. Out of Memory

```
Error: Out of memory
```

**Solution**:
1. Use the `Kronos-mini` model (smaller footprint)
2. Reduce the `pred_len` parameter
3. Increase system memory

## Performance Optimization

### 1. Use GPU (If Available)

```batch
# Check CUDA availability
python -c "import torch; print(torch.cuda.is_available())"
```

If CUDA is available, PyTorch will automatically use the GPU.

### 2. Model Caching

The model is downloaded on first run; subsequent runs use the cached version.

### 3. Batch Processing

Use `batch_forecast_ohlcv` for multi-asset batch processing — significantly more efficient.

## Security Notes

1. **Research only**: All forecasts are for research, backtesting, and paper trading only
2. **Not for live trading**: Do not use predictions for real trading decisions
3. **Use at your own risk**: All risks from using Kronos forecasts are borne by the user

## Changelog

- **v0.5** (2026-04-29): Initial deployment
  - Kronos-base model deployed
  - FinceptTerminal bridge script deployed
  - Windows batch scripts created

## Contact

For issues, please contact the project maintainer.