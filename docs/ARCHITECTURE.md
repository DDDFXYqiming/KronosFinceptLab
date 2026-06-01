# KronosFinceptLab Architecture

This document reflects the current local codebase after the v11 data-source and service-surface alignment work. It focuses on the implemented architecture rather than historical design intent.

## Product Shape

KronosFinceptLab is a local-first quantitative finance cockpit with four entry surfaces:

1. **Web UI** — Next.js app under `web/`, with pages for dashboard, forecast, batch, data, analysis, macro, backtest, alerts, news, watchlist, and settings.
2. **REST API** — FastAPI app in `src/kronos_fincept/api/app.py`, used by the Web UI and external clients.
3. **CLI** — Click-based `kronos` command tree under `src/kronos_fincept/cli/commands/`.
4. **MCP server** — `kronos_mcp/kronos_mcp_server.py`, exposing selected forecast/data/analysis operations to MCP clients.

The backend is Python-first. The frontend is TypeScript/Next.js. Docker builds a combined runtime where the Next.js standalone server is public on port 3000 and talks to the internal FastAPI server on `127.0.0.1:8000`.

## High-Level Flow

```text
Browser / CLI / MCP client
        |
        | HTTP, Click command, or MCP stdio
        v
FastAPI routes / CLI commands / MCP tool handlers
        |
        v
Shared service layer and agent layer
        |
        +-- Kronos model inference and forecast ranking
        +-- Market data adapters and technical indicators
        +-- Backtest, valuation, risk, portfolio, derivative analytics
        +-- Macro data manager and Digital Oracle style providers
        +-- LLM synthesis chain and optional web-search enrichment
        v
Structured JSON, table output, HTML report, or UI state
```

## Backend Layers

### FastAPI Application

`src/kronos_fincept/api/app.py` builds the app and registers all route modules. It also provides:

- API docs gating through `KRONOS_ENABLE_API_DOCS`.
- Request IDs and structured logging.
- Request body size checks.
- API security middleware.
- CORS setup.
- Startup-time Kronos model prewarming when enabled.
- Route registration for health, forecast, batch, data, backtest, analysis, alerts, news, suggestions, jobs, and admin diagnostics.

### Forecast and Analytics Service

`src/kronos_fincept/service.py` is the main shared service layer for forecasting and related operations.

Key responsibilities:

- Single-asset forecast from OHLCV rows.
- Batch forecast and return ranking.
- Probabilistic forecast sampling through `sample_count`.
- Dry-run fallback where allowed.
- Real Kronos model loading/caching.
- Metadata reporting such as elapsed time, backend, cache key, load wait, inference wait, and model cache state.

The API, CLI, and MCP layers call this shared service instead of reimplementing forecast logic.

### Route Modules

Implemented REST surfaces include:

| Area | Routes |
|------|--------|
| Health | `GET /api/health`, `GET /api/health/deep` |
| Forecast | `POST /api/forecast` |
| Batch | `POST /api/batch` |
| Data | `POST /api/data/batch`, `GET /api/data/global/{symbol}`, `GET /api/data/indicator/{symbol}`, `GET /api/data/a-stock/{symbol}`, `GET /api/data/search`, `GET /api/data/money-flow/{symbol}`, `GET /api/data/sector-flow`, `GET /api/data/hsgt-flow`, `GET /api/data/source-market/{artifact}` |
| Backtest | `POST /api/backtest/ranking`, `POST /api/backtest/report` |
| Analysis | `POST /api/v1/analyze/agent`, `/macro`, `/ai`, `/dcf`, `/risk`, `/portfolio`, `/derivative` |
| Alerts | `POST /api/alert/rules`, `GET /api/alert/rules`, `DELETE /api/alert/rules/{rule_id}`, `POST /api/alert/check`, `POST /api/alert/presets/prediction-deviation` |
| News | `POST /api/news/rss` |
| Suggestions | `GET /api/v1/suggestions` |
| Jobs | `GET /api/jobs`, `POST /api/jobs/forecast`, `POST /api/jobs/analyze`, `POST /api/jobs/batch`, `POST /api/jobs/backtest`, `GET /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/cancel` |
| Watchlist | `GET/POST/PUT/DELETE /api/watchlist/lists`, `POST /api/watchlist/research` |
| Admin | `GET /api/admin/security/summary`, model cache clear/prewarm/status routes |

