"""Leakage-safe calendar window selection for Kronos fine-tuning."""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd


def select_calendar_window_starts(
    timestamps: Sequence[Any] | pd.Series,
    *,
    data_type: str,
    lookback: int,
    predict_window: int,
    train_start: str,
    train_end: str,
    validation_start: str,
    validation_end: str,
    diagnostic_start: str,
    diagnostic_end: str,
    embargo_bars: int = 5,
) -> list[int]:
    """Return sequence starts whose prediction tail belongs to one period.

    Kronos predictor training uses ``lookback + predict_window + 1`` rows so
    the token sequence can be shifted by one position.  Validation and
    diagnostic windows may borrow their lookback from the preceding period,
    but every row in their prediction tail stays inside the requested period.
    The first ``embargo_bars`` target starts after each boundary are skipped.
    """

    if lookback <= 0 or predict_window <= 0:
        raise ValueError("lookback and predict_window must be positive")
    if embargo_bars < 0:
        raise ValueError("embargo_bars cannot be negative")

    ts = pd.to_datetime(pd.Series(timestamps), errors="raise").reset_index(drop=True)
    if ts.duplicated().any() or not ts.is_monotonic_increasing:
        raise ValueError("timestamps must be unique and sorted ascending")

    normalized_type = "diagnostic" if data_type == "test" else data_type
    periods = {
        "train": (pd.Timestamp(train_start), pd.Timestamp(train_end)),
        "val": (pd.Timestamp(validation_start), pd.Timestamp(validation_end)),
        "diagnostic": (pd.Timestamp(diagnostic_start), pd.Timestamp(diagnostic_end)),
    }
    if normalized_type not in periods:
        raise ValueError(f"unsupported calendar data_type: {data_type}")
    period_start, period_end = periods[normalized_type]
    if period_start > period_end:
        raise ValueError(f"{normalized_type} start must not exceed end")

    in_period = ts[(ts >= period_start) & (ts <= period_end)]
    if in_period.empty:
        return []
    target_floor = in_period.iloc[0]
    if normalized_type != "train":
        if len(in_period) <= embargo_bars:
            return []
        target_floor = in_period.iloc[embargo_bars]

    sequence_size = lookback + predict_window + 1
    starts: list[int] = []
    for start in range(max(0, len(ts) - sequence_size + 1)):
        target_start = ts.iloc[start + lookback]
        target_end = ts.iloc[start + sequence_size - 1]
        if normalized_type == "train" and ts.iloc[start] < period_start:
            continue
        if target_start < target_floor or target_end > period_end:
            continue
        starts.append(start)
    return starts

