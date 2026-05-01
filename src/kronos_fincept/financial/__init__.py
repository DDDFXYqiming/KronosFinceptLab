"""
Financial analysis module for CFA-level analysis.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    # Schemas
    "FinancialData": ".schemas",
    "IncomeStatement": ".schemas",
    "BalanceSheet": ".schemas",
    "CashFlowStatement": ".schemas",
    "FinancialStatementType": ".schemas",

    # Financial data
    "FinancialDataSource": ".financial_source",
    "FinancialDataManager": ".manager",

    # DCF
    "DCFModel": ".dcf",
    "DCFResult": ".dcf",

    # Risk metrics
    "RiskCalculator": ".risk",
    "RiskMetrics": ".risk",

    # Portfolio optimization
    "PortfolioOptimizer": ".portfolio",
    "PortfolioResult": ".portfolio",

    # Derivatives pricing
    "DerivativesPricer": ".derivatives",
    "OptionResult": ".derivatives",

    # Technical indicators
    "TechnicalIndicators": ".indicators",
    "SMA": ".indicators",
    "EMA": ".indicators",
    "RSI": ".indicators",
    "MACD": ".indicators",
    "BollingerBands": ".indicators",
    "KDJ": ".indicators",
    "ATR": ".indicators",
    "OBV": ".indicators",

    # Trading strategies
    "QuantitativeStrategies": ".strategies",
    "StrategyResult": ".strategies",
    "Signal": ".strategies",

    # Global market
    "GlobalMarketSource": ".global_market",

    # AI Advisor
    "AIInvestmentAdvisor": ".ai_advisor",
    "AIAnalysisResult": ".ai_advisor",
}


def __getattr__(name: str) -> Any:
    """Load financial submodules only when a public symbol is requested."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value

__all__ = [
    "FinancialData",
    "IncomeStatement",
    "BalanceSheet",
    "CashFlowStatement",
    "FinancialStatementType",
    "FinancialDataSource",
    "FinancialDataManager",
    "DCFModel",
    "DCFResult",
    "RiskCalculator",
    "RiskMetrics",
    "PortfolioOptimizer",
    "PortfolioResult",
    "DerivativesPricer",
    "OptionResult",
    "TechnicalIndicators",
    "SMA",
    "EMA",
    "RSI",
    "MACD",
    "BollingerBands",
    "KDJ",
    "ATR",
    "OBV",
    "QuantitativeStrategies",
    "StrategyResult",
    "Signal",
    "GlobalMarketSource",
    "AIInvestmentAdvisor",
    "AIAnalysisResult",
]
