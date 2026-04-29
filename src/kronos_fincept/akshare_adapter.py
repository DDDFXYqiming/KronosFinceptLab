"""AkShare data adapter for A-stock OHLCV data.

Fetches historical candlestick data from A-stock market via AkShare,
and converts it to the format expected by Kronos.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


# AkShare uses Chinese column names
_AKSHARE_COLUMN_MAP = {
    "日期": "timestamp",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "change_pct",
    "涨跌额": "change",
    "换手率": "turnover",
}


def fetch_a_stock_ohlcv(
    symbol: str,
    start_date: str = "20260101",
    end_date: str = "20261231",
    adjust: str = "qfq",
) -> list[dict[str, Any]]:
    """Fetch A-stock daily OHLCV data via AkShare.

    Args:
        symbol: Stock code, e.g. '000001' (平安银行), '600519' (贵州茅台).
        start_date: Start date in YYYYMMDD format.
        end_date: End date in YYYYMMDD format.
        adjust: Price adjustment — 'qfq' (前复权), 'hfq' (后复权), '' (不复权).

    Returns:
        List of dicts with keys: timestamp, open, high, low, close, volume, amount.
        Sorted by timestamp ascending.
    """
    import akshare as ak

    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )

    if df.empty:
        raise ValueError(f"No data returned for symbol {symbol} ({start_date}~{end_date})")

    # Rename columns
    df = df.rename(columns=_AKSHARE_COLUMN_MAP)

    # Keep only OHLCV columns
    keep = ["timestamp", "open", "high", "low", "close", "volume", "amount"]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns from AkShare: {missing}")
    df = df[keep]

    # Convert timestamp to ISO string
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = df[col].astype(float)

    return df.to_dict(orient="records")


def fetch_multi_stock_ohlcv(
    symbols: list[str],
    start_date: str = "20260101",
    end_date: str = "20261231",
    adjust: str = "qfq",
) -> dict[str, list[dict[str, Any]]]:
    """Fetch OHLCV data for multiple A-stocks.

    Returns:
        Dict mapping symbol -> list of OHLCV rows.
    """
    results: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    for sym in symbols:
        try:
            rows = fetch_a_stock_ohlcv(sym, start_date, end_date, adjust)
            results[sym] = rows
        except Exception as exc:
            errors[sym] = str(exc)

    if errors and not results:
        raise RuntimeError(f"All fetches failed: {errors}")

    return results
