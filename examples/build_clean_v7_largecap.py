"""Build the point-in-time clean_v7 A/H large-cap dataset.

The script is intentionally a small staged pipeline so long network fetches can
resume without overwriting clean_v6 or any model checkpoint.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.data_prep import (  # noqa: E402
    REQUIRED_COLUMNS,
    build_clean_dataset,
)
from kronos_fincept.evaluation.pit_universe import (  # noqa: E402
    fetch_csi300_snapshots,
    fetch_hang_seng_snapshots,
    intervals_to_frame,
    snapshots_to_intervals,
)
from kronos_fincept.evaluation.rolling import (  # noqa: E402
    build_compact_evaluation_manifest,
)


FINETUNE_ROOT = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
RAW_DIR = FINETUNE_ROOT / "raw_v7_largecap"
CLEAN_DIR = FINETUNE_ROOT / "clean_v7_largecap"
MEMBERSHIP_PATH = RAW_DIR / "metadata" / "universe_membership.csv"
EVENT_DIR = RAW_DIR / "metadata" / "events"
ACQUISITION_REPORT = RAW_DIR / "acquisition_report.json"
EVALUATION_MANIFEST = PROJECT_ROOT / "output" / "evaluation_manifest_largecap_v7_pit.json"
DATASET_VERSION = "clean_v7_largecap_pit"
SPLITS = {
    "train_start": "2022-01-01",
    "train_end": "2025-12-31",
    "validation_start": "2026-01-01",
    "validation_end": "2026-03-31",
    "diagnostic_start": "2026-04-01",
    "diagnostic_end": "2026-07-31",
    "strict_oos_start": "2026-08-01",
}


def _atomic_json(payload: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, destination)


def _atomic_csv(frame: pd.DataFrame, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    os.replace(temporary, destination)
    return digest


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass


def build_universe(*, start: str, end: str) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    a_snapshots = fetch_csi300_snapshots(start_date=start, end_date=end)
    hk_snapshots = fetch_hang_seng_snapshots(start_date="2021-01-01", end_date=end)

    intervals = snapshots_to_intervals(
        a_snapshots,
        market="A",
        index_name="CSI300",
        end_date=end,
    )
    for index_name in ("HSI", "HSCEI", "HSTECH"):
        intervals.extend(
            snapshots_to_intervals(
                hk_snapshots[index_name],
                market="HK",
                index_name=index_name,
                end_date=end,
            )
        )
    membership = intervals_to_frame(intervals)
    membership.sort_values(["market", "symbol", "index_name", "member_from"], inplace=True)
    _atomic_csv(membership, MEMBERSHIP_PATH)

    a_symbols = sorted(membership.loc[membership["market"] == "A", "symbol"].unique())
    hk_symbols = sorted(membership.loc[membership["market"] == "HK", "symbol"].unique())
    manifest = {
        "dataset_version": "raw_v7_largecap_pit",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "development_only": True,
        "point_in_time_constituents": True,
        "strict_oos_eligible": False,
        "history_start": start,
        "observed_end": end,
        "membership_file": str(MEMBERSHIP_PATH.resolve()),
        "A": {
            "indices": ["CSI300"],
            "source": "BaoStock historical query_hs300_stocks",
            "symbols": len(a_symbols),
            "snapshots": len(a_snapshots),
        },
        "HK": {
            "indices": ["HSI", "HSCEI", "HSTECH"],
            "source": "Hang Seng Indexes official quarterly review PDFs",
            "symbols": len(hk_symbols),
            "snapshots": {name: len(hk_snapshots[name]) for name in hk_snapshots},
        },
    }
    _atomic_json(manifest, RAW_DIR / "universe_manifest.json")
    return manifest


def _possible_a_limit(symbol: str, is_st: bool, pct_chg: float | None) -> bool:
    if pct_chg is None:
        return False
    threshold = 4.5 if is_st else 19.5 if symbol.startswith(("300", "301", "688", "689")) else 9.5
    return abs(pct_chg) >= threshold


def _fetch_a_symbol(
    bs: Any,
    *,
    symbol: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    code = f"sh.{symbol}" if symbol.startswith(("5", "6", "9")) else f"sz.{symbol}"
    fields = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST"
    rows: list[list[str]] = []
    for attempt in range(2):
        result = bs.query_history_k_data_plus(
            code=code,
            fields=fields,
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag="2",
        )
        rows.clear()
        while result.error_code == "0" and result.next():
            rows.append(result.get_row_data())
        if result.error_code == "0":
            break
        if attempt == 0:
            bs.login()
    if result.error_code != "0":
        raise RuntimeError(f"BaoStock {symbol}: {result.error_msg}")

    prices: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for values in rows:
        date = values[0]
        tradable = values[11] == "1"
        is_st = values[13] == "1"
        pct_chg = float(values[12]) if values[12] not in {"", None} else None
        possible_limit = _possible_a_limit(symbol, is_st, pct_chg)
        event_type = (
            "suspended"
            if not tradable
            else "possible_limit"
            if possible_limit
            else "normal"
        )
        events.append(
            {
                "symbol": symbol,
                "market": "A",
                "date": date,
                "listed": True,
                "tradable": tradable,
                "is_st": is_st,
                "possible_limit": possible_limit,
                "adj_factor": None,
                "event_type": event_type,
                "source": "baostock_qfq",
            }
        )
        if not tradable or any(values[index] in {"", None} for index in (2, 3, 4, 5)):
            continue
        prices.append(
            {
                "timestamp": date,
                "open": float(values[2]),
                "high": float(values[3]),
                "low": float(values[4]),
                "close": float(values[5]),
                "volume": float(values[7] or 0),
                "amount": float(values[8] or 0),
            }
        )

    price_frame = pd.DataFrame(prices, columns=REQUIRED_COLUMNS)
    event_frame = pd.DataFrame(events)
    price_path = RAW_DIR / f"cn_{symbol}.csv"
    event_path = EVENT_DIR / f"cn_{symbol}.csv"
    digest = _atomic_csv(price_frame, price_path)
    _atomic_csv(event_frame, event_path)
    return {
        "file": price_path.name,
        "market": "A",
        "provider": "baostock_qfq",
        "adjustment_event_quality": "qfq_prices_without_separate_factor_series",
        "rows": len(price_frame),
        "events": len(event_frame),
        "sha256": digest,
        "status": "fetched",
    }


def _fetch_hk_symbol(*, symbol: str, start: str, end: str, old_tail: dict[str, float] | None = None) -> dict[str, Any]:
    import akshare as ak

    frame = ak.stock_hk_daily(symbol=symbol, adjust="qfq")
    if frame is None or frame.empty:
        raise RuntimeError(f"Sina returned no data for {symbol}")
    frame = frame.reset_index(drop=True)
    timestamps = pd.to_datetime(frame["date"], errors="raise")
    selected = (timestamps >= pd.Timestamp(start)) & (timestamps <= pd.Timestamp(end))
    frame = frame.loc[selected].reset_index(drop=True)
    timestamps = timestamps.loc[selected].reset_index(drop=True)
    prices = pd.DataFrame(
        {
            "timestamp": timestamps.dt.strftime("%Y-%m-%d"),
            "open": pd.to_numeric(frame["open"], errors="coerce"),
            "high": pd.to_numeric(frame["high"], errors="coerce"),
            "low": pd.to_numeric(frame["low"], errors="coerce"),
            "close": pd.to_numeric(frame["close"], errors="coerce"),
            "volume": pd.to_numeric(frame["volume"], errors="coerce").fillna(0),
        }
    )
    prices["amount"] = pd.to_numeric(frame["amount"], errors="coerce").fillna(
        prices["close"] * prices["volume"]
    )
    prices = prices.loc[:, REQUIRED_COLUMNS]
    valid = prices[["open", "high", "low", "close"]].notna().all(axis=1)
    prices = prices.loc[valid].reset_index(drop=True)

    events = pd.DataFrame(
        {
            "symbol": symbol,
            "market": "HK",
            "date": timestamps.dt.strftime("%Y-%m-%d"),
            "listed": True,
            "tradable": True,
            "is_st": False,
            "possible_limit": False,
            "adj_factor": None,
            "event_type": "normal",
            "source": "akshare_sina_qfq",
        }
    )
    price_path = RAW_DIR / f"hk_{symbol}.csv"
    event_path = EVENT_DIR / f"hk_{symbol}.csv"
    digest = _atomic_csv(prices, price_path)
    _atomic_csv(events, event_path)
    entry = {
        "file": price_path.name,
        "market": "HK",
        "provider": "akshare_sina_qfq",
        "amount_quality": "provider_reported_hkd",
        "adjustment_event_quality": "qfq_prices_without_separate_factor_series",
        "rows": len(prices),
        "events": len(events),
        "sha256": digest,
        "status": "fetched",
    }
    if old_tail:
        seam_error = _verify_continuity(price_path, old_tail, symbol)
        if seam_error is not None:
            entry["status"] = "seam_error"
            entry["seam_error"] = seam_error
        else:
            entry["status"] = "refreshed"
    return entry


def _tail_close_snapshot(path: Path, rows: int = 3) -> dict[str, float]:
    """Snapshot the last rows' closes so refreshed qfq files can be continuity-checked."""
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    if frame.empty:
        return {}
    tail = frame.tail(rows)
    return {
        str(row["timestamp"]): float(row["close"])
        for _, row in tail.iterrows()
    }


