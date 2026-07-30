from __future__ import annotations

import pandas as pd

from kronos_fincept.evaluation.splits import select_calendar_window_starts


def test_compact_calendar_windows_keep_targets_inside_their_periods():
    timestamps = pd.bdate_range("2021-08-01", "2026-07-31")
    common = {
        "lookback": 90,
        "predict_window": 5,
        "train_start": "2022-01-01",
        "train_end": "2025-12-31",
        "validation_start": "2026-01-01",
        "validation_end": "2026-03-31",
        "diagnostic_start": "2026-04-01",
        "diagnostic_end": "2026-07-31",
        "embargo_bars": 5,
    }

    train = select_calendar_window_starts(timestamps, data_type="train", **common)
    validation = select_calendar_window_starts(timestamps, data_type="val", **common)
    diagnostic = select_calendar_window_starts(timestamps, data_type="diagnostic", **common)

    assert train and validation and diagnostic
    assert timestamps[train[0]] >= pd.Timestamp("2022-01-01")
    assert timestamps[train[-1] + 90 + 5] <= pd.Timestamp("2025-12-31")

    validation_target_starts = [timestamps[start + 90] for start in validation]
    diagnostic_target_starts = [timestamps[start + 90] for start in diagnostic]
    validation_bars = timestamps[
        (timestamps >= "2026-01-01") & (timestamps <= "2026-03-31")
    ]
    diagnostic_bars = timestamps[
        (timestamps >= "2026-04-01") & (timestamps <= "2026-07-31")
    ]

    assert validation_target_starts[0] == validation_bars[5]
    assert timestamps[validation[-1] + 90 + 5] <= pd.Timestamp("2026-03-31")
    assert timestamps[validation[0]] < pd.Timestamp("2026-01-01")
    assert diagnostic_target_starts[0] == diagnostic_bars[5]
    assert timestamps[diagnostic[-1] + 90 + 5] <= pd.Timestamp("2026-07-31")