### Async Jobs

`src/kronos_fincept/api/routes/jobs.py` provides an in-process job store for slower forecast and analysis operations.

- Forecast jobs call the shared forecast path.
- Analyze jobs call the shared natural-language agent path.
- Batch and backtest jobs reuse the same request models as synchronous API routes.
- Job state includes status, steps, result, error, timestamps, and progress-related metadata.
- The store is bounded and time-limited, so it is suitable for a single-process local or small deployment, not a distributed queue.

### Security Layer

`src/kronos_fincept/api/security.py` and `src/kronos_fincept/security_utils.py` implement deployment hardening:

- `/api/health` is public; other `/api/*` paths are authenticated unless `KRONOS_AUTH_DISABLED=1`.
- API keys can be sent through `X-Kronos-Api-Key` or `Authorization: Bearer <key>`.
- User keys come from `KRONOS_API_KEYS`.
- Admin/internal keys come from `KRONOS_ADMIN_API_KEYS`, `KRONOS_INTERNAL_API_KEYS`, or `KRONOS_INTERNAL_API_KEY`.
- Alert and admin routes require admin role.
- Rate limits are grouped by endpoint category.
- Large bodies are rejected according to `KRONOS_MAX_BODY_BYTES`.
- API docs are disabled unless `KRONOS_ENABLE_API_DOCS=1`.
- Prompt-injection and secret-exfiltration patterns are filtered in user-supplied context.
- Webhook and RSS URLs are restricted to safe HTTPS targets to reduce SSRF risk.
- Kronos model IDs are validated against the supported model family list.

## Agent and LLM Layer

`src/kronos_fincept/agent.py` is the main natural-language analysis engine. It handles:

- Stateless investment questions.
- Symbol and market inference.
- Tool-style research steps.
- Macro analysis handoff.
- Context construction and source summaries.
- LLM provider selection and fallback.
- Deterministic or template fallback when external LLMs are unavailable.

