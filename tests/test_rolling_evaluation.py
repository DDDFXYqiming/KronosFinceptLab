from __future__ import annotations

import pandas as pd

from kronos_fincept.evaluation.rolling import (
    AssetMeta,
    bootstrap_ci,
    build_window_records,
    select_evaluation_samples,
    summarize_prediction_rows,
)


def _asset() -> AssetMeta:
    return AssetMeta("000001", "A", "cn_000001.csv", 40, "2020-01-01", "2020-02-25")


def test_window_records_respect_target_interval_and_embargo():
    timestamps = pd.date_range("2020-01-01", periods=40, freq="D")
    records = build_window_records(
        _asset(),
        timestamps,
        fold="fold_2020",
        target_start="2020-01-20",
        target_end="2020-02-25",
        lookback=5,
        pred_len=3,
        embargo_bars=3,
    )

    assert records
    assert all(record.target_start >= "2020-01-20" for record in records)
    for previous, current in zip(records, records[1:]):
        assert current.target_start_row - previous.target_start_row >= 6


def test_sample_step_cannot_overlap_target_or_embargo():
    timestamps = pd.date_range("2020-01-01", periods=40, freq="D")
    try:
        build_window_records(
            _asset(),
            timestamps,
            fold="fold_2020",
            target_start="2020-01-01",
            target_end="2020-02-25",
            lookback=5,
            pred_len=3,
            sample_step=5,
            embargo_bars=3,
        )
    except ValueError as exc:
        assert "minimum is 6" in str(exc)
    else:
        raise AssertionError("overlapping sample_step should be rejected")


def test_summary_reports_market_groups_and_cluster_bootstrap():
    rows = [
        {"fold": "fold_2025", "symbol": "000001", "market": "A", "target_end": "2025-01-10", "last_close": 10, "pred_close": 11, "true_close": 12},
        {"fold": "fold_2025", "symbol": "000002", "market": "A", "target_end": "2025-01-10", "last_close": 10, "pred_close": 9, "true_close": 8},
        {"fold": "fold_2025", "symbol": "00001", "market": "HK", "target_end": "2025-01-20", "last_close": 10, "pred_close": 11, "true_close": 9},
        {"fold": "fold_2025", "symbol": "00002", "market": "HK", "target_end": "2025-01-20", "last_close": 10, "pred_close": 9, "true_close": 8},
    ]
    summary = summarize_prediction_rows(rows, bootstrap_replicates=50)

    assert summary["overall"]["n_samples"] == 4
    assert set(summary["by_market"]) == {"A", "HK"}
    assert summary["overall"]["top_k"] == 2
    assert "aer" in summary["overall"]
    assert "ir" in summary["overall"]
    assert summary["overall"]["direction_accuracy_ci95"]["cluster"] == "target_end"
    assert summary["by_symbol"]["000001"]["direction_accuracy_ci95"]["n_bootstrap"] == 0
    assert bootstrap_ci(pd.DataFrame(rows), n_bootstrap=10)["n_bootstrap"] == 10


def test_staged_sample_selection_is_balanced_and_deterministic():
    samples = []
    for market, count in (("A", 3), ("HK", 2)):
        for symbol_index in range(count):
            for window in range(8):
                samples.append(
                    {
                        "market": market,
                        "symbol": f"{market}{symbol_index:02d}",
                        "target_start": f"2025-{window + 1:02d}-01",
                        "input_start_row": window,
                        "target_start_row": window + 5,
                        "file": f"{market}_{symbol_index}.csv",
                    }
                )

    first = select_evaluation_samples(samples, mode="screen", seed=42)
    second = select_evaluation_samples(samples, mode="screen", seed=42)

    assert [_sample["file"] for _sample in first] == [_sample["file"] for _sample in second]
    assert len(first) == 25
    assert len({item["symbol"] for item in first if item["market"] == "A"}) == 3
    assert len({item["symbol"] for item in first if item["market"] == "HK"}) == 2
    assert all(sum(item["symbol"] == symbol for item in first) == 5 for symbol in {item["symbol"] for item in first})


def test_zero_bootstrap_replicates_disables_ci_work():
    frame = pd.DataFrame(
        [{"last_close": 10, "pred_close": 11, "true_close": 12, "target_end": "2025-01-01"}]
    )
    result = bootstrap_ci(frame, n_bootstrap=0)
    assert result["n_bootstrap"] == 0
    assert result["lower"] is None
    assert result["upper"] is None
