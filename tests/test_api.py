"""Unit tests for Phase A — FastAPI API layer.

Tests cover:
- Health endpoint
- Forecast endpoint (dry-run)
- Batch endpoint (dry-run)
- Data endpoint (mocked AkShare)
- Backtest endpoint (dry-run)
- Error handling
- Request validation
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app


@pytest.fixture
def app():
    """Create a fresh test app for each test."""
    return create_app()


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


# ── Sample data fixtures ──────────────────────────────────

def _make_ohlcv_rows(n: int = 100, base_price: float = 100.0) -> list[dict]:
    """Generate synthetic OHLCV rows for testing."""
    rows = []
    price = base_price
    for i in range(n):
        open_p = price
        close_p = price * (1 + (i % 5 - 2) * 0.002)
        high_p = max(open_p, close_p) * 1.005
        low_p = min(open_p, close_p) * 0.995
        rows.append({
            "timestamp": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": 1000000 + i * 1000,
            "amount": 100000000 + i * 100000,
        })
        price = close_p
    return rows


# ── Health tests ──────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in {"ok", "degraded"}
        assert data["version"] == "2.0.0"
        assert "model_id" in data
        assert "model_loaded" in data
        assert "capabilities" in data
        assert "device" in data
        assert "uptime_seconds" in data


# ── Forecast tests ────────────────────────────────────────

class TestForecast:
    def test_forecast_dry_run(self, client):
        rows = _make_ohlcv_rows(60)
        resp = client.post("/api/forecast", json={
            "symbol": "600036",
            "timeframe": "1d",
            "pred_len": 5,
            "rows": rows,
            "dry_run": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["symbol"] == "600036"
        assert len(data["forecast"]) == 5
        assert data["metadata"]["backend"] == "dry_run"
        assert data["metadata"]["warning"] != ""

    def test_forecast_validates_missing_rows(self, client):
        resp = client.post("/api/forecast", json={
            "symbol": "600036",
            "pred_len": 5,
            "rows": [],
        })
        assert resp.status_code == 422  # Pydantic validation error

    def test_forecast_validates_missing_symbol(self, client):
        rows = _make_ohlcv_rows(60)
        resp = client.post("/api/forecast", json={
            "pred_len": 5,
            "rows": rows,
        })
        assert resp.status_code == 422

    def test_forecast_validates_pred_len(self, client):
        rows = _make_ohlcv_rows(60)
        resp = client.post("/api/forecast", json={
            "symbol": "600036",
            "pred_len": 0,
            "rows": rows,
        })
        assert resp.status_code == 422

    def test_forecast_output_has_ohlc(self, client):
        rows = _make_ohlcv_rows(60)
        resp = client.post("/api/forecast", json={
            "symbol": "600036",
            "pred_len": 3,
            "rows": rows,
            "dry_run": True,
        })
        data = resp.json()
        for bar in data["forecast"]:
            assert "timestamp" in bar
            assert "open" in bar
            assert "high" in bar
            assert "low" in bar
            assert "close" in bar


# ── Batch tests ───────────────────────────────────────────

class TestBatch:
    def test_batch_dry_run(self, client):
        rows = _make_ohlcv_rows(60, base_price=100.0)
        rows2 = _make_ohlcv_rows(60, base_price=200.0)
        resp = client.post("/api/batch", json={
            "assets": [
                {"symbol": "600036", "rows": rows},
                {"symbol": "000858", "rows": rows2},
            ],
            "pred_len": 5,
            "dry_run": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["rankings"]) == 2
        # Rankings should be sorted by predicted_return descending
        assert data["rankings"][0]["predicted_return"] >= data["rankings"][1]["predicted_return"]
        assert data["rankings"][0]["rank"] == 1

    def test_batch_empty_assets_fails(self, client):
        resp = client.post("/api/batch", json={
            "assets": [],
            "pred_len": 5,
        })
        assert resp.status_code == 422


# ── Data tests (mocked AkShare) ──────────────────────────

class TestData:
    def test_get_a_stock_data(self, client):
        """Test data endpoint with mocked AkShare."""
        mock_rows = _make_ohlcv_rows(30)
        with patch("kronos_fincept.api.routes.data.fetch_a_stock_ohlcv", return_value=mock_rows):
            resp = client.get("/api/data/a-stock/600036?start_date=20260101&end_date=20260430")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["symbol"] == "600036"
        assert data["count"] == 30

    def test_get_a_stock_data_missing_params(self, client):
        resp = client.get("/api/data/a-stock/600036")
        assert resp.status_code == 422  # Missing required query params

    def test_search_stocks(self, client):
        """Test search endpoint with mocked AkShare."""
        import pandas as pd
        mock_df = pd.DataFrame({
            "代码": ["600036", "600518", "000858"],
            "名称": ["招商银行", "贵州百灵", "五粮液"],
        })
        with patch("akshare.stock_zh_a_spot_em", return_value=mock_df):
            resp = client.get("/api/data/search?q=招商银行")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        # "招商银行" should match
        assert len(data["results"]) >= 1
        assert any(r["code"] == "600036" for r in data["results"])


# ── Backtest tests ────────────────────────────────────────

class TestBacktest:
    def test_backtest_dry_run(self, client):
        """Test backtest with mocked data."""
        mock_rows = _make_ohlcv_rows(200, base_price=100.0)
        with patch("kronos_fincept.api.routes.backtest.fetch_a_stock_ohlcv", return_value=mock_rows):
            resp = client.post("/api/backtest/ranking", json={
                "symbols": ["600036", "000858"],
                "start_date": "20250101",
                "end_date": "20260430",
                "top_k": 1,
                "pred_len": 5,
                "window_size": 60,
                "step": 5,
                "dry_run": True,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "metrics" in data
        assert "equity_curve" in data
        assert data["metrics"]["total_trades"] > 0

    def test_backtest_insufficient_data(self, client):
        """Test backtest with too little data."""
        short_rows = _make_ohlcv_rows(10)
        with patch("kronos_fincept.api.routes.backtest.fetch_a_stock_ohlcv", return_value=short_rows):
            resp = client.post("/api/backtest/ranking", json={
                "symbols": ["600036"],
                "start_date": "20250101",
                "end_date": "20260430",
                "top_k": 1,
                "dry_run": True,
            })
        assert resp.status_code == 400


# ── Global error handling ─────────────────────────────────

class TestErrorHandling:
    def test_404_on_unknown_route(self, client):
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

    def test_405_on_wrong_method(self, client):
        resp = client.get("/api/forecast")
        assert resp.status_code == 405
