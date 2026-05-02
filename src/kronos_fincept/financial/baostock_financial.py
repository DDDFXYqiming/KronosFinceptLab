"""
BaoStock financial data source.
"""
import logging
import pandas as pd
from typing import Optional, List
from datetime import datetime

from ..data_sources.baostock_source import BaoStockSource
from .schemas import (
    FinancialData, IncomeStatement, BalanceSheet, CashFlowStatement
)
from .financial_source import FinancialDataSource

logger = logging.getLogger(__name__)


class BaoStockFinancialSource(FinancialDataSource):
    """BaoStock financial data source."""
    
    def __init__(self):
        self.baostock = BaoStockSource()
    
    def _convert_symbol(self, symbol: str) -> str:
        """Convert symbol to BaoStock format (sh.600036 or sz.000858)."""
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
            logger.warning("Error getting financial data from BaoStock: %s", e)
            return None
    
    def get_income_statements(self, symbol: str, periods: int = 4) -> List[IncomeStatement]:
        """Get income statements from BaoStock."""
        try:
            bs_symbol = self._convert_symbol(symbol)
            
            # 直接调用 baostock 库查询盈利数据
            bs = self.baostock._get_bs()
            self.baostock._login()
            
            # 查询盈利能力数据
            rs = bs.query_profit_data(code=bs_symbol, year=2025, quarter=4)
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            
            if not rows:
                # 尝试 2024 年数据
                rs = bs.query_profit_data(code=bs_symbol, year=2024, quarter=4)
                while rs.next():
                    rows.append(rs.get_row_data())
            
            if not rows:
                return []
            
            # 取最新的数据
            row = rows[-1]
            
            # 字段映射：
            # row[0] = code, row[1] = pubDate, row[2] = statDate
            # row[3] = roeAvg, row[4] = npMargin, row[5] = gpMargin
            # row[6] = netProfit, row[7] = epsTTM, row[8] = MBRevenue
            revenue = float(row[8]) if len(row) > 8 and row[8] else 0
            net_income = float(row[6]) if len(row) > 6 and row[6] else 0
            gp_margin = float(row[5]) if len(row) > 5 and row[5] else 0
            gross_profit = revenue * gp_margin if revenue and gp_margin else 0
            
            return [IncomeStatement(
                symbol=symbol,
                period=row[2] if len(row) > 2 else "2024",  # statDate
                revenue=revenue,
                net_income=net_income,
                gross_profit=gross_profit,
                cost_of_goods_sold=revenue - gross_profit if revenue and gross_profit else 0,
                operating_expenses=0,
                operating_income=0,
                interest_expense=0,
                ebit=0,
                ebitda=0
            )]
        except Exception as e:
            logger.warning("Error getting income statements from BaoStock: %s", e)
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
