"""
Financial data schemas for CFA-level analysis.
"""
from datetime import date
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum


class FinancialStatementType(Enum):
    """Financial statement types."""
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW_STATEMENT = "cash_flow_statement"


@dataclass
class IncomeStatement:
    """Income statement data."""
    symbol: str
    period: str  # e.g., "2025-12-31"
    revenue: float
    cost_of_goods_sold: float
    gross_profit: float
    operating_expenses: float
    operating_income: float
    interest_expense: float
    net_income: float
    ebit: float
    ebitda: float
    
    @property
    def operating_margin(self) -> float:
        """Operating margin."""
        return self.operating_income / self.revenue if self.revenue > 0 else 0.0
    
    @property
    def net_margin(self) -> float:
        """Net profit margin."""
        return self.net_income / self.revenue if self.revenue > 0 else 0.0


@dataclass
class BalanceSheet:
    """Balance sheet data."""
    symbol: str
    period: str
    total_assets: float
    current_assets: float
    cash_and_equivalents: float
    accounts_receivable: float
    inventory: float
    total_liabilities: float
    current_liabilities: float
    long_term_debt: float
    shareholders_equity: float
    
    @property
    def current_ratio(self) -> float:
        """Current ratio."""
        return self.current_assets / self.current_liabilities if self.current_liabilities > 0 else 0.0
    
    @property
    def debt_to_equity(self) -> float:
        """Debt to equity ratio."""
        return self.total_liabilities / self.shareholders_equity if self.shareholders_equity > 0 else 0.0
    
    @property
    def total_debt(self) -> float:
        """Total debt (short-term + long-term)."""
        return self.current_liabilities + self.long_term_debt


@dataclass
class CashFlowStatement:
    """Cash flow statement data."""
    symbol: str
    period: str
    operating_cash_flow: float
    capital_expenditures: float
    free_cash_flow: float
    dividends_paid: float
    stock_repurchases: float
    debt_issuance: float
    debt_repayment: float
    
    @property
    def fcfe(self) -> float:
        """Free cash flow to equity."""
        return self.free_cash_flow
    
    @property
    def fcff(self) -> float:
        """Free cash flow to firm."""
        return self.operating_cash_flow - self.capital_expenditures


@dataclass
class FinancialData:
    """Complete financial data for a company."""
    symbol: str
    income_statements: List[IncomeStatement]
    balance_sheets: List[BalanceSheet]
    cash_flow_statements: List[CashFlowStatement]
    
    def get_latest_income(self) -> Optional[IncomeStatement]:
        """Get the most recent income statement."""
        if self.income_statements:
            return sorted(self.income_statements, key=lambda x: x.period, reverse=True)[0]
        return None
    
    def get_latest_balance_sheet(self) -> Optional[BalanceSheet]:
        """Get the most recent balance sheet."""
        if self.balance_sheets:
            return sorted(self.balance_sheets, key=lambda x: x.period, reverse=True)[0]
        return None
    
    def get_latest_cash_flow(self) -> Optional[CashFlowStatement]:
        """Get the most recent cash flow statement."""
        if self.cash_flow_statements:
            return sorted(self.cash_flow_statements, key=lambda x: x.period, reverse=True)[0]
        return None
