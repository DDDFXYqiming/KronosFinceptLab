"""
Portfolio optimization module.
"""
from typing import List, Optional, Dict
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import minimize


@dataclass
class PortfolioResult:
    """Portfolio optimization result."""
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    asset_names: List[str]
    
    @property
    def num_assets(self) -> int:
        """Number of assets."""
        return len(self.weights)
    
    @property
    def is_long_only(self) -> bool:
        """Check if all weights are non-negative."""
        return all(w >= 0 for w in self.weights.values())


class PortfolioOptimizer:
    """
    Portfolio optimization using Mean-Variance Optimization (Markowitz).
    
    Supports:
    - Minimum variance portfolio
    - Maximum Sharpe ratio portfolio
    - Efficient frontier calculation
    - Risk parity model
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.03,
        trading_days_per_year: int = 252
    ):
        self.risk_free_rate = risk_free_rate
        self.trading_days_per_year = trading_days_per_year
    
    def calculate_returns(self, prices: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate daily returns from prices.
        
        Args:
            prices: DataFrame with dates as index and assets as columns
            
        Returns:
            DataFrame of daily returns
        """
        return prices.pct_change().dropna()
    
    def calculate_expected_returns(self, returns: pd.DataFrame) -> np.ndarray:
        """
        Calculate expected (mean) returns.
        
        Args:
            returns: DataFrame of returns
            
        Returns:
            Array of expected returns
        """
        return returns.mean().values
    
    def calculate_covariance_matrix(self, returns: pd.DataFrame) -> np.ndarray:
        """
        Calculate covariance matrix.
        
        Args:
            returns: DataFrame of returns
            
        Returns:
            Covariance matrix
        """
        return returns.cov().values
    
    def portfolio_performance(
        self,
        weights: np.ndarray,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> tuple:
        """
        Calculate portfolio return and volatility.
        
        Args:
            weights: Portfolio weights
            expected_returns: Expected returns
            cov_matrix: Covariance matrix
            
        Returns:
            Tuple of (return, volatility)
        """
        returns = np.dot(weights, expected_returns)
        volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        
        return returns, volatility
    
    def minimize_volatility(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray
    ) -> np.ndarray:
        """
        Find minimum variance portfolio.
        
        Args:
            expected_returns: Expected returns
            cov_matrix: Covariance matrix
            
        Returns:
            Optimal weights
        """
        num_assets = len(expected_returns)
        
        # Objective function: minimize portfolio variance
        def objective(weights):
            return np.dot(weights.T, np.dot(cov_matrix, weights))
        
        # Constraints: weights sum to 1
        constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]
        
        # Bounds: no short selling (0 <= weight <= 1)
        bounds = tuple((0, 1) for _ in range(num_assets))
        
        # Initial guess: equal weights
        initial_guess = np.array([1.0 / num_assets] * num_assets)
        
        # Optimize
        result = minimize(
            objective,
            initial_guess,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        return result.x
    
    def maximize_sharpe_ratio(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        risk_free_rate: Optional[float] = None
    ) -> np.ndarray:
        """
        Find maximum Sharpe ratio portfolio.
        
        Args:
            expected_returns: Expected returns
            cov_matrix: Covariance matrix
            risk_free_rate: Risk-free rate
            
        Returns:
            Optimal weights
        """
        rf = risk_free_rate or self.risk_free_rate
        num_assets = len(expected_returns)
        
        # Objective function: maximize Sharpe ratio (minimize negative Sharpe)
        def objective(weights):
            returns, volatility = self.portfolio_performance(
                weights, expected_returns, cov_matrix
            )
            
            if volatility == 0:
                return 0
            
            sharpe = (returns - rf) / volatility
            return -sharpe  # Minimize negative Sharpe
        
        # Constraints: weights sum to 1
        constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]
        
        # Bounds: no short selling
        bounds = tuple((0, 1) for _ in range(num_assets))
        
        # Initial guess: equal weights
        initial_guess = np.array([1.0 / num_assets] * num_assets)
        
        # Optimize
        result = minimize(
            objective,
            initial_guess,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        return result.x
    
    def calculate_efficient_frontier(
        self,
        expected_returns: np.ndarray,
        cov_matrix: np.ndarray,
        num_points: int = 50
    ) -> List[tuple]:
        """
        Calculate efficient frontier.
        
        Args:
            expected_returns: Expected returns
            cov_matrix: Covariance matrix
            num_points: Number of points on frontier
            
        Returns:
            List of (volatility, return) tuples
        """
        # Find minimum and maximum return portfolios
        min_vol_weights = self.minimize_volatility(expected_returns, cov_matrix)
        min_vol_return, _ = self.portfolio_performance(
            min_vol_weights, expected_returns, cov_matrix
        )
        
        # Target returns from min to max
        max_return = np.max(expected_returns)
        target_returns = np.linspace(min_vol_return, max_return, num_points)
        
        efficient_frontier = []
        
        for target_return in target_returns:
            # Minimize volatility for target return
            num_assets = len(expected_returns)
            
            def objective(weights):
                return np.dot(weights.T, np.dot(cov_matrix, weights))
            
            constraints = [
                {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
                {'type': 'eq', 'fun': lambda x: np.dot(x, expected_returns) - target_return}
            ]
            
            bounds = tuple((0, 1) for _ in range(num_assets))
            initial_guess = np.array([1.0 / num_assets] * num_assets)
            
            result = minimize(
                objective,
                initial_guess,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints
            )
            
            if result.success:
                volatility = np.sqrt(np.dot(result.x.T, np.dot(cov_matrix, result.x)))
                efficient_frontier.append((volatility, target_return))
        
        return efficient_frontier
    
    def calculate_risk_parity(
        self,
        cov_matrix: np.ndarray
    ) -> np.ndarray:
        """
        Calculate risk parity portfolio.
        
        Args:
            cov_matrix: Covariance matrix
            
        Returns:
            Weights that equalize risk contribution
        """
        num_assets = len(cov_matrix)
        
        # Objective: minimize sum of squared differences in risk contribution
        def objective(weights):
            portfolio_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            
            if portfolio_vol == 0:
                return 0
            
            # Risk contribution of each asset
            marginal_contrib = np.dot(cov_matrix, weights)
            risk_contrib = weights * marginal_contrib / portfolio_vol
            
            # Target: equal risk contribution
            target_risk_contrib = portfolio_vol / num_assets
            
            # Minimize squared differences
            return np.sum((risk_contrib - target_risk_contrib) ** 2)
        
        # Constraints: weights sum to 1
        constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]
        
        # Bounds: no short selling
        bounds = tuple((0, 1) for _ in range(num_assets))
        
        # Initial guess: equal weights
        initial_guess = np.array([1.0 / num_assets] * num_assets)
        
        # Optimize
        result = minimize(
            objective,
            initial_guess,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        return result.x
    
    def optimize_portfolio(
        self,
        prices: pd.DataFrame,
        asset_names: List[str],
        optimization_method: str = 'max_sharpe',
        risk_free_rate: Optional[float] = None
    ) -> PortfolioResult:
        """
        Optimize portfolio using specified method.
        
        Args:
            prices: DataFrame with dates as index and assets as columns
            asset_names: List of asset names
            optimization_method: 'min_vol', 'max_sharpe', 'risk_parity', or 'efficient_frontier'
            risk_free_rate: Risk-free rate
            
        Returns:
            PortfolioResult with optimal weights and metrics
        """
        # Calculate returns
        returns = self.calculate_returns(prices)
        
        # Calculate expected returns and covariance matrix
        expected_returns = self.calculate_expected_returns(returns)
        cov_matrix = self.calculate_covariance_matrix(returns)
        
        # Optimize based on method
        if optimization_method == 'min_vol':
            weights = self.minimize_volatility(expected_returns, cov_matrix)
        elif optimization_method == 'max_sharpe':
            weights = self.maximize_sharpe_ratio(
                expected_returns, cov_matrix, risk_free_rate
            )
        elif optimization_method == 'risk_parity':
            weights = self.calculate_risk_parity(cov_matrix)
        else:
            # Default to max Sharpe
            weights = self.maximize_sharpe_ratio(
                expected_returns, cov_matrix, risk_free_rate
            )
        
        # Calculate portfolio performance
        portfolio_return, volatility = self.portfolio_performance(
            weights, expected_returns, cov_matrix
        )
        
        # Annualize
        portfolio_return_annual = portfolio_return * self.trading_days_per_year
        volatility_annual = volatility * np.sqrt(self.trading_days_per_year)
        
        # Calculate Sharpe ratio
        rf = risk_free_rate or self.risk_free_rate
        sharpe = (portfolio_return_annual - rf) / volatility_annual if volatility_annual > 0 else 0
        
        # Create weights dictionary
        weights_dict = {name: float(weight) for name, weight in zip(asset_names, weights)}
        
        return PortfolioResult(
            weights=weights_dict,
            expected_return=portfolio_return_annual,
            volatility=volatility_annual,
            sharpe_ratio=sharpe,
            asset_names=asset_names
        )
    
    def get_efficient_frontier(
        self,
        prices: pd.DataFrame,
        asset_names: List[str],
        num_points: int = 50
    ) -> List[PortfolioResult]:
        """
        Get efficient frontier portfolios.
        
        Args:
            prices: DataFrame with prices
            asset_names: List of asset names
            num_points: Number of points on frontier
            
        Returns:
            List of PortfolioResult objects
        """
        returns = self.calculate_returns(prices)
        expected_returns = self.calculate_expected_returns(returns)
        cov_matrix = self.calculate_covariance_matrix(returns)
        
        frontier_points = self.calculate_efficient_frontier(
            expected_returns, cov_matrix, num_points
        )
        
        # Convert to PortfolioResult objects
        results = []
        
        for volatility, ret in frontier_points:
            # Find weights for this return level (approximate)
            # For simplicity, use equal weights scaled to match the return
            weights = np.array([1.0 / len(asset_names)] * len(asset_names))
            
            # Calculate actual return for these weights
            actual_return = np.dot(weights, expected_returns) * self.trading_days_per_year
            
            # Calculate Sharpe ratio
            rf = self.risk_free_rate
            sharpe = (actual_return - rf) / volatility if volatility > 0 else 0
            
            weights_dict = {name: float(weight) for name, weight in zip(asset_names, weights)}
            
            results.append(PortfolioResult(
                weights=weights_dict,
                expected_return=actual_return,
                volatility=volatility,
                sharpe_ratio=sharpe,
                asset_names=asset_names
            ))
        
        return results
