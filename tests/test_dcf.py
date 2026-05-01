"""
Tests for DCF model.
"""
import pytest
from kronos_fincept.financial.dcf import DCFModel, DCFResult
from kronos_fincept.financial.schemas import (
    FinancialData,
    IncomeStatement,
    BalanceSheet,
    CashFlowStatement
)


class TestDCFModel:
    """Test DCF model."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.dcf = DCFModel(
            risk_free_rate=0.03,
            market_risk_premium=0.05,
            default_growth_rate=0.02,
            projection_years=5
        )
        
        # Create sample financial data
        self.sample_cf = CashFlowStatement(
            symbol="600036",
            period="2025-12-31",
            operating_cash_flow=3000000000.0,
            capital_expenditures=1000000000.0,
            free_cash_flow=2000000000.0,
            dividends_paid=500000000.0,
            stock_repurchases=0.0,
            debt_issuance=0.0,
            debt_repayment=0.0
        )
        
        self.sample_bs = BalanceSheet(
            symbol="600036",
            period="2025-12-31",
            total_assets=100000000000.0,
            current_assets=30000000000.0,
            cash_and_equivalents=10000000000.0,
            accounts_receivable=5000000000.0,
            inventory=2000000000.0,
            total_liabilities=40000000000.0,
            current_liabilities=15000000000.0,
            long_term_debt=25000000000.0,
            shareholders_equity=60000000000.0
        )
        
        self.sample_financial_data = FinancialData(
            symbol="600036",
            income_statements=[],
            balance_sheets=[self.sample_bs],
            cash_flow_statements=[self.sample_cf]
        )
    
    def test_wacc_calculation(self):
        """Test WACC calculation."""
        wacc = self.dcf.calculate_wacc(
            equity_value=60000000000,
            debt_value=25000000000,
            cost_of_equity=0.10,
            cost_of_debt=0.05,
            tax_rate=0.25
        )
        
        # Expected: (60/85)*0.10 + (25/85)*0.05*(1-0.25) = 0.0706 + 0.0110 = 0.0816
        assert wacc == pytest.approx(0.0816, rel=1e-3)
    
    def test_cost_of_equity(self):
        """Test cost of equity calculation using CAPM."""
        # Beta = 1.0, Rf = 3%, MRP = 5%
        cost = self.dcf.calculate_cost_of_equity(beta=1.0)
        assert cost == pytest.approx(0.08, rel=1e-3)
        
        # Beta = 1.5
        cost = self.dcf.calculate_cost_of_equity(beta=1.5)
        assert cost == pytest.approx(0.105, rel=1e-3)
    
    def test_project_free_cash_flows(self):
        """Test free cash flow projection."""
        base_fcf = 1000.0
        growth_rates = [0.10, 0.08, 0.06, 0.05, 0.04]
        wacc = 0.08
        
        result = self.dcf.project_free_cash_flows(
            base_fcf=base_fcf,
            growth_rates=growth_rates,
            wacc=wacc,
            terminal_growth_rate=0.02
        )
        
        # Check projected FCFs
        assert len(result['projected_fcf']) == 5
        assert result['projected_fcf'][0] == pytest.approx(1100.0, rel=1e-3)  # 1000 * 1.10
        assert result['projected_fcf'][1] == pytest.approx(1188.0, rel=1e-3)  # 1100 * 1.08
        
        # Check terminal value
        assert result['terminal_value'] > 0
        
        # Check present values
        assert len(result['present_values']) == 5
        assert result['pv_terminal'] > 0
    
    def test_enterprise_value(self):
        """Test enterprise value calculation."""
        ev = self.dcf.calculate_enterprise_value(
            total_pv_fcf=5000.0,
            pv_terminal=10000.0,
            net_debt=2000.0
        )
        
        assert ev == pytest.approx(15000.0, rel=1e-3)
    
    def test_equity_value(self):
        """Test equity value calculation."""
        equity = self.dcf.calculate_equity_value(
            enterprise_value=15000.0,
            net_debt=2000.0
        )
        
        assert equity == pytest.approx(13000.0, rel=1e-3)
    
    def test_per_share_value(self):
        """Test per share value calculation."""
        per_share = self.dcf.calculate_per_share_value(
            equity_value=13000.0,
            shares_outstanding=1000.0
        )
        
        assert per_share == pytest.approx(13.0, rel=1e-3)
    
    def test_value_company(self):
        """Test full DCF valuation."""
        result = self.dcf.value_company(
            financial_data=self.sample_financial_data,
            shares_outstanding=1000000000,  # 1 billion shares
            beta=0.8,
            debt_value=25000000000.0,
            cash_value=10000000000.0,
            tax_rate=0.25
        )
        
        assert result is not None
        assert isinstance(result, DCFResult)
        assert result.symbol == "600036"
        assert result.enterprise_value > 0
        assert result.equity_value > 0
        assert result.per_share_value > 0
        assert result.wacc > 0
        assert result.terminal_growth_rate == 0.02
        assert result.projection_years == 5
        assert result.sensitivity_table is not None
    
    def test_sensitivity_analysis(self):
        """Test sensitivity analysis."""
        wacc_range = [0.06, 0.08, 0.10]
        growth_range = [0.01, 0.02, 0.03]
        
        result = self.dcf.sensitivity_analysis(
            base_fcf=2000000000.0,
            wacc_range=wacc_range,
            growth_range=growth_range,
            net_debt=15000000000.0,
            shares_outstanding=1000000000.0
        )
        
        assert 'wacc_range' in result
        assert 'growth_range' in result
        assert 'table' in result
        assert len(result['wacc_range']) == 3
        assert len(result['growth_range']) == 3
        
        # Check that lower WACC and higher growth give higher valuations
        low_wacc_high_growth = result['table'][0.06][0.03]['per_share_value']
        high_wacc_low_growth = result['table'][0.10][0.01]['per_share_value']
        
        assert low_wacc_high_growth > high_wacc_low_growth
