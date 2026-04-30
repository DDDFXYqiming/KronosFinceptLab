"""
DCF (Discounted Cash Flow) valuation model.
"""
from typing import Optional, List
from dataclasses import dataclass
from ..financial.schemas import FinancialData, CashFlowStatement, BalanceSheet


@dataclass
class DCFResult:
    """DCF valuation result."""
    symbol: str
    enterprise_value: float
    equity_value: float
    per_share_value: float
    wacc: float
    terminal_growth_rate: float
    projection_years: int
    
    # Sensitivity analysis
    sensitivity_table: Optional[dict] = None
    
    @property
    def implied_pe_ratio(self) -> float:
        """Implied P/E ratio based on current earnings."""
        return 0.0  # Will be calculated with market data


class DCFModel:
    """
    Discounted Cash Flow model for company valuation.
    
    Supports both FCFF (Free Cash Flow to Firm) and FCFE (Free Cash Flow to Equity) models.
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.03,  # 3% risk-free rate
        market_risk_premium: float = 0.05,  # 5% market risk premium
        default_growth_rate: float = 0.02,  # 2% terminal growth
        projection_years: int = 5
    ):
        self.risk_free_rate = risk_free_rate
        self.market_risk_premium = market_risk_premium
        self.default_growth_rate = default_growth_rate
        self.projection_years = projection_years
    
    def calculate_wacc(
        self,
        equity_value: float,
        debt_value: float,
        cost_of_equity: float,
        cost_of_debt: float,
        tax_rate: float = 0.25
    ) -> float:
        """
        Calculate Weighted Average Cost of Capital (WACC).
        
        WACC = (E/V) * Re + (D/V) * Rd * (1 - T)
        
        Args:
            equity_value: Market value of equity
            debt_value: Market value of debt
            cost_of_equity: Cost of equity (Re)
            cost_of_debt: Cost of debt (Rd)
            tax_rate: Corporate tax rate
            
        Returns:
            WACC as a decimal
        """
        total_value = equity_value + debt_value
        
        if total_value == 0:
            return self.risk_free_rate + self.market_risk_premium
        
        equity_weight = equity_value / total_value
        debt_weight = debt_value / total_value
        
        wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt * (1 - tax_rate))
        
        return wacc
    
    def calculate_cost_of_equity(
        self,
        beta: float = 1.0,
        risk_free_rate: Optional[float] = None,
        market_risk_premium: Optional[float] = None
    ) -> float:
        """
        Calculate cost of equity using CAPM.
        
        Re = Rf + β * (Rm - Rf)
        
        Args:
            beta: Stock beta
            risk_free_rate: Risk-free rate
            market_risk_premium: Market risk premium
            
        Returns:
            Cost of equity as a decimal
        """
        rf = risk_free_rate or self.risk_free_rate
        mrp = market_risk_premium or self.market_risk_premium
        
        return rf + (beta * mrp)
    
    def project_free_cash_flows(
        self,
        base_fcf: float,
        growth_rates: List[float],
        wacc: float,
        terminal_growth_rate: Optional[float] = None
    ) -> dict:
        """
        Project free cash flows and calculate terminal value.
        
        Args:
            base_fcf: Base year free cash flow
            growth_rates: List of growth rates for each projection year
            wacc: Weighted average cost of capital
            terminal_growth_rate: Terminal growth rate
            
        Returns:
            Dictionary with projected FCFs, terminal value, and present values
        """
        tgr = terminal_growth_rate or self.default_growth_rate
        
        projected_fcf = []
        present_values = []
        
        current_fcf = base_fcf
        
        for i, growth_rate in enumerate(growth_rates[:self.projection_years]):
            current_fcf = current_fcf * (1 + growth_rate)
            projected_fcf.append(current_fcf)
            
            # Present value of FCF
            pv = current_fcf / ((1 + wacc) ** (i + 1))
            present_values.append(pv)
        
        # Terminal value using Gordon Growth Model
        terminal_fcf = projected_fcf[-1] * (1 + tgr)
        terminal_value = terminal_fcf / (wacc - tgr)
        
        # Present value of terminal value
        pv_terminal = terminal_value / ((1 + wacc) ** self.projection_years)
        
        return {
            'projected_fcf': projected_fcf,
            'terminal_value': terminal_value,
            'present_values': present_values,
            'pv_terminal': pv_terminal,
            'total_pv_fcf': sum(present_values),
            'terminal_growth_rate': tgr
        }
    
    def calculate_enterprise_value(
        self,
        total_pv_fcf: float,
        pv_terminal: float,
        net_debt: float = 0.0
    ) -> float:
        """
        Calculate enterprise value.
        
        Enterprise Value = PV of FCFs + PV of Terminal Value
        
        Args:
            total_pv_fcf: Total present value of projected FCFs
            pv_terminal: Present value of terminal value
            net_debt: Net debt (debt - cash)
            
        Returns:
            Enterprise value
        """
        return total_pv_fcf + pv_terminal
    
    def calculate_equity_value(
        self,
        enterprise_value: float,
        net_debt: float = 0.0
    ) -> float:
        """
        Calculate equity value from enterprise value.
        
        Equity Value = Enterprise Value - Net Debt
        
        Args:
            enterprise_value: Enterprise value
            net_debt: Net debt (debt - cash)
            
        Returns:
            Equity value
        """
        return enterprise_value - net_debt
    
    def calculate_per_share_value(
        self,
        equity_value: float,
        shares_outstanding: float
    ) -> float:
        """
        Calculate per share value.
        
        Args:
            equity_value: Total equity value
            shares_outstanding: Number of shares outstanding
            
        Returns:
            Per share value
        """
        if shares_outstanding <= 0:
            return 0.0
        
        return equity_value / shares_outstanding
    
    def sensitivity_analysis(
        self,
        base_fcf: float,
        wacc_range: List[float],
        growth_range: List[float],
        net_debt: float = 0.0,
        shares_outstanding: float = 1.0
    ) -> dict:
        """
        Perform sensitivity analysis on WACC and growth rate.
        
        Args:
            base_fcf: Base year free cash flow
            wacc_range: List of WACC values to test
            growth_range: List of terminal growth rates to test
            net_debt: Net debt
            shares_outstanding: Number of shares
            
        Returns:
            Dictionary with sensitivity table
        """
        sensitivity = {}
        
        for wacc in wacc_range:
            sensitivity[wacc] = {}
            for growth in growth_range:
                # Use default growth rates for projection
                growth_rates = [0.10, 0.08, 0.06, 0.05, 0.04][:self.projection_years]
                
                result = self.project_free_cash_flows(
                    base_fcf=base_fcf,
                    growth_rates=growth_rates,
                    wacc=wacc,
                    terminal_growth_rate=growth
                )
                
                ev = self.calculate_enterprise_value(
                    result['total_pv_fcf'],
                    result['pv_terminal'],
                    net_debt
                )
                
                equity = self.calculate_equity_value(ev, net_debt)
                per_share = self.calculate_per_share_value(equity, shares_outstanding)
                
                sensitivity[wacc][growth] = {
                    'enterprise_value': ev,
                    'equity_value': equity,
                    'per_share_value': per_share
                }
        
        return {
            'wacc_range': wacc_range,
            'growth_range': growth_range,
            'table': sensitivity
        }
    
    def value_company(
        self,
        financial_data: FinancialData,
        shares_outstanding: float,
        beta: float = 1.0,
        debt_value: float = 0.0,
        cash_value: float = 0.0,
        tax_rate: float = 0.25
    ) -> Optional[DCFResult]:
        """
        Perform full DCF valuation.
        
        Args:
            financial_data: Company financial data
            shares_outstanding: Number of shares outstanding
            beta: Stock beta
            debt_value: Total debt
            cash_value: Cash and equivalents
            tax_rate: Corporate tax rate
            
        Returns:
            DCFResult with valuation or None if data insufficient
        """
        # Get latest cash flow statement
        latest_cf = financial_data.get_latest_cash_flow()
        latest_bs = financial_data.get_latest_balance_sheet()
        
        if not latest_cf:
            print("No cash flow data available for DCF valuation")
            return None
        
        # Calculate free cash flow
        base_fcf = latest_cf.free_cash_flow
        
        if base_fcf <= 0:
            print("Warning: Negative free cash flow, using operating cash flow")
            base_fcf = latest_cf.operating_cash_flow
        
        if base_fcf <= 0:
            print("Insufficient cash flow data for DCF valuation")
            return None
        
        # Calculate WACC
        equity_value = shares_outstanding * (latest_cf.free_cash_flow / shares_outstanding * 10)  # Rough estimate
        cost_of_equity = self.calculate_cost_of_equity(beta)
        cost_of_debt = 0.05  # Assume 5% cost of debt
        
        wacc = self.calculate_wacc(
            equity_value=equity_value,
            debt_value=debt_value,
            cost_of_equity=cost_of_equity,
            cost_of_debt=cost_of_debt,
            tax_rate=tax_rate
        )
        
        # Project cash flows (assume declining growth rates)
        growth_rates = [0.10, 0.08, 0.06, 0.05, 0.04][:self.projection_years]
        
        result = self.project_free_cash_flows(
            base_fcf=base_fcf,
            growth_rates=growth_rates,
            wacc=wacc,
            terminal_growth_rate=self.default_growth_rate
        )
        
        # Calculate enterprise and equity value
        net_debt = debt_value - cash_value
        
        ev = self.calculate_enterprise_value(
            result['total_pv_fcf'],
            result['pv_terminal'],
            net_debt
        )
        
        equity = self.calculate_equity_value(ev, net_debt)
        per_share = self.calculate_per_share_value(equity, shares_outstanding)
        
        # Sensitivity analysis
        wacc_range = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
        growth_range = [0.01, 0.02, 0.03, 0.04, 0.05]
        
        sensitivity = self.sensitivity_analysis(
            base_fcf=base_fcf,
            wacc_range=wacc_range,
            growth_range=growth_range,
            net_debt=net_debt,
            shares_outstanding=shares_outstanding
        )
        
        return DCFResult(
            symbol=financial_data.symbol,
            enterprise_value=ev,
            equity_value=equity,
            per_share_value=per_share,
            wacc=wacc,
            terminal_growth_rate=self.default_growth_rate,
            projection_years=self.projection_years,
            sensitivity_table=sensitivity
        )
