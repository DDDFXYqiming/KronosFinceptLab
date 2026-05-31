# KronosFinceptLab MCP Server

Kronos MCP (Model Context Protocol) server for financial candlestick prediction, market data, money-flow data, source-project cache artifacts, backtesting, AI analysis, macro analysis, jobs, alerts, watchlist research, suggestions, and health checks.

## Tools

| Tool | Description |
|------|-------------|
| `forecast_ohlcv` | Single-asset OHLCV candlestick prediction |
| `batch_forecast_ohlcv` | Multi-asset batch prediction and return ranking |
| `fetch_a_stock` | Fetch A-share daily candlestick data |
| `search_stocks` | Search A-share stocks/instruments |
| `calculate_indicators` | Calculate technical indicators such as RSI/MACD/SMA/EMA |
| `get_money_flow` | Fetch EastMoney main-money-flow rows for an A-share/ETF |
| `get_sector_flow` | Fetch EastMoney sector/concept/region money-flow rankings |
| `get_hsgt_flow` | Fetch Stock Connect flow via Tushare when configured |
| `get_source_market_artifact` | Read source-project market-review cache summary or artifact |
| `run_ranking_backtest` | Run multi-symbol ranking backtest |
| `generate_backtest_report` | Generate a backtest report |
| `analyze_agent` | Natural-language stateless investment analysis agent |
| `analyze_macro` | Macro and cross-market signal analysis |
| `generate_suggestions` | Generate suggested analysis or macro prompts |
| `fetch_rss_news` | Fetch HTTPS RSS/Atom news feeds |
| `submit_backtest_job` | Submit an async backtest job |
| `get_job_status` | Read an in-process async job result |
| `create_prediction_deviation_alerts` | Create prediction-deviation alert rules |
| `macro_provider_status` | Return macro provider status |
| `watchlist_research` | Build weighted watchlist research summary |
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

The server applies low-memory defaults and defers heavy imports until a tool is called. Optional providers such as Tushare, TDX network, TickFlow, source-project caches, and NBS live are skipped or reported as per-tool errors when not configured; they are not startup blockers.

## FinceptTerminal Agent Integration

FinceptTerminal's Agent/Node Editor can invoke Kronos prediction and analysis capabilities via MCP:

1. Agent receives user request, such as "Analyze China Merchants Bank's trend for the next 5 days".
2. Agent calls `fetch_a_stock` to fetch 600036 historical data.
3. Agent calls `forecast_ohlcv` or `batch_forecast_ohlcv` for prediction.
4. Agent can call `calculate_indicators`, `run_ranking_backtest`, `analyze_agent`, or `analyze_macro` for additional context.
5. Agent can enrich A-share context with `get_money_flow`, `get_sector_flow`, and `get_source_market_artifact`.
6. Agent generates an analysis report based on the returned structured data.

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

### Money Flow and Source Cache

```json
{
  "tool": "get_money_flow",
  "arguments": {
    "symbol": "600036",
    "limit": 60
  }
}
```

```json
{
  "tool": "get_source_market_artifact",
  "arguments": {
    "artifact": "summary"
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

### RSS News

```json
{
  "tool": "fetch_rss_news",
  "arguments": {
    "feeds": [
      {
        "id": "fed",
        "title": "Federal Reserve",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml"
      }
    ],
    "limit_per_feed": 5
  }
}
```
