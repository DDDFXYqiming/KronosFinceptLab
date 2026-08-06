"""Conservative preparation of versioned A/H-share training datasets."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PRICE_COLUMNS = ("open", "high", "low", "close")
VALUE_COLUMNS = (*PRICE_COLUMNS, "volume", "amount")
REQUIRED_COLUMNS = ("timestamp", *VALUE_COLUMNS)


def _calendar_timestamps(values: pd.Series) -> pd.Series:
    """Parse daily bars without converting exchange-local dates through UTC."""

    text = values.astype("string").str.strip()
    parsed = pd.to_datetime(
        text.str.slice(0, 10),
        format="%Y-%m-%d",
        errors="coerce",
    )
    missing = parsed.isna()
    if missing.any():
        fallback = pd.to_datetime(
            text.loc[missing],
            errors="coerce",
            format="mixed",
        )
        parsed.loc[missing] = fallback.map(
            lambda value: (
                value.tz_localize(None)
                if isinstance(value, pd.Timestamp) and value.tzinfo is not None
                else value
            )
        )
    return parsed


def merge_refreshed_rows(
    existing: pd.DataFrame,
    refreshed: pd.DataFrame,
) -> pd.DataFrame:
    """Merge a refreshed date range, preferring new rows on duplicate dates."""

    for label, frame in (("existing", existing), ("refreshed", refreshed)):
        missing = set(REQUIRED_COLUMNS).difference(frame.columns)
        if missing:
            raise ValueError(f"{label} missing required columns: {sorted(missing)}")
    combined = pd.concat(
        [
            existing.loc[:, REQUIRED_COLUMNS],
            refreshed.loc[:, REQUIRED_COLUMNS],
        ],
        ignore_index=True,
    )
    parsed = _calendar_timestamps(combined["timestamp"])
    combined = combined.loc[parsed.notna()].copy()
    combined["_timestamp"] = parsed.loc[parsed.notna()]
    combined.sort_values("_timestamp", kind="stable", inplace=True)
    combined.drop_duplicates("_timestamp", keep="last", inplace=True)
    combined["timestamp"] = combined["_timestamp"].dt.strftime("%Y-%m-%d")
    combined.drop(columns="_timestamp", inplace=True)
    combined.reset_index(drop=True, inplace=True)
    return combined


def clean_price_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Remove unambiguous bad rows while retaining and counting large jumps."""

    missing_columns = set(REQUIRED_COLUMNS).difference(frame.columns)
    if missing_columns:
        raise ValueError(f"missing required columns: {sorted(missing_columns)}")

    cleaned = frame.loc[:, REQUIRED_COLUMNS].copy()
    report = {"input_rows": int(len(cleaned))}
    parsed = _calendar_timestamps(cleaned["timestamp"])
    invalid_timestamp = parsed.isna()
    report["invalid_timestamp_rows_removed"] = int(invalid_timestamp.sum())
    cleaned = cleaned.loc[~invalid_timestamp].copy()
    cleaned["_timestamp"] = parsed.loc[~invalid_timestamp]
    cleaned.sort_values("_timestamp", inplace=True)

    duplicate = cleaned["_timestamp"].duplicated(keep="first")
    report["duplicate_rows_removed"] = int(duplicate.sum())
    cleaned = cleaned.loc[~duplicate].copy()

    numeric = cleaned.loc[:, VALUE_COLUMNS].apply(pd.to_numeric, errors="coerce")
    missing_value = numeric.isna().any(axis=1)
    report["missing_value_rows_removed"] = int(missing_value.sum())
    cleaned = cleaned.loc[~missing_value].copy()
    numeric = numeric.loc[~missing_value]
    cleaned.loc[:, VALUE_COLUMNS] = numeric

    nonpositive_price = (numeric.loc[:, PRICE_COLUMNS] <= 0).any(axis=1)
    report["nonpositive_price_rows_removed"] = int(nonpositive_price.sum())
    cleaned = cleaned.loc[~nonpositive_price].copy()
    numeric = numeric.loc[~nonpositive_price]

    negative_volume = numeric["volume"] < 0
    report["negative_volume_rows_removed"] = int(negative_volume.sum())
    cleaned = cleaned.loc[~negative_volume].copy()
    numeric = numeric.loc[~negative_volume]

    negative_amount = numeric["amount"] < 0
    report["negative_amount_rows_removed"] = int(negative_amount.sum())
    cleaned = cleaned.loc[~negative_amount].copy()
    numeric = numeric.loc[~negative_amount]

    invalid_ohlc = (
        numeric["high"] < numeric.loc[:, ("open", "close", "low")].max(axis=1)
    ) | (
        numeric["low"] > numeric.loc[:, ("open", "close", "high")].min(axis=1)
    )
    report["invalid_ohlc_rows_removed"] = int(invalid_ohlc.sum())
    cleaned = cleaned.loc[~invalid_ohlc].copy()

    jumps = cleaned["close"].astype(float).pct_change(fill_method=None).abs() > 0.20
    report["price_jump_rows_flagged"] = int(jumps.sum())
    report["output_rows"] = int(len(cleaned))
    cleaned["timestamp"] = cleaned["_timestamp"].dt.strftime("%Y-%m-%d")
    cleaned.drop(columns="_timestamp", inplace=True)
    cleaned.reset_index(drop=True, inplace=True)
    return cleaned, report


