"""Build the canonical A/HK rolling-origin evaluation manifest.

This command does not load a model and does not copy raw data.  It creates a
versioned JSON manifest containing the universe, temporal partitions, rolling
folds and leakage-safe prediction windows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.rolling import build_evaluation_manifest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT / "external" / "Kronos" / "finetune_csv" / "data_v2",
    )
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "output" / "evaluation_manifest.json")
    parser.add_argument("--history-start", default="2019-01-01")
    parser.add_argument("--validation-start", default="2025-01-01")
    parser.add_argument("--test-start", default="2026-01-01")
    parser.add_argument("--lookback", type=int, default=90)
    parser.add_argument("--pred-len", type=int, default=5)
    parser.add_argument("--sample-step", type=int, default=None)
    parser.add_argument("--embargo-bars", type=int, default=5)
    parser.add_argument("--a-limit", type=int, default=200)
    parser.add_argument("--hk-limit", type=int, default=100)
    args = parser.parse_args()

    manifest = build_evaluation_manifest(
        args.data_dir,
        history_start=args.history_start,
        validation_start=args.validation_start,
        test_start=args.test_start,
        lookback=args.lookback,
        pred_len=args.pred_len,
        sample_step=args.sample_step,
        embargo_bars=args.embargo_bars,
        a_limit=args.a_limit,
        hk_limit=args.hk_limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Manifest: {args.output}")
    print(f"Universe: {len(manifest['universe'])} assets")
    for fold in manifest["rolling_folds"]:
        print(
            f"{fold['id']}: role={fold['role']} samples={fold['sample_count']} "
            f"A={fold['market_counts']['A']} HK={fold['market_counts']['HK']} sealed={fold['sealed']}"
        )


if __name__ == "__main__":
    main()
