"""Data conversion utilities for Kronos-compatible OHLCV inputs."""

from __future__ import annotations

from typing import Any

import pandas as pd

from kronos_fincept.schemas import ForecastRow

KRONOS_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]


def rows_to_dataframe(rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.Series]:
    """Convert raw request rows to Kronos DataFrame and timestamp Series."""
    normalized = [ForecastRow.from_dict(row).to_dict() for row in rows]
    df = pd.DataFrame(normalized)
    timestamps = pd.to_datetime(df.pop("timestamp"), utc=True)
    df = df[KRONOS_COLUMNS].astype(float)
    return df, pd.Series(timestamps)


def make_future_timestamps(timestamps: pd.Series, pred_len: int) -> pd.Series:
    """Infer a regular future timestamp index from historical timestamps."""
    if pred_len <= 0:
        raise ValueError("pred_len must be positive")
    if len(timestamps) == 0:
        raise ValueError("timestamps cannot be empty")

    ts = pd.Series(pd.to_datetime(timestamps, utc=True))
    if len(ts) >= 2:
        step = ts.iloc[-1] - ts.iloc[-2]
        if step <= pd.Timedelta(0):
            raise ValueError("timestamps must be strictly increasing")
    else:
        step = pd.Timedelta(days=1)

    start = ts.iloc[-1] + step
    return pd.Series(pd.date_range(start=start, periods=pred_len, freq=step))
