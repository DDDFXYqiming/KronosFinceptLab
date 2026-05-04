"""POST /api/v1/analyze/ai — AI-powered stock analysis with Kronos prediction.
v8.0: New endpoint for frontend analysis panel. Supports all markets."""

from __future__ import annotations

import logging
import json
import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from kronos_fincept.api.models import ForecastMetadataOut
from kronos_fincept.logging_config import log_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analyze", tags=["analysis"])


# ── Pydantic models ──

from pydantic import BaseModel, Field


class AIAnalyzeRequest(BaseModel):
    symbol: str = Field(..., description="Stock symbol, e.g. '600036', 'AAPL', '0700.HK'")
    market: str = Field(default="cn", description="Market: cn=A股, hk=港股, us=美股, commodity=大宗商品")


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
    question: str = Field(..., min_length=1, description="Natural-language analysis question")
    symbol: str | None = Field(default=None, description="Optional explicit symbol override")
    market: str | None = Field(default=None, description="Optional market override")
    context: dict[str, Any] | None = Field(default=None, description="Optional page/session context")
    dry_run: bool = Field(default=False, description="Use deterministic Kronos dry-run for tests")


class MacroAnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Macro or cross-market analysis question")
    symbols: list[str] = Field(default_factory=list, description="Optional related symbols")
    market: str | None = Field(default=None, description="Optional market hint")
    provider_ids: list[str] | None = Field(default=None, description="Optional provider id override")
    context: dict[str, Any] | None = Field(default=None, description="Optional page/session context")


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

        result = await asyncio.to_thread(
            analyze_macro_question,
            req.question,
            symbols=req.symbols,
            market=req.market,
            provider_ids=req.provider_ids,
            context=req.context,
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


@router.post("/ai", response_model=AIAnalyzeResponse)
async def ai_analyze(req: AIAnalyzeRequest) -> AIAnalyzeResponse:
    """Run full AI analysis on a stock — fetches data, calculates risk,
    runs Kronos prediction, then generates DeepSeek-powered analysis."""
    try:
        from kronos_fincept.financial import AIInvestmentAdvisor, RiskCalculator
        from kronos_fincept.schemas import ForecastRequest, ForecastRow
        from kronos_fincept.service import forecast_from_request
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
        from datetime import datetime

        # ── 1. Fetch price data ──
        price_data = None
        if req.market == "cn":
            price_data = fetch_a_stock_ohlcv(
                symbol=req.symbol,
                start_date="20250101",
                end_date=datetime.now().strftime("%Y%m%d"),
            )
        else:
            # For HK/US/commodity — try Yahoo Finance directly
            try:
                from kronos_fincept.financial import GlobalMarketSource
                gms = GlobalMarketSource()
                raw_data = gms.fetch_data(req.symbol, market=req.market)
                if raw_data and len(raw_data) > 0:
                    price_data = raw_data
            except Exception as e:
                log_event(
                    logger,
                    logging.WARNING,
                    "ai_analysis.global_market_fetch.failure",
                    "Global market fetch failed",
                    symbol=req.symbol,
                    market=req.market,
                    error_type=type(e).__name__,
                    error=str(e),
                )

        if not price_data or len(price_data) == 0:
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
                error=f"No price data available for {req.symbol} ({req.market})",
            )

        closes = [row["close"] for row in price_data]
        latest = price_data[-1]

        market_data = {
            "current_price": latest["close"],
            "data_points": len(price_data),
            "price_change_1d": (latest["close"] - price_data[-2]["close"]) / price_data[-2]["close"] * 100 if len(price_data) > 1 else 0,
            "price_change_1w": (latest["close"] - price_data[-5]["close"]) / price_data[-5]["close"] * 100 if len(price_data) > 5 else 0,
            "volume": latest.get("volume", 0),
            "high_52w": max(closes) if closes else 0,
            "low_52w": min(closes) if closes else 0,
        }

        # ── 2. Risk metrics ──
        risk_data = None
        try:
            risk_calc = RiskCalculator()
            risk_metrics = risk_calc.calculate_risk_metrics(req.symbol, closes)
            risk_data = {
                "var_95": risk_metrics.var_95,
                "sharpe_ratio": risk_metrics.sharpe_ratio,
                "max_drawdown": risk_metrics.max_drawdown,
                "volatility": risk_metrics.volatility,
                "sortino_ratio": getattr(risk_metrics, "sortino_ratio", 0),
            }
        except Exception as e:
            log_event(
                logger,
                logging.WARNING,
                "ai_analysis.risk_calc.failure",
                "Risk calc failed",
                symbol=req.symbol,
                market=req.market,
                error_type=type(e).__name__,
                error=str(e),
            )

        # ── 3. Kronos prediction ──
        prediction_data = None
        try:
            forecast_rows = [
                ForecastRow(
                    timestamp=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)),
                    amount=float(row.get("amount", 0)),
                )
                for row in price_data[-100:]
            ]

            request = ForecastRequest(
                symbol=req.symbol,
                timeframe="1d",
                rows=forecast_rows,
                pred_len=5,
                sample_count=1,
            )

            result = forecast_from_request(request)
            if result["ok"]:
                prediction_data = ForecastDataOut(
                    model=result.get("model_id", "Kronos"),
                    prediction_days=5,
                    forecast=result["forecast"],
                    probabilistic=result.get("probabilistic"),
                )
        except Exception as e:
            log_event(
                logger,
                logging.WARNING,
                "ai_analysis.kronos_prediction.failure",
                "Kronos prediction failed",
                symbol=req.symbol,
                market=req.market,
                error_type=type(e).__name__,
                error=str(e),
            )

        # ── 4. AI Analysis ──
        advisor = AIInvestmentAdvisor()
        ai_result = advisor.analyze_stock(req.symbol, market_data, risk_data, prediction_data.dict() if prediction_data else None)

        return AIAnalyzeResponse(
            ok=True,
            symbol=ai_result.symbol,
            market=req.market,
            summary=ai_result.summary,
            detailed_analysis=ai_result.detailed_analysis,
            recommendation=ai_result.recommendation,
            confidence=ai_result.confidence,
            risk_level=ai_result.risk_level,
            current_price=latest["close"],
            risk_metrics=risk_data,
            kronos_prediction=prediction_data,
            timestamp=ai_result.timestamp,
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
