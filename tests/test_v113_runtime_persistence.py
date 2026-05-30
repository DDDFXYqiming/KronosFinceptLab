"""v11.3 persistent runtime layer regression tests."""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _client_with_runtime_db(monkeypatch, tmp_path: Path) -> TestClient:
    db_path = tmp_path / "runtime.sqlite3"
    monkeypatch.setenv("KRONOS_RUNTIME_DB", str(db_path))

    import kronos_fincept.api.routes.jobs as jobs
    import kronos_fincept.api.routes.watchlist as watchlist
    import kronos_fincept.api.app as app_module

    importlib.reload(jobs)
    importlib.reload(watchlist)
    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_v113_job_history_survives_route_reload(monkeypatch, tmp_path):
    client = _client_with_runtime_db(monkeypatch, tmp_path)

    submit = client.post(
        "/api/jobs/batch",
        json={
            "symbols": ["600036", "300750"],
            "market": "cn",
            "start_date": "20250101",
            "end_date": "20260430",
            "pred_len": 5,
            "dry_run": True,
            "start_immediately": False,
        },
    )
    assert submit.status_code == 200
    job_id = submit.json()["job_id"]

    listed = client.get("/api/jobs")
    assert listed.status_code == 200
    assert any(job["job_id"] == job_id and job["kind"] == "batch" for job in listed.json()["jobs"])

    import kronos_fincept.api.routes.jobs as jobs
    importlib.reload(jobs)

    restored = jobs.get_job_snapshot(job_id)
    assert restored is not None
    assert restored["status"] == "queued"
    assert restored["kind"] == "batch"


def test_v113_watchlist_crud_survives_route_reload(monkeypatch, tmp_path):
    client = _client_with_runtime_db(monkeypatch, tmp_path)

    created = client.post(
        "/api/watchlist/lists",
        json={
            "name": "核心持仓",
            "market": "cn",
            "symbols": ["600036", "300750", "600036"],
            "weights": {"600036": 0.6, "300750": 0.4},
            "tags": ["core", "ai"],
        },
    )
    assert created.status_code == 200
    payload = created.json()
    watchlist_id = payload["id"]
    assert payload["symbols"] == ["600036", "300750"]

    listed = client.get("/api/watchlist/lists")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    import kronos_fincept.api.routes.watchlist as watchlist
    importlib.reload(watchlist)

    restored = watchlist.get_watchlist_snapshot(watchlist_id)
    assert restored is not None
    assert restored["name"] == "核心持仓"
    assert restored["symbols"] == ["600036", "300750"]

    updated = client.put(
        f"/api/watchlist/lists/{watchlist_id}",
        json={"name": "核心持仓-更新", "symbols": ["000001"], "market": "cn"},
    )
    assert updated.status_code == 200
    assert updated.json()["symbols"] == ["000001"]

    deleted = client.delete(f"/api/watchlist/lists/{watchlist_id}")
    assert deleted.status_code == 200
    assert client.get("/api/watchlist/lists").json()["total"] == 0


def test_v113_alert_rules_use_runtime_db_when_configured(monkeypatch, tmp_path):
    client = _client_with_runtime_db(monkeypatch, tmp_path)

    created = client.post(
        "/api/alert/rules",
        json={
            "name": "招商银行偏离",
            "alert_type": "prediction_deviation",
            "symbol": "600036",
            "market": "cn",
            "params": {"deviation_pct": 8.0},
            "channel": "feishu",
        },
    )
    assert created.status_code == 200
    rule_id = created.json()["id"]

    import kronos_fincept.api.routes.alert as alert_route
    importlib.reload(alert_route)

    listed = client.get("/api/alert/rules")
    assert listed.status_code == 200
    assert any(rule["id"] == rule_id for rule in listed.json()["rules"])

    db_path = tmp_path / "runtime.sqlite3"
    assert db_path.exists()
