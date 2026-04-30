"""
BaoStock financial data source.
"""
import pandas as pd
from typing import Optional, List
from datetime import datetime

from ..data_sources.baostock_source import BaoStockSource
from .schemas import (
    FinancialData, IncomeStatement, BalanceSheet, CashFlowStatement
)
from .financial_source import FinancialDataSource


class BaoStockFinancialSource(FinancialDataSource):
    """BaoStock financial data source."""
    
    def __init__(self):
        self.baostock = BaoStockSource()
    
    def _convert_symbol(self, symbol: str) -> str:
        """Convert symbol to BaoStock format (sh.600519 or sz.000858)."""
        if symbol.startswith('sh') or symbol.startswith('sz'):
            return symbol
        if symbol.startswith('6'):
            return f"sh.{symbol}"
        else:
            return f"sz.{symbol}"
    
    def get_financial_data(self, symbol: str, periods: int = 4) -> Optional[FinancialData]:
        """Get financial data for a symbol."""
        try:
            bs_symbol = self._convert_symbol(symbol)
            
            income_statements = self.get_income_statements(symbol, periods)
            balance_sheets = self.get_balance_sheets(symbol, periods)
            cash_flow_statements = self.get_cash_flow_statements(symbol, periods)
            
            if not income_statements and not balance_sheets and not cash_flow_statements:
                return None
            
            return FinancialData(
                symbol=symbol,
                income_statements=income_statements,
                balance_sheets=balance_sheets,
                cash_flow_statements=cash_flow_statements
            )
        except Exception as e:
            print(f"Error getting financial data from BaoStock: {e}")
            return None
    
    def get_income_statements(self, symbol: str, periods: int = 4) -> List[IncomeStatement]:
        """Get income statements from BaoStock."""
        try:
            bs_symbol = self._convert_symbol(symbol)
            
            # Get profitability data
            fields = "pubDate,statDate,roeAvg,npMargin,gpMargin,netProfit,epsTTM,MBRevenue,totalShare,liqaShare"
            rs = self.baostock.query_profit_data(code=bs_symbol, year=2025, quarter=4)
            
            income_statements = []
            for i in range(min(periods, rs.get_row_num())):
                row = rs.get_row_data()
                if row[1] and row[5]:  # statDate and netProfit exist
                    income_statements.append(IncomeStatement(
                        symbol=symbol,
                        period=row[1][:10],  # YYYY-MM-DD
                        revenue=float(row[6]) if row[6] else 0.0,
                        cost_of_goods_sold=0.0,  # Not directly available
                        gross_profit=0.0,
                        operating_expenses=0.0,
                        operating_income=0.0,
                        interest_expense=0.0,
                        net_income=float(row[5]),
                        ebit=float(row[5]),  # Approximation
                        ebitda=float(row[5])
                    ))
            
            return income_statements
        except Exception as e:
            print(f"Error getting income statements: {e}")
            return []
    
    def get_balance_sheets(self, symbol: str, periods: int = 4) -> List[BalanceSheet]:
        """Get balance sheets from BaoStock."""
        # BaoStock doesn't directly provide detailed balance sheet data
        # Return empty list for now
        return []
    
    def get_cash_flow_statements(self, symbol: str, periods: int = 4) -> List[CashFlowStatement]:
        """Get cash flow statements from BaoStock."""
        # BaoStock doesn't directly provide detailed cash flow data
        # Return empty list for now
        return []
