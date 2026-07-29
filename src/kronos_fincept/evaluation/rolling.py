"""Rolling-origin evaluation primitives.

This module deliberately contains no model code.  It defines the data contract
used by the training/validation/test manifest and by the production-path model
evaluator.  Keeping window construction separate from inference makes it
possible to test leakage and overlap rules without loading a large checkpoint.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


TIMESTAMP_COLUMNS = ("timestamp", "timestamps")
MARKET_PREFIXES = (("cn_", "A"), ("hk_", "HK"))


@dataclass(frozen=True)
class AssetMeta:
    """Point-in-time-independent metadata for one source file."""

    symbol: str
    market: str
    file: str
    row_count: int
    start: str
    end: str


@dataclass(frozen=True)
class WindowRecord:
    """A prediction window represented by row positions and timestamps.

    Row ends are exclusive.  The target interval is always fully contained in
    the requested evaluation interval, so a window cannot borrow labels from a
    neighbouring fold.
    """

    fold: str
    symbol: str
    market: str
    file: str
    input_start_row: int
    input_end_row: int
    target_start_row: int
    target_end_row: int
    input_start: str
    input_end: str
    target_start: str
    target_end: str


def _date(value: Any) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is not None:
        parsed = parsed.tz_localize(None)
    return parsed.normalize()


def _date_text(value: Any) -> str:
    return _date(value).date().isoformat()


def _timestamp_column(path: Path) -> str:
    header = pd.read_csv(path, nrows=0)
    for name in TIMESTAMP_COLUMNS:
        if name in header.columns:
            return name
    raise ValueError(f"{path} does not contain timestamp/timestamps")


def read_timestamps(path: Path) -> pd.Series:
    """Read and validate timestamps without loading price columns."""

    column = _timestamp_column(path)
    values = pd.read_csv(path, usecols=[column])[column]
    timestamps = pd.to_datetime(values, errors="coerce")
    if timestamps.isna().any():
        raise ValueError(f"{path} contains unparseable timestamps")
    if timestamps.duplicated().any():
        raise ValueError(f"{path} contains duplicate timestamps")
    if not timestamps.is_monotonic_increasing:
        raise ValueError(f"{path} timestamps are not sorted ascending")
    return timestamps.reset_index(drop=True)


def _symbol_market(path: Path) -> tuple[str, str] | None:
    for prefix, market in MARKET_PREFIXES:
        if path.name.startswith(prefix):
            return path.stem[len(prefix) :], market
    return None


def discover_universe(
    data_dir: str | Path,
    *,
    a_limit: int | None = 200,
    hk_limit: int | None = 100,
) -> list[AssetMeta]:
    """Discover a deterministic A/HK universe from ``cn_``/``hk_`` CSVs."""

    root = Path(data_dir)
    candidates: list[tuple[Path, str, str]] = []
    for path in sorted(root.glob("*.csv")):
        parsed = _symbol_market(path)
        if parsed is not None:
            symbol, market = parsed
            candidates.append((path, symbol, market))

    selected: list[tuple[Path, str, str]] = []
    for market, limit in (("A", a_limit), ("HK", hk_limit)):
        market_files = [item for item in candidates if item[2] == market]
        if limit is not None:
            market_files = market_files[: max(0, limit)]
        selected.extend(market_files)

    assets: list[AssetMeta] = []
    for path, symbol, market in selected:
        timestamps = read_timestamps(path)
        assets.append(
            AssetMeta(
                symbol=symbol,
                market=market,
                file=path.name,
                row_count=len(timestamps),
                start=_date_text(timestamps.iloc[0]),
                end=_date_text(timestamps.iloc[-1]),
            )
        )
    return assets


def build_window_records(
    asset: AssetMeta,
    timestamps: Sequence[Any] | pd.Series,
    *,
    fold: str,
    target_start: Any,
    target_end: Any,
    lookback: int = 90,
    pred_len: int = 5,
    sample_step: int | None = None,
    embargo_bars: int = 0,
) -> list[WindowRecord]:
    """Build non-overlapping, embargoed target windows for one asset."""

    if lookback <= 0 or pred_len <= 0:
        raise ValueError("lookback and pred_len must be positive")
    if embargo_bars < 0:
        raise ValueError("embargo_bars cannot be negative")

    ts = pd.to_datetime(pd.Series(timestamps), errors="raise").reset_index(drop=True)
    minimum_step = pred_len + embargo_bars
    step = minimum_step if sample_step is None else int(sample_step)
    if step < minimum_step:
        raise ValueError(
            f"sample_step={step} would overlap target/embargo; minimum is {minimum_step}"
        )

    start = _date(target_start)
    end = _date(target_end)
    records: list[WindowRecord] = []
    window = lookback + pred_len
    for input_start_row in range(0, max(0, len(ts) - window + 1), step):
        input_end_row = input_start_row + lookback
        target_start_row = input_end_row
        target_end_row = target_start_row + pred_len
        target_first = _date(ts.iloc[target_start_row])
        target_last = _date(ts.iloc[target_end_row - 1])
        if target_first < start or target_last > end:
            continue
        records.append(
            WindowRecord(
                fold=fold,
                symbol=asset.symbol,
                market=asset.market,
                file=asset.file,
                input_start_row=input_start_row,
                input_end_row=input_end_row,
                target_start_row=target_start_row,
                target_end_row=target_end_row,
                input_start=_date_text(ts.iloc[input_start_row]),
                input_end=_date_text(ts.iloc[input_end_row - 1]),
                target_start=_date_text(ts.iloc[target_start_row]),
                target_end=_date_text(ts.iloc[target_end_row - 1]),
            )
        )
    return records


def _last_day(assets: Iterable[AssetMeta]) -> str:
    values = [asset.end for asset in assets]
    if not values:
        raise ValueError("the selected universe is empty")
    return max(values)


def build_evaluation_manifest(
    data_dir: str | Path,
    *,
    history_start: str = "2019-01-01",
    validation_start: str = "2025-01-01",
    test_start: str = "2026-01-01",
    lookback: int = 90,
    pred_len: int = 5,
    sample_step: int | None = None,
    embargo_bars: int = 5,
    a_limit: int | None = 200,
    hk_limit: int | None = 100,
) -> dict[str, Any]:
    """Create the canonical train/validation/sealed-test manifest.

    The final test interval is deliberately 2026 onward by default.  A model
    checkpoint trained with any 2026 rows must not be reported as a clean test
    result against this manifest; it needs to be retrained with a cutoff before
    the sealed interval.
    """

    root = Path(data_dir)
    assets = discover_universe(root, a_limit=a_limit, hk_limit=hk_limit)
    if not assets:
        raise ValueError(f"no cn_*.csv or hk_*.csv files found under {root}")

    history = _date(history_start)
    validation = _date(validation_start)
    test = _date(test_start)
    if not history < validation < test:
        raise ValueError("history_start < validation_start < test_start is required")

    data_end = _last_day(assets)
    effective_step = sample_step if sample_step is not None else pred_len + embargo_bars
    partitions = [
        {
            "name": "train",
            "role": "fit",
            "start": _date_text(history),
            "end": _date_text(validation - pd.Timedelta(days=1)),
            "sealed": False,
        },
        {
            "name": "validation",
            "role": "model_selection",
            "start": _date_text(validation),
            "end": _date_text(test - pd.Timedelta(days=1)),
            "sealed": False,
        },
        {
            "name": "test",
            "role": "final_sealed_test",
            "start": _date_text(test),
            "end": data_end,
            "sealed": True,
        },
    ]

    def fold_for(year: int) -> dict[str, Any]:
        fold_id = f"fold_{year}"
        eval_start = _date(f"{year}-01-01")
        eval_end = min(_date(f"{year}-12-31"), _date(data_end))
        role = "final_sealed_test" if year == test.year else "validation_like_oos"
        return {
            "id": fold_id,
            "role": role,
            "fit_start": _date_text(history),
            "fit_end": _date_text(eval_start - pd.Timedelta(days=1)),
            "evaluation_start": _date_text(eval_start),
            "evaluation_end": _date_text(eval_end),
            "sealed": role == "final_sealed_test",
        }

    folds: list[dict[str, Any]] = []
    samples_by_fold: dict[str, list[dict[str, Any]]] = {}
    for year in range(validation.year - 2, test.year + 1):
        fold = fold_for(year)
        fold_samples: list[dict[str, Any]] = []
        for asset in assets:
            timestamps = read_timestamps(root / asset.file)
            records = build_window_records(
                asset,
                timestamps,
                fold=fold["id"],
                target_start=fold["evaluation_start"],
                target_end=fold["evaluation_end"],
                lookback=lookback,
                pred_len=pred_len,
                sample_step=effective_step,
                embargo_bars=embargo_bars,
            )
            fold_samples.extend(asdict(record) for record in records)
        fold["sample_count"] = len(fold_samples)
        fold["symbol_count"] = len({item["symbol"] for item in fold_samples})
        fold["market_counts"] = {
            market: sum(item["market"] == market for item in fold_samples)
            for market in ("A", "HK")
        }
        folds.append(fold)
        samples_by_fold[fold["id"]] = fold_samples

    return {
        "manifest_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "data_dir": str(root),
        "universe_policy": {
            "markets": ["A", "HK"],
            "selection": "deterministic sorted filenames; point-in-time constituent metadata is required before trading claims",
            "a_limit": a_limit,
            "hk_limit": hk_limit,
        },
        "protocol": {
            "lookback": lookback,
            "pred_len": pred_len,
            "sample_step": effective_step,
            "embargo_bars": embargo_bars,
            "target_windows_non_overlapping_per_symbol": effective_step >= pred_len,
            "normalization": "production rolling-context normalization only",
            "evaluation_path": "raw data -> predictor -> decode -> original price-space metrics",
        },
        "partitions": partitions,
        "rolling_folds": folds,
        "universe": [asdict(asset) for asset in assets],
        "samples": samples_by_fold,
    }


def select_evaluation_samples(
    samples: Sequence[Mapping[str, Any]],
    *,
    mode: str = "final",
    seed: int = 42,
    a_symbols: int = 20,
    hk_symbols: int = 10,
    windows_per_symbol: int = 5,
    max_samples: int | None = None,
) -> list[dict[str, Any]]:
    """Select a deterministic, market-balanced evaluation subset.

    ``screen`` and ``confirm`` intentionally keep the historical project's
    small comparison scale (20 A-share + 10 HK symbols, five windows each),
    but select windows from a fold rather than from the end of the raw CSV.
    This keeps model selection away from the sealed fold while preserving a
    cheap apples-to-apples comparison.
    """

    if mode not in {"smoke", "screen", "confirm", "final"}:
        raise ValueError(f"unsupported evaluation mode: {mode}")

    ordered = sorted(
        (dict(item) for item in samples),
        key=lambda item: (
            str(item.get("market", "")),
            str(item.get("symbol", "")),
            str(item.get("target_start", "")),
            int(item.get("input_start_row", 0)),
        ),
    )
    if mode == "final" and max_samples is None:
        return ordered

    if mode == "final" and max_samples is not None:
        if max_samples <= 0:
            return []
        if max_samples >= len(ordered):
            return ordered
        selected: list[dict[str, Any]] = []
        for market in ("A", "HK"):
            market_items = [item for item in ordered if item.get("market") == market]
            if not market_items:
                continue
            target = round(max_samples * len(market_items) / len(ordered))
            target = min(len(market_items), max(1, target))
            positions = [round(i * (len(market_items) - 1) / (target - 1)) for i in range(target)] if target > 1 else [0]
            selected.extend(market_items[position] for position in positions)
        return selected[:max_samples]

    if mode == "smoke":
        a_symbols, hk_symbols, windows_per_symbol = 4, 4, 2
    elif mode in {"screen", "confirm"}:
        a_symbols, hk_symbols, windows_per_symbol = (
            max(1, a_symbols),
            max(1, hk_symbols),
            max(1, windows_per_symbol),
        )

    selected: list[dict[str, Any]] = []
    for market, symbol_limit in (("A", a_symbols), ("HK", hk_symbols)):
        market_items = [item for item in ordered if item.get("market") == market]
        symbols = sorted({str(item["symbol"]) for item in market_items})[:symbol_limit]
        for symbol in symbols:
            symbol_items = [item for item in market_items if str(item["symbol"]) == symbol]
            if not symbol_items:
                continue
            count = min(windows_per_symbol, len(symbol_items))
            if count == len(symbol_items):
                positions = list(range(len(symbol_items)))
            else:
                # Evenly cover the fold's time range, with a seeded rotation
                # only for the rare case of tied/duplicate positions.
                positions = [round(i * (len(symbol_items) - 1) / (count - 1)) for i in range(count)]
                rotation = int(seed) % count
                positions = positions[rotation:] + positions[:rotation]
            selected.extend(symbol_items[position] for position in positions)

    if max_samples is not None and len(selected) > max_samples:
        # Preserve market balance when a production-parameter audit asks for a
        # smaller subset than the full fold.
        selected = selected[:max_samples]
    return selected


def _safe_corr(left: pd.Series, right: pd.Series, *, rank: bool = False) -> float | None:
    if rank:
        left = left.rank(method="average")
        right = right.rank(method="average")
    if len(left) < 3 or left.nunique() < 2 or right.nunique() < 2:
        return None
    return float(np.corrcoef(left.to_numpy(dtype=float), right.to_numpy(dtype=float))[0, 1])


def _direction_values(frame: pd.DataFrame) -> pd.Series:
    return (
        (frame["pred_close"].astype(float) > frame["last_close"].astype(float))
        == (frame["true_close"].astype(float) > frame["last_close"].astype(float))
    ).astype(float)


def _metric(frame: pd.DataFrame, name: str) -> float | None:
    if frame.empty:
        return None
    if name == "direction_accuracy":
        return float(_direction_values(frame).mean())
    if name == "ic":
        return _safe_corr(frame["pred_return"], frame["actual_return"])
    if name == "rankic":
        return _safe_corr(frame["pred_return"], frame["actual_return"], rank=True)
    raise ValueError(f"unsupported metric: {name}")


def _portfolio_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    """Match the historical top-k AER/IR comparison in original return space."""

    if frame.empty:
        return {"top_k": 0, "portfolio_return": None, "aer": None, "ir": None}
    top_k = min(10, max(1, len(frame) // 2))
    selected = frame.nlargest(top_k, "pred_return")
    portfolio_return = float(selected["actual_return"].mean())
    benchmark_return = float(frame["actual_return"].mean())
    aer = portfolio_return - benchmark_return
    tracking_error = float(frame["actual_return"].std(ddof=0))
    return {
        "top_k": top_k,
        "portfolio_return": portfolio_return,
        "aer": aer,
        "ir": aer / tracking_error if tracking_error > 0 else None,
    }


def bootstrap_ci(
    frame: pd.DataFrame,
    *,
    metric: str = "direction_accuracy",
    cluster_column: str = "target_end",
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Cluster-bootstrap a metric by target date to preserve cross-sectional dependence."""

    if frame.empty or n_bootstrap <= 0:
        return {"lower": None, "upper": None, "n_bootstrap": 0, "cluster": cluster_column}
    if cluster_column not in frame.columns:
        cluster_column = "_row_cluster"
        frame = frame.copy()
        frame[cluster_column] = np.arange(len(frame))
    cluster_values = frame[cluster_column].astype(str)
    clusters = cluster_values.drop_duplicates().tolist()
    if not clusters:
        return {"lower": None, "upper": None, "n_bootstrap": 0, "cluster": cluster_column}
    cluster_frames = {
        str(cluster): group
        for cluster, group in frame.assign(_bootstrap_cluster=cluster_values).groupby(
            "_bootstrap_cluster", sort=False
        )
    }

    rng = np.random.default_rng(seed)
    estimates: list[float] = []
    for _ in range(max(1, n_bootstrap)):
        selected = rng.choice(clusters, size=len(clusters), replace=True)
        pieces = [cluster_frames[str(cluster)] for cluster in selected]
        value = _metric(pd.concat(pieces, ignore_index=True), metric)
        if value is not None and np.isfinite(value):
            estimates.append(float(value))
    if not estimates:
        return {"lower": None, "upper": None, "n_bootstrap": 0, "cluster": cluster_column}
    return {
        "lower": float(np.quantile(estimates, 0.025)),
        "upper": float(np.quantile(estimates, 0.975)),
        "n_bootstrap": len(estimates),
        "cluster": cluster_column,
    }


