"""
Financial data manager with fallback support.
"""
from typing import Optional, List
from datetime import datetime
import time
import os
import json
from pathlib import Path

from .schemas import FinancialData
from .financial_source import FinancialDataSource
from .baostock_financial import BaoStockFinancialSource
from .yahoo_financial import YahooFinanceFinancialSource


class FinancialDataManager:
    """
    Financial data manager with automatic fallback.
    
    Fallback order: BaoStock → Yahoo Finance
    """
    
    def __init__(self):
        # Initialize sources in fallback order
        self.sources: List[FinancialDataSource] = [
            BaoStockFinancialSource(),
            YahooFinanceFinancialSource()
        ]
        
        # Circuit breaker state
        self.failed_attempts = {}
        self.disabled_until = {}
        self.DISABLE_DURATION = 300  # 5 minutes
        self.MAX_ATTEMPTS = 5
        
        # Cache
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour for financial data
        
        # Cache directory
        self.cache_dir = Path('.cache/financial')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_key(self, symbol: str) -> str:
        """Generate cache key."""
        return f"{symbol}_{datetime.now().strftime('%Y%m%d')}"
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file is valid."""
        if not cache_file.exists():
            return False
        
        file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
        now = datetime.now()
        return (now - file_time).total_seconds() < self.cache_ttl
    
    def _load_from_cache(self, symbol: str) -> Optional[FinancialData]:
        """Load from file cache."""
        cache_file = self.cache_dir / f"{self._get_cache_key(symbol)}.json"
        
        if not self._is_cache_valid(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                # Reconstruct FinancialData object
                return self._dict_to_financial_data(data)
        except Exception:
            return None
    
    def _save_to_cache(self, symbol: str, data: FinancialData) -> None:
        """Save to file cache."""
        cache_file = self.cache_dir / f"{self._get_cache_key(symbol)}.json"
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(self._financial_data_to_dict(data), f)
        except Exception:
            pass
    
    def _financial_data_to_dict(self, data: FinancialData) -> dict:
        """Convert FinancialData to dict for caching."""
        return {
            'symbol': data.symbol,
            'income_statements': [
                {
                    'period': stmt.period,
                    'revenue': stmt.revenue,
                    'cost_of_goods_sold': stmt.cost_of_goods_sold,
                    'gross_profit': stmt.gross_profit,
                    'operating_expenses': stmt.operating_expenses,
                    'operating_income': stmt.operating_income,
                    'interest_expense': stmt.interest_expense,
                    'net_income': stmt.net_income,
                    'ebit': stmt.ebit,
                    'ebitda': stmt.ebitda
                }
                for stmt in data.income_statements
            ],
            'balance_sheets': [
                {
                    'period': bs.period,
                    'total_assets': bs.total_assets,
                    'current_assets': bs.current_assets,
                    'cash_and_equivalents': bs.cash_and_equivalents,
                    'accounts_receivable': bs.accounts_receivable,
                    'inventory': bs.inventory,
                    'total_liabilities': bs.total_liabilities,
                    'current_liabilities': bs.current_liabilities,
                    'long_term_debt': bs.long_term_debt,
                    'shareholders_equity': bs.shareholders_equity
                }
                for bs in data.balance_sheets
            ],
            'cash_flow_statements': [
                {
                    'period': cf.period,
                    'operating_cash_flow': cf.operating_cash_flow,
                    'capital_expenditures': cf.capital_expenditures,
                    'free_cash_flow': cf.free_cash_flow,
                    'dividends_paid': cf.dividends_paid,
                    'stock_repurchases': cf.stock_repurchases,
                    'debt_issuance': cf.debt_issuance,
                    'debt_repayment': cf.debt_repayment
                }
                for cf in data.cash_flow_statements
            ]
        }
    
    def _dict_to_financial_data(self, data: dict) -> FinancialData:
        """Convert dict back to FinancialData object."""
        from .schemas import IncomeStatement, BalanceSheet, CashFlowStatement
        
        income_statements = [
            IncomeStatement(
                symbol=data['symbol'],
                period=stmt['period'],
                revenue=stmt['revenue'],
                cost_of_goods_sold=stmt['cost_of_goods_sold'],
                gross_profit=stmt['gross_profit'],
                operating_expenses=stmt['operating_expenses'],
                operating_income=stmt['operating_income'],
                interest_expense=stmt['interest_expense'],
                net_income=stmt['net_income'],
                ebit=stmt['ebit'],
                ebitda=stmt['ebitda']
            )
            for stmt in data['income_statements']
        ]
        
        balance_sheets = [
            BalanceSheet(
                symbol=data['symbol'],
                period=bs['period'],
                total_assets=bs['total_assets'],
                current_assets=bs['current_assets'],
                cash_and_equivalents=bs['cash_and_equivalents'],
                accounts_receivable=bs['accounts_receivable'],
                inventory=bs['inventory'],
                total_liabilities=bs['total_liabilities'],
                current_liabilities=bs['current_liabilities'],
                long_term_debt=bs['long_term_debt'],
                shareholders_equity=bs['shareholders_equity']
            )
            for bs in data['balance_sheets']
        ]
        
        cash_flow_statements = [
            CashFlowStatement(
                symbol=data['symbol'],
                period=cf['period'],
                operating_cash_flow=cf['operating_cash_flow'],
                capital_expenditures=cf['capital_expenditures'],
                free_cash_flow=cf['free_cash_flow'],
                dividends_paid=cf['dividends_paid'],
                stock_repurchases=cf['stock_repurchases'],
                debt_issuance=cf['debt_issuance'],
                debt_repayment=cf['debt_repayment']
            )
            for cf in data['cash_flow_statements']
        ]
        
        return FinancialData(
            symbol=data['symbol'],
            income_statements=income_statements,
            balance_sheets=balance_sheets,
            cash_flow_statements=cash_flow_statements
        )
    
    def _is_disabled(self, source_name: str) -> bool:
        """Check if source is disabled due to circuit breaker."""
        if source_name in self.disabled_until:
            if datetime.now().timestamp() < self.disabled_until[source_name]:
                return True
            else:
                # Re-enable after disable duration
                del self.disabled_until[source_name]
                self.failed_attempts[source_name] = 0
        return False
    
    def _record_failure(self, source_name: str) -> None:
        """Record failure and potentially disable source."""
        self.failed_attempts[source_name] = self.failed_attempts.get(source_name, 0) + 1
        
        if self.failed_attempts[source_name] >= self.MAX_ATTEMPTS:
            self.disabled_until[source_name] = datetime.now().timestamp() + self.DISABLE_DURATION
            print(f"Source {source_name} disabled for {self.DISABLE_DURATION} seconds due to repeated failures")
    
    def _record_success(self, source_name: str) -> None:
        """Record success and reset failure count."""
        self.failed_attempts[source_name] = 0
    
    def get_financial_data(self, symbol: str, periods: int = 4) -> Optional[FinancialData]:
        """
        Get financial data with automatic fallback.
        
        Args:
            symbol: Stock symbol
            periods: Number of periods to retrieve
            
        Returns:
            FinancialData object or None if all sources fail
        """
        # Check cache first
        cached_data = self._load_from_cache(symbol)
        if cached_data:
            return cached_data
        
        # Try each source in order
        for source in self.sources:
            source_name = source.__class__.__name__
            
            if self._is_disabled(source_name):
                continue
            
            try:
                print(f"Trying {source_name} for {symbol}...")
                data = source.get_financial_data(symbol, periods)
                
                if data:
                    self._record_success(source_name)
                    self.cache[symbol] = data
                    self._save_to_cache(symbol, data)
                    print(f"Successfully got financial data from {source_name}")
                    return data
                else:
                    print(f"{source_name} returned no data for {symbol}")
                    
            except Exception as e:
                print(f"{source_name} failed: {e}")
                self._record_failure(source_name)
                continue
        
        print(f"All financial data sources failed for {symbol}")
        return None
    
    def get_source_status(self) -> dict:
        """Get status of all sources."""
        status = {}
        for source in self.sources:
            source_name = source.__class__.__name__
            status[source_name] = {
                'disabled': self._is_disabled(source_name),
                'failed_attempts': self.failed_attempts.get(source_name, 0),
                'disabled_until': datetime.fromtimestamp(self.disabled_until[source_name]).isoformat() 
                    if source_name in self.disabled_until else None
            }
        return status
