"""Watchlist and portfolio research endpoints."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from kronos_fincept.api.models import MARKET_PATTERN, SYMBOL_PATTERN
from kronos_fincept.runtime_store import get_runtime_store
from kronos_fincept.schemas import RESEARCH_WARNING

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _normalize_symbol_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        symbol = str(value).strip().upper()
        if not symbol or symbol in seen:
            continue
        normalized.append(symbol)
        seen.add(symbol)
    return normalized


class WatchlistRankingIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32, pattern=SYMBOL_PATTERN)
    predicted_return: float = Field(..., ge=-1.0, le=1.0)
    last_close: float | None = Field(default=None, ge=0)
    predicted_close: float | None = Field(default=None, ge=0)


class WatchlistResearchRequest(BaseModel):
    name: str = Field(default="Watchlist", min_length=1, max_length=80)
    symbols: list[str] = Field(..., min_length=1, max_length=100)
    weights: dict[str, float] = Field(default_factory=dict)
    rankings: list[WatchlistRankingIn] = Field(default_factory=list)

    @field_validator("symbols")
    @classmethod
    def _normalize_symbols(cls, values: list[str]) -> list[str]:
        return _normalize_symbol_list(values)


class WatchlistListIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    market: str = Field(default="cn", min_length=1, max_length=16, pattern=MARKET_PATTERN)
    symbols: list[str] = Field(..., min_length=1, max_length=100)
    weights: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("symbols")
    @classmethod
    def _normalize_symbols(cls, values: list[str]) -> list[str]:
        return _normalize_symbol_list(values)


class WatchlistListOut(BaseModel):
    ok: bool = True
    id: str
    name: str
    market: str
    symbols: list[str]
    weights: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    created_at: float
    updated_at: float


class WatchlistCollectionOut(BaseModel):
    ok: bool = True
    watchlists: list[WatchlistListOut]
    total: int


class WatchlistDeleteOut(BaseModel):
    ok: bool = True
    id: str
    deleted: bool


class WatchlistResearchResponse(BaseModel):
    ok: bool = True
    name: str
    symbol_count: int
    expected_return: float
    weighted_return: float
    top_symbols: list[str]
    risk_flags: list[str]
    rows: list[dict[str, Any]]
    metadata: dict[str, Any]


def build_watchlist_research(req: WatchlistResearchRequest) -> WatchlistResearchResponse:
    ranking_by_symbol = {item.symbol.upper(): item for item in req.rankings}
    raw_weights = {str(key).upper(): float(value) for key, value in req.weights.items() if float(value) >= 0}
    covered_weight = sum(raw_weights.get(symbol, 0.0) for symbol in req.symbols)
    equal_weight = 1.0 / len(req.symbols)

    rows: list[dict[str, Any]] = []
    for symbol in req.symbols:
        ranking = ranking_by_symbol.get(symbol)
        weight = raw_weights.get(symbol, 0.0)
        if covered_weight <= 0:
            weight = equal_weight
        elif symbol in raw_weights:
            weight = weight / covered_weight
        else:
            weight = 0.0
        predicted_return = float(ranking.predicted_return) if ranking else 0.0
        rows.append({
            "symbol": symbol,
            "weight": round(weight, 6),
            "predicted_return": round(predicted_return, 6),
            "weighted_contribution": round(weight * predicted_return, 6),
            "last_close": ranking.last_close if ranking else None,
            "predicted_close": ranking.predicted_close if ranking else None,
            "covered": ranking is not None,
        })

    weighted_return = sum(row["weighted_contribution"] for row in rows)
    missing = [row["symbol"] for row in rows if not row["covered"]]
    negative = [row["symbol"] for row in rows if row["predicted_return"] < -0.02]
    concentrated = [row["symbol"] for row in rows if row["weight"] > 0.6]
    risk_flags: list[str] = []
    if missing:
        risk_flags.append(f"missing_forecast:{','.join(missing)}")
    if negative:
        risk_flags.append(f"negative_signal:{','.join(negative)}")
    if concentrated:
        risk_flags.append(f"concentrated_weight:{','.join(concentrated)}")

    top_symbols = [row["symbol"] for row in sorted(rows, key=lambda item: item["predicted_return"], reverse=True)]
    return WatchlistResearchResponse(
        name=req.name,
        symbol_count=len(req.symbols),
        expected_return=round(weighted_return, 6),
        weighted_return=round(weighted_return, 6),
        top_symbols=top_symbols,
        risk_flags=risk_flags,
        rows=rows,
        metadata={"warning": RESEARCH_WARNING},
    )


@router.post("/research", response_model=WatchlistResearchResponse)
async def watchlist_research(req: WatchlistResearchRequest) -> WatchlistResearchResponse:
    """Summarize watchlist forecast rankings into a weighted portfolio research view."""
    return build_watchlist_research(req)


def _watchlist_payload(req: WatchlistListIn, watchlist_id: str | None = None, created_at: float | None = None) -> dict[str, Any]:
    now = time.time()
    return {
        "id": watchlist_id or uuid.uuid4().hex,
        "name": req.name,
        "market": req.market,
        "symbols": req.symbols,
        "weights": {str(key).upper(): float(value) for key, value in req.weights.items() if float(value) >= 0},
        "tags": [str(tag).strip() for tag in req.tags if str(tag).strip()],
        "note": req.note,
        "created_at": created_at or now,
        "updated_at": now,
    }


def get_watchlist_snapshot(watchlist_id: str) -> dict[str, Any] | None:
    return get_runtime_store().get_watchlist(watchlist_id)


def _watchlist_out(item: dict[str, Any]) -> WatchlistListOut:
    return WatchlistListOut(**item)


@router.get("/lists", response_model=WatchlistCollectionOut)
async def list_watchlists() -> WatchlistCollectionOut:
    items = get_runtime_store().list_watchlists()
    return WatchlistCollectionOut(watchlists=[_watchlist_out(item) for item in items], total=len(items))


@router.post("/lists", response_model=WatchlistListOut)
async def create_watchlist(req: WatchlistListIn) -> WatchlistListOut:
    item = _watchlist_payload(req)
    get_runtime_store().upsert_watchlist(item)
    return _watchlist_out(item)


@router.get("/lists/{watchlist_id}", response_model=WatchlistListOut)
async def get_watchlist(watchlist_id: str) -> WatchlistListOut:
    item = get_runtime_store().get_watchlist(watchlist_id)
    if not item:
        raise HTTPException(status_code=404, detail="watchlist not found")
    return _watchlist_out(item)


@router.put("/lists/{watchlist_id}", response_model=WatchlistListOut)
async def update_watchlist(watchlist_id: str, req: WatchlistListIn) -> WatchlistListOut:
    existing = get_runtime_store().get_watchlist(watchlist_id)
    if not existing:
        raise HTTPException(status_code=404, detail="watchlist not found")
    item = _watchlist_payload(req, watchlist_id=watchlist_id, created_at=float(existing.get("created_at", time.time())))
    get_runtime_store().upsert_watchlist(item)
    return _watchlist_out(item)


@router.delete("/lists/{watchlist_id}", response_model=WatchlistDeleteOut)
async def delete_watchlist(watchlist_id: str) -> WatchlistDeleteOut:
    deleted = get_runtime_store().delete_watchlist(watchlist_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="watchlist not found")
    return WatchlistDeleteOut(id=watchlist_id, deleted=True)
