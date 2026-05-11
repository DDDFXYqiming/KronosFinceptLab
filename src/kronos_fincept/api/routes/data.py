"""GET /api/data -- A-stock data retrieval endpoints."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from fastapi import APIRouter, HTTPException, Path, Query
from kronos_fincept.api.models import DataResponseOut, MARKET_PATTERN, SearchResponseOut, SearchResultOut, SYMBOL_PATTERN
from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv


logger = logging.getLogger(__name__)
router = APIRouter()

MAX_DATA_RANGE_DAYS = 800
MAX_RETURN_ROWS = 1024


def _validate_date_range(start_date: str, end_date: str) -> None:
    try:
        start = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.strptime(end_date, "%Y%m%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Dates must use YYYYMMDD format") from exc
    if end < start:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    if (end - start).days > MAX_DATA_RANGE_DAYS:
        raise HTTPException(status_code=422, detail=f"Date range exceeds {MAX_DATA_RANGE_DAYS} days")


def _trim_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rows[-MAX_RETURN_ROWS:] if len(rows) > MAX_RETURN_ROWS else rows


@router.get("/data/global/{symbol}", response_model=DataResponseOut)
async def get_global_market_data(
    symbol: str = Path(..., min_length=1, max_length=32, pattern=SYMBOL_PATTERN),
    market: str = Query("us", min_length=1, max_length=16, pattern=MARKET_PATTERN, description="Market: us, hk, commodity"),
    start_date: str = Query("20250101", min_length=8, max_length=8, description="Start date YYYYMMDD"),
    end_date: str = Query(..., min_length=8, max_length=8, description="End date YYYYMMDD"),
) -> DataResponseOut:
    """Fetch global market (HK/US/Commodity) OHLCV data via Yahoo Finance."""
    _validate_date_range(start_date, end_date)
    try:
        from kronos_fincept.financial import GlobalMarketSource

        def _fetch():
            gms = GlobalMarketSource()
            return gms.fetch_data(symbol, start_date, end_date, market=market)

        raw_data = await asyncio.to_thread(_fetch)
        if not raw_data or len(raw_data) == 0:
            raise HTTPException(status_code=404, detail=f"No data for {symbol} ({market})")
        raw_data = _trim_rows(raw_data)
        return DataResponseOut(
            ok=True,
            symbol=symbol,
            market=market,
            count=len(raw_data),
            rows=raw_data,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch global data for %s", symbol)
        raise HTTPException(status_code=502, detail=f"Data source error: {exc}")


@router.get("/data/indicator/{symbol}")
async def get_technical_indicators(
    symbol: str = Path(..., min_length=1, max_length=32, pattern=SYMBOL_PATTERN),
    market: str = Query("cn", min_length=1, max_length=16, pattern=MARKET_PATTERN, description="Market: cn, us, hk, commodity"),
) -> dict:
    """Calculate technical indicators for a symbol (SMA, EMA, RSI, MACD, Bollinger, KDJ)."""
    try:
        from kronos_fincept.financial import TechnicalIndicators, GlobalMarketSource

        def _fetch_data():
            if market == "cn":
                return fetch_a_stock_ohlcv(symbol, "20250101", "20260430")
            else:
                gms = GlobalMarketSource()
                return gms.fetch_data(symbol, "20250101", "20260430", market=market)

        rows = await asyncio.to_thread(_fetch_data)

        if not rows or len(rows) < 30:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")

        closes = [row["close"] for row in rows]
        highs = [row["high"] for row in rows]
        lows = [row["low"] for row in rows]
        volumes = [row.get("volume", 0) for row in rows]

        ti = TechnicalIndicators()
        indicators = ti.calculate_all_indicators(closes, highs, lows, volumes)

        result = {}
        for name, obj in indicators.items():
            if hasattr(obj, "__dict__"):
                result[name] = {k: round(float(v), 4) if isinstance(v, (int, float)) else v
                               for k, v in obj.__dict__.items()}
            else:
                result[name] = str(obj)

        latest = rows[-1]
        return {
            "ok": True,
            "symbol": symbol,
            "market": market,
            "current_price": latest["close"],
            "indicators": result,
            "data_points": len(rows),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Indicator calc failed for %s", symbol)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/data/a-stock/{symbol}", response_model=DataResponseOut)
async def get_a_stock_data(
    symbol: str = Path(..., min_length=1, max_length=32, pattern=SYMBOL_PATTERN),
    start_date: str = Query(..., min_length=8, max_length=8, description="Start date YYYYMMDD"),
    end_date: str = Query(..., min_length=8, max_length=8, description="End date YYYYMMDD"),
    adjust: str = Query(default="qfq", max_length=8, pattern=r"^(qfq|hfq)?$", description="Price adjustment: qfq, hfq, or empty"),
) -> DataResponseOut:
    """Fetch A-stock historical OHLCV data via DataSourceManager (AkShare -> BaoStock -> Yahoo)."""
    _validate_date_range(start_date, end_date)
    try:
        rows = await asyncio.to_thread(
            fetch_a_stock_ohlcv, symbol=symbol, start_date=start_date,
            end_date=end_date, adjust=adjust,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to fetch data for %s", symbol)
        raise HTTPException(status_code=502, detail=f"Data source error: {exc}")

    rows = _trim_rows(rows)
    return DataResponseOut(
        ok=True,
        symbol=symbol,
        market="cn",
        count=len(rows),
        rows=rows,
    )


@router.get("/data/search", response_model=SearchResponseOut)
async def search_stocks(
    q: str = Query(..., min_length=1, max_length=64, description="Search keyword (stock code or name)"),
) -> SearchResponseOut:
    """Search A-stock by code or name with multi-source fallback (AkShare -> BaoStock)."""
    try:
        from kronos_fincept.akshare_adapter import search_stocks as search_stocks_fn

        raw = await asyncio.to_thread(search_stocks_fn, q)
        results = [SearchResultOut(**r) for r in raw]

        return SearchResponseOut(ok=True, results=results)

    except Exception as exc:
        logger.exception("Stock search failed for query: %s", q)
        return SearchResponseOut(ok=True, results=[])
