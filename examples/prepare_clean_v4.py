"""Build the frozen clean_v4 A/H-share fine-tuning dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.data_prep import build_clean_dataset  # noqa: E402


def main() -> None:
    default_root = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=default_root / "data_v3")
    parser.add_argument("--output", type=Path, default=default_root / "clean_v4")
    args = parser.parse_args()
    manifest = build_clean_dataset(args.source, args.output)
    totals = {
        "files": manifest["file_count"],
        "A": sum(item["market"] == "A" for item in manifest["files"]),
        "HK": sum(item["market"] == "HK" for item in manifest["files"]),
        "input_rows": sum(item["cleaning"]["input_rows"] for item in manifest["files"]),
        "output_rows": sum(item["cleaning"]["output_rows"] for item in manifest["files"]),
        "jump_flags": sum(item["cleaning"]["price_jump_rows_flagged"] for item in manifest["files"]),
    }
    print(json.dumps(totals, ensure_ascii=False, indent=2))
    print(f"manifest={args.output.resolve() / 'manifest.json'}")


if __name__ == "__main__":
    main()
