from __future__ import annotations

import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app
from kronos_fincept.api.routes.jobs import clear_jobs


def _rows(n: int = 60, base: float = 100.0) -> list[dict]:
    out = []
    price = base
    for i in range(n):
        close = price * (1 + ((i % 5) - 2) * 0.001)
        out.append({
            "timestamp": f"2026-01-{(i % 28) + 1:02d}",
            "open": round(price, 2),
            "high": round(max(price, close) * 1.01, 2),
            "low": round(min(price, close) * 0.99, 2),
            "close": round(close, 2),
            "volume": 1000 + i,
            "amount": 100000 + i,
        })
        price = close
    return out


def _client() -> TestClient:
    clear_jobs()
    return TestClient(create_app())


def test_batch_data_endpoint_returns_per_symbol_success_and_failure():
    client = _client()

    def fake_cn(symbol: str, start_date: str, end_date: str, adjust: str = "qfq"):
        if symbol == "000000":
            raise ValueError("missing symbol")
        return _rows(35, 100.0 if symbol == "600036" else 200.0)

    with patch("kronos_fincept.api.routes.data.fetch_a_stock_ohlcv", side_effect=fake_cn):
        resp = client.post("/api/data/batch", json={
            "symbols": ["600036", "000858", "000000"],
            "market": "cn",
            "start_date": "20260101",
            "end_date": "20260430",
            "adjust": "qfq",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["market"] == "cn"
    assert body["count"] == 2
    assert body["errors"]["000000"] == "missing symbol"
    assert {item["symbol"] for item in body["items"]} == {"600036", "000858"}
    assert all(item["count"] == 35 for item in body["items"])


def test_submit_batch_job_fetches_data_runs_forecast_and_reports_progress():
    client = _client()

    with patch("kronos_fincept.api.routes.jobs.fetch_market_rows_for_batch") as fetch_rows:
        fetch_rows.side_effect = lambda symbol, market, start_date, end_date, adjust: _rows(60, 100.0 if symbol == "600036" else 200.0)
        submit = client.post("/api/jobs/batch", json={
            "symbols": ["600036", "000858"],
            "market": "cn",
            "start_date": "20260101",
            "end_date": "20260430",
            "pred_len": 5,
            "dry_run": True,
        })

    assert submit.status_code == 200
    job_id = submit.json()["job_id"]

    status = None
    for _ in range(20):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] == "completed":
            break
        time.sleep(0.02)

    assert status is not None
    assert status["status"] == "completed"
    assert status["kind"] == "batch"
    assert [step["status"] for step in status["steps"]] == ["completed", "completed", "completed"]
    result = status["result"]
    assert result["ok"] is True
    assert len(result["rankings"]) == 2
    assert result["failures"] == []
    assert result["progress"] == {"total": 2, "completed": 2, "success": 2, "failed": 0, "running": []}


def test_cancel_batch_job_marks_queued_job_cancelled_before_work_starts():
    client = _client()
    submit = client.post("/api/jobs/batch", json={
        "symbols": ["600036"],
        "market": "cn",
        "start_date": "20260101",
        "end_date": "20260430",
        "pred_len": 5,
        "dry_run": True,
        "start_immediately": False,
    })
    assert submit.status_code == 200
    job_id = submit.json()["job_id"]

    cancel = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "cancelled"


def test_admin_model_cache_endpoints_are_observable_and_clearable():
    client = _client()

    cache = client.get("/api/admin/model/cache")
    assert cache.status_code == 200
    assert cache.json()["ok"] is True
    assert "size" in cache.json()["cache"]

    cleared = client.post("/api/admin/model/clear-cache")
    assert cleared.status_code == 200
    assert cleared.json()["ok"] is True
    assert cleared.json()["after"]["size"] == 0


def test_macro_provider_status_endpoint_exposes_runtime_rows():
    client = _client()

    resp = client.get("/api/v1/analyze/macro/providers/status?mode=fast")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["mode"] == "fast"
    assert len(body["providers"]) >= 1
    assert {"provider_id", "status", "cached_entries", "timeout_seconds"}.issubset(body["providers"][0])
