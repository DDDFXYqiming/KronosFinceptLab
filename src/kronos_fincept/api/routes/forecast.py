"""POST /api/forecast -- Single-asset OHLCV prediction."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from fastapi import APIRouter
from kronos_fincept.api.models import (
    ForecastMetadataOut,
    ForecastRequestIn,
    ForecastResponseOut,
)
from kronos_fincept.schemas import ForecastRequest, RESEARCH_WARNING
from kronos_fincept.service import forecast_from_request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/forecast", response_model=ForecastResponseOut)
async def predict(req: ForecastRequestIn) -> ForecastResponseOut:
    """Run single-asset forecast.

    Accepts OHLCV rows directly. For convenience with A-stock data,
    use the CLI's `--symbol` flag which auto-fetches via AkShare.
    """
    internal_req = ForecastRequest.from_pydantic(req)
    result = await asyncio.to_thread(forecast_from_request, internal_req)

    if not result.get("ok"):
        from kronos_fincept.schemas import build_error_response
        return ForecastResponseOut(**build_error_response(result.get("error", "unknown"), req.symbol))

    return ForecastResponseOut(
        ok=True,
        symbol=result["symbol"],
        timeframe=result["timeframe"],
        model_id=result["model_id"],
        tokenizer_id=result["tokenizer_id"],
        pred_len=result["pred_len"],
        forecast=result["forecast"],
        probabilistic=result.get("probabilistic"),
        metadata=ForecastMetadataOut(**result["metadata"]),
    )
