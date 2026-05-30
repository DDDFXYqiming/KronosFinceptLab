"""Watchlist and portfolio research endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from kronos_fincept.api.models import SYMBOL_PATTERN
from kronos_fincept.schemas import RESEARCH_WARNING

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


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
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            symbol = str(value).strip().upper()
            if not symbol or symbol in seen:
                continue
            normalized.append(symbol)
            seen.add(symbol)
        return normalized


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
