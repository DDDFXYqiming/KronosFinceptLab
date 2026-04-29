import pandas as pd

from kronos_fincept.data_adapter import rows_to_dataframe, make_future_timestamps


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
