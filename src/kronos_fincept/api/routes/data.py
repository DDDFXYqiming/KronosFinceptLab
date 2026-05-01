"""GET /api/data — A-stock data retrieval endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from kronos_fincept.api.models import DataResponseOut, SearchResponseOut, SearchResultOut
from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/data/global/{symbol}", response_model=DataResponseOut)
async def get_global_market_data(
    symbol: str,
    market: str = Query("us", description="Market: us, hk, commodity"),
    start_date: str = Query("20250101", description="Start date YYYYMMDD"),
    end_date: str = Query(..., description="End date YYYYMMDD"),
) -> DataResponseOut:
    """Fetch global market (HK/US/Commodity) OHLCV data via Yahoo Finance."""
    try:
        from kronos_fincept.financial import GlobalMarketSource
        gms = GlobalMarketSource()
        yahoo_suffix = {"hk": ".HK", "us": "", "commodity": ""}
        suff = yahoo_suffix.get(market, "")
        yahoo_symbol = f"{symbol}{suff}" if suff else symbol
        raw_data = gms.fetch_data(yahoo_symbol, start_date, end_date)
        if not raw_data or len(raw_data) == 0:
            raise HTTPException(status_code=404, detail=f"No data for {symbol} ({market})")
        return DataResponseOut(
            ok=True,
            symbol=symbol,
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
    symbol: str,
    market: str = Query("cn", description="Market: cn, us, hk, commodity"),
) -> dict:
    """Calculate technical indicators for a symbol (SMA, EMA, RSI, MACD, Bollinger, KDJ)."""
    try:
        from kronos_fincept.financial import TechnicalIndicators

        # Fetch price data
        if market == "cn":
            rows = fetch_a_stock_ohlcv(symbol, "20250101", "20260430")
        else:
            from kronos_fincept.financial import GlobalMarketSource
            gms = GlobalMarketSource()
            yahoo_suffix = {"hk": ".HK", "us": "", "commodity": ""}
            suff = yahoo_suffix.get(market, "")
            yahoo_symbol = f"{symbol}{suff}" if suff else symbol
            rows = gms.fetch_data(yahoo_symbol, "20250101", "20260430")

        if not rows or len(rows) < 30:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")

        closes = [row["close"] for row in rows]
        highs = [row["high"] for row in rows]
        lows = [row["low"] for row in rows]
        volumes = [row.get("volume", 0) for row in rows]

        ti = TechnicalIndicators()
        indicators = ti.calculate_all_indicators(closes, highs, lows, volumes)

        # Convert to serializable dict
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
    symbol: str,
    start_date: str = Query(..., description="Start date YYYYMMDD"),
    end_date: str = Query(..., description="End date YYYYMMDD"),
    adjust: str = Query(default="qfq", description="Price adjustment: qfq, hfq, or empty"),
) -> DataResponseOut:
    """Fetch A-stock historical OHLCV data via DataSourceManager (AkShare -> BaoStock -> Yahoo)."""
    try:
        rows = fetch_a_stock_ohlcv(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to fetch data for %s", symbol)
        raise HTTPException(status_code=502, detail=f"Data source error: {exc}")

    return DataResponseOut(
        ok=True,
        symbol=symbol,
        count=len(rows),
        rows=rows,
    )


@router.get("/data/search", response_model=SearchResponseOut)
async def search_stocks(
    q: str = Query(..., min_length=1, description="Search keyword (stock code or name)"),
) -> SearchResponseOut:
    """Search A-stock by code or name with multi-source fallback (AkShare -> BaoStock)."""
    try:
        from kronos_fincept.akshare_adapter import search_stocks

        raw = search_stocks(q)
        results = [SearchResultOut(**r) for r in raw]

        return SearchResponseOut(ok=True, results=results)

    except Exception as exc:
        logger.exception("Stock search failed for query: %s", q)
        # Return empty results on failure rather than 500
        return SearchResponseOut(ok=True, results=[])
