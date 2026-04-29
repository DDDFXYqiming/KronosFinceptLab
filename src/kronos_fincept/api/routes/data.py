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
    """Fetch A-stock historical OHLCV data via AkShare."""
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
    """Search A-stock by code or name.

    Uses AkShare's stock info endpoint to find matching stocks.
    """
    try:
        import akshare as ak
        # ak.stock_zh_a_spot_em() returns all A-stock real-time quotes
        # We use it as a lightweight stock directory
        df = ak.stock_zh_a_spot_em()
        # Filter by code or name
        mask = (
            df["代码"].str.contains(q, case=False, na=False)
            | df["名称"].str.contains(q, case=False, na=False)
        )
        matches = df[mask].head(20)

        results = []
        for _, row in matches.iterrows():
            code = str(row["代码"])
            name = str(row["名称"])
            # Infer market from code prefix
            if code.startswith("6"):
                market = "SSE"  # Shanghai
            elif code.startswith(("0", "3")):
                market = "SZSE"  # Shenzhen
            elif code.startswith(("4", "8")):
                market = "BSE"  # Beijing
            else:
                market = "UNKNOWN"

            results.append(SearchResultOut(code=code, name=name, market=market))

        return SearchResponseOut(ok=True, results=results)

    except Exception as exc:
        logger.exception("Stock search failed for query: %s", q)
        # Return empty results on failure rather than 500
        return SearchResponseOut(ok=True, results=[])
