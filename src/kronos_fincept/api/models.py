"""Pydantic models for API request/response validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from kronos_fincept.schemas import DEFAULT_MODEL_ID, DEFAULT_TOKENIZER_ID


# ── Forecast ──────────────────────────────────────────────

class ForecastRowIn(BaseModel):
    """One OHLCV row."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float = 0.0


class ForecastRequestIn(BaseModel):
    """POST /api/forecast request body."""
    symbol: str = Field(..., description="Stock symbol, e.g. '600036'")
    timeframe: str = Field(default="1d", description="Timeframe: 1d, 1h, etc.")
    pred_len: int = Field(default=5, ge=1, le=60, description="Number of future bars to predict")
    rows: list[ForecastRowIn] = Field(..., min_length=1, description="Historical OHLCV data")
    model_id: str = Field(default=DEFAULT_MODEL_ID)
    tokenizer_id: str = Field(default=DEFAULT_TOKENIZER_ID)
    dry_run: bool = Field(default=False, description="Use deterministic mock predictor")
    max_context: int = Field(default=512, ge=1)
    temperature: float = Field(default=1.0, gt=0)
    top_k: int = Field(default=0, ge=0)
    top_p: float = Field(default=0.9, gt=0, le=1)
    sample_count: int = Field(default=1, ge=1)


class ForecastMetadataOut(BaseModel):
    device: str
    elapsed_ms: int
    backend: str
    warning: str


class ForecastRangeOut(BaseModel):
    min: float
    max: float


class ProbabilisticOut(BaseModel):
    sample_count: int
    upside_probability: float
    volatility_amplification: float
    forecast_range: ForecastRangeOut
    mean_final_close: float


class ForecastResponseOut(BaseModel):
    ok: bool
    symbol: str
    timeframe: str
    model_id: str
    tokenizer_id: str
    pred_len: int
    forecast: list[dict[str, Any]]
    probabilistic: ProbabilisticOut | None = None
    metadata: ForecastMetadataOut


# ── Batch ─────────────────────────────────────────────────

class BatchForecastItemIn(BaseModel):
    """One symbol in a batch request — shares format with single forecast but rows required."""
    symbol: str
    timeframe: str = "1d"
    rows: list[ForecastRowIn] = Field(..., min_length=1)
    model_id: str | None = None
    tokenizer_id: str | None = None
    max_context: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    sample_count: int | None = None


class BatchForecastRequestIn(BaseModel):
    """POST /api/batch request body."""
    assets: list[BatchForecastItemIn] = Field(..., min_length=1)
    pred_len: int = Field(default=5, ge=1, le=60)
    dry_run: bool = False


class RankedSignalOut(BaseModel):
    rank: int
    symbol: str
    last_close: float
    predicted_close: float
    predicted_return: float
    elapsed_ms: int


class BatchForecastResponseOut(BaseModel):
    ok: bool
    rankings: list[RankedSignalOut]
    metadata: ForecastMetadataOut


# ── Data ──────────────────────────────────────────────────

class DataResponseOut(BaseModel):
    ok: bool
    symbol: str
    count: int
    rows: list[dict[str, Any]]


class SearchResultOut(BaseModel):
    code: str
    name: str
    market: str


class SearchResponseOut(BaseModel):
    ok: bool
    results: list[SearchResultOut]


# ── Backtest ──────────────────────────────────────────────

class BacktestRequestIn(BaseModel):
    """POST /api/backtest/ranking request body."""
    symbols: list[str] = Field(..., min_length=1, description="Stock symbols to backtest")
    start_date: str = Field(..., description="Start date YYYYMMDD")
    end_date: str = Field(..., description="End date YYYYMMDD")
    top_k: int = Field(default=3, ge=1, description="Number of top stocks to hold")
    pred_len: int = Field(default=5, ge=1, le=60)
    window_size: int = Field(default=60, ge=10, le=250, description="Lookback window for each prediction")
    step: int = Field(default=5, ge=1, description="Trading days between rebalances")
    dry_run: bool = True


class BacktestMetricsOut(BaseModel):
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    win_rate: float
    avg_holding_days: int


class BacktestResponseOut(BaseModel):
    ok: bool
    symbols: list[str]
    start_date: str
    end_date: str
    top_k: int
    metrics: BacktestMetricsOut
    equity_curve: list[dict[str, Any]]
    metadata: ForecastMetadataOut


# ── Health ────────────────────────────────────────────────

class HealthResponseOut(BaseModel):
    status: str
    version: str
    model_loaded: bool
    model_id: str
    tokenizer_id: str | None = None
    device: str
    uptime_seconds: float
    capabilities: dict[str, bool] = Field(default_factory=dict)
    model_error: str | None = None


# ── Backtest Report ─────────────────────────────────────────

class BacktestReportRequestIn(BaseModel):
    """POST /api/backtest/report request body."""
    symbols: list[str] = Field(..., min_length=1, description="Stock symbols to backtest")
    start_date: str = Field(..., description="Start date YYYYMMDD")
    end_date: str = Field(..., description="End date YYYYMMDD")
    top_k: int = Field(default=3, ge=1, description="Number of top stocks to hold")
    pred_len: int = Field(default=5, ge=1, le=60)
    window_size: int = Field(default=60, ge=10, le=250, description="Lookback window for each prediction")
    step: int = Field(default=5, ge=1, description="Trading days between rebalances")
    dry_run: bool = True
    benchmark: str | None = Field(default=None, description="Benchmark index symbol, e.g. '000300' for CSI 300")
    strategy_name: str = Field(default="Ranking Strategy", description="Display name for the report")


class BacktestReportResponseOut(BaseModel):
    ok: bool
    html: str
    filename: str
