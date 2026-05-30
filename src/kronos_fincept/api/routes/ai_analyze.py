"""POST /api/v1/analyze/ai — AI-powered stock analysis with Kronos prediction.
v8.0: New endpoint for frontend analysis panel. Supports all markets."""

from __future__ import annotations

import logging
import json
import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from kronos_fincept.api.models import ForecastMetadataOut
from kronos_fincept.logging_config import log_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analyze", tags=["analysis"])


# ── Pydantic models ──

from pydantic import BaseModel, Field, field_validator

from kronos_fincept.security_utils import contains_prompt_injection, sanitize_client_context


class AIAnalyzeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32, description="Stock symbol, e.g. '600036', 'AAPL', '0700.HK'")
    market: str = Field(default="cn", min_length=1, max_length=16, description="Market: cn=A股, hk=港股, us=美股, commodity=大宗商品")


class ForecastDataOut(BaseModel):
    model: str
    prediction_days: int
    forecast: list[dict[str, Any]]
    probabilistic: dict[str, Any] | None = None


class AIAnalyzeResponse(BaseModel):
    ok: bool
    symbol: str
    market: str
    summary: str
    detailed_analysis: str
    recommendation: str
    confidence: float
    risk_level: str
    current_price: float
    risk_metrics: dict[str, Any] | None = None
    kronos_prediction: ForecastDataOut | None = None
    timestamp: str
    error: str | None = None


class AgentAnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Natural-language analysis question")
    symbol: str | None = Field(default=None, max_length=32, description="Optional explicit symbol override")
    market: str | None = Field(default=None, max_length=16, description="Optional market override")
    context: dict[str, Any] | None = Field(default=None, description="Optional page/session context")
    dry_run: bool = Field(default=False, description="Use deterministic Kronos dry-run for tests")

    @field_validator("context")
    @classmethod
    def _sanitize_context(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return sanitize_client_context(value)

    @field_validator("question")
    @classmethod
    def _reject_prompt_injection(cls, value: str) -> str:
        if contains_prompt_injection(value):
            raise ValueError("question contains unsafe prompt-injection content")
        return value


class MacroAnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Macro or cross-market analysis question")
    symbols: list[str] = Field(default_factory=list, max_length=20, description="Optional related symbols")
    market: str | None = Field(default=None, max_length=16, description="Optional market hint")
    provider_ids: list[str] | None = Field(default=None, max_length=20, description="Optional provider id override")
    mode: Literal["fast", "complete"] = Field(default="fast", description="fast uses dashboard timeouts; complete uses longer provider collection")
    context: dict[str, Any] | None = Field(default=None, description="Optional page/session context")

    @field_validator("context")
    @classmethod
    def _sanitize_context(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return sanitize_client_context(value)

    @field_validator("question")
    @classmethod
    def _reject_prompt_injection(cls, value: str) -> str:
        if contains_prompt_injection(value):
            raise ValueError("question contains unsafe prompt-injection content")
        return value

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(str(value)) > 32:
                raise ValueError("symbol is too long")
        return values


class AgentAnalyzeResponse(BaseModel):
    ok: bool
    question: str
    symbol: str | None = None
    symbols: list[str] = Field(default_factory=list)
    market: str | None = None
    report: dict[str, Any]
    final_report: str
    recommendation: str
    confidence: float
    risk_level: str
    current_price: float | None = None
    risk_metrics: dict[str, Any] | None = None
    kronos_prediction: dict[str, Any] | None = None
    asset_results: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: str
    rejected: bool = False
    security_reason: str | None = None
    clarification_required: bool = False
    clarifying_question: str | None = None
    error: str | None = None
    macro_provider_coverage: dict[str, Any] | None = None
    macro_data_quality: dict[str, Any] | None = None
    macro_dimension_coverage: dict[str, Any] | None = None
    macro_evidence_insufficiency: dict[str, Any] | None = None
    evidence_pack: dict[str, Any] | None = None
    cited_claims: list[dict[str, Any]] = Field(default_factory=list)
    confidence_breakdown: dict[str, float] | None = None


# ── Endpoints ──


@router.post("/agent", response_model=AgentAnalyzeResponse)
async def agent_analyze(req: AgentAnalyzeRequest) -> AgentAnalyzeResponse:
    """Run the shared stateless natural-language AI analysis agent."""
    try:
        from kronos_fincept.agent import analyze_investment_question

        result = await asyncio.to_thread(
            analyze_investment_question,
            req.question,
            symbol=req.symbol,
            market=req.market,
            context=req.context,
            dry_run=req.dry_run,
        )
        return AgentAnalyzeResponse(**result.to_dict())
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "agent.analysis.failure",
            "Agent analysis failed",
            symbol=req.symbol,
            market=req.market,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        from datetime import datetime

        return AgentAnalyzeResponse(
            ok=False,
            question=req.question,
            report={
                "conclusion": "Agent 分析失败。",
                "risk": str(exc),
                "disclaimer": "本报告仅供研究，不构成投资建议。",
            },
            final_report=f"Agent 分析失败：{exc}",
            recommendation="失败",
            confidence=0.0,
            risk_level="未知",
            tool_calls=[],
            steps=[{"name": "执行", "status": "failed", "summary": str(exc), "elapsed_ms": 0}],
            timestamp=datetime.now().isoformat(),
            error=str(exc),
        )


@router.post("/macro", response_model=AgentAnalyzeResponse)
async def macro_analyze(req: MacroAnalyzeRequest) -> AgentAnalyzeResponse:
    """Run macro-only signal analysis backed by Digital Oracle style providers."""
    try:
        from kronos_fincept.agent import analyze_macro_question

        context = {**(req.context or {}), "macro_mode": req.mode}
        result = await asyncio.to_thread(
            analyze_macro_question,
            req.question,
            symbols=req.symbols,
            market=req.market,
            provider_ids=req.provider_ids,
            context=context,
        )
        return AgentAnalyzeResponse(**result.to_dict())
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "macro.analysis.failure",
            "Macro analysis failed",
            market=req.market,
            symbols=req.symbols,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        from datetime import datetime

        return AgentAnalyzeResponse(
            ok=False,
            question=req.question,
            report={
                "conclusion": "宏观分析失败。",
                "risk": str(exc),
                "disclaimer": "本报告仅供研究，不构成投资建议。",
            },
            final_report=f"宏观分析失败：{exc}",
            recommendation="失败",
            confidence=0.0,
            risk_level="未知",
            tool_calls=[],
            steps=[{"name": "执行", "status": "failed", "summary": str(exc), "elapsed_ms": 0}],
            timestamp=datetime.now().isoformat(),
            error=str(exc),
        )


@router.get("/macro/providers/status")
async def macro_provider_status(mode: Literal["fast", "complete"] = Query("fast")) -> dict[str, Any]:
    """Return macro provider operational status without running LLM synthesis."""
    from kronos_fincept.agent import _create_macro_data_manager

    manager = _create_macro_data_manager(fast_mode=(mode == "fast"))
    return {"ok": True, "mode": mode, "providers": manager.provider_status()}


@router.post("/ai", response_model=AIAnalyzeResponse)
async def ai_analyze(req: AIAnalyzeRequest) -> AIAnalyzeResponse:
    """Run full AI analysis through the shared OpenRouter→DeepSeek agent chain."""
    try:
        from kronos_fincept.agent import analyze_investment_question

        question = f"请分析 {req.symbol} 的当前行情、Kronos 预测、风险和投资建议。"
        result = await asyncio.to_thread(
            analyze_investment_question,
            question,
            symbol=req.symbol,
            market=req.market,
            context={"source": "api_ai_analyze", "channel": "web"},
        )
        report = result.report or {}
        return AIAnalyzeResponse(
            ok=result.ok,
            symbol=result.symbol or req.symbol,
            market=result.market or req.market,
            summary=str(report.get("conclusion") or result.final_report or ""),
            detailed_analysis=result.final_report,
            recommendation=result.recommendation,
            confidence=result.confidence,
            risk_level=result.risk_level,
            current_price=float(result.current_price or 0.0),
            risk_metrics=result.risk_metrics,
            kronos_prediction=ForecastDataOut(**result.kronos_prediction) if result.kronos_prediction else None,
            timestamp=result.timestamp,
            error=result.error or result.security_reason or result.clarifying_question,
        )

    except Exception as e:
        log_event(
            logger,
            logging.ERROR,
            "ai_analysis.failure",
            "AI analysis failed",
            symbol=req.symbol,
            market=req.market,
            error_type=type(e).__name__,
            exc_info=True,
        )
        return AIAnalyzeResponse(
            ok=False,
            symbol=req.symbol,
            market=req.market,
            summary="",
            detailed_analysis="",
            recommendation="",
            confidence=0.0,
            risk_level="",
            current_price=0.0,
            timestamp="",
            error=str(e),
        )
