"""Refresh recent A/H bars into an isolated raw_v5_compact snapshot."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv  # noqa: E402
from kronos_fincept.evaluation.data_prep import (  # noqa: E402
    REQUIRED_COLUMNS,
    merge_refreshed_rows,
)
from kronos_fincept.financial import GlobalMarketSource  # noqa: E402


def _atomic_csv(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, destination)


def _atomic_json(payload: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def _fetch(path: Path, start: str, end: str) -> tuple[pd.DataFrame, str]:
    symbol = path.stem[3:]
    if path.name.startswith("cn_"):
        rows = fetch_a_stock_ohlcv(
            symbol,
            start.replace("-", ""),
            end.replace("-", ""),
            "qfq",
        )
        source = "project_multi_source_qfq"
    else:
        rows = GlobalMarketSource().fetch_data(
            symbol,
            start.replace("-", ""),
            end.replace("-", ""),
            market="hk",
        )
        source = "yfinance_auto_adjust_repair"
    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS), source
    frame = pd.DataFrame(rows)
    return frame.loc[:, REQUIRED_COLUMNS], source


def _scale_changed(existing: pd.DataFrame, refreshed: pd.DataFrame) -> bool:
    if refreshed.empty:
        return False
    comparison_columns = ("timestamp", "close", "volume", "amount")
    left = existing.loc[:, comparison_columns].copy()
    right = refreshed.loc[:, comparison_columns].copy()
    left["timestamp"] = pd.to_datetime(left["timestamp"], utc=True).dt.strftime("%Y-%m-%d")
    right["timestamp"] = pd.to_datetime(right["timestamp"], utc=True).dt.strftime("%Y-%m-%d")
    overlap = left.merge(right, on="timestamp", suffixes=("_old", "_new"))
    if len(overlap) < 3:
        return False
    thresholds = {"close": 0.005, "volume": 0.20, "amount": 0.20}
    for column, tolerance in thresholds.items():
        old = pd.to_numeric(overlap[f"{column}_old"], errors="coerce")
        new = pd.to_numeric(overlap[f"{column}_new"], errors="coerce")
        valid = (old > 0) & (new > 0)
        if int(valid.sum()) < 3:
            continue
        median_ratio = float((new.loc[valid] / old.loc[valid]).median())
        if abs(median_ratio - 1.0) > tolerance:
            return True
    return False


def _refresh_one(
    path: Path,
    destination: Path,
    *,
    refresh_start: str,
    full_start: str,
    end: str,
    resume: bool,
) -> dict[str, Any]:
    if resume and destination.exists():
        existing_output = pd.read_csv(destination)
        return {
            "file": path.name,
            "market": "A" if path.name.startswith("cn_") else "HK",
            "provider": "preserved_from_previous_refresh",
            "status": "resumed",
            "full_refresh": False,
            "previous_end": str(existing_output["timestamp"].iloc[-1]),
            "current_end": str(existing_output["timestamp"].iloc[-1]),
            "fetched_rows": 0,
            "output_rows": int(len(existing_output)),
        }
    existing = pd.read_csv(path)
    refreshed, provider = _fetch(path, refresh_start, end)
    full_refresh = _scale_changed(existing, refreshed)
    if full_refresh:
        refreshed, provider = _fetch(path, full_start, end)
    merged = merge_refreshed_rows(existing, refreshed)
    _atomic_csv(merged, destination)
    return {
        "file": path.name,
        "market": "A" if path.name.startswith("cn_") else "HK",
        "provider": provider,
        "status": "refreshed" if not refreshed.empty else "no_new_rows",
        "full_refresh": full_refresh,
        "previous_end": str(existing["timestamp"].iloc[-1]),
        "current_end": str(merged["timestamp"].iloc[-1]),
        "fetched_rows": int(len(refreshed)),
        "output_rows": int(len(merged)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-start", default="2026-06-01")
    parser.add_argument("--full-start", default="2021-08-01")
    parser.add_argument("--end", default="2026-07-30")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--market", choices=("all", "A", "HK"), default="all")
    args = parser.parse_args()
    if args.workers <= 0:
        parser.error("--workers must be positive")

    source = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv" / "data_v3"
    output = (
        PROJECT_ROOT / "external" / "Kronos" / "finetune_csv" / "raw_v5_compact"
    )
    report_path = output / (
        "refresh_report.json"
        if args.market == "all"
        else f"refresh_report_{args.market.lower()}.json"
    )
    files = sorted(
        path
        for path in source.glob("*.csv")
        if re.fullmatch(r"(?:cn|hk)_\d+\.csv", path.name)
        and (
            args.market == "all"
            or (args.market == "A" and path.name.startswith("cn_"))
            or (args.market == "HK" and path.name.startswith("hk_"))
        )
    )
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_dir": str(source),
        "output_dir": str(output),
        "refresh_start": args.refresh_start,
        "full_start": args.full_start,
        "requested_end": args.end,
        "files": [],
        "errors": [],
    }
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                _refresh_one,
                path,
                output / path.name,
                refresh_start=args.refresh_start,
                full_start=args.full_start,
                end=args.end,
                resume=args.resume,
            ): path
            for path in files
        }
        completed = 0
        for future in as_completed(futures):
            path = futures[future]
            try:
                report["files"].append(future.result())
            except Exception as exc:
                existing = pd.read_csv(path)
                _atomic_csv(existing.loc[:, REQUIRED_COLUMNS], output / path.name)
                report["errors"].append(
                    {"file": path.name, "error": f"{type(exc).__name__}: {exc}"}
                )
            completed += 1
            if completed % 20 == 0 or completed == len(files):
                report["files"].sort(key=lambda item: item["file"])
                _atomic_json(report, report_path)
                print(
                    f"[refresh] {completed}/{len(files)} "
                    f"errors={len(report['errors'])}",
                    flush=True,
                )

    report["files"].sort(key=lambda item: item["file"])
    _atomic_json(report, report_path)
    print(f"Refresh report: {report_path}")


if __name__ == "__main__":
    main()
