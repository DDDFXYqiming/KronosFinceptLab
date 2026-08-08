"""Full-history indicator alignment: cache, weekly buckets, volume ratio, S/R."""

from __future__ import annotations

import math
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from kronos_fincept import full_history
from kronos_fincept.methodology import (
    _cluster_swing_levels,
    _fractal_swings,
    _volume_profile_nodes,
    compute_fox_rules,
    compute_methodology,
)


def _synthetic_rows(count: int = 420, start_price: float = 10.0) -> list[dict]:
    rows: list[dict] = []
    for index in range(count):
        price = start_price + math.sin(index / 18.0) * 2.0 + index * 0.004
        open_ = price - 0.05
        high = price + 0.25
        low = price - 0.25
        close = price
        volume = 1_000_000.0 + (index % 7) * 50_000.0
        rows.append(
            {
                "timestamp": f"2024-01-{index % 28 + 1:02d}T00:00:00Z",
                "open": round(open_, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": volume,
                "amount": round(close * volume, 2),
            }
        )
    return rows


def _asset_with(full_rows: list[dict], display_rows: list[dict]) -> dict:
    return {
        "symbol": "600036",
        "market": "cn",
        "asset_class": "equity",
        "market_data": {"rows": display_rows},
        "full_rows": full_rows,
    }


def test_full_history_cache_reuses_rows_and_refreshes_next_day(monkeypatch):
    calls: list[str] = []
    rows = _synthetic_rows(120)
    monkeypatch.setattr(full_history, "_MEM_CACHE", {})

    def fake_fetch(symbol, market, adjust):
        calls.append(f"{symbol}:{market}:{adjust}")
        return rows

    monkeypatch.setattr(full_history, "_fetch_full_rows", fake_fetch)
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(full_history, "_CACHE_ROOT", Path(tmp) / "full_rows")

        first = full_history.get_full_history_rows("600036", "cn", "qfq")
        second = full_history.get_full_history_rows("600036", "cn", "qfq")

        assert len(first) == len(rows)
        assert len(calls) == 1
        assert len(second) == len(rows)
        assert (Path(tmp) / "full_rows" / "cn_600036_qfq.json").is_file()


def test_full_history_falls_back_to_stale_cache_on_fetch_failure(monkeypatch):
    rows = _synthetic_rows(80)
    monkeypatch.setattr(full_history, "_MEM_CACHE", {})
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(full_history, "_CACHE_ROOT", Path(tmp) / "full_rows")
        monkeypatch.setattr(full_history, "_fetch_full_rows", lambda *a: rows)
        full_history.get_full_history_rows("600036", "cn", "qfq")

        def fail(*args):
            raise ConnectionError("boom")

        monkeypatch.setattr(full_history, "_fetch_full_rows", fail)
        monkeypatch.setattr(full_history, "_today", lambda: "2099-01-01")

        stale = full_history.get_full_history_rows("600036", "cn", "qfq")
        assert len(stale) == len(rows)


def test_weekly_structure_uses_calendar_weeks_and_volume_ratio():
    rows: list[dict] = []
    start = datetime(2024, 1, 1)
    for index in range(25 * 7):
        close = 10.0 + index * 0.05
        ts = start + timedelta(days=index)
        rows.append(
            {
                "timestamp": ts.strftime("%Y-%m-%dT00:00:00Z"),
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 1_500_000.0 if index >= 170 else 500_000.0,
                "amount": close * 1_000_000.0,
            }
        )

    rules = compute_fox_rules(_asset_with(rows, rows[-100:]))
    weekly = next(rule for rule in rules if rule["id"] == "weekly_structure")
    assert weekly["status"] == "ok"
    assert "周K线方向" in weekly["detail"]
    assert "20周均线" in weekly["detail"]

    volume_rule = next(rule for rule in rules if rule["id"] == "volume_amount_resonance")
    assert volume_rule["status"] == "ok"
    assert "量能MA5/MA20=2.00" in volume_rule["detail"]


def test_support_resistance_uses_swing_touches_volume_profile_and_pivots():
    rows = _synthetic_rows(420)
    rules = compute_fox_rules(_asset_with(rows, rows[-100:]))
    sr = next(rule for rule in rules if rule["id"] == "support_resistance")

    assert sr["status"] == "ok"
    assert "支撑" in sr["detail"]
    assert "压力" in sr["detail"]
    assert "pivot" in sr["detail"]
    assert sr["evidence"]["support"] is not None
    assert sr["evidence"]["resistance"] is not None
    assert sr["evidence"]["pivots"]


def test_swing_and_volume_profile_helpers():
    rows = _synthetic_rows(420)
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    closes = [row["close"] for row in rows]
    amounts = [row["amount"] for row in rows]

    swings = _fractal_swings(highs, lows, amounts)
    clusters = _cluster_swing_levels(swings)
    nodes = _volume_profile_nodes(closes, highs, lows, amounts)

    assert len(swings) > 0
    assert any(cluster["touches"] >= 1 for cluster in clusters)
    assert any(node["poc"] for node in nodes)


def test_methodology_reports_data_scope():
    rows = _synthetic_rows(420)
    methodology = compute_methodology(_asset_with(rows, rows[-100:]))

    assert methodology["data_scope"]["adjust"] == "qfq"
    assert methodology["data_scope"]["full_bars"] == 420
    assert methodology["data_scope"]["display_bars"] == 100
