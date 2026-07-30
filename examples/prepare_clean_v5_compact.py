"""Build the compact, leakage-audited A/H-share clean_v5 dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.data_prep import build_clean_dataset  # noqa: E402


def main() -> None:
    finetune_root = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
    refreshed = finetune_root / "raw_v5_compact"
    source = refreshed if (refreshed / "refresh_report.json").exists() else finetune_root / "data_v3"
    output = (
        finetune_root / "clean_v5_compact"
    )
    manifest = build_clean_dataset(
        source,
        output,
        dataset_version="clean_v5_compact",
        train_start="2022-01-01",
        train_end="2025-12-31",
        validation_start="2026-01-01",
        validation_end="2026-03-31",
        diagnostic_start="2026-04-01",
        diagnostic_end="2026-07-31",
        strict_oos_start="2026-08-01",
        source_policy={
            "A": {
                "provider": "project_multi_source",
                "priority": "BaoStock -> EastMoney -> AkShare -> TDX -> Tushare -> Yahoo -> Stooq",
                "adjustment": "qfq",
                "exact_historical_fallback": "not_persisted_in_data_v3",
            },
            "HK": {
                "provider": "yfinance",
                "adjustment": "auto_adjust=True",
                "repair": True,
                "exact_historical_version": "not_persisted_in_data_v3",
            },
        },
    )
    totals = {
        key: sum(item["partitions"][key] for item in manifest["files"])
        for key in (
            "pretrain_history_rows",
            "train_rows",
            "validation_rows",
            "diagnostic_rows",
            "future_oos_rows",
        )
    }
    print(
        json.dumps(
            {
                "output": str(output),
                "files": manifest["file_count"],
                "A": sum(item["market"] == "A" for item in manifest["files"]),
                "HK": sum(item["market"] == "HK" for item in manifest["files"]),
                "partitions": totals,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
