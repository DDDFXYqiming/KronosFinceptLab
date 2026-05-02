"""GET /api/health — Health check endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from kronos_fincept.api.models import HealthResponseOut
from kronos_fincept.api.deps import get_model_info

router = APIRouter()


@router.get("/health", response_model=HealthResponseOut)
async def health_check(request: Request) -> HealthResponseOut:
    """Return service health status."""
    start_time = getattr(request.app.state, "start_time", time.time())
    uptime = time.time() - start_time
    model_info = get_model_info()

    return HealthResponseOut(
        status=model_info["status"],
        version="2.0.0",
        model_loaded=model_info["model_loaded"],
        model_id=model_info["model_id"],
        tokenizer_id=model_info["tokenizer_id"],
        device=model_info["device"],
        uptime_seconds=round(uptime, 1),
        capabilities=model_info["capabilities"],
        model_error=model_info["model_error"],
    )