def _verify_continuity(path: Path, snapshot: dict[str, float], symbol: str) -> str | None:
    """Return an error string when refreshed prices disagree with the previous snapshot."""
    if not snapshot:
        return None
    frame = pd.read_csv(path)
    index = {str(row["timestamp"]): float(row["close"]) for _, row in frame.iterrows()}
    for date, old_close in snapshot.items():
        new_close = index.get(date)
        if new_close is None:
            return f"{symbol}: previous row {date} missing after refresh"
        if old_close and abs(new_close - old_close) / old_close > 0.02:
            return f"{symbol}: qfq seam mismatch on {date} (old={old_close:.6f} new={new_close:.6f})"
    return None


def fetch_market_data(*, start: str, end: str, resume: bool, hk_workers: int, refresh: bool = False) -> dict[str, Any]:
    if not MEMBERSHIP_PATH.exists():
        raise FileNotFoundError(f"build universe first: {MEMBERSHIP_PATH}")
    membership = pd.read_csv(MEMBERSHIP_PATH, dtype={"symbol": str})
    a_symbols = sorted(membership.loc[membership["market"] == "A", "symbol"].str.zfill(6).unique())
    hk_symbols = sorted(membership.loc[membership["market"] == "HK", "symbol"].str.zfill(5).unique())
    EVENT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "start": start,
        "end": end,
        "files": [],
        "errors": [],
    }

    import baostock as bs

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
    try:
        for index, symbol in enumerate(a_symbols, start=1):
            price_path = RAW_DIR / f"cn_{symbol}.csv"
            event_path = EVENT_DIR / f"cn_{symbol}.csv"
            if resume and not refresh and price_path.exists() and event_path.exists():
                report["files"].append({"file": price_path.name, "market": "A", "status": "resumed"})
                continue
            old_tail = _tail_close_snapshot(price_path) if refresh else {}
            try:
                entry = _fetch_a_symbol(bs, symbol=symbol, start=start, end=end)
                if refresh and old_tail:
                    seam_error = _verify_continuity(price_path, old_tail, symbol)
                    if seam_error is not None:
                        entry["status"] = "seam_error"
                        entry["seam_error"] = seam_error
                        report["errors"].append({"file": price_path.name, "error": seam_error})
                    else:
                        entry["status"] = "refreshed"
                report["files"].append(entry)
            except Exception as exc:
                report["errors"].append({"file": price_path.name, "error": f"{type(exc).__name__}: {exc}"})
            if index % 20 == 0 or index == len(a_symbols):
                _atomic_json(report, ACQUISITION_REPORT)
                print(f"[A] {index}/{len(a_symbols)} errors={len(report['errors'])}", flush=True)
    finally:
        bs.logout()

    with ThreadPoolExecutor(max_workers=max(1, hk_workers)) as pool:
        futures = {}
        for symbol in hk_symbols:
            price_path = RAW_DIR / f"hk_{symbol}.csv"
            event_path = EVENT_DIR / f"hk_{symbol}.csv"
            if resume and not refresh and price_path.exists() and event_path.exists():
                report["files"].append({"file": price_path.name, "market": "HK", "status": "resumed"})
                continue
            old_tail = _tail_close_snapshot(price_path) if refresh else {}
            futures[
                pool.submit(_fetch_hk_symbol, symbol=symbol, start=start, end=end, old_tail=old_tail)
            ] = symbol
        for index, future in enumerate(as_completed(futures), start=1):
            symbol = futures[future]
            try:
                entry = future.result()
                if entry.get("seam_error"):
                    report["errors"].append({"file": entry["file"], "error": entry["seam_error"]})
                report["files"].append(entry)
            except Exception as exc:
                report["errors"].append({"file": f"hk_{symbol}.csv", "error": f"{type(exc).__name__}: {exc}"})
            if index % 20 == 0 or index == len(futures):
                _atomic_json(report, ACQUISITION_REPORT)
                print(f"[HK] {index}/{len(futures)} errors={len(report['errors'])}", flush=True)

    report["files"].sort(key=lambda item: item["file"])
    _atomic_json(report, ACQUISITION_REPORT)
    return report


