"""Build the fixed market/date sample fixture used by Kronos Confirm."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.rolling import (  # noqa: E402
    select_cross_sectional_samples,
    select_evaluation_samples,
    validate_prediction_samples,
)


def _sample_key(item: dict[str, object]) -> str:
    return ":".join(
        str(item.get(field, ""))
        for field in ("file", "input_start_row", "target_start_row", "target_end")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--fold", default="validation_2026_q1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dates-per-market", type=int, default=5)
    parser.add_argument("--a-symbols-per-date", type=int, default=80)
    parser.add_argument("--hk-symbols-per-date", type=int, default=40)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    pred_len = int(manifest["protocol"]["pred_len"])
    samples = select_cross_sectional_samples(
        manifest["samples"][args.fold],
        dates_per_market=args.dates_per_market,
        a_symbols_per_date=args.a_symbols_per_date,
        hk_symbols_per_date=args.hk_symbols_per_date,
        seed=args.seed,
    )
    if args.max_samples is not None:
        samples = select_evaluation_samples(
            samples,
            mode="final",
            seed=args.seed,
            max_samples=args.max_samples,
        )
    validate_prediction_samples(samples, pred_len=pred_len)
    sample_hash = hashlib.sha256(
        "\n".join(_sample_key(item) for item in samples).encode("utf-8")
    ).hexdigest()
    payload = {
        "version": 1,
        "manifest": str(args.manifest),
        "fold": args.fold,
        "pred_len": pred_len,
        "seed": args.seed,
        "selection": {
            "strategy": "market_date_cross_section",
            "dates_per_market": args.dates_per_market,
            "a_symbols_per_date": args.a_symbols_per_date,
            "hk_symbols_per_date": args.hk_symbols_per_date,
            "max_samples": args.max_samples,
            "n_samples": len(samples),
            "sample_hash": sample_hash,
        },
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, args.output)
    print(f"samples={len(samples)} hash={sample_hash}")
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
