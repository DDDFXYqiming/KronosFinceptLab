"""Build the fixed 2022-2026 compact evaluation manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation import build_compact_evaluation_manifest  # noqa: E402


def main() -> None:
    data_dir = (
        PROJECT_ROOT
        / "external"
        / "Kronos"
        / "finetune_csv"
        / "clean_v5_compact"
    )
    output = PROJECT_ROOT / "output" / "evaluation_manifest_compact_v5.json"
    manifest = build_compact_evaluation_manifest(data_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Manifest: {output}")
    print(f"Observed data end: {manifest['observed_data_end']}")
    for fold in manifest["rolling_folds"]:
        print(
            f"{fold['id']}: samples={fold['sample_count']} "
            f"A={fold['market_counts']['A']} HK={fold['market_counts']['HK']}"
        )


if __name__ == "__main__":
    main()

