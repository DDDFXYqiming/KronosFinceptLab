"""Build the evaluation manifest for the development-only large-cap dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation import build_compact_evaluation_manifest  # noqa: E402


def main() -> None:
    root = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
    data_dir = root / "clean_v6_largecap"
    universe = json.loads((root / "raw_v6_largecap" / "universe_manifest.json").read_text(encoding="utf-8"))
    if not universe.get("development_only"):
        raise RuntimeError("large-cap evaluation requires an explicit development_only universe")
    manifest = build_compact_evaluation_manifest(data_dir, a_limit=200, hk_limit=100)
    manifest["dataset_version"] = "clean_v6_largecap_dev"
    manifest["development_only"] = True
    manifest["strict_oos_eligible"] = False
    manifest["universe_source_manifest"] = str((root / "raw_v6_largecap" / "universe_manifest.json").resolve())
    output = PROJECT_ROOT / "output" / "evaluation_manifest_largecap_v6_dev.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    print(f"Manifest: {output}")
    print(f"Observed data end: {manifest['observed_data_end']}")
    print(f"Development only: {manifest['development_only']}")
    for fold in manifest["rolling_folds"]:
        print(
            f"{fold['id']}: samples={fold['sample_count']} "
            f"A={fold['market_counts']['A']} HK={fold['market_counts']['HK']}"
        )


if __name__ == "__main__":
    main()
