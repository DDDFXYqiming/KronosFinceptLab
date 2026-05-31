# KronosFinceptLab CLI Guide

## Installation

```bash
pip install -e ".[api,astock,cli,kronos]"
```

## Global Options

```bash
kronos --output json <command>
kronos --output table <command>
```

- `--output json` is the default machine-readable format.
- `--output table` is available for selected human-readable commands.

## Top-Level Commands

| Command | Purpose |
|---------|---------|
| `forecast` | Single-asset Kronos forecast |
| `batch` | Multi-asset forecast and return ranking |
| `data` | Market data, indicators, and instrument search |
| `backtest` | Ranking backtest and report generation |
| `serve` | Start the FastAPI service |
| `analyze` | AI, macro, valuation, risk, portfolio, indicator, strategy, and derivative analysis |
| `alert` | Alert rule management and monitoring |
| `news` | HTTPS RSS/Atom news fetching |
| `health` | API/model health check |
| `suggestions` | Suggested analysis or macro prompts |
| `model` | Model utility wrappers such as upstream CSV fine-tuning |

## Commands

### Forecast

```bash
kronos forecast --symbol 600036 --pred-len 5 --dry-run
kronos forecast --symbol 600036 --pred-len 5 --sample-count 10
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
kronos data fetch --symbol AAPL --market us --start 20240101 --end 20260430
kronos data indicator --symbol 600036
kronos data search --q "China Merchants Bank"
kronos data money-flow --symbol 600036 --limit 60
kronos data sector-flow --sector-type industry
kronos data hsgt-flow --start 20250101 --end 20260430
kronos data source-market --artifact summary
kronos data source-market --artifact dragon_tiger --date 2026-05-26 --limit 100
```

`money-flow` and `sector-flow` use EastMoney and do not require an API key. `hsgt-flow` requires `TUSHARE_TOKEN`. `source-market` reads the configured source-project market-review cache and exits with a normal JSON error if the cache is unavailable; it does not block CLI startup.

### Backtest

```bash
kronos backtest ranking --symbols 600036,000858 --start 20250101 --end 20260430 --top-k 1
kronos backtest report --symbols 600036,000858 --start 20250101 --end 20260430
kronos --output table backtest ranking --symbols 600036,000858 --dry-run
```

### Analyze

```bash
# Natural-language stateless agent
kronos analyze agent --question "Is China Merchants Bank a good buy right now?" --symbol 600036 --market cn

# Macro signal analysis
kronos analyze macro --question "How do US yields and the dollar affect gold?" --symbols GC=F,DXY

# AI stock analysis and Q&A
kronos analyze ai-analyze --symbol 600036 --market cn
kronos analyze ai-question --question "What are the main risks for 600036?" --symbol 600036
kronos analyze ai-report --symbol 600036

# Market data helpers
kronos analyze global-data --symbol AAPL --market us
kronos analyze market-summary

# Financial analytics
kronos analyze dcf --symbol AAPL --shares 1000000000
kronos analyze risk --symbol AAPL --market-symbol SPY
kronos analyze portfolio --symbols AAPL,MSFT,NVDA
kronos analyze derivative --underlying 100 --strike 105 --expiry 0.5 --volatility 0.2 --rate 0.03

# Technical indicators and strategies
kronos analyze indicator --symbol 600036 --indicator rsi
kronos analyze strategy --symbol 600036 --strategy ma_crossover
```

The shared LLM path currently prioritizes DeepSeek and falls back to OpenRouter when both providers are configured. Web-search enrichment is optional and controlled by `WEB_SEARCH_PROVIDER`, `WEB_SEARCH_API_KEY`, and `ANYSEARCH_ENABLED`.

### Alerts

```bash
kronos alert add --type price_change --symbol 600036 --threshold 3.0
kronos alert list
kronos alert remove <id>
kronos alert check
kronos alert monitor --interval 5
```

Supported alert types include price change, price above/below, RSI overbought/oversold, MACD crossover, prediction deviation, and volume spike.

### Suggestions

```bash
kronos suggestions --type analysis
kronos suggestions --type macro
```

Suggestions use cache/singleflight behavior and deterministic fallback when LLM providers are unavailable.

### News

```bash
kronos news rss --feed "fed|Federal Reserve|https://www.federalreserve.gov/feeds/press_all.xml" --limit 5
kronos news rss --feed https://example.com/feed.xml --json
```

RSS URLs must be HTTPS and pass the same public-network safety validation used by the REST API.

### Serve

```bash
kronos serve --host 0.0.0.0 --port 8000
kronos serve --host 0.0.0.0 --port 8000 --workers 4
```

Interactive API docs require `KRONOS_ENABLE_API_DOCS=1`.

### Health

```bash
kronos health
```

### Model Utilities

```bash
# Dry run: prints the upstream Kronos finetune_csv command
kronos model finetune-csv --config configs/finetune.yaml --stage sequential

# Execute the selected upstream script
kronos model finetune-csv --config configs/finetune.yaml --stage sequential --execute
```

`--stage` supports `tokenizer`, `predictor`, and `sequential`. The command uses `KRONOS_REPO_PATH` or `external/Kronos` to find upstream scripts.

## Hermes Agent Integration

```bash
# Via terminal command in Feishu or another Hermes-connected shell
kronos --output json forecast --symbol 600036 --pred-len 5
kronos --output json analyze agent --question "Summarize risks for 600036" --symbol 600036 --market cn
```