def summarize_prediction_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_replicates: int = 1000,
    bootstrap_seed: int = 42,
) -> dict[str, Any]:
    """Return overall, market, symbol, fold and year-level summaries."""

    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"overall": {"n_samples": 0}, "by_market": {}, "by_symbol": {}, "by_fold": {}, "by_year": {}}

    frame["pred_return"] = frame["pred_close"].astype(float) / frame["last_close"].astype(float) - 1.0
    frame["actual_return"] = frame["true_close"].astype(float) / frame["last_close"].astype(float) - 1.0

    def summarize(group: pd.DataFrame, *, include_bootstrap: bool = True) -> dict[str, Any]:
        group_bootstrap = bootstrap_replicates if include_bootstrap else 0
        portfolio = _portfolio_metrics(group)
        return {
            "n_samples": int(len(group)),
            "n_symbols": int(group["symbol"].nunique()) if "symbol" in group else None,
            "n_target_dates": int(group["target_end"].nunique()) if "target_end" in group else None,
            "direction_accuracy": _metric(group, "direction_accuracy"),
            "ic": _metric(group, "ic"),
            "rankic": _metric(group, "rankic"),
            "mean_actual_return": float(group["actual_return"].mean()),
            **portfolio,
            "direction_accuracy_ci95": bootstrap_ci(
                group, metric="direction_accuracy", n_bootstrap=group_bootstrap, seed=bootstrap_seed
            ),
            "ic_ci95": bootstrap_ci(
                group, metric="ic", n_bootstrap=group_bootstrap, seed=bootstrap_seed + 1
            ),
            "rankic_ci95": bootstrap_ci(
                group, metric="rankic", n_bootstrap=group_bootstrap, seed=bootstrap_seed + 2
            ),
        }

    def grouped(column: str, *, include_bootstrap: bool = True) -> dict[str, Any]:
        return {
            str(key): summarize(group, include_bootstrap=include_bootstrap)
            for key, group in frame.groupby(column, sort=True)
        }

    frame["target_year"] = pd.to_datetime(frame["target_end"]).dt.year.astype(str)
    return {
        "overall": summarize(frame),
        "by_market": grouped("market"),
        # Per-symbol point estimates are required, but per-symbol bootstrap
        # multiplies runtime by the number of assets without improving the
        # portfolio-level uncertainty estimate.
        "by_symbol": grouped("symbol", include_bootstrap=False),
        "by_fold": grouped("fold", include_bootstrap=False),
        "by_year": grouped("target_year", include_bootstrap=False),
    }
