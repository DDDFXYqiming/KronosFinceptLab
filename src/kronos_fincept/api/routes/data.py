"""GET /api/data — A-stock data retrieval endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from kronos_fincept.api.models import DataResponseOut, SearchResponseOut, SearchResultOut
from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv

logger = logging.getLogger(__name__)
router = APIRouter()


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
