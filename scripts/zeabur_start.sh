#!/bin/sh
set -eu

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${PORT:-3000}"

export PYTHONPATH="${PYTHONPATH:-/app/src}"
export NEXT_TELEMETRY_DISABLED=1
export KRONOS_LOW_MEMORY_DEFAULTS="${KRONOS_LOW_MEMORY_DEFAULTS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_MAX_THREADS="${NUMEXPR_MAX_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

cleanup() {
  if [ -n "${api_pid:-}" ] && kill -0 "$api_pid" 2>/dev/null; then
    kill "$api_pid" 2>/dev/null || true
  fi
  if [ -n "${web_pid:-}" ] && kill -0 "$web_pid" 2>/dev/null; then
    kill "$web_pid" 2>/dev/null || true
  fi
}

trap cleanup INT TERM EXIT

python -m uvicorn kronos_fincept.api.app:app --host "$API_HOST" --port "$API_PORT" &
api_pid="$!"

cd /app/web
HOSTNAME="$WEB_HOST" PORT="$WEB_PORT" node server.js &
web_pid="$!"

while true; do
  if ! kill -0 "$api_pid" 2>/dev/null; then
    wait "$api_pid"
    exit "$?"
  fi
  if ! kill -0 "$web_pid" 2>/dev/null; then
    wait "$web_pid"
    exit "$?"
  fi
  sleep 2
done
