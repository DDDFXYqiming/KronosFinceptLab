"""
API routes for financial analysis (v4.0).
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, List, Dict
import pandas as pd

router = APIRouter(prefix="/api/v1/analyze", tags=["analysis"])

SYMBOL_PATTERN = r"^[A-Za-z0-9._=\-^/]{1,32}$"
PORTFOLIO_METHODS = {"max_sharpe", "min_vol", "risk_parity", "efficient_frontier"}


# Request/Response models
class DCFRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32, pattern=SYMBOL_PATTERN)
    shares_outstanding: float = Field(default=1_000_000_000, gt=0, le=10_000_000_000_000)
    beta: float = Field(default=1.0, ge=0, le=5)
    debt_value: float = Field(default=0.0, ge=0, le=1_000_000_000_000_000)
    cash_value: float = Field(default=0.0, ge=0, le=1_000_000_000_000_000)
    tax_rate: float = Field(default=0.25, ge=0, le=1)


class DCFResponse(BaseModel):
    symbol: str
    enterprise_value: float
    equity_value: float
    per_share_value: float
    wacc: float
    terminal_growth_rate: float
    projection_years: int


class RiskRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32, pattern=SYMBOL_PATTERN)
    market_symbol: Optional[str] = Field(default="000300", max_length=32, pattern=SYMBOL_PATTERN)
    days: int = Field(default=252, ge=20, le=1024)


class RiskResponse(BaseModel):
    symbol: str
    var_95: float
    var_99: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    volatility: float
    downside_deviation: float
    beta: Optional[float]
    alpha: Optional[float]


class PortfolioRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=2, max_length=20)
    method: str = Field(default="max_sharpe", max_length=32)
    risk_free_rate: float = Field(default=0.03, ge=-0.1, le=0.5)
    days: int = Field(default=252, ge=20, le=1024)

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, values: list[str]) -> list[str]:
        import re

        pattern = re.compile(SYMBOL_PATTERN)
        for value in values:
            if not pattern.match(str(value)):
                raise ValueError("invalid symbol")
        return values

    @field_validator("method")
    @classmethod
    def _validate_method(cls, value: str) -> str:
        if value not in PORTFOLIO_METHODS:
            raise ValueError("invalid optimization method")
        return value


class PortfolioResponse(BaseModel):
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    method: str


class DerivativeRequest(BaseModel):
    underlying_price: float = Field(..., gt=0, le=1_000_000_000)
    strike_price: float = Field(..., gt=0, le=1_000_000_000)
    time_to_expiration: float = Field(..., gt=0, le=100)
    volatility: float = Field(..., gt=0, le=10)
    risk_free_rate: float = Field(default=0.03, ge=-0.1, le=0.5)
    option_type: Literal["call", "put"] = "call"


class DerivativeResponse(BaseModel):
    option_type: str
    underlying_price: float
    strike_price: float
    time_to_expiration: float
    volatility: float
    option_price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    intrinsic_value: float
    time_value: float


# Endpoints
@router.post("/dcf", response_model=DCFResponse)
async def analyze_dcf(request: DCFRequest):
    """DCF valuation analysis."""
    try:
        from kronos_fincept.financial import DCFModel, FinancialDataManager
        
        # Get financial data
        fin_manager = FinancialDataManager()
        financial_data = fin_manager.get_financial_data(request.symbol)
        
        if not financial_data:
            raise HTTPException(status_code=404, detail=f"Financial data not found for {request.symbol}")
        
        # Run DCF valuation
        dcf_model = DCFModel()
        result = dcf_model.value_company(
            financial_data=financial_data,
            shares_outstanding=request.shares_outstanding,
            beta=request.beta,
            debt_value=request.debt_value,
            cash_value=request.cash_value,
            tax_rate=request.tax_rate
        )
        
        if not result:
            raise HTTPException(status_code=500, detail="DCF valuation failed")
        
        return DCFResponse(
            symbol=result.symbol,
            enterprise_value=result.enterprise_value,
            equity_value=result.equity_value,
            per_share_value=result.per_share_value,
            wacc=result.wacc,
            terminal_growth_rate=result.terminal_growth_rate,
            projection_years=result.projection_years
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk", response_model=RiskResponse)
async def analyze_risk(request: RiskRequest):
    """Risk metrics analysis."""
    try:
        from kronos_fincept.financial import RiskCalculator
        from kronos_fincept.data_sources import DataSourceManager
        
        # Get price data
        data_manager = DataSourceManager()
        
        # Get asset prices
        asset_data = data_manager.get_data(request.symbol, period=request.days)
        if not asset_data or len(asset_data) == 0:
            raise HTTPException(status_code=404, detail=f"Price data not found for {request.symbol}")
        
        asset_prices = [row['close'] for row in asset_data]
        
        # Get market prices for beta
        market_prices = None
        if request.market_symbol:
            market_data = data_manager.get_data(request.market_symbol, period=request.days)
            if market_data and len(market_data) > 0:
                market_prices = [row['close'] for row in market_data]
        
        # Calculate risk metrics
        calculator = RiskCalculator()
        metrics = calculator.calculate_risk_metrics(
            symbol=request.symbol,
            prices=asset_prices,
            market_prices=market_prices
        )
        
        return RiskResponse(
            symbol=metrics.symbol,
            var_95=metrics.var_95,
            var_99=metrics.var_99,
            sharpe_ratio=metrics.sharpe_ratio,
            sortino_ratio=metrics.sortino_ratio,
            max_drawdown=metrics.max_drawdown,
            volatility=metrics.volatility,
            downside_deviation=metrics.downside_deviation,
            beta=metrics.beta,
            alpha=metrics.alpha
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portfolio", response_model=PortfolioResponse)
async def analyze_portfolio(request: PortfolioRequest):
    """Portfolio optimization."""
    try:
        from kronos_fincept.financial import PortfolioOptimizer
        from kronos_fincept.data_sources import DataSourceManager
        
        if len(request.symbols) < 2:
            raise HTTPException(status_code=400, detail="At least 2 symbols required")
        
        # Get price data for all symbols
        data_manager = DataSourceManager()
        price_data = {}
        
        for symbol in request.symbols:
            data = data_manager.get_data(symbol, period=request.days)
            if data and len(data) > 0:
                price_data[symbol] = [row['close'] for row in data]
        
        if len(price_data) < 2:
            raise HTTPException(status_code=404, detail="Could not get price data for at least 2 symbols")
        
        # Create DataFrame
        min_length = min(len(prices) for prices in price_data.values())
        prices_df = pd.DataFrame({
            symbol: prices[:min_length] for symbol, prices in price_data.items()
        })
        
        # Optimize portfolio
        optimizer = PortfolioOptimizer(risk_free_rate=request.risk_free_rate)
        result = optimizer.optimize_portfolio(
            prices=prices_df,
            asset_names=list(price_data.keys()),
            optimization_method=request.method
        )
        
        return PortfolioResponse(
            weights=result.weights,
            expected_return=result.expected_return,
            volatility=result.volatility,
            sharpe_ratio=result.sharpe_ratio,
            method=request.method
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/derivative", response_model=DerivativeResponse)
async def analyze_derivative(request: DerivativeRequest):
    """Option pricing (Black-Scholes)."""
    try:
        from kronos_fincept.financial import DerivativesPricer
        
        if request.option_type not in ['call', 'put']:
            raise HTTPException(status_code=400, detail="option_type must be 'call' or 'put'")
        
        pricer = DerivativesPricer(risk_free_rate=request.risk_free_rate)
        
        result = pricer.black_scholes(
            underlying_price=request.underlying_price,
            strike_price=request.strike_price,
            time_to_expiration=request.time_to_expiration,
            volatility=request.volatility,
            option_type=request.option_type
        )
        
        return DerivativeResponse(
            option_type=result.option_type,
            underlying_price=result.underlying_price,
            strike_price=result.strike_price,
            time_to_expiration=result.time_to_expiration,
            volatility=result.volatility,
            option_price=result.option_price,
            delta=result.delta,
            gamma=result.gamma,
            theta=result.theta,
            vega=result.vega,
            rho=result.rho,
            intrinsic_value=result.intrinsic_value,
            time_value=result.time_value
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
