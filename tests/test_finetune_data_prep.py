from __future__ import annotations

import json

import pandas as pd

from kronos_fincept.evaluation.data_prep import (
    build_clean_dataset,
    clean_price_frame,
    merge_refreshed_rows,
)


def _row(timestamp: str, close: float, **overrides):
    row = {
        "timestamp": timestamp,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 100,
        "amount": 1000,
    }
    row.update(overrides)
    return row


def test_clean_price_frame_removes_invalid_rows_but_keeps_flagged_price_jumps():
    frame = pd.DataFrame(
        [
            _row("2024-01-01", 10),
            _row("2024-01-01", 10),
            _row("2024-01-02", 13),
            _row("2024-01-03", 12, high=11),
            _row("2024-01-04", 12, volume=-1),
        ]
    )

    cleaned, report = clean_price_frame(frame)

    assert list(cleaned["timestamp"]) == ["2024-01-01", "2024-01-02"]
    assert report["duplicate_rows_removed"] == 1
    assert report["invalid_ohlc_rows_removed"] == 1
    assert report["negative_volume_rows_removed"] == 1
    assert report["price_jump_rows_flagged"] == 1


def test_refreshed_rows_replace_overlap_and_keep_older_history():
    existing = pd.DataFrame(
        [
            _row("2026-06-01", 10),
            _row("2026-06-02", 11),
        ]
    )
    refreshed = pd.DataFrame(
        [
            _row("2026-06-02T00:00:00+08:00", 12),
            _row("2026-06-03T00:00:00+08:00", 13),
        ]
    )

    merged = merge_refreshed_rows(existing, refreshed)

    assert list(merged["timestamp"]) == [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
    ]
    assert list(merged["close"]) == [10, 12, 13]


def test_build_clean_dataset_writes_calendar_partitions_and_manifest(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "clean_v5_compact"
    source.mkdir()
    pd.DataFrame(
        [
            _row("2021-12-31", 9),
            _row("2022-01-03", 10),
            _row("2025-12-31", 11),
            _row("2026-01-02", 12),
            _row("2026-03-31", 13),
            _row("2026-04-01", 14),
            _row("2026-07-31", 15),
            _row("2026-08-03", 16),
        ]
    ).to_csv(source / "cn_000001.csv", index=False)
    pd.DataFrame({"code": ["000001"]}).to_csv(source / "a_share_stocks.csv", index=False)

    source_policy = {
        "A": {"provider": "project_multi_source", "adjustment": "qfq"},
        "HK": {"provider": "yfinance", "adjustment": "auto_adjust"},
    }
    manifest = build_clean_dataset(source, output, source_policy=source_policy)

    written = pd.read_csv(output / "cn_000001.csv")
    disk_manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert len(written) == 8
    assert manifest == disk_manifest
    assert disk_manifest["files"][0]["partitions"] == {
        "pretrain_history_rows": 1,
        "train_rows": 2,
        "validation_rows": 2,
        "diagnostic_rows": 2,
        "future_oos_rows": 1,
    }
    assert disk_manifest["dataset_version"] == "clean_v5_compact"
    assert disk_manifest["source_policy"] == source_policy
    assert disk_manifest["cutoffs"] == {
        "train_start": "2022-01-01",
        "train_end": "2025-12-31",
        "validation_start": "2026-01-01",
        "validation_end": "2026-03-31",
        "diagnostic_start": "2026-04-01",
        "diagnostic_end": "2026-07-31",
        "strict_oos_start": "2026-08-01",
    }
    assert not (output / "a_share_stocks.csv").exists()
