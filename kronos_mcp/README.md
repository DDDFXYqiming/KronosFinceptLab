# KronosFinceptLab MCP Server

Kronos MCP (Model Context Protocol) server for financial candlestick prediction.

## Tools

| Tool | Description |
|------|------------|
| `forecast_ohlcv` | Single asset OHLCV candlestick prediction |
| `batch_forecast_ohlcv` | Multi-asset batch prediction + return ranking |
| `fetch_a_stock` | Fetch A-share real daily candlestick data (AkShare) |

## Installation

```bash
pip install -e ".[mcp,kronos,astock]"
```

## Running

```bash
# Direct execution (stdio transport)
python kronos_mcp/kronos_mcp_server.py

# Or as a module
python -m kronos_mcp.kronos_mcp_server
```

## MCP Client Configuration

### Claude Desktop / Cursor / Other MCP Clients

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "kronos-fincept": {
      "command": "python",
      "args": ["mcp/kronos_mcp_server.py"],
      "cwd": "/path/to/KronosFinceptLab",
      "env": {
        "PYTHONPATH": "src",
        "KRONOS_REPO_PATH": "/path/to/Kronos",
        "HF_HOME": "/path/to/model/cache"
      }
    }
  }
}
```

### FinceptTerminal Agent Integration

FinceptTerminal's Agent/Node Editor can invoke Kronos prediction capabilities via the MCP protocol:

1. Agent receives user request: "Analyze China Merchants Bank's trend for the next 5 days"
2. Agent calls `fetch_a_stock` to fetch 600036 historical data
3. Agent calls `forecast_ohlcv` to fetch predictions
4. Agent generates an analysis report based on the predictions

## Usage Examples

### Single Asset Prediction

```json
{
  "tool": "forecast_ohlcv",
  "arguments": {
    "symbol": "600036",
    "pred_len": 5,
    "rows": [
      {"timestamp": "2026-04-01", "open": 1400, "high": 1420, "low": 1390, "close": 1410},
      ...
    ]
  }
}
```

### Batch Ranking

```json
{
  "tool": "batch_forecast_ohlcv",
  "arguments": {
    "pred_len": 5,
    "assets": [
      {"symbol": "600036", "rows": [...]},
      {"symbol": "000858", "rows": [...]},
      {"symbol": "601318", "rows": [...]}
    ]
  }
}
```

### Fetch A-share Data

```json
{
  "tool": "fetch_a_stock",
  "arguments": {
    "symbol": "600036",
    "start_date": "20250101",
    "end_date": "20260429"
  }
}
```