def clean_dataset(*, start: str, end: str) -> dict[str, Any]:
    universe = json.loads((RAW_DIR / "universe_manifest.json").read_text(encoding="utf-8"))
    if not universe.get("point_in_time_constituents"):
        raise RuntimeError("clean_v7 requires point-in-time universe metadata")
    report = json.loads(ACQUISITION_REPORT.read_text(encoding="utf-8"))
    if report.get("errors"):
        raise RuntimeError(f"acquisition has {len(report['errors'])} unresolved errors")

    manifest = build_clean_dataset(
        RAW_DIR,
        CLEAN_DIR,
        dataset_version=DATASET_VERSION,
        **SPLITS,
        source_policy={
            "development_only": True,
            "point_in_time_constituents": True,
            "A": {
                "universe": "historical CSI300",
                "prices": "BaoStock qfq",
                "adjustment_events": "not separately available; prices are BaoStock qfq",
                "volume_unit": "shares",
                "amount_unit": "CNY",
            },
            "HK": {
                "universe": "historical HSI+HSCEI+HSTECH union",
                "prices": "AKShare/Sina qfq",
                "volume_unit": "shares",
                "amount_unit": "HKD provider reported",
            },
        },
    )
    clean_metadata = CLEAN_DIR / "metadata"
    clean_metadata.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MEMBERSHIP_PATH, clean_metadata / MEMBERSHIP_PATH.name)
    event_files = sorted(EVENT_DIR.glob("*.csv"))
    events = pd.concat((pd.read_csv(path) for path in event_files), ignore_index=True)
    _atomic_csv(events, clean_metadata / "security_events.csv")

    membership = pd.read_csv(MEMBERSHIP_PATH, dtype={"symbol": str})
    expected = {
        "A": set(membership.loc[membership["market"] == "A", "symbol"].str.zfill(6)),
        "HK": set(membership.loc[membership["market"] == "HK", "symbol"].str.zfill(5)),
    }
    actual = {
        "A": {path.stem[3:] for path in CLEAN_DIR.glob("cn_*.csv")},
        "HK": {path.stem[3:] for path in CLEAN_DIR.glob("hk_*.csv")},
    }
    coverage = {
        market: {
            "expected_symbols": len(expected[market]),
            "available_symbols": len(expected[market] & actual[market]),
            "ratio": len(expected[market] & actual[market]) / max(1, len(expected[market])),
            "missing": sorted(expected[market] - actual[market]),
        }
        for market in ("A", "HK")
    }
    if any(item["ratio"] < 0.98 for item in coverage.values()):
        raise RuntimeError(f"clean_v7 symbol coverage below 98%: {coverage}")
    manifest["point_in_time_constituents"] = True
    manifest["development_only"] = True
    manifest["strict_oos_eligible"] = False
    manifest["membership_file"] = str((clean_metadata / MEMBERSHIP_PATH.name).resolve())
    manifest["security_events_file"] = str((clean_metadata / "security_events.csv").resolve())
    manifest["symbol_coverage"] = coverage
    _atomic_json(manifest, CLEAN_DIR / "manifest.json")
    return manifest


