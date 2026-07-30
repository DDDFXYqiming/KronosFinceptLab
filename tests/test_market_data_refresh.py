from __future__ import annotations

import pandas as pd

from examples.refresh_compact_market_data import _scale_changed


def test_refresh_detects_volume_and_amount_unit_changes():
    existing = pd.DataFrame(
        {
            "timestamp": ["2026-06-01", "2026-06-02", "2026-06-03"],
            "close": [10.0, 10.1, 10.2],
            "volume": [1000.0, 1100.0, 1200.0],
            "amount": [10_000.0, 11_000.0, 12_000.0],
        }
    )
    refreshed = existing.copy()
    refreshed["timestamp"] += "T00:00:00Z"
    refreshed["volume"] *= 100
    refreshed["amount"] *= 1000

    assert _scale_changed(existing, refreshed) is True
