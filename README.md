# KronosFinceptLab

Version: v10.9 + v11 data-source alignment - research-only quantitative finance cockpit.

> Your local-first quantitative finance cockpit.

An integrated quantitative finance analytics platform combining **market data, AI-powered forecasting, technical analysis, macroeconomic signals, AI investment research, news monitoring, alerts, and MCP integration** — all running locally on your machine with automatic data source fallback. Accessible via CLI, API, Web UI, and MCP.

---

## Core Capabilities

| Capability | Description |
|------------|-------------|
| Market Data | OHLCV, search, A-share money flow, sector flow, Stock Connect flow, market-review cache artifacts, HK/US/crypto/commodity data, and auto-fallback providers |
| AI K-line Forecasting | Future K-line prediction powered by the Kronos foundation model, supporting single-asset, batch, probabilistic sampling, and async jobs |
| Technical Analysis | SMA, EMA, RSI, MACD, Bollinger, KDJ, ATR, OBV and other common indicators |
| AI Investment Advisor | Natural-language stock Q&A, investment analysis reports, risk assessment, DCF, portfolio optimization, derivatives pricing, and conversational context |
| Macroeconomic Signals | Digital Oracle style aggregation of 17+ signal types plus China macro, source-project macro cache, optional FRED, NBS live, ChinaDataLive, and web-enriched research |
| Strategy Backtest | Multi-symbol ranking backtest with HTML report generation |
| Watchlist & News | Watchlist research workspace, CSV import/export, quote summaries, risk tags, and HTTPS RSS/Atom news aggregation |
| Smart Alerts | Rule-based monitoring for price changes, indicator triggers, prediction deviation, volume spikes, webhook/email delivery, and continuous monitoring |
| Security & Deployment | API key roles, rate limits, request-size budgets, API docs gating, SSRF-safe URL handling, and combined Web/API Docker runtime |
| MCP Integration | MCP server exposing forecast, data, money-flow, source-cache, indicator, backtest, agent, macro, jobs, alerts, watchlist, suggestions, and health tools |

## Capabilities Matrix

| Capability | Web | API | CLI | MCP |
|------------|-----|-----|-----|-----|
| Dashboard | Dashboard page | `GET /api/health` | `kronos health` | `health_check` |
| Forecasting | Forecast page | `POST /api/forecast` | `kronos forecast` | `forecast_ohlcv` |
| Async forecast/analyze/backtest jobs | Forecast/analysis clients | `POST /api/jobs/forecast`, `/analyze`, `/batch`, `/backtest`, `GET /api/jobs/{job_id}` | API-backed | `submit_backtest_job`, `get_job_status` |
| Batch ranking | Batch page | `POST /api/batch` | `kronos batch` | `batch_forecast_ohlcv` |
| Market data | Data page, Watchlist page | `GET /api/data/*` | `kronos data fetch/search/indicator/money-flow/sector-flow/hsgt-flow/source-market` | `fetch_a_stock`, `search_stocks`, `calculate_indicators`, `get_money_flow`, `get_sector_flow`, `get_hsgt_flow`, `get_source_market_artifact` |
| Backtest | Backtest page | `POST /api/backtest/ranking`, `POST /api/backtest/report` | `kronos backtest ranking/report` | `run_ranking_backtest`, `generate_backtest_report` |
| Natural-language agent analysis | Analysis page | `POST /api/v1/analyze/agent` | `kronos analyze agent` | `analyze_agent` |
| Macro signals | Macro page | `POST /api/v1/analyze/macro` | `kronos analyze macro` | `analyze_macro` |
| AI stock report | Analysis page | `POST /api/v1/analyze/ai` | `kronos analyze ai-analyze` | Via agent tools |
| Valuation, risk, portfolio, derivatives | Analysis page | `POST /api/v1/analyze/dcf`, `/risk`, `/portfolio`, `/derivative` | `kronos analyze dcf/risk/portfolio/derivative` | API/CLI only |
| Suggestions | Analysis/Macro pages | `GET /api/v1/suggestions` | `kronos suggestions` | `generate_suggestions` |
| Alerts | Alerts page | `POST/GET/DELETE /api/alert/*` | `kronos alert add/list/remove/check/monitor` | `create_prediction_deviation_alerts` plus API-backed checks |
| News/RSS | News page | `POST /api/news/rss` | `kronos news rss` | `fetch_rss_news` |
| Watchlist | Watchlist page | `GET/POST/PUT/DELETE /api/watchlist/lists`, `POST /api/watchlist/research` | API-backed | `watchlist_research` |
| Model utilities | CLI-only | N/A | `kronos model finetune-csv` | N/A |
| Admin security summary | Settings/admin clients | `GET /api/admin/security/summary` | API-only | API-only |

## What Makes It Unique

- **Local-first** — Core capabilities can run locally with no cloud lock-in; external data/LLM/search providers are optional and degrade gracefully.
- **Unified multi-entry** — CLI (`kronos`), REST API (`kronos serve`), Web UI, and MCP server share the same analysis and forecasting engines.
- **Data source circuit breaking** — EastMoney, Tushare, TDX local, AkShare, BaoStock, Yahoo/Stooq, Binance/OKX, source-project caches, Treasury, BIS, SEC/EDGAR, CFTC, and web-search enrichment are used with fallback, caching, timeout handling, and stale-cache fallback.
- **AI-native** — Built-in Kronos K-line model inference plus LLM synthesis. The current shared LLM chain prioritizes DeepSeek and falls back to OpenRouter when configured.
- **Observable and deployable** — JSON Lines structured logging with `request_id`, build fingerprints, API key roles, rate limits, request budgets, and Docker-friendly startup.

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

