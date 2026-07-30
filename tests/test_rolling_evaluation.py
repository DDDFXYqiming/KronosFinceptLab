from __future__ import annotations

import pandas as pd

from kronos_fincept.evaluation.rolling import (
    AssetMeta,
    bootstrap_ci,
    build_compact_evaluation_manifest,
    build_window_records,
    compare_candidate_to_baseline,
    composite_score,
    select_screen_candidate,
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


def test_compact_manifest_uses_q1_validation_and_recent_diagnostic_period(tmp_path):
    timestamps = pd.bdate_range("2021-08-01", "2026-07-31")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "volume": 100.0,
            "amount": 1000.0,
        }
    )
    frame.to_csv(tmp_path / "cn_000001.csv", index=False)
    frame.to_csv(tmp_path / "hk_00005.csv", index=False)

    manifest = build_compact_evaluation_manifest(
        tmp_path,
        a_limit=None,
        hk_limit=None,
    )

    assert [partition["name"] for partition in manifest["partitions"]] == [
        "train",
        "validation",
        "diagnostic",
        "strict_future_oos",
    ]
    assert manifest["partitions"][0]["start"] == "2022-01-01"
    assert manifest["partitions"][0]["end"] == "2025-12-31"
    assert manifest["partitions"][1]["start"] == "2026-01-01"
    assert manifest["partitions"][1]["end"] == "2026-03-31"
    assert manifest["partitions"][2]["start"] == "2026-04-01"
    assert manifest["partitions"][2]["end"] == "2026-07-31"
    assert manifest["partitions"][3]["start"] == "2026-08-01"
    assert set(manifest["samples"]) == {
        "validation_2026_q1",
        "diagnostic_2026_04_07",
    }
    assert all(
        "2026-01-01" <= row["target_start"] <= row["target_end"] <= "2026-03-31"
        for row in manifest["samples"]["validation_2026_q1"]
    )
    assert all(
        "2026-04-01" <= row["target_start"] <= row["target_end"] <= "2026-07-31"
        for row in manifest["samples"]["diagnostic_2026_04_07"]
    )


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


def test_summary_uses_market_date_cross_sectional_rankic_instead_of_pooled_rankic():
    rows = []
    groups = [
        ("A", "2025-01-10", [0.10, 0.20, 0.30], [-0.30, -0.20, -0.10]),
        ("A", "2025-02-10", [-0.30, -0.20, -0.10], [0.10, 0.20, 0.30]),
    ]
    for market, target_end, actual_returns, predicted_returns in groups:
        for index, (actual_return, predicted_return) in enumerate(zip(actual_returns, predicted_returns)):
            rows.append(
                {
                    "fold": "fold_2025",
                    "symbol": f"{target_end}-{index}",
                    "market": market,
                    "target_end": target_end,
                    "last_close": 100.0,
                    "pred_close": 100.0 * (1.0 + predicted_return),
                    "true_close": 100.0 * (1.0 + actual_return),
                }
            )

    summary = summarize_prediction_rows(rows, bootstrap_replicates=0)

    assert summary["overall"]["rankic"] < 0
    assert summary["overall"]["mean_daily_rankic"] == 1.0
    assert summary["overall"]["rankic_periods"] == 2


def test_composite_score_uses_fixed_direction_and_rankic_weights():
    assert composite_score(0.60, 0.20) == 0.60


def test_candidate_promotion_requires_both_metrics_and_positive_paired_ci():
    candidate_rows = []
    baseline_rows = []
    for month in range(1, 7):
        target_end = f"2025-{month:02d}-20"
        for index, actual_return in enumerate((-0.03, -0.01, 0.01, 0.03)):
            common = {
                "fold": "fold_2025",
                "symbol": f"{index:06d}",
                "market": "A",
                "target_end": target_end,
                "last_close": 100.0,
                "true_close": 100.0 * (1.0 + actual_return),
            }
            candidate_rows.append(
                {**common, "pred_close": 100.0 * (1.0 + actual_return)}
            )
            baseline_rows.append(
                {**common, "pred_close": 100.0 * (1.0 - actual_return)}
            )

    comparison = compare_candidate_to_baseline(
        candidate_rows,
        baseline_rows,
        n_bootstrap=100,
        seed=42,
    )

    assert comparison["candidate"]["direction_accuracy"] > comparison["baseline"]["direction_accuracy"]
    assert comparison["candidate"]["mean_daily_rankic"] > comparison["baseline"]["mean_daily_rankic"]
    assert comparison["score_delta_ci95"]["lower"] > 0
    assert comparison["promoted"] is True


def test_screen_selection_retains_baseline_when_no_candidate_clears_both_metrics():
    baseline = {"direction_accuracy": 0.55, "mean_daily_rankic": 0.10}
    candidates = {
        "direction_only": {"direction_accuracy": 0.60, "mean_daily_rankic": 0.09},
        "rank_only": {"direction_accuracy": 0.54, "mean_daily_rankic": 0.20},
    }

    decision = select_screen_candidate(candidates, baseline)

    assert decision["selected"] == "pretrained_baseline"
    assert decision["decision"] == "retain_pretrained_baseline"
