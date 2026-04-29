"""POST /api/forecast — Single-asset OHLCV prediction."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from kronos_fincept.api.models import (
    ForecastMetadataOut,
    ForecastRequestIn,
    ForecastResponseOut,
)
from kronos_fincept.schemas import ForecastRequest, ForecastRow, RESEARCH_WARNING
from kronos_fincept.service import forecast_from_request

logger = logging.getLogger(__name__)
router = APIRouter()


def _pydantic_to_forecast_request(req: ForecastRequestIn) -> ForecastRequest:
    """Convert Pydantic API model to internal dataclass ForecastRequest."""
    rows = [
        ForecastRow(
            timestamp=r.timestamp,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
            amount=r.amount,
        )
        for r in req.rows
    ]
    return ForecastRequest(
        symbol=req.symbol,
        timeframe=req.timeframe,
        pred_len=req.pred_len,
        rows=rows,
        model_id=req.model_id,
        tokenizer_id=req.tokenizer_id,
        dry_run=req.dry_run,
        max_context=req.max_context,
        temperature=req.temperature,
        top_k=req.top_k,
        top_p=req.top_p,
        sample_count=req.sample_count,
    )


@router.post("/forecast", response_model=ForecastResponseOut)
async def predict(req: ForecastRequestIn) -> ForecastResponseOut:
    """Run single-asset forecast.

    Accepts OHLCV rows directly. For convenience with A-stock data,
    use the CLI's `--symbol` flag which auto-fetches via AkShare.
    """
    internal_req = _pydantic_to_forecast_request(req)
    result = forecast_from_request(internal_req)

    if not result.get("ok"):
        logger.warning("Forecast failed for %s: %s", req.symbol, result.get("error"))
        return ForecastResponseOut(
            ok=False,
            symbol=req.symbol,
            timeframe=req.timeframe,
            model_id=req.model_id,
            tokenizer_id=req.tokenizer_id,
            pred_len=req.pred_len,
            forecast=[],
            metadata=ForecastMetadataOut(
                device="unknown",
                elapsed_ms=0,
                backend="error",
                warning=result.get("error", "Unknown error"),
            ),
        )

    return ForecastResponseOut(
        ok=result["ok"],
        symbol=result["symbol"],
        timeframe=result["timeframe"],
        model_id=result["model_id"],
        tokenizer_id=result["tokenizer_id"],
        pred_len=result["pred_len"],
        forecast=result["forecast"],
        metadata=ForecastMetadataOut(**result["metadata"]),
    )