# Fetch market data and indicators
kronos data fetch --symbol 600036 --start 20240101 --end 20260429
kronos data indicator --symbol 600036
kronos data money-flow --symbol 600036 --limit 60
kronos data sector-flow --sector-type industry
kronos data source-market --artifact summary

# Strategy backtest
kronos backtest ranking --symbols 600036,000858 --start 20240101 --end 20260429

# AI analysis (A-shares)
kronos analyze ai-analyze --symbol 600036 --market cn

# Natural-language agent and macro analysis
kronos analyze agent --question "Is China Merchants Bank a good buy right now?"
kronos analyze macro --question "How do US yields and the dollar affect gold?" --symbols GC=F,DXY

# Suggested analysis prompts
kronos suggestions --type analysis

# Fetch RSS/Atom news
kronos news rss --feed "fed|Federal Reserve|https://www.federalreserve.gov/feeds/press_all.xml" --limit 5

# Add alert rule and start continuous monitoring
kronos alert add --type price_change --symbol 600036 --threshold 3.0
kronos alert monitor --interval 5

# Wrap upstream Kronos finetune_csv scripts (dry run by default)
kronos model finetune-csv --config configs/finetune.yaml --stage sequential
```

### API Service

```bash
kronos serve --host 0.0.0.0 --port 8000
# Swagger docs: http://localhost:8000/docs (requires KRONOS_ENABLE_API_DOCS=1)
```

Most `/api/*` endpoints require an API key unless `KRONOS_AUTH_DISABLED=1` is set for local development. Send the key as `X-Kronos-Api-Key` or `Authorization: Bearer <key>`.

### Web Frontend

```bash
cd web
npm install
npm run dev
# Open http://localhost:3000
```

The Web UI contains dashboard, forecast, batch, data, analysis, macro, backtest, alerts, news, watchlist, and settings pages. API keys are read from `localStorage` (`kronos_api_key`) or `NEXT_PUBLIC_KRONOS_API_KEY`.

---

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/ARCHITECTURE.md` | Current architecture, module boundaries, data/LLM flows, and security/deployment notes |
| `docs/API.md` | REST endpoint inventory, auth, error format, and feature flags |
| `docs/CLI.md` | CLI command tree and examples |
| `docs/DEPLOYMENT.md` | Local and Docker deployment notes |
| `START_GUIDE.md` | Quick startup instructions |
| `kronos_mcp/README.md` | MCP server tools and client configuration |

---

## CLI Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Asset symbol |
| `timeframe` | string | `"1d"` | K-line timeframe |
| `pred_len` | int | required | Number of predicted K-lines |
| `dry_run` | bool | false | Use dry-run predictor when allowed |
| `model_id` | string | `NeoQuasar/Kronos-base` | Model ID; supported families include mini, small, and base |
| `temperature` | float | 1.0 | Sampling temperature |
| `sample_count` | int | 1 | Number of parallel forecast samples |

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
| `KRONOS_MODEL_ID` | Kronos model ID, default `NeoQuasar/Kronos-base` |
| `KRONOS_REPO_PATH` | Upstream Kronos repo path |
| `HF_HOME` / `HF_HUB_CACHE` | HuggingFace cache/model weights directory |
| `KRONOS_ENABLE_REAL_MODEL` | Enable real Kronos inference backend |
| `KRONOS_PREWARM_ON_STARTUP` | Preload model during API startup |
| `KRONOS_API_KEYS` | User API authentication keys |
| `KRONOS_ADMIN_API_KEYS` / `KRONOS_INTERNAL_API_KEY` | Admin/internal API keys for alert/admin operations |
| `KRONOS_AUTH_DISABLED` | Disable API auth for local development only |
| `KRONOS_ENABLE_API_DOCS` | Enable `/docs`, `/redoc`, and `/openapi.json` |
| `KRONOS_RATE_LIMIT_*` | Per-category rate limiting |
| `DEEPSEEK_API_KEY` | Primary LLM provider key for the shared analysis chain |
| `OPENROUTER_API_KEY` | Optional fallback LLM provider key |
| `TUSHARE_TOKEN` | Optional Tushare Pro token for A-share and Stock Connect fallback data |
| `FRED_API_KEY` | Optional FRED API key for U.S. macro indicators |
| `KRONOS_SOURCE_PROJECT_ROOT` | Optional path to the verified source project for market/macro cache reuse |
| `KRONOS_ENABLE_TDX_NETWORK` | Optional TDX network source; off by default for container/Linux safety |
| `KRONOS_ENABLE_TICKFLOW` | Optional TickFlow source; skipped when dependency is unavailable |
| `KRONOS_ENABLE_NBS_LIVE` | Optional NBS live client; off by default and cache/public sources are preferred |
| `KRONOS_LOW_MEMORY_DEFAULTS` | Enables conservative thread/import defaults for local and container startup |
| `WEB_SEARCH_PROVIDER` / `WEB_SEARCH_API_KEY` | Generic web search configuration |
| `ANYSEARCH_ENABLED` | Optional anonymous AnySearch enrichment toggle |
| `PORT` / `API_PORT` | Web/API ports |

---

## Requirements

| Component | Requirement |
|-----------|-------------|
| Python | >= 3.11 |
| Node.js | >= 18 for local frontend; Docker build uses Node 22 |

**Upstream projects**: [Kronos](https://github.com/shiyu-coder/Kronos) · [FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) · [Digital Oracle](https://github.com/komako-workshop/digital-oracle)

> All forecasts and analysis are for research purposes only and do not constitute investment advice.
