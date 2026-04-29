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
        status="ok",
        version="2.0.0",
        model_loaded=True,
        model_id=model_info["model_id"],
        device=model_info["device"],
        uptime_seconds=round(uptime, 1),
    )
