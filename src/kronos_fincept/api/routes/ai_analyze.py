"""POST /api/v1/analyze/ai — AI-powered stock analysis with Kronos prediction.
v8.0: New endpoint for frontend analysis panel. Supports all markets."""

from __future__ import annotations

import logging
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from kronos_fincept.api.models import ForecastMetadataOut

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


# ── Endpoints ──


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
                # Map market to Yahoo suffix
                yahoo_suffix = {"hk": ".HK", "us": "", "commodity": ""}
                suff = yahoo_suffix.get(req.market, "")
                yahoo_symbol = f"{req.symbol}{suff}" if suff else req.symbol
                raw_data = gms.fetch_data(yahoo_symbol)
                if raw_data and len(raw_data) > 0:
                    price_data = raw_data
            except Exception as e:
                logger.warning("Global market fetch failed: %s", e)

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
            logger.warning("Risk calc failed: %s", e)

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
                sample_count=100,
            )

            result = forecast_from_request(request)
            if result["ok"]:
                prediction_data = ForecastDataOut(
                    model="Kronos-base",
                    prediction_days=5,
                    forecast=result["forecast"],
                    probabilistic=result.get("probabilistic"),
                )
        except Exception as e:
            logger.warning("Kronos prediction failed: %s", e)

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
        logger.exception("AI analysis failed for %s", req.symbol)
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
