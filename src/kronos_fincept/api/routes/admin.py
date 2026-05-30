"""Admin-only operational diagnostics."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kronos_fincept.api.security import get_security_summary
from kronos_fincept.predictor import clear_predictor_cache, predictor_cache_stats
from kronos_fincept.service import prewarm_default_predictor

router = APIRouter(prefix="/admin", tags=["admin"])


class ModelPrewarmRequest(BaseModel):
    force: bool = Field(default=False, description="Clear cache before prewarming")


@router.get("/security/summary")
async def security_summary() -> dict:
    """Return aggregate security counters without request bodies or secrets."""
    return get_security_summary()


@router.get("/model/cache")
async def model_cache_status() -> dict[str, Any]:
    """Return lightweight Kronos model cache diagnostics without loading a model."""
    stats = predictor_cache_stats()
    return {"ok": True, "cache": stats, "checked_at": time.time()}


@router.post("/model/clear-cache")
async def model_clear_cache() -> dict[str, Any]:
    """Clear the in-process Kronos predictor cache for controlled troubleshooting."""
    before = predictor_cache_stats()
    clear_predictor_cache()
    after = predictor_cache_stats()
    return {"ok": True, "before": before, "after": after, "checked_at": time.time()}


@router.post("/model/prewarm")
async def model_prewarm(req: ModelPrewarmRequest | None = None) -> dict[str, Any]:
    """Prewarm the configured Kronos predictor and return load/cache metadata."""
    try:
        if req and req.force:
            clear_predictor_cache()
        result = prewarm_default_predictor()
        return {"ok": True, "result": result, "checked_at": time.time()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
