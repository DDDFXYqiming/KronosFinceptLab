from __future__ import annotations

import pandas as pd

from kronos_fincept.evaluation.pit_universe import (
    filter_starts_by_membership,
    intervals_to_frame,
    load_membership_intervals,
    snapshots_to_intervals,
)


def test_snapshots_become_closed_point_in_time_intervals(tmp_path):
    intervals = snapshots_to_intervals(
        [
            ("2022-01-01", {"600000", "000001"}, "first"),
            ("2022-06-13", {"600000", "000002"}, "second"),
        ],
        market="A",
        index_name="CSI300",
        end_date="2022-12-31",
    )

    frame = intervals_to_frame(intervals)
    removed = frame.loc[frame["symbol"] == "000001"].iloc[0]
    added = frame.loc[frame["symbol"] == "000002"].iloc[0]
    assert removed["member_to"] == "2022-06-12"
    assert added["member_from"] == "2022-06-13"

    path = tmp_path / "universe_membership.csv"
    frame.to_csv(path, index=False)
    loaded = load_membership_intervals(path)
    assert loaded[("A", "600000")] == [
        (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31"))
    ]


def test_training_windows_use_membership_at_forecast_origin(tmp_path):
    sidecar = tmp_path / "universe_membership.csv"
    pd.DataFrame(
        [
            {
                "symbol": "600000",
                "market": "A",
                "index_name": "CSI300",
                "member_from": "2022-01-05",
                "member_to": "2022-01-08",
                "source_url": "test",
            }
        ]
    ).to_csv(sidecar, index=False)
    intervals = load_membership_intervals(sidecar)
    timestamps = pd.date_range("2022-01-01", periods=12, freq="D")

    starts = filter_starts_by_membership(
        range(7),
        timestamps,
        lookback=3,
        market="A",
        symbol="600000",
        intervals=intervals,
    )

    # start=2 -> forecast origin row 4 -> 2022-01-05
    # start=5 -> forecast origin row 7 -> 2022-01-08
    assert starts == [2, 3, 4, 5]
