"""Full-history daily OHLCV for indicator alignment with mainstream charting apps.

Long-period indicators (EMA144/169/288/338 tunnels, MACD, weekly series, volume
baselines) only converge with years of data. This module provides a separate
full-history feed that is independent from the model input window (last 90
bars) and from any user-selected date range.

Caching: in-memory TTL + JSON disk cache under ``output/cache/full_rows/``,
keyed by market/symbol/adjust. Entries refresh once per local calendar day; a
failed refresh falls back to the previous day's cache so indicators never
become unavailable because of a transient network error.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_ROOT = Path(__file__).resolve().parents[2] / "output" / "cache" / "full_rows"
_MEM_CACHE: dict[str, tuple[str, list[dict[str, Any]]]] = {}
_MEM_LOCK = threading.RLock()


def _today() -> str:
    return date.today().isoformat()


def _cache_file(market: str, symbol: str, adjust: str) -> Path:
    safe_symbol = "".join(ch for ch in symbol if ch.isalnum() or ch in "._-")
    return _CACHE_ROOT / f"{market}_{safe_symbol}_{adjust}.json"


def _load_disk(market: str, symbol: str, adjust: str) -> tuple[str, list[dict[str, Any]]] | None:
    path = _cache_file(market, symbol, adjust)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows")
        day = str(payload.get("fetched_day") or "")
        if isinstance(rows, list) and day:
            return day, rows
    except Exception as exc:
        logger.debug("[full_history] disk cache read failed %s: %s", path.name, exc)
    return None


def _save_disk(market: str, symbol: str, adjust: str, rows: list[dict[str, Any]]) -> None:
    try:
        _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        payload = {"fetched_day": _today(), "rows": rows}
        _cache_file(market, symbol, adjust).write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("[full_history] disk cache write failed: %s", exc)


def _fetch_cn(symbol: str, adjust: str) -> list[dict[str, Any]]:
    from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv

    end = datetime.now()
    start = datetime(2015, 1, 1)
    return fetch_a_stock_ohlcv(
        symbol=symbol,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust=adjust,
    )


def _fetch_hk(symbol: str) -> list[dict[str, Any]]:
    from kronos_fincept.agent import _fetch_hk_ohlcv_akshare

    return _fetch_hk_ohlcv_akshare(symbol, lookback_days=None)


def _fetch_us(symbol: str, market: str) -> list[dict[str, Any]]:
    from kronos_fincept.financial import GlobalMarketSource

    source = GlobalMarketSource()
    normalized = "us" if market == "commodity" else market
    try:
        frame = source.get_stock_data(symbol, market=normalized, period="10y", interval="1d")
        if frame is not None and not frame.empty:
            rows: list[dict[str, Any]] = []
            for row in frame.to_dict(orient="records"):
                close = _safe_float(row.get("close"))
                volume = _safe_float(row.get("volume"))
                rows.append(
                    {
                        "timestamp": str(row.get("timestamp")),
                        "open": _safe_float(row.get("open")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "close": close,
                        "volume": volume,
                        "amount": _safe_float(row.get("amount", 0.0)) or (close * volume if close and volume else 0.0),
                    }
                )
            if rows:
                return rows
    except Exception as exc:
        logger.debug("[full_history] yfinance full history failed for %s: %s", symbol, exc)

    # AkShare/Sina US daily fallback so a Yahoo rate limit never blocks
    # full-history indicators for US/global tickers.
    try:
        import akshare as ak

        frame = ak.stock_us_daily(symbol=symbol, adjust="qfq")
        if frame is not None and not frame.empty:
            us_rows: list[dict[str, Any]] = []
            for _, row in frame.iterrows():
                close = _safe_float(row.get("close"))
                volume = _safe_float(row.get("volume"))
                ts = row.get("date")
                timestamp = ts.strftime("%Y-%m-%dT00:00:00Z") if hasattr(ts, "strftime") else str(ts)
                us_rows.append(
                    {
                        "timestamp": timestamp,
                        "open": _safe_float(row.get("open")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "close": close,
                        "volume": volume,
                        "amount": close * volume if close and volume else 0.0,
                    }
                )
            if us_rows:
                return us_rows
    except Exception as exc:
        logger.debug("[full_history] akshare us daily fallback failed for %s: %s", symbol, exc)
    return []


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number else 0.0


def _fetch_full_rows(symbol: str, market: str, adjust: str) -> list[dict[str, Any]]:
    if market == "cn":
        return _fetch_cn(symbol, adjust)
    if market == "hk":
        return _fetch_hk(symbol)
    return _fetch_us(symbol, market)


def get_full_history_rows(symbol: str, market: str, adjust: str = "qfq") -> list[dict[str, Any]]:
    """Return full-history daily rows (ascending), cached per day."""
    key = f"{market}|{symbol}|{adjust}"
    today = _today()
    with _MEM_LOCK:
        cached = _MEM_CACHE.get(key)
        if cached and cached[0] == today:
            return [dict(row) for row in cached[1]]

    disk = _load_disk(market, symbol, adjust)
    if disk and disk[0] == today:
        with _MEM_LOCK:
            _MEM_CACHE[key] = disk
        return [dict(row) for row in disk[1]]

    try:
        rows = _fetch_full_rows(symbol, market, adjust)
    except Exception as exc:
        logger.warning("[full_history] fetch failed for %s/%s: %s", market, symbol, _short_error(exc))
        rows = []
    if rows:
        rows.sort(key=lambda row: str(row.get("timestamp") or ""))
        with _MEM_LOCK:
            _MEM_CACHE[key] = (today, rows)
        _save_disk(market, symbol, adjust, rows)
        return [dict(row) for row in rows]

    # Transient failure: keep yesterday's cache so indicators stay available.
    if disk and disk[1]:
        logger.warning("[full_history] using stale cache for %s/%s (%s rows)", market, symbol, len(disk[1]))
        with _MEM_LOCK:
            _MEM_CACHE[key] = (today, disk[1])
        return [dict(row) for row in disk[1]]
    return []


def _short_error(exc: BaseException) -> str:
    return str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__
