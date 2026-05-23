"""Admin-only operational diagnostics."""

from __future__ import annotations

from fastapi import APIRouter

from kronos_fincept.api.security import get_security_summary

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/security/summary")
async def security_summary() -> dict:
    """Return aggregate security counters without request bodies or secrets."""
    return get_security_summary()
