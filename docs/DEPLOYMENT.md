# KronosFinceptLab Deployment Guide

## Local Development

### Backend
```bash
cd KronosFinceptLab
python -m venv .venv
source .venv/bin/activate
pip install -e ".[api,astock,dev]"
uvicorn kronos_fincept.api.app:app --reload --port 8000
```

### Frontend
```bash
cd web
npm install
npm run dev
```

### CLI
```bash
kronos forecast --symbol 600036 --pred-len 5 --dry-run
```

## Docker
```bash
docker-compose up --build
```

## Environment Variables
- `KRONOS_MODEL_ID`: Model ID (default: NeoQuasar/Kronos-base)
- `KRONOS_DEVICE`: cpu/cuda/rocm
- `KRONOS_REPO_PATH`: Path to upstream Kronos repo

## Ports
- Backend API: 8000
- Frontend: 3000
- API Docs: http://localhost:8000/docs
