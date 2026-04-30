"""
Abstract base class for financial data sources.
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from .schemas import FinancialData, IncomeStatement, BalanceSheet, CashFlowStatement


class FinancialDataSource(ABC):
    """Abstract base class for financial data sources."""
    
    @abstractmethod
    def get_financial_data(self, symbol: str, periods: int = 4) -> Optional[FinancialData]:
        """
        Get financial data for a symbol.
        
        Args:
            symbol: Stock symbol
            periods: Number of periods to retrieve (default: 4 for 4 quarters)
            
        Returns:
            FinancialData object or None if unavailable
        """
        pass
    
    @abstractmethod
    def get_income_statements(self, symbol: str, periods: int = 4) -> List[IncomeStatement]:
        """Get income statements."""
        pass
    
    @abstractmethod
    def get_balance_sheets(self, symbol: str, periods: int = 4) -> List[BalanceSheet]:
        """Get balance sheets."""
        pass
    
    @abstractmethod
    def get_cash_flow_statements(self, symbol: str, periods: int = 4) -> List[CashFlowStatement]:
        """Get cash flow statements."""
        pass
