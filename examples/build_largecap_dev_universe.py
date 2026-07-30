"""Build a development-only large-cap A/H universe from the versioned v5 data.

The A-share side uses the current CSI 300 snapshot returned by AKShare. The
existing HK files are retained as a curated high-liquidity proxy until
point-in-time Hang Seng constituent snapshots are available. The output is
explicitly marked development_only and must not be used as strict OOS proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINETUNE_ROOT = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"


def _atomic_json(payload: dict, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{__import__('os').getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)


def _csi300_codes(index_code: str) -> tuple[str, str]:
    frame = ak.index_stock_cons_csindex(symbol=index_code)
    if frame.empty or frame.shape[1] < 5:
        raise RuntimeError("AKShare returned an empty or unexpected CSI constituent table")
    # AKShare's component code is the fifth column; column names can be
    # mangled by a non-UTF8 Windows console, so use the stable schema position.
    codes = {
        str(value).strip().split(".")[0].zfill(6)
        for value in frame.iloc[:, 4].tolist()
        if str(value).strip().split(".")[0].isdigit()
    }
    if len(codes) < 250:
        raise RuntimeError(f"CSI {index_code} snapshot is unexpectedly small: {len(codes)}")
    observed = str(frame.iloc[0, 0])
    return observed, ",".join(sorted(codes))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-code", default="000300")
    parser.add_argument("--source-dir", type=Path, default=FINETUNE_ROOT / "raw_v5_compact")
    parser.add_argument("--output-dir", type=Path, default=FINETUNE_ROOT / "raw_v6_largecap")
    args = parser.parse_args()

    source = args.source_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    observed_date, code_text = _csi300_codes(args.index_code)
    csi_codes = set(code_text.split(","))

    selected: list[dict] = []
    missing_a: list[str] = []
    for code in sorted(csi_codes):
        source_file = source / f"cn_{code}.csv"
        if not source_file.exists():
            missing_a.append(code)
            continue
        destination = output / source_file.name
        shutil.copy2(source_file, destination)
        selected.append(
            {
                "file": destination.name,
                "market": "A",
                "selection": "current_csi300_snapshot",
                "snapshot_date": observed_date,
                "point_in_time": False,
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            }
        )

    hk_files = sorted(source.glob("hk_*.csv"))
    for source_file in hk_files:
        destination = output / source_file.name
        shutil.copy2(source_file, destination)
        selected.append(
            {
                "file": destination.name,
                "market": "HK",
                "selection": "legacy_curated_high_liquidity_proxy",
                "snapshot_date": None,
                "point_in_time": False,
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            }
        )

    if not selected:
        raise RuntimeError("no large-cap development files were selected")

    manifest = {
        "dataset_version": "raw_v6_largecap_dev",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_dir": str(source),
        "output_dir": str(output),
        "development_only": True,
        "point_in_time_constituents": False,
        "strict_oos_eligible": False,
        "a_policy": {
            "index": f"CSI {args.index_code}",
            "snapshot_date": observed_date,
            "missing_files": missing_a,
        },
        "hk_policy": {
            "selection": "existing v5 curated high-liquidity proxy",
            "historical_membership_status": "not_available",
        },
        "files": selected,
    }
    _atomic_json(manifest, output / "universe_manifest.json")
    print(
        json.dumps(
            {
                "output": str(output),
                "files": len(selected),
                "A": sum(item["market"] == "A" for item in selected),
                "HK": sum(item["market"] == "HK" for item in selected),
                "missing_csi_files": missing_a,
                "development_only": True,
                "strict_oos_eligible": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
