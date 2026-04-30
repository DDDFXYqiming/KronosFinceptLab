"""
Tests for risk metrics calculation.
"""
import pytest
import numpy as np
from kronos_fincept.financial.risk import RiskCalculator, RiskMetrics


class TestRiskCalculator:
    """Test RiskCalculator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = RiskCalculator(
            risk_free_rate=0.03,
            trading_days_per_year=252
        )
        
        # Sample prices (100 days of data)
        np.random.seed(42)
        self.sample_prices = [100.0]
        for _ in range(99):
            self.sample_prices.append(self.sample_prices[-1] * (1 + np.random.normal(0.0005, 0.02)))
        
        # Sample market prices
        self.market_prices = [1000.0]
        for _ in range(99):
            self.market_prices.append(self.market_prices[-1] * (1 + np.random.normal(0.0003, 0.01)))
    
    def test_calculate_returns(self):
        """Test return calculation."""
        returns = self.calculator.calculate_returns(self.sample_prices)
        
        assert len(returns) == 99
        assert isinstance(returns, np.ndarray)
        
        # Returns should be around 0 for random walk
        assert abs(np.mean(returns)) < 0.01
    
    def test_calculate_log_returns(self):
        """Test log return calculation."""
        log_returns = self.calculator.calculate_log_returns(self.sample_prices)
        
        assert len(log_returns) == 99
        assert isinstance(log_returns, np.ndarray)
    
    def test_var_historical(self):
        """Test historical VaR."""
        returns = self.calculator.calculate_returns(self.sample_prices)
        
        var_95 = self.calculator.calculate_var_historical(returns, 0.95)
        var_99 = self.calculator.calculate_var_historical(returns, 0.99)
        
        assert var_95 > 0
        assert var_99 > var_95  # 99% VaR should be higher than 95% VaR
    
    def test_var_parametric(self):
        """Test parametric VaR."""
        returns = self.calculator.calculate_returns(self.sample_prices)
        
        var_95 = self.calculator.calculate_var_parametric(returns, 0.95)
        
        assert var_95 > 0
    
    def test_var_monte_carlo(self):
        """Test Monte Carlo VaR."""
        returns = self.calculator.calculate_returns(self.sample_prices)
        
        var_95 = self.calculator.calculate_var_monte_carlo(returns, 0.95, num_simulations=1000)
        
        assert var_95 > 0
    
    def test_sharpe_ratio(self):
        """Test Sharpe ratio."""
        returns = self.calculator.calculate_returns(self.sample_prices)
        
        sharpe = self.calculator.calculate_sharpe_ratio(returns)
        
        # Sharpe ratio should be reasonable (typically between -2 and 5)
        assert -2 < sharpe < 5
    
    def test_sortino_ratio(self):
        """Test Sortino ratio."""
        returns = self.calculator.calculate_returns(self.sample_prices)
        
        sortino = self.calculator.calculate_sortino_ratio(returns)
        
        # Sortino should be reasonable
        assert -2 < sortino < 10
    
    def test_max_drawdown(self):
        """Test maximum drawdown."""
        max_dd = self.calculator.calculate_max_drawdown(self.sample_prices)
        
        assert 0 <= max_dd <= 1
    
    def test_volatility(self):
        """Test volatility."""
        returns = self.calculator.calculate_returns(self.sample_prices)
        
        volatility = self.calculator.calculate_volatility(returns)
        
        # Volatility should be positive and reasonable
        assert 0 < volatility < 1
    
    def test_downside_deviation(self):
        """Test downside deviation."""
        returns = self.calculator.calculate_returns(self.sample_prices)
        
        downside_dev = self.calculator.calculate_downside_deviation(returns)
        
        # Downside deviation should be non-negative
        assert downside_dev >= 0
    
    def test_beta(self):
        """Test beta calculation."""
        asset_returns = self.calculator.calculate_returns(self.sample_prices)
        market_returns = self.calculator.calculate_returns(self.market_prices)
        
        beta = self.calculator.calculate_beta(asset_returns, market_returns)
        
        # Beta should be reasonable (typically between -1 and 3)
        assert -1 < beta < 3
    
    def test_alpha(self):
        """Test alpha calculation."""
        asset_returns = self.calculator.calculate_returns(self.sample_prices)
        market_returns = self.calculator.calculate_returns(self.market_prices)
        
        alpha = self.calculator.calculate_alpha(asset_returns, market_returns)
        
        # Alpha should be reasonable
        assert -0.5 < alpha < 0.5
    
    def test_calculate_risk_metrics(self):
        """Test comprehensive risk metrics."""
        metrics = self.calculator.calculate_risk_metrics(
            symbol="600519",
            prices=self.sample_prices,
            market_prices=self.market_prices
        )
        
        assert isinstance(metrics, RiskMetrics)
        assert metrics.symbol == "600519"
        assert metrics.var_95 > 0
        assert metrics.var_99 > 0
        assert -2 < metrics.sharpe_ratio < 5
        assert -2 < metrics.sortino_ratio < 10
        assert 0 <= metrics.max_drawdown <= 1
        assert 0 < metrics.volatility < 1
        assert metrics.downside_deviation >= 0
        assert metrics.beta is not None
        assert metrics.alpha is not None
    
    def test_empty_prices(self):
        """Test with empty prices."""
        returns = self.calculator.calculate_returns([])
        assert len(returns) == 0
        
        var = self.calculator.calculate_var_historical(returns)
        assert var == 0.0
    
    def test_single_price(self):
        """Test with single price."""
        returns = self.calculator.calculate_returns([100.0])
        assert len(returns) == 0
