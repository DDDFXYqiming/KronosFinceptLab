"""A-stock OHLCV data adapter with automatic multi-source fallback.

Fetches historical candlestick data via DataSourceManager (AkShare → BaoStock → Yahoo Finance).
All callers (CLI, API, backtest) automatically get the fallback without changes.
"""

from __future__ import annotations

import re
from typing import Any

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
_cache: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}

# Source priority for A-share historical data (BaoStock first — its qfq
# is consistently correct; East Money / AkShare may return wrong qfq
# for stocks with bonus issues / stock splits).
_A_HIST_SOURCE_ORDER = [
    "baostock",
    "eastmoney",
    "akshare",
    "tdx_local",
    "tdx_network",
    "tushare",
    "yahoo_finance",
    "stooq",
]


def _get_manager():
    """Get (or create) the global DataSourceManager singleton."""
    global _manager
    if _manager is None:
        from kronos_fincept.data_sources.init import init_data_sources

        _manager = init_data_sources()
    return _manager


def _post_process_rows(rows: list[dict[str, Any]], source_name: str) -> list[dict[str, Any]]:
    """Validate and normalize OHLCV rows.

    Shared logic used by fetch functions after obtaining raw data.
    """
    conv = [_convert_row_to_english(r) for r in rows]
    conv.sort(key=lambda r: r["timestamp"])
    for r in conv:
        missing = [k for k in _OHLCV_KEYS if k not in r]
        if missing:
            raise ValueError(f"Missing columns in data from {source_name}: {missing}")
    return conv


def _convert_row_to_english(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DataSourceManager result row (Chinese keys) to English keys."""
    out: dict[str, Any] = {}

    dt = str(row.get("日期", ""))
    if re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
        out["timestamp"] = f"{dt}T00:00:00Z"
    else:
        out["timestamp"] = dt

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
    """Fetch A-stock daily OHLCV data with deterministic multi-source fallback.

    Tries DataSourceManager sources in a fixed order that prioritises
    *data correctness over speed*.  Sequence (sequential, NOT parallel):

      1. BaoStock      (qfq verified correct; login-based, stable)
      2. East Money    (Push2 direct, fast but qfq may be wrong for some stocks)
      3. AkShare       (East Money API wrapper)
      4. TDX local     (no adjust support → skipped when adjust is set)
      5. TDX network
      6. Tushare Pro   (if TUSHARE_TOKEN configured)
      7. Yahoo Finance (global fallback)
      8. Stooq

    Returns:
        List of dicts sorted by timestamp ascending, each with keys:
        timestamp, open, high, low, close, volume, amount.
    """
    cache_key = (symbol, start_date, end_date, adjust)
    if cache_key in _cache:
        return _cache[cache_key][:]

    manager = _get_manager()
    sources = {s.config.name: s for s in manager.get_sorted_sources()}
    kwargs = dict(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )

    last_error: str | None = None
    for name in _A_HIST_SOURCE_ORDER:
        src = sources.get(name)
        if src is None or not src.supports_endpoint("stock_zh_a_hist"):
            continue
        try:
            result = src.fetch(endpoint="stock_zh_a_hist", **kwargs)
            if not result.get("success"):
                last_error = f"{name}: {result.get('error', 'unknown')}"
                continue
            data = result.get("data", [])
            if not data:
                last_error = f"{name}: empty data"
                continue
            rows = _post_process_rows(data, name)
            _cache[cache_key] = rows
            return rows[:]
        except Exception as exc:
            last_error = f"{name}: {exc}"
            continue

    raise ValueError(
        f"All data sources failed for {symbol} ({start_date}~{end_date}): {last_error}"
    )


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
    """Fetch OHLCV data for multiple A-stocks in parallel (P1 #5).

    Each symbol is fetched independently with full fallback support.
    Returns:
        Dict mapping symbol -> list of OHLCV rows.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=min(len(symbols), 8), thread_name_prefix="stock-fetch") as pool:
        futures = {
            pool.submit(fetch_a_stock_ohlcv, sym, start_date, end_date, adjust): sym
            for sym in symbols
        }
        for future in as_completed(futures):
            sym = futures[future]
            try:
                results[sym] = future.result()
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

    Tries the unified DataSourceManager first, so EastMoney/AkShare/BaoStock/
    TDX/TickFlow stock lists share the same cache and failover behavior.

    Returns:
        List of dicts with keys: code, name, market.
    """
    manager = _get_manager()
    try:
        result = manager.fetch(
            endpoint="stock_zh_a_spot_em",
            use_cache=True,
            cache_ttl=300,
            page_size=6000,
        )
        results = _search_stock_rows(result.get("data", []), query, max_results)
        if results:
            return results
    except Exception:
        pass

    try:
        result = manager.fetch(
            endpoint="stock_info_a_code_name",
            use_cache=True,
            cache_ttl=86400,  # 24h cache — stock list rarely changes
        )
        return _search_stock_rows(result.get("data", []) if result.get("success") else [], query, max_results)

    except Exception:
        return []


def _search_stock_rows(rows: Any, query: str, max_results: int) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        return []
    needle = str(query or "").strip().lower()
    if not needle:
        return []
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("代码") or row.get("code") or row.get("symbol") or "").strip()
        name = str(row.get("名称") or row.get("name") or row.get("code_name") or row.get("stock_name") or "").strip()
        if not code or not name:
            continue
        if needle not in code.lower() and needle not in name.lower():
            continue
        normalized_code = code.split(".")[0]
        key = normalized_code.upper()
        if key in seen:
            continue
        seen.add(key)
        results.append({"code": normalized_code, "name": name, "market": _infer_cn_market(normalized_code)})
        if len(results) >= max_results:
            break
    return results


def _infer_cn_market(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return "SSE"
    if code.startswith(("0", "2", "3")):
        return "SZSE"
    if code.startswith(("4", "8")):
        return "BSE"
    return "UNKNOWN"

