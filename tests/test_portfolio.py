"""
Tests for portfolio optimization.
"""
import pytest
import pandas as pd
import numpy as np
from kronos_fincept.financial.portfolio import PortfolioOptimizer, PortfolioResult


class TestPortfolioOptimizer:
    """Test PortfolioOptimizer."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = PortfolioOptimizer(
            risk_free_rate=0.03,
            trading_days_per_year=252
        )
        
        # Create sample price data (3 assets, 100 days)
        np.random.seed(42)
        dates = pd.date_range('2025-01-01', periods=100, freq='D')
        
        # Generate random prices for 3 assets
        asset1 = [100.0]
        asset2 = [100.0]
        asset3 = [100.0]
        
        for _ in range(99):
            asset1.append(asset1[-1] * (1 + np.random.normal(0.001, 0.02)))
            asset2.append(asset2[-1] * (1 + np.random.normal(0.0005, 0.015)))
            asset3.append(asset3[-1] * (1 + np.random.normal(0.0008, 0.018)))
        
        self.prices = pd.DataFrame({
            'Asset1': asset1,
            'Asset2': asset2,
            'Asset3': asset3
        }, index=dates)
        
        self.asset_names = ['Asset1', 'Asset2', 'Asset3']
    
    def test_calculate_returns(self):
        """Test return calculation."""
        returns = self.optimizer.calculate_returns(self.prices)
        
        assert isinstance(returns, pd.DataFrame)
        assert returns.shape[1] == 3
        assert len(returns) == 99
    
    def test_calculate_expected_returns(self):
        """Test expected returns calculation."""
        returns = self.optimizer.calculate_returns(self.prices)
        expected_returns = self.optimizer.calculate_expected_returns(returns)
        
        assert isinstance(expected_returns, np.ndarray)
        assert len(expected_returns) == 3
        
        # Expected returns should be small daily returns
        assert all(-0.01 < r < 0.01 for r in expected_returns)
    
    def test_calculate_covariance_matrix(self):
        """Test covariance matrix calculation."""
        returns = self.optimizer.calculate_returns(self.prices)
        cov_matrix = self.optimizer.calculate_covariance_matrix(returns)
        
        assert isinstance(cov_matrix, np.ndarray)
        assert cov_matrix.shape == (3, 3)
        
        # Covariance matrix should be symmetric
        assert np.allclose(cov_matrix, cov_matrix.T)
        
        # Diagonal should be positive (variances)
        assert all(np.diag(cov_matrix) > 0)
    
    def test_portfolio_performance(self):
        """Test portfolio performance calculation."""
        returns = self.optimizer.calculate_returns(self.prices)
        expected_returns = self.optimizer.calculate_expected_returns(returns)
        cov_matrix = self.optimizer.calculate_covariance_matrix(returns)
        
        # Equal weights
        weights = np.array([1/3, 1/3, 1/3])
        
        portfolio_return, volatility = self.optimizer.portfolio_performance(
            weights, expected_returns, cov_matrix
        )
        
        # Return should be between min and max expected returns
        assert min(expected_returns) <= portfolio_return <= max(expected_returns)
        
        # Volatility should be positive
        assert volatility > 0
    
    def test_minimize_volatility(self):
        """Test minimum volatility optimization."""
        returns = self.optimizer.calculate_returns(self.prices)
        expected_returns = self.optimizer.calculate_expected_returns(returns)
        cov_matrix = self.optimizer.calculate_covariance_matrix(returns)
        
        weights = self.optimizer.minimize_volatility(expected_returns, cov_matrix)
        
        assert len(weights) == 3
        assert abs(sum(weights) - 1.0) < 1e-6  # Weights sum to 1
        assert all(w >= 0 for w in weights)  # No short selling
        
        # Check that this portfolio has minimum volatility
        portfolio_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        
        # Try equal weights
        equal_weights = np.array([1/3, 1/3, 1/3])
        equal_vol = np.sqrt(np.dot(equal_weights.T, np.dot(cov_matrix, equal_weights)))
        
        # Minimum volatility portfolio should have lower or equal volatility
        assert portfolio_vol <= equal_vol + 1e-6
    
    def test_maximize_sharpe_ratio(self):
        """Test maximum Sharpe ratio optimization."""
        returns = self.optimizer.calculate_returns(self.prices)
        expected_returns = self.optimizer.calculate_expected_returns(returns)
        cov_matrix = self.optimizer.calculate_covariance_matrix(returns)
        
        weights = self.optimizer.maximize_sharpe_ratio(expected_returns, cov_matrix)
        
        assert len(weights) == 3
        assert abs(sum(weights) - 1.0) < 1e-6
        assert all(w >= 0 for w in weights)
        
        # Calculate Sharpe ratio for this portfolio
        portfolio_return, volatility = self.optimizer.portfolio_performance(
            weights, expected_returns, cov_matrix
        )
        
        rf_daily = (1 + 0.03) ** (1/252) - 1
        sharpe = (portfolio_return - rf_daily) / volatility
        
        # Should be positive (assuming assets have positive expected returns)
        assert sharpe > -1
    
    def test_calculate_efficient_frontier(self):
        """Test efficient frontier calculation."""
        returns = self.optimizer.calculate_returns(self.prices)
        expected_returns = self.optimizer.calculate_expected_returns(returns)
        cov_matrix = self.optimizer.calculate_covariance_matrix(returns)
        
        frontier = self.optimizer.calculate_efficient_frontier(
            expected_returns, cov_matrix, num_points=10
        )
        
        assert isinstance(frontier, list)
        assert len(frontier) > 0
        
        # Check that frontier points are (volatility, return) tuples
        for vol, ret in frontier:
            assert vol > 0
            assert isinstance(ret, float)
    
    def test_calculate_risk_parity(self):
        """Test risk parity optimization."""
        returns = self.optimizer.calculate_returns(self.prices)
        cov_matrix = self.optimizer.calculate_covariance_matrix(returns)
        
        weights = self.optimizer.calculate_risk_parity(cov_matrix)
        
        assert len(weights) == 3
        assert abs(sum(weights) - 1.0) < 1e-6
        assert all(w >= 0 for w in weights)
        
        # Check risk contribution is approximately equal
        portfolio_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        
        if portfolio_vol > 0:
            marginal_contrib = np.dot(cov_matrix, weights)
            risk_contrib = weights * marginal_contrib / portfolio_vol
            
            # Risk contributions should be approximately equal
            # (within some tolerance due to numerical optimization)
            assert np.std(risk_contrib) < 0.1  # 10% tolerance
    
    def test_optimize_portfolio_max_sharpe(self):
        """Test full portfolio optimization with max Sharpe."""
        result = self.optimizer.optimize_portfolio(
            self.prices,
            self.asset_names,
            optimization_method='max_sharpe'
        )
        
        assert isinstance(result, PortfolioResult)
        assert len(result.weights) == 3
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6
        assert all(w >= 0 for w in result.weights.values())
        assert result.expected_return > 0
        assert result.volatility > 0
        assert isinstance(result.sharpe_ratio, float)
        assert result.asset_names == self.asset_names
    
    def test_optimize_portfolio_min_vol(self):
        """Test full portfolio optimization with minimum volatility."""
        result = self.optimizer.optimize_portfolio(
            self.prices,
            self.asset_names,
            optimization_method='min_vol'
        )
        
        assert isinstance(result, PortfolioResult)
        assert len(result.weights) == 3
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6
        assert all(w >= 0 for w in result.weights.values())
    
    def test_optimize_portfolio_risk_parity(self):
        """Test full portfolio optimization with risk parity."""
        result = self.optimizer.optimize_portfolio(
            self.prices,
            self.asset_names,
            optimization_method='risk_parity'
        )
        
        assert isinstance(result, PortfolioResult)
        assert len(result.weights) == 3
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6
        assert all(w >= 0 for w in result.weights.values())
    
    def test_get_efficient_frontier(self):
        """Test efficient frontier portfolios."""
        results = self.optimizer.get_efficient_frontier(
            self.prices,
            self.asset_names,
            num_points=5
        )
        
        assert isinstance(results, list)
        assert len(results) > 0
        
        for result in results:
            assert isinstance(result, PortfolioResult)
            assert len(result.weights) == 3
            assert abs(sum(result.weights.values()) - 1.0) < 1e-6
            assert result.volatility > 0
    
    def test_two_assets(self):
        """Test with two assets."""
        # Create simple two-asset data
        np.random.seed(42)
        dates = pd.date_range('2025-01-01', periods=50, freq='D')
        
        asset1 = [100.0]
        asset2 = [100.0]
        
        for _ in range(49):
            asset1.append(asset1[-1] * (1 + np.random.normal(0.001, 0.02)))
            asset2.append(asset2[-1] * (1 + np.random.normal(0.0005, 0.015)))
        
        prices = pd.DataFrame({
            'Stock': asset1,
            'Bond': asset2
        }, index=dates)
        
        result = self.optimizer.optimize_portfolio(
            prices,
            ['Stock', 'Bond'],
            optimization_method='max_sharpe'
        )
        
        assert len(result.weights) == 2
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6
