"""POST /api/batch -- Multi-asset batch prediction with ranking."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from fastapi import APIRouter
from kronos_fincept.api.models import (
    BatchForecastItemIn,
    BatchForecastRequestIn,
    BatchForecastResponseOut,
    ForecastMetadataOut,
    RankedSignalOut,
)
from kronos_fincept.schemas import ForecastRequest
from kronos_fincept.service import batch_forecast_from_requests

logger = logging.getLogger(__name__)
router = APIRouter()


def _item_to_forecast_request(
    item: BatchForecastItemIn,
    pred_len: int,
    dry_run: bool,
) -> ForecastRequest:
    """Convert one batch item to internal ForecastRequest."""
    return ForecastRequest.from_batch_item(
        symbol=item.symbol,
        timeframe=item.timeframe,
        pred_len=pred_len,
        rows=item.rows,
        model_id=item.model_id,
        tokenizer_id=item.tokenizer_id,
        dry_run=dry_run,
        max_context=item.max_context,
        temperature=item.temperature,
        top_k=item.top_k,
        top_p=item.top_p,
        sample_count=item.sample_count,
    )


@router.post("/batch", response_model=BatchForecastResponseOut)
async def batch_predict(req: BatchForecastRequestIn) -> BatchForecastResponseOut:
    """Run batch forecast on multiple assets and return ranked by predicted return."""
    requests = [
        _item_to_forecast_request(item, req.pred_len, req.dry_run)
        for item in req.assets
    ]

    signals = await asyncio.to_thread(batch_forecast_from_requests, requests)

    rankings = [
        RankedSignalOut(
            rank=sig.rank,
            symbol=sig.symbol,
            last_close=sig.last_close,
            predicted_close=sig.predicted_close,
            predicted_return=sig.predicted_return,
            elapsed_ms=sig.elapsed_ms,
        )
        for sig in signals
    ]

    total_elapsed = sum(r.elapsed_ms for r in rankings)

    return BatchForecastResponseOut(
        ok=True,
        rankings=rankings,
        metadata=ForecastMetadataOut(
            device="cpu",
            elapsed_ms=total_elapsed,
            backend="batch",
            warning="Research forecast only; not trading advice.",
        ),
    )
