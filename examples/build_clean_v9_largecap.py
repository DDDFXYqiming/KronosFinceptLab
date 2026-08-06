"""Build the clean_v9_largecap PIT dataset on top of the v7 builder.

v9 adds three production-governance sidecars that clean_v8 explicitly deferred:

1. independent corporate-action events (BaoStock dividend records: cash dividend,
   share dividend / rights issue, ex-dividend date) -- prices remain qfq, so the
   events are recorded for future factor reconstruction rather than used to
   re-derive an independent adjustment-factor series;
2. suspend / limit-up-down / untradeable state (already captured by the v7 fetch
   as ``security_events.csv``; kept and validated);
3. delisting confirmation (BaoStock ``query_stock_basic`` ``outDate``), written to
   ``delistings.csv`` so the last tradable day can be confirmed per symbol.

The training/validation splits match clean_v8 (train to 2026-04-30, validation
2026-05-01..07-31, diagnostic from 2026-08-01) so v9 is directly comparable.

Usage (from the repository root):

    .\\.venv311\\Scripts\\python.exe examples\\build_clean_v9_largecap.py --stage all

Stages: ``universe`` -> ``events`` -> ``fetch`` -> ``clean`` -> ``manifest``.
``--resume`` / ``--refresh`` are forwarded to the v7 fetch stage.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V7_BUILDER = PROJECT_ROOT / "examples" / "build_clean_v7_largecap.py"
FINETUNE_ROOT = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"

RAW_DIR = FINETUNE_ROOT / "raw_v9_largecap"
CLEAN_DIR = FINETUNE_ROOT / "clean_v9_largecap"
EVALUATION_MANIFEST = PROJECT_ROOT / "output" / "evaluation_manifest_largecap_v9_recent.json"
DATASET_VERSION = "clean_v9_largecap"
SPLITS = {
    "train_start": "2022-01-01",
    "train_end": "2026-04-30",
    "validation_start": "2026-05-01",
    "validation_end": "2026-07-31",
    "diagnostic_start": "2026-08-01",
    "diagnostic_end": "2026-08-06",
    "strict_oos_start": "2026-08-01",
}


def _load_v7() -> Any:
    spec = importlib.util.spec_from_file_location("v7_builder", V7_BUILDER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.RAW_DIR = RAW_DIR
    module.CLEAN_DIR = CLEAN_DIR
    module.EVALUATION_MANIFEST = EVALUATION_MANIFEST
    module.DATASET_VERSION = DATASET_VERSION
    module.SPLITS.update(SPLITS)
    return module


def _atomic_json(payload: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{__import__('os').getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    __import__("os").replace(temporary, destination)


def _atomic_csv(frame: pd.DataFrame, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{__import__('os').getpid()}.tmp")
    frame.to_csv(temporary, index=False)
    digest = __import__("hashlib").sha256(temporary.read_bytes()).hexdigest()
    __import__("os").replace(temporary, destination)
    return digest


def build_events(*, start: str, end: str, delistings: bool = True, dividends: bool = True) -> dict[str, Any]:
    """Fetch delisting confirmation and corporate-action sidecars for A symbols."""
    import baostock as bs

    membership = pd.read_csv(RAW_DIR / "metadata" / "universe_membership.csv", dtype={"symbol": str})
    a_symbols = sorted(membership.loc[membership["market"] == "A", "symbol"].str.zfill(6).unique())
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "start": start,
        "end": end,
        "delistings": [],
        "dividends": [],
        "errors": [],
    }

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
    try:
        if delistings:
            result = bs.query_stock_basic()
            rows: list[dict[str, Any]] = []
            while result.error_code == "0" and result.next():
                row = dict(zip(result.fields, result.get_row_data()))
                rows.append(row)
            if result.error_code != "0":
                raise RuntimeError(f"query_stock_basic failed: {result.error_msg}")
            basic = pd.DataFrame(rows)
            basic = basic[basic["code"].str.endswith((".sh", ".sz"))]
            basic["symbol"] = basic["code"].str.split(".").str[1]
            basic["market"] = basic["code"].str.split(".").str[0].map({"sh": "A", "sz": "A"})
            basic = basic[(basic["symbol"].isin(a_symbols)) & (basic["type"] == "1")].copy()
            active_out = basic[basic["outDate"].fillna("").astype(str).str.strip() != ""]
            delisted = active_out[active_out["outDate"].astype(str) <= end].copy()
            delisted = delisted[
                ["symbol", "code_name", "ipoDate", "outDate", "type", "status"]
            ].rename(columns={"code_name": "name", "ipoDate": "ipo_date", "outDate": "delist_date"})
            delisted = delisted.sort_values("symbol")
            digest = _atomic_csv(delisted, RAW_DIR / "metadata" / "delistings.csv")
            report["delistings"] = {
                "rows": len(delisted),
                "sha256": digest,
            }

        if dividends:
            dividend_rows: list[dict[str, Any]] = []
            for index, symbol in enumerate(a_symbols, start=1):
                code = f"sh.{symbol}" if symbol.startswith(("5", "6", "9")) else f"sz.{symbol}"
                for year in range(2018, 2027):
                    try:
                        result = bs.query_dividend_data(code=code, year=str(year), yearType="report")
                        if result.error_code != "0":
                            raise RuntimeError(f"{symbol}: {result.error_msg}")
                        while result.next():
                            values = dict(zip(result.fields, result.get_row_data()))
                            dividend_date = (
                                values.get("dividOperateDate")
                                or values.get("dividPayDate")
                                or values.get("dividRegistDate")
                            )
                            if dividend_date and str(dividend_date) <= end:
                                dividend_rows.append(
                                    {
                                        "symbol": symbol,
                                        "market": "A",
                                        "date": str(dividend_date),
                                        "event_type": "dividend",
                                        "cash_dividend_before_tax": values.get("dividCashPsBeforeTax"),
                                        "cash_dividend_after_tax": values.get("dividCashPsAfterTax"),
                                        "share_dividend_ratio": values.get("dividStocksPs"),
                                        "dividend_description": values.get("dividCashStock"),
                                        "dividend_year": str(dividend_date)[:4],
                                        "source": "baostock_query_dividend_data",
                                    }
                                )
                    except Exception as exc:
                        report["errors"].append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
                        break
                if index % 50 == 0 or index == len(a_symbols):
                    _atomic_json(report, RAW_DIR / "metadata" / "v9_events_report.json")
                    print(f"[v9-events] dividends {index}/{len(a_symbols)} errors={len(report['errors'])}", flush=True)
            dividend_frame = pd.DataFrame(dividend_rows)
            if not dividend_frame.empty:
                dividend_frame = dividend_frame.sort_values(["symbol", "date"])
                digest = _atomic_csv(dividend_frame, RAW_DIR / "metadata" / "dividends.csv")
            else:
                dividend_frame.to_csv(RAW_DIR / "metadata" / "dividends.csv", index=False)
                digest = __import__("hashlib").sha256(
                    (RAW_DIR / "metadata" / "dividends.csv").read_bytes()
                ).hexdigest()
            report["dividends"] = {
                "rows": len(dividend_frame),
                "sha256": digest,
            }
    finally:
        bs.logout()

    _atomic_json(report, RAW_DIR / "metadata" / "v9_events_report.json")
    return report


def clean_dataset(*, start: str, end: str, v7: Any) -> dict[str, Any]:
    manifest = v7.clean_dataset(start=start, end=end)
    clean_metadata = CLEAN_DIR / "metadata"
    clean_metadata.mkdir(parents=True, exist_ok=True)
    sidecars = {
        "delistings_file": RAW_DIR / "metadata" / "delistings.csv",
        "dividends_file": RAW_DIR / "metadata" / "dividends.csv",
    }
    for key, source in sidecars.items():
        if source.exists():
            import shutil

            shutil.copy2(source, clean_metadata / source.name)
            manifest[key] = str((clean_metadata / source.name).resolve())
    manifest["dataset_version"] = DATASET_VERSION
    manifest["point_in_time_constituents"] = True
    manifest["development_only"] = True
    manifest["strict_oos_eligible"] = False
    _atomic_json(manifest, CLEAN_DIR / "manifest.json")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("universe", "events", "fetch", "clean", "manifest", "all"), default="all")
    parser.add_argument("--start", default="2021-08-01")
    parser.add_argument("--end", default="2026-08-06")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--hk-workers", type=int, default=4)
    parser.add_argument("--no-delistings", action="store_true")
    parser.add_argument("--no-dividends", action="store_true")
    args = parser.parse_args()

    v7 = _load_v7()
    stages = ("universe", "events", "fetch", "clean", "manifest") if args.stage == "all" else (args.stage,)
    for stage in stages:
        if stage == "universe":
            result = v7.build_universe(start=args.start, end=args.end)
        elif stage == "events":
            result = build_events(
                start=args.start,
                end=args.end,
                delistings=not args.no_delistings,
                dividends=not args.no_dividends,
            )
        elif stage == "fetch":
            result = v7.fetch_market_data(
                start=args.start,
                end=args.end,
                resume=args.resume,
                hk_workers=args.hk_workers,
                refresh=args.refresh,
            )
        elif stage == "clean":
            result = clean_dataset(start=args.start, end=args.end, v7=v7)
        else:
            result = v7.build_evaluation_manifest()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:8000])


if __name__ == "__main__":
    main()
