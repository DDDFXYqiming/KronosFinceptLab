"""POST /api/forecast -- Single-asset OHLCV prediction."""

from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, HTTPException
from kronos_fincept.api.deps import get_model_info
from kronos_fincept.api.models import (
    ForecastMetadataOut,
    ForecastRequestIn,
    ForecastResponseOut,
    ForecastRuntimeConfigOut,
)
from kronos_fincept.config import settings
from kronos_fincept.logging_config import log_perf
from kronos_fincept.schemas import ForecastRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/forecast/config", response_model=ForecastRuntimeConfigOut)
async def forecast_config() -> ForecastRuntimeConfigOut:
    """Return the shared runtime prediction parameters for the forecast UI."""
    model_id = get_model_info(deep=False).get("model_id") or settings.kronos.model_id
    return ForecastRuntimeConfigOut(
        lookback=settings.runtime.lookback,
        pred_len=settings.runtime.pred_len,
        temperature=settings.runtime.temperature,
        top_p=settings.runtime.top_p,
        sample_count=settings.runtime.sample_count,
        agent_sample_count_single=settings.runtime.agent_sample_count_single,
        agent_sample_count_multi=settings.runtime.agent_sample_count_multi,
        model_id=model_id,
    )


@router.post("/forecast", response_model=ForecastResponseOut)
@log_perf(event="api.forecast", level=20)
async def predict(req: ForecastRequestIn) -> ForecastResponseOut:
    """Run single-asset forecast.

    Accepts OHLCV rows directly. For convenience with A-stock data,
    use the CLI's `--symbol` flag which auto-fetches via AkShare.
    """
    from kronos_fincept.service import forecast_from_request

    internal_req = ForecastRequest.from_pydantic(req)
    result = await asyncio.to_thread(forecast_from_request, internal_req)

    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error", "unknown"))

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
