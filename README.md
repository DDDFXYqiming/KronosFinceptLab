# KronosFinceptLab

Version: v10.8 — research-only quantitative finance cockpit.

> Your local-first quantitative finance cockpit.

An integrated quantitative finance analytics platform combining **market data, AI-powered forecasting, technical analysis, macroeconomic signals, and an AI investment advisor** — all running locally on your machine with automatic data source fallback. Accessible via CLI, API, Web UI, and MCP.

---

## Core Capabilities

| Capability | Description |
|------------|-------------|
| Market Data | OHLCV data for A-shares, HK stocks, US stocks, crypto, commodities and more across multiple exchanges with auto-fallback |
| AI K-line Forecasting | Future K-line prediction powered by the Kronos foundation model, supporting single-asset, batch, and probabilistic sampling |
| Technical Analysis | SMA, EMA, RSI, MACD, Bollinger, KDJ, ATR, OBV and other common indicators |
| AI Investment Advisor | Natural-language stock Q&A, investment analysis reports, risk assessment with conversational context |
| Macroeconomic Signals | Aggregation of 17+ signal types including interest rates, CFTC COT, on-chain data, SEC/EDGAR, BIS, WorldBank, fear & greed index, and more |
| Strategy Backtest | Multi-symbol ranking backtest with HTML report generation |
| Valuation & Portfolio | DCF valuation, risk analysis, portfolio optimization, derivatives pricing |
| Smart Alerts | Rule-based monitoring for price changes, indicator triggers, with webhook/email delivery |

## Capabilities Matrix

| Capability | Web | API | CLI |
|------------|-----|-----|-----|
| Natural-language agent analysis | Analysis page | `POST /api/v1/analyze/agent` | `kronos analyze agent` |
| Forecasting | Forecast page | `POST /api/forecast` | `kronos forecast` |
| Macro signals | Macro page | `POST /api/v1/analyze/macro` | `kronos analyze macro` |
| Batch ranking | Batch page | `POST /api/batch` | `kronos batch` |

The macro layer is orchestrated by `MacroDataManager`, with optional Digital Oracle integration: https://github.com/komako-workshop/digital-oracle.
LLM synthesis uses OpenRouter first, then DeepSeek-compatible `https://api.deepseek.com/chat/completions` fallback when configured.

## What Makes It Unique

- **Local-first** — All core capabilities run offline with no cloud dependency lock-in
- **Unified multi-entry** — CLI (`kronos`), REST API (`kronos serve`), Web UI, and MCP server all share the same analysis engine
- **Data source circuit breaking** — BaoStock -> AkShare -> Yahoo Finance -> Binance/OKX, automatic fallback when one fails
- **AI-native** — Built-in Kronos K-line model inference + LLM natural language analysis, no external orchestration needed
- **Observable** — JSON Lines structured logging with `request_id` for full request tracing, production-ready

---

## Quick Start

### Installation

```bash
cd KronosFinceptLab

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac

# Install with optional extras
pip install -e .[api,cli,astock,kronos]
```

### CLI Usage

```bash
# Single-asset forecast
kronos forecast --symbol 600036 --pred-len 5

# Probabilistic forecast (Monte Carlo sampling)
kronos forecast --symbol 600036 --pred-len 5 --sample-count 10

# Batch forecast
kronos batch --symbols 600036,000858,000001 --pred-len 5

# Fetch market data
kronos data fetch --symbol 600036 --start 20240101 --end 20260429

# Strategy backtest
kronos backtest ranking --symbols 600036,000858 --start 20240101 --end 20260429

# AI analysis (A-shares)
kronos analyze ai-analyze --symbol 600036 --market cn

# Natural-language agent analysis
kronos analyze agent --question "Is China Merchants Bank a good buy right now?"

# Add alert rule
kronos alert add --type price_change --symbol 600036 --threshold 3.0

# Start continuous monitoring
kronos alert monitor --interval 5
```

### API Service

```bash
kronos serve --host 0.0.0.0 --port 8000
# Swagger docs: http://localhost:8000/docs (requires KRONOS_ENABLE_API_DOCS=1)
```

### Web Frontend

```bash
cd web
npm install
npm run dev
# Open http://localhost:3000
```

---

## CLI Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Asset symbol |
| `timeframe` | string | `"1d"` | K-line timeframe |
| `pred_len` | int | required | Number of predicted K-lines |
| `dry_run` | bool | false | Use dry-run predictor |
| `model_id` | string | `NeoQuasar/Kronos-base` | Model ID |
| `temperature` | float | 1.0 | Sampling temperature |
| `sample_count` | int | 1 | Number of parallel samples |

---

## Quality Gates

```bash
# Backend tests
python -m pytest tests -q

# Frontend quality gates
cd web && npm run typecheck
cd web && npm run lint
cd web && npm run test:frontend
cd web && npm run build
cd web && npm run check:bundle
cd web && npm run smoke:pages
```

---

## Configuration

Key environment variables (see `.env.example` for full reference):

| Variable | Purpose |
|----------|---------|
| `KRONOS_MODEL_ID` | Kronos model ID |
| `KRONOS_REPO_PATH` | Kronos repo path |
| `HF_HUB_CACHE` | HuggingFace cache directory |
| `KRONOS_API_KEYS` | API authentication keys |
| `KRONOS_AUTH_DISABLED` | Disable API auth (default: enabled) |
| `KRONOS_RATE_LIMIT_*` | Per-category rate limiting |
| `WEB_SEARCH_PROVIDER` / `WEB_SEARCH_API_KEY` | Web search configuration |
| `PORT` / `API_PORT` | Web/API ports |

---

## Rust Native Acceleration (Optional)

```bash
cargo test --workspace
python -m maturin build --manifest-path crates/kronos-python/Cargo.toml --release --out dist/native

# Enable
$env:USE_RUST_ENGINE="1"
python -m pytest tests/test_rust_native_bridge.py -v
```

---

## Requirements

| Component | Requirement |
|-----------|-------------|
| Python | >= 3.11 |
| Node.js | >= 18 (frontend) |
| Rust | Optional (native acceleration) |

**Upstream projects**: [Kronos](https://github.com/shiyu-coder/Kronos) · [FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) · [Digital Oracle](https://github.com/komako-workshop/digital-oracle)

> All forecasts and analysis are for research purposes only and do not constitute investment advice.