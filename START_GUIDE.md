# KronosFinceptLab Startup Guide

## Windows (Double-click)

Simply double-click `start.bat` to launch both services:

1. **API Backend** — Runs at http://localhost:8000 in a separate window
2. **Web Frontend** — Runs at http://localhost:3000 in a separate window

A browser will open automatically once started.

## WSL/Linux

```bash
./start.sh
```

Press `Ctrl+C` to stop all services.

## Manual Startup

### Start API Backend

```bash
# Windows
set PYTHONPATH=src
python -m kronos_fincept.api.app

# WSL/Linux
PYTHONPATH=src python3 -m kronos_fincept.api.app
```

You can also start the backend through the CLI:

```bash
kronos serve --host 0.0.0.0 --port 8000
```

Interactive API docs are off by default. Enable them only when needed:

```bash
set KRONOS_ENABLE_API_DOCS=1        # Windows cmd
# export KRONOS_ENABLE_API_DOCS=1   # WSL/Linux
kronos serve --host 0.0.0.0 --port 8000
```

### Start Web Frontend

```bash
cd web
npm install  # first time only
npm run dev
```

## Access URLs

| Service | URL | Notes |
|---------|-----|-------|
| Web Frontend | http://localhost:3000 | Dashboard, forecast, batch, data, analysis, macro, backtest, alerts, news, watchlist, settings |
| API Backend | http://localhost:8000 | REST API used by Web/CLI/external clients |
| API Docs | http://localhost:8000/docs | Requires `KRONOS_ENABLE_API_DOCS=1` |
| Health | http://localhost:8000/api/health | Public health endpoint |

## Quick Capability Checks

```bash
kronos health
kronos data fetch --symbol 600036 --start 20250101 --end 20260430
kronos data money-flow --symbol 600036 --limit 10
kronos data sector-flow --sector-type industry
kronos data source-market --artifact summary
kronos analyze macro --question "How do US yields affect gold?" --symbols GC=F,DXY
kronos news rss --feed "fed|Federal Reserve|https://www.federalreserve.gov/feeds/press_all.xml" --limit 5
```

`source-market` depends on `KRONOS_SOURCE_PROJECT_ROOT`. `hsgt-flow` depends on `TUSHARE_TOKEN`. If those are not configured, the command/API returns a normal error instead of blocking startup.

## API Keys

Most `/api/*` endpoints require an API key unless local auth is disabled with `KRONOS_AUTH_DISABLED=1`.

- User keys: `KRONOS_API_KEYS`
- Admin keys: `KRONOS_ADMIN_API_KEYS`, `KRONOS_INTERNAL_API_KEY`, or `KRONOS_INTERNAL_API_KEYS`
- Web UI storage key: `kronos_api_key` in browser `localStorage`
- Request header: `X-Kronos-Api-Key`

For local-only experiments, `KRONOS_AUTH_DISABLED=1` can be used, but do not use it for public deployments.

## Low-Memory Startup

Local and Zeabur deployments default to conservative startup behavior: API reload is off unless `KRONOS_API_RELOAD=1`, heavy imports are deferred, and optional sources such as TDX network, TickFlow, and NBS live are skipped unless explicitly enabled. For small containers, use `KRONOS_MODEL_ID=NeoQuasar/Kronos-mini` and keep `KRONOS_PREWARM_ON_STARTUP=0` until the instance has enough memory.

## Stopping Services

### Windows

- Close the "KronosFinceptLab API" and "KronosFinceptLab Web" command windows.

### WSL/Linux

- Press `Ctrl+C` in the terminal running `start.sh`.

## Troubleshooting

### Port Already in Use

If ports 8000 or 3000 are occupied:

- Close the program using the port.
- Or modify the port numbers in the startup script.

### Python Not Found

Ensure Python 3.11+ is installed and added to PATH.

### Node.js Not Found

Ensure Node.js 18+ is installed and added to PATH.

### API Docs Return 404

This is expected unless `KRONOS_ENABLE_API_DOCS=1` is set before starting the backend.

### API Requests Return 401 or 403

Set a valid API key in the Web settings page, browser `localStorage`, or request headers. Alert and admin routes require an admin/internal key.

### npm install Fails

Try clearing the cache and reinstalling:

```bash
cd web
rm -rf node_modules package-lock.json
npm install
```