def _atomic_csv(frame: pd.DataFrame, destination: Path) -> str:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    frame.to_csv(temporary, index=False)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    os.replace(temporary, destination)
    return digest


def _atomic_json(payload: dict[str, Any], destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, destination)


def build_clean_dataset(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    dataset_version: str = "clean_v5_compact",
    train_start: str = "2022-01-01",
    train_end: str = "2025-12-31",
    validation_start: str = "2026-01-01",
    validation_end: str = "2026-03-31",
    diagnostic_start: str = "2026-04-01",
    diagnostic_end: str = "2026-07-31",
    strict_oos_start: str = "2026-08-01",
    source_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build clean A/H CSVs and a provenance/partition manifest."""

    source = Path(source_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    cutoffs = {
        "train_start": train_start,
        "train_end": train_end,
        "validation_start": validation_start,
        "validation_end": validation_end,
        "diagnostic_start": diagnostic_start,
        "diagnostic_end": diagnostic_end,
        "strict_oos_start": strict_oos_start,
    }
    parsed_cutoffs = {name: pd.Timestamp(value) for name, value in cutoffs.items()}
    ordered = [parsed_cutoffs[name] for name in cutoffs]
    empty_diagnostic_boundary = (
        parsed_cutoffs["diagnostic_start"]
        == parsed_cutoffs["diagnostic_end"]
        == parsed_cutoffs["strict_oos_start"]
    )
    if ordered != sorted(ordered) or (
        len(set(ordered)) != len(ordered) and not empty_diagnostic_boundary
    ):
        raise ValueError("dataset cutoffs must be strictly increasing")

    for path in sorted(source.glob("*.csv")):
        if not path.name.startswith(("cn_", "hk_")):
            continue
        header = pd.read_csv(path, nrows=0)
        if not set(REQUIRED_COLUMNS).issubset(header.columns):
            continue
        cleaned, cleaning = clean_price_frame(pd.read_csv(path))
        if cleaned.empty:
            continue
        timestamps = pd.to_datetime(cleaned["timestamp"], errors="raise")
        destination = output / path.name
        digest = _atomic_csv(cleaned, destination)
        records.append(
            {
                "file": path.name,
                "market": "A" if path.name.startswith("cn_") else "HK",
                "source": str(path.resolve()),
                "start": timestamps.iloc[0].date().isoformat(),
                "end": timestamps.iloc[-1].date().isoformat(),
                "sha256": digest,
                "cleaning": cleaning,
                "partitions": {
                    "pretrain_history_rows": int(
                        (timestamps < parsed_cutoffs["train_start"]).sum()
                    ),
                    "train_rows": int(
                        (
                            (timestamps >= parsed_cutoffs["train_start"])
                            & (timestamps <= parsed_cutoffs["train_end"])
                        ).sum()
                    ),
                    "validation_rows": int(
                        (
                            (timestamps >= parsed_cutoffs["validation_start"])
                            & (timestamps <= parsed_cutoffs["validation_end"])
                        ).sum()
                    ),
                    "diagnostic_rows": int(
                        (
                            (timestamps >= parsed_cutoffs["diagnostic_start"])
                            & (timestamps <= parsed_cutoffs["diagnostic_end"])
                        ).sum()
                    ),
                    "future_oos_rows": int(
                        (timestamps >= parsed_cutoffs["strict_oos_start"]).sum()
                    ),
                },
            }
        )

    manifest: dict[str, Any] = {
        "dataset_version": dataset_version,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_dir": str(source),
        "output_dir": str(output),
        "markets": ["A", "HK"],
        "source_policy": source_policy or {},
        "large_jump_policy": "flag_only_keep_row",
        "cutoffs": cutoffs,
        "file_count": len(records),
        "files": records,
    }
    _atomic_json(manifest, output / "manifest.json")
    return manifest
