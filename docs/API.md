# KronosFinceptLab API Documentation

Base URL: `http://localhost:8000`

Most `/api/*` endpoints require an API key unless `KRONOS_AUTH_DISABLED=1` is set for local development. Send credentials with either:

```http
X-Kronos-Api-Key: <key>
Authorization: Bearer <key>
```

Admin-only surfaces such as alerts and admin diagnostics require an admin/internal key from `KRONOS_ADMIN_API_KEYS`, `KRONOS_INTERNAL_API_KEYS`, or `KRONOS_INTERNAL_API_KEY`.

## Endpoint Inventory

| Area | Method | Path | Notes |
|------|--------|------|-------|
| Health | GET | `/api/health` | Public liveness and model/build metadata |
| Health | GET | `/api/health/deep` | Deeper dependency health information |
| Forecast | POST | `/api/forecast` | Single-asset Kronos forecast |
| Batch | POST | `/api/batch` | Multi-asset forecast and ranking |
| Data | POST | `/api/data/batch` | Multi-symbol OHLCV fetch with per-symbol errors |
| Data | GET | `/api/data/global/{symbol}` | Global market OHLCV data |
| Data | GET | `/api/data/indicator/{symbol}` | Technical indicators |
| Data | GET | `/api/data/a-stock/{symbol}` | A-share OHLCV data |
| Data | GET | `/api/data/search` | Stock/instrument search |
| Data | GET | `/api/data/money-flow/{symbol}` | EastMoney main-money-flow rows |
| Data | GET | `/api/data/sector-flow` | EastMoney sector/concept money-flow rankings |
| Data | GET | `/api/data/hsgt-flow` | Stock Connect flow via Tushare when configured |
| Data | GET | `/api/data/source-market/{artifact}` | Source-project market-review cache artifact or summary |
| Backtest | POST | `/api/backtest/ranking` | Multi-symbol ranking backtest |
| Backtest | POST | `/api/backtest/report` | HTML/text report generation |
| Analysis | POST | `/api/v1/analyze/agent` | Natural-language stateless analysis agent |
| Analysis | POST | `/api/v1/analyze/macro` | Macro and cross-market signal analysis |
| Analysis | POST | `/api/v1/analyze/ai` | AI stock analysis report |
| Analysis | POST | `/api/v1/analyze/dcf` | DCF valuation |
| Analysis | POST | `/api/v1/analyze/risk` | Risk metrics |
| Analysis | POST | `/api/v1/analyze/portfolio` | Portfolio optimization |
| Analysis | POST | `/api/v1/analyze/derivative` | Option pricing |
| Alerts | POST | `/api/alert/rules` | Create alert rule; admin key required |
| Alerts | GET | `/api/alert/rules` | List alert rules; admin key required |
| Alerts | DELETE | `/api/alert/rules/{rule_id}` | Remove alert rule; admin key required |
| Alerts | POST | `/api/alert/check` | Run alert checks; admin key required |
| Alerts | POST | `/api/alert/presets/prediction-deviation` | Create prediction-deviation rules for a watchlist; admin key required |
| News | POST | `/api/news/rss` | Fetch HTTPS RSS/Atom feeds with SSRF-safe URL checks |
| Suggestions | GET | `/api/v1/suggestions` | Suggested analysis or macro prompts |
| Watchlist | GET | `/api/watchlist/lists` | List persisted watchlists |
| Watchlist | POST | `/api/watchlist/lists` | Create watchlist |
| Watchlist | PUT | `/api/watchlist/lists/{watchlist_id}` | Update watchlist |
| Watchlist | DELETE | `/api/watchlist/lists/{watchlist_id}` | Delete watchlist |
| Watchlist | POST | `/api/watchlist/research` | Build weighted watchlist research summary |
| Jobs | POST | `/api/jobs/forecast` | Submit async forecast job |
| Jobs | POST | `/api/jobs/analyze` | Submit async agent-analysis job |
| Jobs | POST | `/api/jobs/batch` | Submit async batch forecast job |
| Jobs | POST | `/api/jobs/backtest` | Submit async ranking backtest job |
| Jobs | GET | `/api/jobs` | List bounded in-process job history |
| Jobs | GET | `/api/jobs/{job_id}` | Read async job state/result |
| Jobs | POST | `/api/jobs/{job_id}/cancel` | Cancel queued/running job when possible |
| Admin | GET | `/api/admin/security/summary` | Security configuration summary; admin key required |
| Admin | GET | `/api/admin/model/cache` | Model cache state; admin key required |
| Admin | POST | `/api/admin/model/clear-cache` | Clear model cache; admin key required |
| Admin | POST | `/api/admin/model/prewarm` | Preload model; admin key required |

## Health Check

```http
GET /api/health
```

Returns model/build/runtime metadata such as status, version, supported model IDs, model load state, device, uptime, and request tracing fields.

## Forecast

