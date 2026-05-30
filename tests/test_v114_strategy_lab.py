"""v11.4 Portfolio Strategy Lab regression tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from kronos_fincept.api.app import app


def _rows(days: int = 220, base: float = 100.0, drift: float = 0.001) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    price = base
    start = date(2025, 1, 1)
    for i in range(days):
        price *= 1.0 + drift + ((i % 7) - 3) * 0.0004
        rows.append({
            "timestamp": (start + timedelta(days=i)).isoformat(),
            "open": round(price * 0.99, 4),
            "high": round(price * 1.01, 4),
            "low": round(price * 0.98, 4),
            "close": round(price, 4),
            "volume": 1000000 + i * 1000,
        })
    return rows


def _mock_fetch(symbol: str, start: str, end: str):
    drift = {"600036": 0.0015, "000858": 0.0008, "300750": -0.0002}.get(symbol, 0.0005)
    return _rows(base=80.0 + len(symbol), drift=drift)


def test_v114_strategy_backtest_supports_multiple_strategies():
    client = TestClient(app)
    with patch("kronos_fincept.api.routes.backtest.fetch_a_stock_ohlcv", side_effect=_mock_fetch):
        resp = client.post("/api/backtest/strategy", json={
            "symbols": ["600036", "000858", "300750"],
            "start_date": "20250101",
            "end_date": "20250630",
            "strategies": ["equal_weight", "momentum", "mean_reversion", "top_k_ranking"],
            "top_k": 2,
            "window_size": 40,
            "step": 10,
            "pred_len": 5,
            "dry_run": True,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["best_strategy"] in {"equal_weight", "momentum", "mean_reversion", "top_k_ranking"}
    assert [row["strategy"] for row in data["results"]] == ["equal_weight", "momentum", "mean_reversion", "top_k_ranking"]
    for row in data["results"]:
        assert row["metrics"]["total_trades"] > 0
        assert row["equity_curve"]
        assert "turnover" in row["metadata"]


def test_v114_strategy_parameter_scan_and_rolling_validation():
    client = TestClient(app)
    with patch("kronos_fincept.api.routes.backtest.fetch_a_stock_ohlcv", side_effect=_mock_fetch):
        scan = client.post("/api/backtest/strategy/scan", json={
            "symbols": ["600036", "000858", "300750"],
            "start_date": "20250101",
            "end_date": "20250630",
            "strategy": "momentum",
            "top_k_values": [1, 2],
            "step_values": [5, 10],
            "window_size": 40,
            "pred_len": 5,
            "dry_run": True,
        })
        rolling = client.post("/api/backtest/strategy/rolling", json={
            "symbols": ["600036", "000858", "300750"],
            "start_date": "20250101",
            "end_date": "20250630",
            "strategy": "equal_weight",
            "folds": 3,
            "top_k": 2,
            "window_size": 40,
            "step": 10,
            "pred_len": 5,
            "dry_run": True,
        })
    assert scan.status_code == 200
    scan_data = scan.json()
    assert scan_data["ok"] is True
    assert len(scan_data["results"]) == 4
    assert scan_data["best"]["params"]["top_k"] in {1, 2}
    assert scan_data["results"][0]["rank"] == 1

    assert rolling.status_code == 200
    rolling_data = rolling.json()
    assert rolling_data["ok"] is True
    assert len(rolling_data["folds"]) == 3
    assert rolling_data["summary"]["folds"] == 3
    assert "avg_total_return" in rolling_data["summary"]


def test_v114_frontend_exposes_strategy_lab_controls():
    page = Path("web/src/app/backtest/page.tsx").read_text(encoding="utf-8")
    client = Path("web/src/lib/api.ts").read_text(encoding="utf-8")
    types = Path("web/src/types/api.ts").read_text(encoding="utf-8")

    assert "api.strategyBacktest" in page
    assert "api.strategyScan" in page
    assert "api.strategyRolling" in page
    assert "Portfolio Strategy Lab" in page
    assert "strategyBacktest" in client
    assert "StrategyBacktestResponse" in types
