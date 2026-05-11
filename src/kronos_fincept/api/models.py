"""Pydantic models for API request/response validation."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from kronos_fincept.schemas import DEFAULT_MODEL_ID, DEFAULT_TOKENIZER_ID
from kronos_fincept.security_utils import validate_kronos_model_id


SYMBOL_PATTERN = r"^[A-Za-z0-9._=\-^/]{1,32}$"
MARKET_PATTERN = r"^[A-Za-z0-9_-]{1,16}$"
DATE_PATTERN = r"^\d{8}$"


# ── Forecast ──────────────────────────────────────────────

class ForecastRowIn(BaseModel):
    """One OHLCV row."""
    timestamp: str = Field(..., min_length=1, max_length=40)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float = 0.0


class ForecastRequestIn(BaseModel):
    """POST /api/forecast request body."""
    symbol: str = Field(..., min_length=1, max_length=32, pattern=SYMBOL_PATTERN, description="Stock symbol, e.g. '600036'")
    timeframe: str = Field(default="1d", min_length=1, max_length=16, description="Timeframe: 1d, 1h, etc.")
    pred_len: int = Field(default=5, ge=1, le=60, description="Number of future bars to predict")
    rows: list[ForecastRowIn] = Field(..., min_length=1, max_length=1024, description="Historical OHLCV data")
    model_id: str | None = Field(default=DEFAULT_MODEL_ID, max_length=64)
    tokenizer_id: str | None = Field(default=DEFAULT_TOKENIZER_ID, max_length=64)
    dry_run: bool = Field(default=False, description="Use deterministic mock predictor")
    max_context: int = Field(default=512, ge=1, le=2048)
    temperature: float = Field(default=1.0, gt=0, le=2)
    top_k: int = Field(default=0, ge=0, le=100)
    top_p: float = Field(default=0.9, gt=0, le=1)
    sample_count: int = Field(default=1, ge=1, le=8)

    @field_validator("model_id")
    @classmethod
    def _validate_model_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_kronos_model_id(value)


class ForecastMetadataOut(BaseModel):
    device: str
    elapsed_ms: int
    backend: str
    warning: str
    model_cached: bool = False
    cache_key: str = ""
    load_wait_ms: int = 0
    inference_wait_ms: int = 0


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
    symbol: str = Field(..., min_length=1, max_length=32, pattern=SYMBOL_PATTERN)
    timeframe: str = Field(default="1d", min_length=1, max_length=16)
    rows: list[ForecastRowIn] = Field(..., min_length=1, max_length=1024)
    model_id: str | None = Field(default=None, max_length=64)
    tokenizer_id: str | None = Field(default=None, max_length=64)
    max_context: int | None = Field(default=None, ge=1, le=2048)
    temperature: float | None = Field(default=None, gt=0, le=2)
    top_k: int | None = Field(default=None, ge=0, le=100)
    top_p: float | None = Field(default=None, gt=0, le=1)
    sample_count: int | None = Field(default=None, ge=1, le=8)

    @field_validator("model_id")
    @classmethod
    def _validate_model_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_kronos_model_id(value)


class BatchForecastRequestIn(BaseModel):
    """POST /api/batch request body."""
    assets: list[BatchForecastItemIn] = Field(..., min_length=1, max_length=20)
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
    market: str = "cn"
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
    symbols: list[str] = Field(..., min_length=1, max_length=20, description="Stock symbols to backtest")
    start_date: str = Field(..., pattern=DATE_PATTERN, description="Start date YYYYMMDD")
    end_date: str = Field(..., pattern=DATE_PATTERN, description="End date YYYYMMDD")
    top_k: int = Field(default=3, ge=1, le=20, description="Number of top stocks to hold")
    pred_len: int = Field(default=5, ge=1, le=60)
    window_size: int = Field(default=60, ge=10, le=250, description="Lookback window for each prediction")
    step: int = Field(default=5, ge=1, le=60, description="Trading days between rebalances")
    initial_equity: float = Field(default=100000.0, gt=0, description="Initial portfolio equity")
    benchmark: str | None = Field(default=None, max_length=32, description="Optional benchmark symbol for UI/report alignment")
    fee_bps: float = Field(default=0.0, ge=0, le=1000, description="One-way trading fee in basis points")
    slippage_bps: float = Field(default=0.0, ge=0, le=1000, description="One-way slippage in basis points")
    dry_run: bool = True

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, values: list[str]) -> list[str]:
        pattern = re.compile(SYMBOL_PATTERN)
        for value in values:
            if not pattern.match(str(value)):
                raise ValueError("invalid symbol")
        return values


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
    app_version: str
    build_commit: str
    build_ref: str
    build_source: str
    model_loaded: bool
    model_id: str
    tokenizer_id: str | None = None
    device: str
    uptime_seconds: float
    runtime_mode: str = "standard"
    model_enabled: bool = True
    deep_check: bool = False
    capabilities: dict[str, bool] = Field(default_factory=dict)
    model_error: str | None = None


# ── Backtest Report ─────────────────────────────────────────

class BacktestReportRequestIn(BaseModel):
    """POST /api/backtest/report request body."""
    symbols: list[str] = Field(..., min_length=1, max_length=20, description="Stock symbols to backtest")
    start_date: str = Field(..., pattern=DATE_PATTERN, description="Start date YYYYMMDD")
    end_date: str = Field(..., pattern=DATE_PATTERN, description="End date YYYYMMDD")
    top_k: int = Field(default=3, ge=1, le=20, description="Number of top stocks to hold")
    pred_len: int = Field(default=5, ge=1, le=60)
    window_size: int = Field(default=60, ge=10, le=250, description="Lookback window for each prediction")
    step: int = Field(default=5, ge=1, le=60, description="Trading days between rebalances")
    initial_equity: float = Field(default=100000.0, gt=0, description="Initial portfolio equity")
    fee_bps: float = Field(default=0.0, ge=0, le=1000, description="One-way trading fee in basis points")
    slippage_bps: float = Field(default=0.0, ge=0, le=1000, description="One-way slippage in basis points")
    dry_run: bool = True
    benchmark: str | None = Field(default=None, max_length=32, description="Benchmark index symbol, e.g. '000300' for CSI 300")
    strategy_name: str = Field(default="Ranking Strategy", min_length=1, max_length=80, description="Display name for the report")

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, values: list[str]) -> list[str]:
        pattern = re.compile(SYMBOL_PATTERN)
        for value in values:
            if not pattern.match(str(value)):
                raise ValueError("invalid symbol")
        return values


class BacktestReportResponseOut(BaseModel):
    ok: bool
    html: str
    filename: str