The shared LLM provider is a single OpenAI-compatible endpoint configured through `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. AnySearch is optional and only participates when `ANYSEARCH_ENABLED=true`. Generic web search is enabled through `WEB_SEARCH_PROVIDER` and `WEB_SEARCH_API_KEY`.

For A-share questions, the agent also pulls local market-review context from the source-project cache when available. This gives the AI report access to locally accumulated market replay artifacts such as funds flow, dragon-tiger lists, limit-up/down records, and sector flow without requiring browser automation or heavyweight collectors at runtime.

## Market Data Layer

`src/kronos_fincept/data_sources/` contains the provider abstraction and concrete sources. `DataSourceManager.fetch(...)` handles endpoint routing, TTL-based local cache, circuit-breaker state, retries, and stale-cache fallback after live providers fail.

Current data-source families:

- **A-share live/public data**: EastMoney, AkShare, BaoStock, TDX local files, and optional Tushare enrichment.
- **Global/crypto data**: Yahoo Finance, Stooq, Binance, and OKX.
- **Market replay cache**: source-project market-review parquet/json artifacts, exposed as `source_market_review`.
- **Optional heavy sources**: TDX network, TickFlow, and NBS live are feature-flagged and skipped when unavailable so Linux/Zeabur startup remains reliable.

The same endpoints are exposed through REST, Web API client, CLI data commands, and MCP data tools where practical.

## Macro Data Layer

The macro subsystem is centered around:

- `src/kronos_fincept/macro/manager.py`
- `src/kronos_fincept/macro/providers/`
- `src/kronos_fincept/macro/providers/digital_oracle.py`

The Digital Oracle inspired provider layer normalizes heterogeneous external data into `MacroSignal` records. It includes provider-specific handling for Treasury/FiscalData, FRED, China macro AkShare, ChinaDataLive, source-project macro cache, NBS cached datasets, optional NBS live data, BIS, SEC/EDGAR, CFTC, Yahoo/Stooq style market data, web search, and AnySearch enrichment. Providers are expected to return empty results when optional dependencies or credentials are missing instead of fabricating values.

## Frontend Architecture

The Web UI lives under `web/` and uses Next.js with a shared API client in `web/src/lib/api.ts`.

Current page set:

| Page | Purpose |
|------|---------|
| `/` | Dashboard and health-oriented overview |
| `/forecast` | Single-symbol Kronos forecast |
| `/batch` | Multi-symbol forecast/ranking |
| `/data` | Market data and indicators |
| `/analysis` | AI stock, agent, and financial analysis workflows |
| `/macro` | Macro signal analysis |
| `/backtest` | Ranking backtest and report generation |
| `/alerts` | Alert rule management and checks |
| `/news` | HTTPS RSS/Atom feed aggregation |
| `/watchlist` | Watchlist workspace with quote summaries, risk tags, CSV import/export, and links into analysis flows |
| `/settings` | API key and runtime settings |

The frontend API client centralizes:

- API base URL resolution.
- API key storage and header injection.
- Request IDs and test-run IDs.
- Timeout handling, including longer timeouts for LLM and macro workflows.
- Error formatting for 401/403/429 and network failures.
- Job, RSS, security summary, alert, analysis, and data methods.

## CLI Architecture

The CLI entry point is `src/kronos_fincept/cli/main.py`. It uses lazy command loading to keep startup light.

Registered top-level commands:

- `forecast`
- `batch`
- `data` (`fetch`, `search`, `indicator`, `money-flow`, `sector-flow`, `hsgt-flow`, `source-market`)
- `backtest`
- `serve`
- `analyze`
- `alert`
- `news` (`rss`)
- `health`
- `suggestions`
- `model`

The `model finetune-csv` command wraps upstream Kronos `finetune_csv` scripts. It is dry-run by default and only executes training when `--execute` is passed.

## MCP Architecture

`kronos_mcp/kronos_mcp_server.py` provides MCP stdio tools over the same project capabilities:

- `forecast_ohlcv`
- `batch_forecast_ohlcv`
- `fetch_a_stock`
- `search_stocks`
- `calculate_indicators`
- `get_money_flow`
- `get_sector_flow`
- `get_hsgt_flow`
- `get_source_market_artifact`
- `run_ranking_backtest`
- `generate_backtest_report`
- `analyze_agent`
- `analyze_macro`
- `generate_suggestions`
- `fetch_rss_news`
- `submit_backtest_job`
- `get_job_status`
- `create_prediction_deviation_alerts`
- `macro_provider_status`
- `watchlist_research`
- `health_check`

This layer is suitable for agent clients that prefer tool calls over raw HTTP.

## Deployment Architecture

### Local Development

Local development usually runs FastAPI on port 8000 and Next.js on port 3000.

- Backend: `kronos serve --host 0.0.0.0 --port 8000` or `uvicorn kronos_fincept.api.app:app --reload --port 8000`.
- Frontend: `cd web && npm run dev`.
- Startup scripts: `start.bat` on Windows and `start.sh` on Linux/WSL.

### Docker / Zeabur

The Docker image is multi-stage:

1. Build the Next.js frontend.
2. Build a Python backend environment with optional CPU Kronos runtime.
3. Run both FastAPI and the Next.js standalone server from `scripts/zeabur_start.sh`.

The public container port is 3000. The API listens internally on `127.0.0.1:8000`, and the frontend calls it through `INTERNAL_API_URL`.

Startup defaults favor low memory: reload is off unless `KRONOS_API_RELOAD=1`, BLAS/tokenizer thread counts are capped when `KRONOS_LOW_MEMORY_DEFAULTS` is enabled, model prewarm is explicit, and MCP/CLI defer heavy imports until a tool or command actually needs them.

## Notes and Known Drift Risks

- `pyproject.toml` and `web/package.json` use package version `2.0.0`, while deployment/build metadata can expose app version values such as `v10.8.9`. Treat these as separate package/build version surfaces unless the release process standardizes them.
- `.env.example` is configuration reference text, not runtime truth. Runtime behavior should be checked against `config.py`, `agent.py`, and `api/security.py`.
- External data providers can fail independently. The architecture is designed to prefer empty signals, fallback providers, or degraded reports over fabricated data.
- Optional providers that require credentials or heavyweight runtimes are deliberately not startup blockers. Missing Tushare/FRED/NBS live/TDX network/TickFlow configuration should be surfaced as a skipped provider or per-request data-source error, not as a process crash.
