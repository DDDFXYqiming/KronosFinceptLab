"""GET /api/health — Health check endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from kronos_fincept.api.models import HealthResponseOut
from kronos_fincept.api.deps import get_model_info
from kronos_fincept.build_info import get_build_info

router = APIRouter()


@router.get("/health", response_model=HealthResponseOut)
async def health_check(request: Request) -> HealthResponseOut:
    """Return lightweight service health status."""
    return _build_health_response(request, deep=False)


@router.get("/health/deep", response_model=HealthResponseOut)
async def deep_health_check(request: Request) -> HealthResponseOut:
    """Return heavyweight runtime diagnostics for operator checks."""
    return _build_health_response(request, deep=True)


def _build_health_response(request: Request, deep: bool) -> HealthResponseOut:
    start_time = getattr(request.app.state, "start_time", time.time())
    uptime = time.time() - start_time
    model_info = get_model_info(deep=deep)
    build_info = get_build_info()

    return HealthResponseOut(
        status=model_info["status"],
        version="2.0.0",
        app_version=build_info.app_version,
        build_commit=build_info.build_commit,
        build_ref=build_info.build_ref,
        build_source=build_info.build_source,
        model_loaded=model_info["model_loaded"],
        model_id=model_info["model_id"],
        tokenizer_id=model_info["tokenizer_id"],
        device=model_info["device"],
        uptime_seconds=round(uptime, 1),
        runtime_mode=model_info["runtime_mode"],
        model_enabled=model_info["model_enabled"],
        deep_check=model_info["deep_check"],
        capabilities=model_info["capabilities"],
        model_error=model_info["model_error"],
    )
