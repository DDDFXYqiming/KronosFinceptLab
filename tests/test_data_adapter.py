import pandas as pd
import datetime as _dt

from kronos_fincept.data_adapter import (
    rows_to_dataframe,
    make_future_timestamps,
)


def test_rows_to_dataframe_normalizes_and_orders_columns():
    rows = [
        {
            "timestamp": "2026-04-29T00:00:00Z",
            "open": "100",
            "high": "110",
            "low": "90",
            "close": "105",
        }
    ]

    df, timestamps = rows_to_dataframe(rows)

    assert list(df.columns) == ["open", "high", "low", "close", "volume", "amount"]
    assert df.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 0.0,
        "amount": 0.0,
    }
    assert timestamps.iloc[0] == pd.Timestamp("2026-04-29T00:00:00Z")


def test_make_future_timestamps_infers_hourly_frequency():
    timestamps = pd.Series(
        pd.to_datetime(
            ["2026-04-29T00:00:00Z", "2026-04-29T01:00:00Z", "2026-04-29T02:00:00Z"]
        )
    )

    future = make_future_timestamps(timestamps, pred_len=2)

    assert list(future.astype(str)) == [
        "2026-04-29 03:00:00+00:00",
        "2026-04-29 04:00:00+00:00",
    ]


def test_rows_to_dataframe_backfills_all_zero_amount(monkeypatch):
    rows = [
        {
            "timestamp": "2026-04-29T00:00:00Z",
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 1000.0,
            "amount": 0.0,
        },
        {
            "timestamp": "2026-04-30T00:00:00Z",
            "open": 105.0,
            "high": 112.0,
            "low": 101.0,
            "close": 108.0,
            "volume": 1200.0,
            "amount": 0.0,
        },
    ]

    df, _ = rows_to_dataframe(rows)

    assert df["amount"].tolist() == [105.0 * 1000.0, 108.0 * 1200.0]


def test_rows_to_dataframe_keeps_real_amount(monkeypatch):
    rows = [
        {
            "timestamp": "2026-04-29T00:00:00Z",
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 1000.0,
            "amount": 123456.0,
        }
    ]

    df, _ = rows_to_dataframe(rows)

    assert df["amount"].tolist() == [123456.0]


def test_make_future_timestamps_uses_trade_calendar(monkeypatch):
    calendar = [
        _dt.date(2026, 4, 27),
        _dt.date(2026, 4, 28),
        _dt.date(2026, 4, 29),
        _dt.date(2026, 4, 30),
        _dt.date(2026, 5, 4),
        _dt.date(2026, 5, 5),
    ]
    monkeypatch.setattr("kronos_fincept.data_adapter._load_trade_calendar", lambda: calendar)

    timestamps = pd.Series(
        pd.to_datetime(["2026-04-28T00:00:00Z", "2026-04-29T00:00:00Z", "2026-04-30T00:00:00Z"])
    )

    future = make_future_timestamps(timestamps, pred_len=2)

    assert [value.date().isoformat() for value in future] == ["2026-05-04", "2026-05-05"]


def test_make_future_timestamps_falls_back_without_calendar(monkeypatch):
    monkeypatch.setattr("kronos_fincept.data_adapter._load_trade_calendar", lambda: None)

    timestamps = pd.Series(
        pd.to_datetime(["2026-04-28T00:00:00Z", "2026-04-29T00:00:00Z", "2026-04-30T00:00:00Z"])
    )

    future = make_future_timestamps(timestamps, pred_len=2)

    assert [value.date().isoformat() for value in future] == ["2026-05-01", "2026-05-02"]
