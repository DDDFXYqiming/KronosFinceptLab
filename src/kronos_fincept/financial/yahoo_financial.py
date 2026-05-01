"""
Yahoo Finance financial data source.
"""
import pandas as pd
from typing import Optional, List
from datetime import datetime

from ..data_sources.yahoo_source import YahooFinanceSource
from .schemas import (
    FinancialData, IncomeStatement, BalanceSheet, CashFlowStatement
)
from .financial_source import FinancialDataSource


class YahooFinanceFinancialSource(FinancialDataSource):
    """Yahoo Finance financial data source."""
    
    def __init__(self):
        self.yahoo = YahooFinanceSource()
    
    def _convert_symbol(self, symbol: str) -> str:
        """Convert symbol to Yahoo Finance format (600036.SS or 000858.SZ)."""
        if '.' in symbol:
            return symbol
        if symbol.startswith('6'):
            return f"{symbol}.SS"
        else:
            return f"{symbol}.SZ"
    
    def get_financial_data(self, symbol: str, periods: int = 4) -> Optional[FinancialData]:
        """Get financial data for a symbol."""
        try:
            yahoo_symbol = self._convert_symbol(symbol)
            
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
            print(f"Error getting financial data from Yahoo Finance: {e}")
            return None
    
    def get_income_statements(self, symbol: str, periods: int = 4) -> List[IncomeStatement]:
        """Get income statements from Yahoo Finance."""
        try:
            yahoo_symbol = self._convert_symbol(symbol)
            
            import yfinance as yf
            ticker = yf.Ticker(yahoo_symbol)
            income_df = ticker.quarterly_income_stmt
            
            if income_df.empty:
                return []
            
            income_statements = []
            for col in income_df.columns[:periods]:
                try:
                    revenue = float(income_df.loc['Total Revenue', col]) if 'Total Revenue' in income_df.index else 0.0
                    cost_of_goods = float(income_df.loc['Cost Of Revenue', col]) if 'Cost Of Revenue' in income_df.index else 0.0
                    gross_profit = float(income_df.loc['Gross Profit', col]) if 'Gross Profit' in income_df.index else 0.0
                    operating_expenses = float(income_df.loc['Operating Expense', col]) if 'Operating Expense' in income_df.index else 0.0
                    operating_income = float(income_df.loc['Operating Income', col]) if 'Operating Income' in income_df.index else 0.0
                    net_income = float(income_df.loc['Net Income', col]) if 'Net Income' in income_df.index else 0.0
                    ebit = float(income_df.loc['EBIT', col]) if 'EBIT' in income_df.index else operating_income
                    ebitda = float(income_df.loc['EBITDA', col]) if 'EBITDA' in income_df.index else ebit
                    
                    income_statements.append(IncomeStatement(
                        symbol=symbol,
                        period=col.strftime('%Y-%m-%d'),
                        revenue=revenue,
                        cost_of_goods_sold=cost_of_goods,
                        gross_profit=gross_profit,
                        operating_expenses=operating_expenses,
                        operating_income=operating_income,
                        interest_expense=0.0,  # Not directly available
                        net_income=net_income,
                        ebit=ebit,
                        ebitda=ebitda
                    ))
                except Exception as e:
                    print(f"Error parsing income statement: {e}")
                    continue
            
            return income_statements
        except Exception as e:
            print(f"Error getting income statements: {e}")
            return []
    
    def get_balance_sheets(self, symbol: str, periods: int = 4) -> List[BalanceSheet]:
        """Get balance sheets from Yahoo Finance."""
        try:
            yahoo_symbol = self._convert_symbol(symbol)
            
            import yfinance as yf
            ticker = yf.Ticker(yahoo_symbol)
            balance_df = ticker.quarterly_balance_sheet
            
            if balance_df.empty:
                return []
            
            balance_sheets = []
            for col in balance_df.columns[:periods]:
                try:
                    total_assets = float(balance_df.loc['Total Assets', col]) if 'Total Assets' in balance_df.index else 0.0
                    current_assets = float(balance_df.loc['Current Assets', col]) if 'Current Assets' in balance_df.index else 0.0
                    cash = float(balance_df.loc['Cash And Cash Equivalents', col]) if 'Cash And Cash Equivalents' in balance_df.index else 0.0
                    receivables = float(balance_df.loc['Net Receivables', col]) if 'Net Receivables' in balance_df.index else 0.0
                    inventory = float(balance_df.loc['Inventory', col]) if 'Inventory' in balance_df.index else 0.0
                    total_liabilities = float(balance_df.loc['Total Liabilities Net Minority Interest', col]) if 'Total Liabilities Net Minority Interest' in balance_df.index else 0.0
                    current_liabilities = float(balance_df.loc['Current Liabilities', col]) if 'Current Liabilities' in balance_df.index else 0.0
                    long_term_debt = float(balance_df.loc['Long Term Debt', col]) if 'Long Term Debt' in balance_df.index else 0.0
                    equity = float(balance_df.loc['Stockholders Equity', col]) if 'Stockholders Equity' in balance_df.index else 0.0
                    
                    balance_sheets.append(BalanceSheet(
                        symbol=symbol,
                        period=col.strftime('%Y-%m-%d'),
                        total_assets=total_assets,
                        current_assets=current_assets,
                        cash_and_equivalents=cash,
                        accounts_receivable=receivables,
                        inventory=inventory,
                        total_liabilities=total_liabilities,
                        current_liabilities=current_liabilities,
                        long_term_debt=long_term_debt,
                        shareholders_equity=equity
                    ))
                except Exception as e:
                    print(f"Error parsing balance sheet: {e}")
                    continue
            
            return balance_sheets
        except Exception as e:
            print(f"Error getting balance sheets: {e}")
            return []
    
    def get_cash_flow_statements(self, symbol: str, periods: int = 4) -> List[CashFlowStatement]:
        """Get cash flow statements from Yahoo Finance."""
        try:
            yahoo_symbol = self._convert_symbol(symbol)
            
            import yfinance as yf
            ticker = yf.Ticker(yahoo_symbol)
            cashflow_df = ticker.quarterly_cashflow
            
            if cashflow_df.empty:
                return []
            
            cash_flow_statements = []
            for col in cashflow_df.columns[:periods]:
                try:
                    operating_cf = float(cashflow_df.loc['Operating Cash Flow', col]) if 'Operating Cash Flow' in cashflow_df.index else 0.0
                    capex = float(cashflow_df.loc['Capital Expenditure', col]) if 'Capital Expenditure' in cashflow_df.index else 0.0
                    free_cf = operating_cf + capex  # CapEx is typically negative
                    dividends = float(cashflow_df.loc['Cash Dividends Paid', col]) if 'Cash Dividends Paid' in cashflow_df.index else 0.0
                    
                    cash_flow_statements.append(CashFlowStatement(
                        symbol=symbol,
                        period=col.strftime('%Y-%m-%d'),
                        operating_cash_flow=operating_cf,
                        capital_expenditures=abs(capex),
                        free_cash_flow=free_cf,
                        dividends_paid=abs(dividends),
                        stock_repurchases=0.0,
                        debt_issuance=0.0,
                        debt_repayment=0.0
                    ))
                except Exception as e:
                    print(f"Error parsing cash flow statement: {e}")
                    continue
            
            return cash_flow_statements
        except Exception as e:
            print(f"Error getting cash flow statements: {e}")
            return []
