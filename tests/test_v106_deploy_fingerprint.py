from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _fake_model_info(deep: bool = False) -> dict:
    return {
        "status": "ok",
        "model_loaded": False,
        "model_id": "NeoQuasar/Kronos-base",
        "tokenizer_id": None,
        "device": "cpu",
        "runtime_mode": "standard",
        "model_enabled": True,
        "deep_check": deep,
        "capabilities": {"real_model": False, "dry_run": True},
        "model_error": None,
    }


def test_v106_build_info_reads_only_safe_whitelisted_env(monkeypatch):
    monkeypatch.setenv("KRONOS_APP_VERSION", "v10.6.2")
    monkeypatch.setenv("KRONOS_BUILD_COMMIT", "c14ad60e1c0b414782442291fb3c2042ade716c8")
    monkeypatch.setenv("KRONOS_BUILD_REF", "main")
    monkeypatch.setenv("KRONOS_BUILD_SOURCE", "zeabur")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret-that-must-not-leak")

    from kronos_fincept.build_info import get_build_info

    info = get_build_info().as_dict()

    assert info == {
        "app_version": "v10.6.2",
        "build_commit": "c14ad60e1c0b414782442291fb3c2042ade716c8",
        "build_ref": "main",
        "build_source": "zeabur",
    }
    assert "secret" not in json.dumps(info)
    assert "DEEPSEEK" not in json.dumps(info)


def test_v106_build_info_uses_safe_defaults_when_env_missing(monkeypatch):
    for key in [
        "KRONOS_APP_VERSION",
        "KRONOS_BUILD_COMMIT",
        "KRONOS_BUILD_REF",
        "KRONOS_BUILD_SOURCE",
        "ZEABUR_GIT_COMMIT_SHA",
        "GITHUB_SHA",
    ]:
        monkeypatch.delenv(key, raising=False)

    from kronos_fincept.build_info import get_build_info

    info = get_build_info().as_dict()

    assert info["app_version"] == "v10.6.2"
    assert info["build_commit"] == "unknown"
    assert info["build_ref"] == "unknown"
    assert info["build_source"] == "unknown"


def test_v106_health_endpoint_returns_build_metadata_without_deep_model_check(monkeypatch):
    monkeypatch.setenv("KRONOS_APP_VERSION", "v10.6.2")
    monkeypatch.setenv("KRONOS_BUILD_COMMIT", "abcdef1234567890")
    monkeypatch.setenv("KRONOS_BUILD_REF", "main")
    monkeypatch.setenv("KRONOS_BUILD_SOURCE", "local-test")

    from kronos_fincept.api.routes import health as health_route
    from kronos_fincept.api.app import create_app

    calls: list[bool] = []

    def fake_model_info(deep: bool = False) -> dict:
        calls.append(deep)
        return _fake_model_info(deep=deep)

    monkeypatch.setattr(health_route, "get_model_info", fake_model_info)
    client = TestClient(create_app())

    response = client.get("/api/health")
    payload = response.json()

    assert response.status_code == 200
    assert calls == [False]
    assert payload["app_version"] == "v10.6.2"
    assert payload["build_commit"] == "abcdef1234567890"
    assert payload["build_ref"] == "main"
    assert payload["build_source"] == "local-test"
    assert payload["version"] == "2.0.0"


def test_v106_deep_health_endpoint_keeps_same_build_metadata(monkeypatch):
    monkeypatch.setenv("KRONOS_APP_VERSION", "v10.6.2")
    monkeypatch.setenv("KRONOS_BUILD_COMMIT", "fedcba0987654321")
    monkeypatch.setenv("KRONOS_BUILD_REF", "release/v10.6.2")
    monkeypatch.setenv("KRONOS_BUILD_SOURCE", "zeabur")

    from kronos_fincept.api.routes import health as health_route
    from kronos_fincept.api.app import create_app

    calls: list[bool] = []

    def fake_model_info(deep: bool = False) -> dict:
        calls.append(deep)
        return _fake_model_info(deep=deep)

    monkeypatch.setattr(health_route, "get_model_info", fake_model_info)
    client = TestClient(create_app())

    payload = client.get("/api/health/deep").json()

    assert calls == [True]
    assert payload["deep_check"] is True
    assert payload["app_version"] == "v10.6.2"
    assert payload["build_commit"] == "fedcba0987654321"
    assert payload["build_ref"] == "release/v10.6.2"
    assert payload["build_source"] == "zeabur"


def test_v106_dockerfile_and_dashboard_expose_build_metadata_contract():
    dockerfile = read("Dockerfile")
    types = read("web/src/types/api.ts")
    dashboard = read("web/src/app/page.tsx")

    for marker in [
        "ARG KRONOS_APP_VERSION=v10.7.3",
        "ARG KRONOS_BUILD_COMMIT=unknown",
        "ARG KRONOS_BUILD_REF=unknown",
        "ARG KRONOS_BUILD_SOURCE=docker",
        "KRONOS_APP_VERSION=$KRONOS_APP_VERSION",
        "KRONOS_BUILD_COMMIT=$KRONOS_BUILD_COMMIT",
        "KRONOS_BUILD_REF=$KRONOS_BUILD_REF",
        "KRONOS_BUILD_SOURCE=$KRONOS_BUILD_SOURCE",
    ]:
        assert marker in dockerfile

    for field in ["app_version", "build_commit", "build_ref", "build_source"]:
        assert field in types

    assert "部署版本" in dashboard
    assert "shortCommit" in dashboard
    assert "health?.app_version" in dashboard
    assert "health?.build_commit" in dashboard
