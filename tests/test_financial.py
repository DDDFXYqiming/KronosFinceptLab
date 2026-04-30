"""
Tests for financial data module.
"""
import pytest
from kronos_fincept.financial.schemas import (
    FinancialData,
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement
)
from kronos_fincept.financial.manager import FinancialDataManager


class TestFinancialSchemas:
    """Test financial data schemas."""
    
    def test_income_statement_properties(self):
        """Test IncomeStatement properties."""
        stmt = IncomeStatement(
            symbol="600519",
            period="2025-12-31",
            revenue=1000000.0,
            cost_of_goods_sold=600000.0,
            gross_profit=400000.0,
            operating_expenses=200000.0,
            operating_income=200000.0,
            interest_expense=10000.0,
            net_income=150000.0,
            ebit=210000.0,
            ebitda=250000.0
        )
        
        assert stmt.operating_margin == 0.2  # 200000/1000000
        assert stmt.net_margin == 0.15  # 150000/1000000
    
    def test_balance_sheet_properties(self):
        """Test BalanceSheet properties."""
        bs = BalanceSheet(
            symbol="600519",
            period="2025-12-31",
            total_assets=5000000.0,
            current_assets=2000000.0,
            cash_and_equivalents=500000.0,
            accounts_receivable=300000.0,
            inventory=200000.0,
            total_liabilities=2000000.0,
            current_liabilities=1000000.0,
            long_term_debt=1000000.0,
            shareholders_equity=3000000.0
        )
        
        assert bs.current_ratio == 2.0  # 2000000/1000000
        assert bs.debt_to_equity == pytest.approx(0.6667, rel=1e-3)  # 2000000/3000000
        assert bs.total_debt == 2000000.0  # 1000000 + 1000000
    
    def test_cash_flow_statement_properties(self):
        """Test CashFlowStatement properties."""
        cf = CashFlowStatement(
            symbol="600519",
            period="2025-12-31",
            operating_cash_flow=300000.0,
            capital_expenditures=100000.0,
            free_cash_flow=200000.0,
            dividends_paid=50000.0,
            stock_repurchases=0.0,
            debt_issuance=0.0,
            debt_repayment=0.0
        )
        
        assert cf.fcfe == 200000.0
        assert cf.fcff == 200000.0  # 300000 - 100000
    
    def test_financial_data_getters(self):
        """Test FinancialData getter methods."""
        income1 = IncomeStatement(
            symbol="600519", period="2025-12-31",
            revenue=1000000, cost_of_goods_sold=600000,
            gross_profit=400000, operating_expenses=200000,
            operating_income=200000, interest_expense=10000,
            net_income=150000, ebit=210000, ebitda=250000
        )
        income2 = IncomeStatement(
            symbol="600519", period="2025-09-30",
            revenue=900000, cost_of_goods_sold=540000,
            gross_profit=360000, operating_expenses=180000,
            operating_income=180000, interest_expense=10000,
            net_income=135000, ebit=189000, ebitda=225000
        )
        
        financial_data = FinancialData(
            symbol="600519",
            income_statements=[income2, income1],  # Note: income2 is more recent
            balance_sheets=[],
            cash_flow_statements=[]
        )
        
        # Should return the most recent (sorted by period)
        latest_income = financial_data.get_latest_income()
        assert latest_income.period == "2025-12-31"
        
        # Empty list should return None
        assert financial_data.get_latest_balance_sheet() is None
        assert financial_data.get_latest_cash_flow() is None


class TestFinancialDataManager:
    """Test FinancialDataManager."""
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = FinancialDataManager()
        assert len(manager.sources) == 2  # BaoStock and Yahoo Finance
        
        status = manager.get_source_status()
        assert len(status) == 2
        assert all(not info['disabled'] for info in status.values())
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        manager = FinancialDataManager()
        key = manager._get_cache_key("600519")
        assert "600519" in key
        assert len(key) > 10  # Should include date
