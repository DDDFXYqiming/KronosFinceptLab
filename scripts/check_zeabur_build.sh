#!/usr/bin/env sh
set -eu

SKIP_FRONTEND_BUILD="${SKIP_FRONTEND_BUILD:-0}"
SKIP_DOCKER="${SKIP_DOCKER:-0}"
DOCKER_TAG="${DOCKER_TAG:-kronos-fincept-lab:zeabur-check}"

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
WEB_DIR="$ROOT/web"
NEXT_DIR="$WEB_DIR/.next"
DOCKERFILE="$ROOT/Dockerfile"

assert_path() {
  if [ ! -e "$1" ]; then
    echo "$2 missing: $1" >&2
    exit 1
  fi
}

assert_contains() {
  if ! grep -Eq "$2" "$1"; then
    echo "$3 not found in $1" >&2
    exit 1
  fi
}

if [ "$SKIP_FRONTEND_BUILD" != "1" ]; then
  rm -rf "$NEXT_DIR"
  (
    cd "$WEB_DIR"
    NEXT_IGNORE_INCORRECT_LOCKFILE=1 NEXT_TELEMETRY_DISABLED=1 npm run build:zeabur
  )
fi

assert_path "$NEXT_DIR/standalone" "Next standalone output"
assert_path "$NEXT_DIR/static" "Next static output"
assert_path "$WEB_DIR/public" "Web public directory"
assert_path "$WEB_DIR/public/.gitkeep" "Tracked public placeholder"

assert_contains "$DOCKERFILE" "NEXT_IGNORE_INCORRECT_LOCKFILE=1" "Docker SWC lockfile guard"
assert_contains "$DOCKERFILE" "\\.next/standalone" "Docker standalone copy"
assert_contains "$DOCKERFILE" "web/public" "Docker public copy"
assert_contains "$DOCKERFILE" "zeabur_start\\.sh" "Docker startup script"

if [ "$SKIP_DOCKER" != "1" ]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found. Re-run with SKIP_DOCKER=1 for frontend-only validation." >&2
    exit 1
  fi
  docker build --target backend -t "$DOCKER_TAG" "$ROOT"
fi

echo "Zeabur build checks passed."
