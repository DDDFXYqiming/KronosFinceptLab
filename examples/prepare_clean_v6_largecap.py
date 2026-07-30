"""Prepare the development-only clean_v6_largecap training dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.data_prep import build_clean_dataset  # noqa: E402


def main() -> None:
    root = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
    source = root / "raw_v6_largecap"
    output = root / "clean_v6_largecap"
    universe_manifest = json.loads((source / "universe_manifest.json").read_text(encoding="utf-8"))
    if not universe_manifest.get("development_only"):
        raise RuntimeError("raw_v6_largecap must be explicitly marked development_only")
    manifest = build_clean_dataset(
        source,
        output,
        dataset_version="clean_v6_largecap_dev",
        train_start="2022-01-01",
        train_end="2025-12-31",
        validation_start="2026-01-01",
        validation_end="2026-03-31",
        diagnostic_start="2026-04-01",
        diagnostic_end="2026-07-31",
        strict_oos_start="2026-08-01",
        source_policy={
            "development_only": True,
            "point_in_time_constituents": False,
            "A": {"selection": "current CSI 300 snapshot", "source_manifest": "universe_manifest.json"},
            "HK": {"selection": "legacy curated high-liquidity proxy", "source_manifest": "universe_manifest.json"},
        },
    )
    totals = {
        key: sum(item["partitions"][key] for item in manifest["files"])
        for key in ("pretrain_history_rows", "train_rows", "validation_rows", "diagnostic_rows", "future_oos_rows")
    }
    print(json.dumps({"output": str(output), "files": manifest["file_count"], "partitions": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
