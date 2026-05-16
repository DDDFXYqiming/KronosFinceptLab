# KronosFinceptLab Startup Guide

## Windows (Double-click)

Simply double-click `start.bat` to launch both services:

1. **API Backend** — Runs at http://localhost:8000 (new window)
2. **Web Frontend** — Runs at http://localhost:3000 (new window)

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

### Start Web Frontend

```bash
cd web
npm install  # first time only
npm run dev
```

## Access URLs

| Service | URL |
|---------|-----|
| Web Frontend | http://localhost:3000 |
| API Backend | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## Stopping Services

### Windows
- Close the "KronosFinceptLab API" and "KronosFinceptLab Web" command windows

### WSL/Linux
- Press `Ctrl+C` in the terminal running `start.sh`

## Troubleshooting

### Port Already in Use
If ports 8000 or 3000 are occupied:
- Close the program using the port
- Or modify the port numbers in the startup script

### Python Not Found
Ensure Python 3.11+ is installed and added to PATH.

### Node.js Not Found
Ensure Node.js 18+ is installed and added to PATH.

### npm install Fails
Try clearing the cache:
```bash
cd web
rm -rf node_modules package-lock.json
npm install
```