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

## API Keys

Most `/api/*` endpoints require an API key unless local auth is disabled with `KRONOS_AUTH_DISABLED=1`.

- User keys: `KRONOS_API_KEYS`
- Admin keys: `KRONOS_ADMIN_API_KEYS`, `KRONOS_INTERNAL_API_KEY`, or `KRONOS_INTERNAL_API_KEYS`
- Web UI storage key: `kronos_api_key` in browser `localStorage`
- Request header: `X-Kronos-Api-Key`

For local-only experiments, `KRONOS_AUTH_DISABLED=1` can be used, but do not use it for public deployments.

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