```http
POST /api/forecast
Content-Type: application/json

{
  "symbol": "600036",
  "timeframe": "1d",
  "pred_len": 5,
  "rows": [
    { "timestamp": "2026-01-02T00:00:00Z", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000000 }
  ],
  "dry_run": false,
  "model_id": "NeoQuasar/Kronos-base",
  "sample_count": 1
}
```

Supported model families include `NeoQuasar/Kronos-mini`, `NeoQuasar/Kronos-small`, and `NeoQuasar/Kronos-base`. Forecast responses include predicted rows and metadata such as backend, elapsed time, cache key, and model cache state. When `sample_count > 1`, probability-oriented fields such as upside probability and forecast range can be returned.

## Batch Forecast

```http
POST /api/batch
Content-Type: application/json

{
  "assets": [
    { "symbol": "600036", "rows": [] },
    { "symbol": "000858", "rows": [] }
  ],
  "pred_len": 5,
  "dry_run": false
}
```

The batch path ranks assets by predicted return and uses shared model loading/caching where possible.

## Data

```http
GET /api/data/a-stock/600036?start_date=20250101&end_date=20260430&adjust=qfq
GET /api/data/global/AAPL?market=us&start_date=20250101&end_date=20260430
GET /api/data/indicator/600036?market=cn
GET /api/data/indicator/600036?market=cn&start_date=20250101&end_date=20260430
GET /api/data/search?q=China+Merchants+Bank
GET /api/data/money-flow/600036?limit=60
GET /api/data/sector-flow?sector_type=industry
GET /api/data/hsgt-flow?start_date=20250101&end_date=20260430
GET /api/data/source-market/summary
GET /api/data/source-market/dragon_tiger?date=2026-05-26&limit=100
```

`/api/data/money-flow` and `/api/data/sector-flow` use the no-key EastMoney Push2 source. `/api/data/hsgt-flow` requires `TUSHARE_TOKEN`. `/api/data/source-market/{artifact}` reads verified local cache artifacts from `KRONOS_SOURCE_PROJECT_ROOT` when configured and returns 404 rather than breaking startup when the cache is unavailable.

Data endpoints route through `DataSourceManager` where possible. Supported providers include EastMoney, Tushare, TDX local, AkShare, BaoStock, Yahoo/Stooq, Binance/OKX, and source-project caches. Optional heavy providers such as TDX network, TickFlow, and NBS live are disabled unless their feature flags and dependencies are present.

## Backtest

```http
POST /api/backtest/ranking
Content-Type: application/json

{
  "symbols": ["600036", "000858"],
  "start_date": "20250101",
  "end_date": "20260430",
  "top_k": 1,
  "pred_len": 5,
  "dry_run": true
}
```

Use `/api/backtest/report` to generate report output for a completed ranking backtest request.

## AI and Macro Analysis

```http
POST /api/v1/analyze/agent
Content-Type: application/json

{
  "question": "Is China Merchants Bank a good buy right now?",
  "symbol": "600036",
  "market": "cn",
  "dry_run": false
}
```

```http
POST /api/v1/analyze/macro
Content-Type: application/json

{
  "question": "How do US yields and the dollar affect gold?",
  "symbols": ["GC=F", "DXY"],
  "market": "global"
}
```

The shared LLM synthesis path uses one OpenAI-compatible provider configured with `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. Macro providers include no-key public sources plus optional FRED (`FRED_API_KEY`) and Tushare (`TUSHARE_TOKEN`) enrichment. Generic web search requires `WEB_SEARCH_PROVIDER` and `WEB_SEARCH_API_KEY`; AnySearch requires `ANYSEARCH_ENABLED=true`.

## Async Jobs

```http
POST /api/jobs/forecast
POST /api/jobs/analyze
POST /api/jobs/batch
POST /api/jobs/backtest
GET /api/jobs
GET /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
```

Jobs are stored in process with bounded size and TTL. They are intended for local/single-process usage and frontend long-running operations, not as a distributed queue.

## News/RSS

```http
POST /api/news/rss
Content-Type: application/json

{
  "feeds": [
    { "id": "fed", "title": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml" }
  ],
  "limit_per_feed": 8
}
```

RSS URLs must use HTTPS and pass private-network/localhost/metadata-host checks.

## Suggestions

```http
GET /api/v1/suggestions?type=analysis
GET /api/v1/suggestions?type=macro
```

Suggestions use caching, singleflight behavior, and deterministic fallback when LLM providers are unavailable.

## Error Format

Common error responses use a JSON shape similar to:

```json
{ "ok": false, "error": "Error message", "error_type": "optional_machine_code" }
```

401, 403, and 429 responses indicate missing/invalid credentials, insufficient admin role, or rate limiting.

## Interactive Docs

Interactive API docs are disabled by default.

```bash
KRONOS_ENABLE_API_DOCS=1 kronos serve --host 0.0.0.0 --port 8000
```

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json
