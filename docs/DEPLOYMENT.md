# KronosFinceptLab Deployment Guide

## Local Development

### Backend

```bash
cd KronosFinceptLab
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scriptsctivate
pip install -e ".[api,astock,cli,kronos,dev]"
kronos serve --host 0.0.0.0 --port 8000
```

Alternative FastAPI development server:

```bash
PYTHONPATH=src uvicorn kronos_fincept.api.app:app --reload --port 8000
```

Interactive API docs are disabled by default. Enable them explicitly when needed:

```bash
KRONOS_ENABLE_API_DOCS=1 kronos serve --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd web
npm install
npm run dev
```

The development frontend is served at http://localhost:3000 and calls the API at http://localhost:8000.

### CLI

```bash
kronos forecast --symbol 600036 --pred-len 5 --dry-run
kronos analyze agent --question "Is China Merchants Bank a good buy right now?" --symbol 600036 --market cn
```

## Windows / WSL Startup Scripts

```bash
# Windows: double-click start.bat or run it from a terminal
start.bat

# WSL/Linux
./start.sh
```

The scripts start the API backend and Web frontend together for local use.

## Docker

```bash
docker-compose up --build
```

The current Docker image is a combined Web/API runtime:

- Next.js standalone server is exposed publicly on port 3000.
- FastAPI listens internally on `127.0.0.1:8000`.
- The frontend talks to the backend through `INTERNAL_API_URL=http://127.0.0.1:8000`.
- The container healthcheck probes `http://127.0.0.1:8000/api/health`.

## Zeabur / Single-Container Runtime

`scripts/zeabur_start.sh` starts both services in one container:

```text
python -m uvicorn kronos_fincept.api.app:app --host $API_HOST --port $API_PORT
node /app/web/server.js on $PORT
```

Default container-oriented environment:

| Variable | Default/Role |
|----------|--------------|
| `PORT` | Public Web port, default 3000 |
| `API_HOST` | Internal API bind host, default `127.0.0.1` |
| `API_PORT` | Internal API port, default 8000 |
| `INTERNAL_API_URL` | Frontend-to-backend URL, default `http://127.0.0.1:8000` |
| `KRONOS_MODEL_ID` | Default `NeoQuasar/Kronos-base` |
| `KRONOS_ENABLE_REAL_MODEL` | Docker default enables real model inference |
| `KRONOS_ALLOW_DRY_RUN` | Docker default disables dry-run fallback |
| `KRONOS_PREWARM_ON_STARTUP` | Docker default preloads the model |
| `KRONOS_LOG_FORMAT` | Docker default `json` |
| `KRONOS_LOG_ENABLE_FILE` | Docker default disables file logging |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `KRONOS_MODEL_ID` | Model ID, default `NeoQuasar/Kronos-base` |
| `KRONOS_DEVICE` | `cpu`, `cuda`, or `rocm` |
| `KRONOS_REPO_PATH` | Path to upstream Kronos repo |
| `HF_HOME` / `HF_HUB_CACHE` | HuggingFace cache/model weights directory |
| `KRONOS_ENABLE_REAL_MODEL` | Enable real Kronos inference backend |
| `KRONOS_ALLOW_DRY_RUN` | Allow dry-run fallback requests |
| `KRONOS_PREWARM_ON_STARTUP` | Preload model during API startup |
| `KRONOS_API_KEYS` | User API keys |
| `KRONOS_ADMIN_API_KEYS` | Admin API keys for alert/admin routes |
| `KRONOS_INTERNAL_API_KEY` / `KRONOS_INTERNAL_API_KEYS` | Internal admin keys |
| `KRONOS_AUTH_DISABLED` | Disable API auth for local development only |
| `KRONOS_ENABLE_API_DOCS` | Enable `/docs`, `/redoc`, and `/openapi.json` |
| `DEEPSEEK_API_KEY` | Primary LLM provider key |
| `OPENROUTER_API_KEY` | Optional fallback LLM provider key |
| `WEB_SEARCH_PROVIDER` / `WEB_SEARCH_API_KEY` | Generic web-search enrichment |
| `ANYSEARCH_ENABLED` | Optional AnySearch enrichment toggle |

## Ports

| Service | Local Development | Docker/Zeabur |
|---------|-------------------|---------------|
| Web Frontend | http://localhost:3000 | Public port 3000 / `$PORT` |
| Backend API | http://localhost:8000 | Internal `127.0.0.1:8000` |
| API Docs | http://localhost:8000/docs when `KRONOS_ENABLE_API_DOCS=1` | Internal only unless explicitly exposed |

## Deployment Notes

- Do not enable `KRONOS_AUTH_DISABLED=1` on public deployments.
- Configure at least one user API key for normal Web/API use and an admin key for alerts/admin diagnostics.
- API docs should stay disabled in public deployments unless explicitly needed.
- Real model inference requires the upstream Kronos repo and HuggingFace model cache to be available to the runtime.
- External LLM/search providers are optional; when missing, the agent layer degrades to deterministic/template reports where possible.