def build_evaluation_manifest() -> dict[str, Any]:
    dataset = json.loads((CLEAN_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest = build_compact_evaluation_manifest(
        CLEAN_DIR,
        a_limit=None,
        hk_limit=None,
        train_end=SPLITS["train_end"],
        validation_start=SPLITS["validation_start"],
        validation_end=SPLITS["validation_end"],
        diagnostic_start=SPLITS["diagnostic_start"],
        diagnostic_end=SPLITS["diagnostic_end"],
        strict_oos_start=SPLITS["strict_oos_start"],
        validation_fold_id="validation_2026_05_07",
        diagnostic_fold_id="diagnostic_2026_08_forward",
    )
    manifest["dataset_version"] = dataset["dataset_version"]
    manifest["development_only"] = True
    manifest["point_in_time_constituents"] = True
    manifest["strict_oos_eligible"] = False
    manifest["dataset_manifest"] = str((CLEAN_DIR / "manifest.json").resolve())
    _atomic_json(manifest, EVALUATION_MANIFEST)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("universe", "fetch", "clean", "manifest", "all"), default="all")
    parser.add_argument("--start", default="2021-08-01")
    parser.add_argument("--end", default="2026-07-31")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--hk-workers", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--evaluation-manifest", type=Path, default=None)
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--train-end", default=None)
    parser.add_argument("--validation-start", default=None)
    parser.add_argument("--validation-end", default=None)
    parser.add_argument("--diagnostic-start", default=None)
    parser.add_argument("--diagnostic-end", default=None)
    parser.add_argument("--strict-oos-start", default=None)
    args = parser.parse_args()
    _load_environment()

    global CLEAN_DIR, EVALUATION_MANIFEST, DATASET_VERSION, SPLITS
    if args.output_dir is not None:
        CLEAN_DIR = args.output_dir
    if args.evaluation_manifest is not None:
        EVALUATION_MANIFEST = args.evaluation_manifest
    if args.dataset_version is not None:
        DATASET_VERSION = args.dataset_version
    for key, value in {
        "train_end": args.train_end,
        "validation_start": args.validation_start,
        "validation_end": args.validation_end,
        "diagnostic_start": args.diagnostic_start,
        "diagnostic_end": args.diagnostic_end,
        "strict_oos_start": args.strict_oos_start,
    }.items():
        if value is not None:
            SPLITS[key] = value

    stages = ("universe", "fetch", "clean", "manifest") if args.stage == "all" else (args.stage,)
    for stage in stages:
        if stage == "universe":
            result = build_universe(start=args.start, end=args.end)
        elif stage == "fetch":
            result = fetch_market_data(
                start=args.start,
                end=args.end,
                resume=args.resume,
                hk_workers=args.hk_workers,
                refresh=args.refresh,
            )
        elif stage == "clean":
            result = clean_dataset(start=args.start, end=args.end)
        else:
            result = build_evaluation_manifest()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:8000])


if __name__ == "__main__":
    main()
