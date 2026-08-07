"""Data conversion utilities for Kronos-compatible OHLCV inputs."""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from kronos_fincept.schemas import ForecastRow

KRONOS_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]

_logger = logging.getLogger(__name__)

_TRADE_CALENDAR_CACHE: list[_dt.date] | None = None
_CALENDAR_FILE = Path(__file__).resolve().parents[2] / "output" / "calendars" / "trade_dates.csv"


def _load_trade_calendar() -> list[_dt.date] | None:
    """Load the A/H trading calendar (AkShare), cached under output/calendars/.

    Returns None when the calendar is unavailable so callers can fall back to
    naive step extrapolation without failing.
    """
    global _TRADE_CALENDAR_CACHE
    if _TRADE_CALENDAR_CACHE is not None:
        return _TRADE_CALENDAR_CACHE

    cached_dates: list[_dt.date] = []
    if _CALENDAR_FILE.is_file():
        try:
            cached_dates = [
                _dt.date.fromisoformat(line.strip())
                for line in _CALENDAR_FILE.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except ValueError:
            cached_dates = []
        if cached_dates:
            _TRADE_CALENDAR_CACHE = cached_dates
            return cached_dates

    try:
        import akshare as ak

        frame = ak.tool_trade_date_hist_sina()
        raw = [str(value) for value in frame["trade_date"].tolist()]
        cached_dates = sorted({_dt.date.fromisoformat(value[:10]) for value in raw})
    except Exception as exc:
        _logger.debug("Trading calendar unavailable, falling back to step extrapolation: %s", exc)
        return None

    if not cached_dates:
        return None
    try:
        _CALENDAR_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CALENDAR_FILE.write_text(
            "\n".join(value.isoformat() for value in cached_dates) + "\n",
            encoding="utf-8",
        )
    except OSError:
        _logger.debug("Failed to persist trading calendar cache at %s", _CALENDAR_FILE)
    _TRADE_CALENDAR_CACHE = cached_dates
    return cached_dates


def rows_to_dataframe(rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.Series]:
    """Convert raw request rows to Kronos DataFrame and timestamp Series."""
    normalized = [ForecastRow.from_dict(row).to_dict() for row in rows]
    df = pd.DataFrame(normalized)
    timestamps = pd.to_datetime(df.pop("timestamp"), utc=True)
    df = df[KRONOS_COLUMNS].astype(float)
    if (df["amount"] == 0).all():
        _logger.warning(
            "amount is all zero for %d rows; backfilling close*volume per upstream rule",
            len(df),
        )
        df["amount"] = df["close"] * df["volume"]
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

    if step == pd.Timedelta(days=1):
        calendar = _load_trade_calendar()
        if calendar is not None:
            last_date = ts.iloc[-1].date()
            future = [value for value in calendar if value > last_date][:pred_len]
            if len(future) == pred_len:
                _logger.debug(
                    "future timestamps generated from trading calendar: %s..%s",
                    future[0],
                    future[-1],
                )
                return pd.Series(
                    pd.to_datetime([f"{value.isoformat()}T00:00:00Z" for value in future], utc=True)
                )
            _logger.warning(
                "trading calendar has only %d future dates (need %d); falling back to step extrapolation",
                len(future),
                pred_len,
            )

    start = ts.iloc[-1] + step
    return pd.Series(pd.date_range(start=start, periods=pred_len, freq=step))
