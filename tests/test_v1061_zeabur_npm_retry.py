from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v1061_frontend_builder_hardens_npm_ci_against_network_flakes():
    dockerfile = read("Dockerfile")

    for marker in [
        "ARG NPM_REGISTRY=https://registry.npmjs.org/",
        "NPM_CONFIG_REGISTRY=${NPM_REGISTRY}",
        "NPM_CONFIG_FETCH_RETRIES=5",
        "NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=20000",
        "NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000",
        "NPM_CONFIG_FETCH_TIMEOUT=300000",
        "NPM_CONFIG_AUDIT=false",
        "NPM_CONFIG_FUND=false",
        "npm ci --include=optional --no-audit --no-fund",
        "https://registry.npmmirror.com",
        "sleep $((attempt * 10))",
    ]:
        assert marker in dockerfile


def test_v1061_zeabur_build_failure_was_frontend_npm_ci_not_backend_apt():
    dockerfile = read("Dockerfile")

    frontend_pos = dockerfile.index("FROM node:22-alpine AS frontend-builder")
    backend_pos = dockerfile.index("FROM node:22-bookworm-slim AS backend")
    npm_ci_pos = dockerfile.index("npm ci --include=optional --no-audit --no-fund")
    apt_pos = dockerfile.index("apt-get update")

    assert frontend_pos < npm_ci_pos < backend_pos < apt_pos
