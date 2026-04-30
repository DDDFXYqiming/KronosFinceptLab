"""A-stock OHLCV data adapter with automatic multi-source fallback.

Fetches historical candlestick data via DataSourceManager (AkShare → BaoStock → Yahoo Finance).
All callers (CLI, API, backtest) automatically get the fallback without changes.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# AkShare uses Chinese column names — reused by all DataSourceManager sources
_CN_COLUMN_MAP = {
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

_OHLCV_KEYS = ["timestamp", "open", "high", "low", "close", "volume", "amount"]

# Lazy-init DataSourceManager
_manager = None


def _get_manager():
    """Get (or create) the global DataSourceManager singleton."""
    global _manager
    if _manager is None:
        from kronos_fincept.data_sources.init import init_data_sources

        _manager = init_data_sources()
    return _manager


def _convert_row_to_english(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DataSourceManager result row (Chinese keys) to English keys."""
    out: dict[str, Any] = {}

    dt = row.get("日期", "")
    if len(str(dt)) == 10:  # "2026-04-29"
        out["timestamp"] = f"{dt}T00:00:00Z"
    else:
        out["timestamp"] = str(dt)

    # Numeric fields — BaoStock returns strings, Yahoo returns np.float64
    for cn_key, en_key in [
        ("开盘", "open"),
        ("收盘", "close"),
        ("最高", "high"),
        ("最低", "low"),
    ]:
        val = row.get(cn_key, 0)
        out[en_key] = float(val) if val is not None else 0.0

    # Volume — could be int or float string
    vol = row.get("成交量", 0)
    out["volume"] = float(str(vol).replace(",", "")) if vol else 0.0

    # Amount
    amt = row.get("成交额", 0)
    out["amount"] = float(str(amt).replace(",", "")) if amt else 0.0

    return out


def fetch_a_stock_ohlcv(
    symbol: str,
    start_date: str = "20260101",
    end_date: str = "20261231",
    adjust: str = "qfq",
) -> list[dict[str, Any]]:
    """Fetch A-stock daily OHLCV data with automatic multi-source fallback.

    Tries DataSourceManager sources in priority order:
      1. AkShare  (eastmoney, may be blocked by anti-scraping)
      2. BaoStock (stable, login-based)
      3. Yahoo Finance (global, no registration needed)

    Returns:
        List of dicts sorted by timestamp ascending, each with keys:
        timestamp, open, high, low, close, volume, amount.
    """
    manager = _get_manager()

    result = manager.fetch(
        endpoint="stock_zh_a_hist",
        use_cache=True,
        cache_ttl=3600,  # 1-hour cache
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )

    if not result.get("success"):
        err = result.get("error", "Unknown error")
        raise ValueError(
            f"All data sources failed for {symbol}: {err}"
        )

    data = result.get("data", [])
    if not data:
        raise ValueError(
            f"No data returned for symbol {symbol} ({start_date}~{end_date})"
        )

    # Convert Chinese keys → English keys
    rows = [_convert_row_to_english(r) for r in data]

    # Ensure sorted ascending by timestamp
    rows.sort(key=lambda r: r["timestamp"])

    # Validate required columns
    for r in rows:
        missing = [k for k in _OHLCV_KEYS if k not in r]
        if missing:
            raise ValueError(f"Missing columns in data source output: {missing}")

    return rows


def fetch_crypto_ohlcv(
    symbol: str = "BTCUSDT",
    timeframe: str = "1d",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Fetch crypto OHLCV data from Binance.

    Args:
        symbol: Crypto pair (e.g., 'BTCUSDT', 'BTC/USDT')
        timeframe: Time interval ('1m', '5m', '15m', '1h', '4h', '1d')
        limit: Number of bars to fetch (max 1000)

    Returns:
        List of dicts with keys: timestamp, open, high, low, close, volume, amount.
    """
    manager = _get_manager()

    result = manager.fetch(
        endpoint="binance_kline",
        use_cache=True,
        cache_ttl=300,  # 5-minute cache for crypto
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )

    if not result.get("success"):
        err = result.get("error", "Unknown error")
        raise ValueError(f"Binance fetch failed for {symbol}: {err}")

    data = result.get("data", [])
    if not data:
        raise ValueError(f"No data returned for {symbol} ({timeframe})")

    # Binance returns English keys directly
    rows = []
    for r in data:
        rows.append({
            "timestamp": str(r.get("timestamp", "")),
            "open": float(r.get("open", 0)),
            "high": float(r.get("high", 0)),
            "low": float(r.get("low", 0)),
            "close": float(r.get("close", 0)),
            "volume": float(r.get("volume", 0)),
            "amount": float(r.get("amount", 0)),
        })

    # Ensure sorted ascending by timestamp
    rows.sort(key=lambda r: r["timestamp"])
    return rows


def fetch_multi_stock_ohlcv(
    symbols: list[str],
    start_date: str = "20260101",
    end_date: str = "20261231",
    adjust: str = "qfq",
) -> dict[str, list[dict[str, Any]]]:
    """Fetch OHLCV data for multiple A-stocks.

    Each symbol is fetched independently with full fallback support.

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


def search_stocks(
    query: str,
    max_results: int = 20,
) -> list[dict[str, str]]:
    """Search A-stocks by code or name with multi-source fallback.

    Tries AkShare first (eastmoney real-time quotes), then BaoStock (stock list).

    Returns:
        List of dicts with keys: code, name, market.
    """
    # Try AkShare first (eastmoney real-time quotes, fast with filtering)
    try:
        import akshare as ak

        df = ak.stock_zh_a_spot_em()
        mask = df["代码"].str.contains(query, case=False, na=False) | df[
            "名称"
        ].str.contains(query, case=False, na=False)
        matches = df[mask].head(max_results)

        results = []
        for _, row in matches.iterrows():
            code = str(row["代码"])
            name = str(row["名称"])
            if code.startswith("6"):
                market = "SSE"
            elif code.startswith(("0", "3")):
                market = "SZSE"
            elif code.startswith(("4", "8")):
                market = "BSE"
            else:
                market = "UNKNOWN"
            results.append({"code": code, "name": name, "market": market})

        if results:  # Only return if we got actual results
            return results

        # AkShare returned empty — fall through to BaoStock
    except Exception:
        pass  # Fall through to BaoStock

    # Fallback: BaoStock stock list
    try:
        manager = _get_manager()
        result = manager.fetch(
            endpoint="stock_info_a_code_name",
            use_cache=True,
            cache_ttl=86400,  # 24h cache — stock list rarely changes
        )

        if not result.get("success"):
            return []

        rows = result.get("data", [])
        results = []
        for r in rows:
            code = str(r.get("code", ""))
            # BaoStock returns "name" (not "code_name")
            name = str(r.get("name", r.get("code_name", "")))
            if not code or not name:
                continue
            # Filter by query
            if query.lower() in code.lower() or query.lower() in name.lower():
                if code.startswith("6"):
                    market = "SSE"
                elif code.startswith(("0", "3")):
                    market = "SZSE"
                elif code.startswith(("4", "8")):
                    market = "BSE"
                else:
                    market = "UNKNOWN"
                results.append({"code": code, "name": name, "market": market})
                if len(results) >= max_results:
                    break

        return results

    except Exception:
        return []

