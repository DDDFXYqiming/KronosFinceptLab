# KronosFinceptLab MCP Server

Kronos MCP (Model Context Protocol) server for financial candlestick prediction, market data, backtesting, AI analysis, macro analysis, suggestions, and health checks.

## Tools

| Tool | Description |
|------|-------------|
| `forecast_ohlcv` | Single-asset OHLCV candlestick prediction |
| `batch_forecast_ohlcv` | Multi-asset batch prediction and return ranking |
| `fetch_a_stock` | Fetch A-share daily candlestick data |
| `search_stocks` | Search A-share stocks/instruments |
| `calculate_indicators` | Calculate technical indicators such as RSI/MACD/SMA/EMA |
| `run_ranking_backtest` | Run multi-symbol ranking backtest |
| `generate_backtest_report` | Generate a backtest report |
| `analyze_agent` | Natural-language stateless investment analysis agent |
| `analyze_macro` | Macro and cross-market signal analysis |
| `generate_suggestions` | Generate suggested analysis or macro prompts |
| `health_check` | Return API/model/runtime health information |

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
      "args": ["kronos_mcp/kronos_mcp_server.py"],
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

For a real-model deployment, ensure the upstream Kronos repo and model cache are available. For local dry-run or degraded operation, configure the same environment variables used by the REST API/CLI.

## FinceptTerminal Agent Integration

FinceptTerminal's Agent/Node Editor can invoke Kronos prediction and analysis capabilities via MCP:

1. Agent receives user request, such as "Analyze China Merchants Bank's trend for the next 5 days".
2. Agent calls `fetch_a_stock` to fetch 600036 historical data.
3. Agent calls `forecast_ohlcv` or `batch_forecast_ohlcv` for prediction.
4. Agent can call `calculate_indicators`, `run_ranking_backtest`, `analyze_agent`, or `analyze_macro` for additional context.
5. Agent generates an analysis report based on the returned structured data.

## Usage Examples

### Single Asset Prediction

```json
{
  "tool": "forecast_ohlcv",
  "arguments": {
    "symbol": "600036",
    "pred_len": 5,
    "rows": [
      {"timestamp": "2026-04-01", "open": 1400, "high": 1420, "low": 1390, "close": 1410}
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
      {"symbol": "600036", "rows": []},
      {"symbol": "000858", "rows": []},
      {"symbol": "601318", "rows": []}
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

### Agent Analysis

```json
{
  "tool": "analyze_agent",
  "arguments": {
    "question": "Is China Merchants Bank a good buy right now?",
    "symbol": "600036",
    "market": "cn"
  }
}
```

### Macro Analysis

```json
{
  "tool": "analyze_macro",
  "arguments": {
    "question": "How do US yields and the dollar affect gold?",
    "symbols": ["GC=F", "DXY"],
    "market": "global"
  }
}
```
