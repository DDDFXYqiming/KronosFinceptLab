"""
Risk metrics calculation module.
"""
from typing import List, Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy import stats
from kronos_fincept import native


@dataclass
class RiskMetrics:
    """Risk metrics result."""
    symbol: str
    var_95: float  # 95% VaR
    var_99: float  # 99% VaR
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    volatility: float
    downside_deviation: float
    beta: Optional[float] = None
    alpha: Optional[float] = None
    
    @property
    def var_95_annualized(self) -> float:
        """Annualized 95% VaR."""
        return self.var_95 * np.sqrt(252)
    
    @property
    def var_99_annualized(self) -> float:
        """Annualized 99% VaR."""
        return self.var_99 * np.sqrt(252)


class RiskCalculator:
    """
    Risk metrics calculator.
    
    Supports VaR (Historical, Parametric, Monte Carlo), Sharpe, Sortino,
    maximum drawdown, and volatility calculations.
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.03,
        trading_days_per_year: int = 252
    ):
        self.risk_free_rate = risk_free_rate
        self.trading_days_per_year = trading_days_per_year
    
    def calculate_returns(self, prices: List[float]) -> np.ndarray:
        """
        Calculate daily returns from prices.
        
        Args:
            prices: List of prices
            
        Returns:
            Array of daily returns
        """
        if len(prices) < 2:
            return np.array([])
        
        prices_array = np.array(prices)
        returns = (prices_array[1:] - prices_array[:-1]) / prices_array[:-1]
        
        return returns
    
    def calculate_log_returns(self, prices: List[float]) -> np.ndarray:
        """
        Calculate log returns from prices.
        
        Args:
            prices: List of prices
            
        Returns:
            Array of log returns
        """
        if len(prices) < 2:
            return np.array([])
        
        prices_array = np.array(prices)
        log_returns = np.log(prices_array[1:] / prices_array[:-1])
        
        return log_returns
    
    def calculate_var_historical(
        self,
        returns: np.ndarray,
        confidence_level: float = 0.95,
        holding_period: int = 1
    ) -> float:
        """
        Calculate Value at Risk using historical simulation.
        
        Args:
            returns: Array of returns
            confidence_level: Confidence level (e.g., 0.95 for 95%)
            holding_period: Holding period in days
            
        Returns:
            VaR value (positive number representing loss)
        """
        rust_var = native.calculate_var_historical(returns, confidence_level, holding_period)
        if rust_var is not None:
            return rust_var

        if len(returns) == 0:
            return 0.0
        
        # Sort returns
        sorted_returns = np.sort(returns)
        
        # Find the index corresponding to the confidence level
        index = int((1 - confidence_level) * len(sorted_returns))
        
        # VaR is the negative of the return at that index
        var = -sorted_returns[index] * np.sqrt(holding_period)
        
        return var
    
    def calculate_var_parametric(
        self,
        returns: np.ndarray,
        confidence_level: float = 0.95,
        holding_period: int = 1
    ) -> float:
        """
        Calculate VaR using parametric method (assumes normal distribution).
        
        Args:
            returns: Array of returns
            confidence_level: Confidence level
            holding_period: Holding period in days
            
        Returns:
            VaR value
        """
        if len(returns) == 0:
            return 0.0
        
        mean = np.mean(returns)
        std = np.std(returns)
        
        # Z-score for confidence level
        z_score = stats.norm.ppf(1 - confidence_level)
        
        # VaR calculation
        var = -(mean + z_score * std) * np.sqrt(holding_period)
        
        return var
    
    def calculate_var_monte_carlo(
        self,
        returns: np.ndarray,
        confidence_level: float = 0.95,
        holding_period: int = 1,
        num_simulations: int = 10000
    ) -> float:
        """
        Calculate VaR using Monte Carlo simulation.
        
        Args:
            returns: Array of returns
            confidence_level: Confidence level
            holding_period: Holding period in days
            num_simulations: Number of simulations
            
        Returns:
            VaR value
        """
        if len(returns) == 0:
            return 0.0
        
        mean = np.mean(returns)
        std = np.std(returns)
        
        # Generate random returns
        simulated_returns = np.random.normal(
            mean * holding_period,
            std * np.sqrt(holding_period),
            num_simulations
        )
        
        # Calculate VaR
        var = -np.percentile(simulated_returns, (1 - confidence_level) * 100)
        
        return var
    
    def calculate_sharpe_ratio(
        self,
        returns: np.ndarray,
        risk_free_rate: Optional[float] = None
    ) -> float:
        """
        Calculate Sharpe ratio.
        
        Sharpe = (Rp - Rf) / σp
        
        Args:
            returns: Array of returns
            risk_free_rate: Risk-free rate (annualized)
            
        Returns:
            Sharpe ratio
        """
        if len(returns) == 0:
            return 0.0
        
        rf = risk_free_rate or self.risk_free_rate
        
        # Convert annual risk-free rate to daily
        rf_daily = (1 + rf) ** (1 / self.trading_days_per_year) - 1
        
        excess_returns = returns - rf_daily
        
        if np.std(excess_returns) == 0:
            return 0.0
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns)
        
        # Annualize
        sharpe_annualized = sharpe * np.sqrt(self.trading_days_per_year)
        
        return sharpe_annualized
    
    def calculate_sortino_ratio(
        self,
        returns: np.ndarray,
        risk_free_rate: Optional[float] = None,
        target_return: float = 0.0
    ) -> float:
        """
        Calculate Sortino ratio.
        
        Sortino = (Rp - Rf) / Downside Deviation
        
        Args:
            returns: Array of returns
            risk_free_rate: Risk-free rate
            target_return: Target return for downside calculation
            
        Returns:
            Sortino ratio
        """
        if len(returns) == 0:
            return 0.0
        
        rf = risk_free_rate or self.risk_free_rate
        
        # Convert annual risk-free rate to daily
        rf_daily = (1 + rf) ** (1 / self.trading_days_per_year) - 1
        
        excess_returns = returns - rf_daily
        
        # Calculate downside deviation
        downside_returns = returns[returns < target_return]
        
        if len(downside_returns) == 0:
            return float('inf') if np.mean(excess_returns) > 0 else 0.0
        
        downside_deviation = np.sqrt(np.mean(downside_returns ** 2))
        
        if downside_deviation == 0:
            return 0.0
        
        sortino = np.mean(excess_returns) / downside_deviation
        
        # Annualize
        sortino_annualized = sortino * np.sqrt(self.trading_days_per_year)
        
        return sortino_annualized
    
    def calculate_max_drawdown(self, prices: List[float]) -> float:
        """
        Calculate maximum drawdown.
        
        Args:
            prices: List of prices
            
        Returns:
            Maximum drawdown as a positive number (e.g., 0.3 for 30%)
        """
        if len(prices) < 2:
            return 0.0
        
        prices_array = np.array(prices)
        
        # Calculate cumulative returns
        cummax = np.maximum.accumulate(prices_array)
        drawdowns = (cummax - prices_array) / cummax
        
        max_drawdown = np.max(drawdowns)
        
        return max_drawdown
    
    def calculate_volatility(
        self,
        returns: np.ndarray,
        annualize: bool = True
    ) -> float:
        """
        Calculate volatility (standard deviation of returns).
        
        Args:
            returns: Array of returns
            annualize: Whether to annualize
            
        Returns:
            Volatility
        """
        if len(returns) == 0:
            return 0.0
        
        volatility = np.std(returns)
        
        if annualize:
            volatility = volatility * np.sqrt(self.trading_days_per_year)
        
        return volatility
    
    def calculate_downside_deviation(
        self,
        returns: np.ndarray,
        target_return: float = 0.0
    ) -> float:
        """
        Calculate downside deviation.
        
        Args:
            returns: Array of returns
            target_return: Target return
            
        Returns:
            Downside deviation
        """
        if len(returns) == 0:
            return 0.0
        
        downside_returns = returns[returns < target_return]
        
        if len(downside_returns) == 0:
            return 0.0
        
        downside_deviation = np.sqrt(np.mean(downside_returns ** 2))
        
        return downside_deviation
    
    def calculate_beta(
        self,
        asset_returns: np.ndarray,
        market_returns: np.ndarray
    ) -> float:
        """
        Calculate beta.
        
        β = Cov(Ra, Rm) / Var(Rm)
        
        Args:
            asset_returns: Asset returns
            market_returns: Market returns
            
        Returns:
            Beta
        """
        if len(asset_returns) != len(market_returns) or len(asset_returns) < 2:
            return 1.0
        
        covariance = np.cov(asset_returns, market_returns)[0][1]
        market_variance = np.var(market_returns)
        
        if market_variance == 0:
            return 1.0
        
        beta = covariance / market_variance
        
        return beta
    
    def calculate_alpha(
        self,
        asset_returns: np.ndarray,
        market_returns: np.ndarray,
        risk_free_rate: Optional[float] = None
    ) -> float:
        """
        Calculate alpha (Jensen's alpha).
        
        α = Rp - [Rf + β * (Rm - Rf)]
        
        Args:
            asset_returns: Asset returns
            market_returns: Market returns
            risk_free_rate: Risk-free rate
            
        Returns:
            Alpha (annualized)
        """
        if len(asset_returns) < 2 or len(market_returns) < 2:
            return 0.0
        
        rf = risk_free_rate or self.risk_free_rate
        
        # Convert to daily
        rf_daily = (1 + rf) ** (1 / self.trading_days_per_year) - 1
        
        # Calculate beta
        beta = self.calculate_beta(asset_returns, market_returns)
        
        # Calculate expected return
        expected_return = rf_daily + beta * (np.mean(market_returns) - rf_daily)
        
        # Calculate alpha
        alpha_daily = np.mean(asset_returns) - expected_return
        
        # Annualize
        alpha_annualized = alpha_daily * self.trading_days_per_year
        
        return alpha_annualized
    
    def calculate_risk_metrics(
        self,
        symbol: str,
        prices: List[float],
        market_prices: Optional[List[float]] = None,
        confidence_level: float = 0.95
    ) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics.
        
        Args:
            symbol: Asset symbol
            prices: List of prices
            market_prices: Market prices for beta/alpha calculation
            confidence_level: Confidence level for VaR
            
        Returns:
            RiskMetrics object
        """
        returns = self.calculate_returns(prices)
        
        if len(returns) == 0:
            return RiskMetrics(
                symbol=symbol,
                var_95=0.0,
                var_99=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                volatility=0.0,
                downside_deviation=0.0
            )
        
        # Calculate metrics
        var_95 = self.calculate_var_historical(returns, 0.95)
        var_99 = self.calculate_var_historical(returns, 0.99)
        sharpe = self.calculate_sharpe_ratio(returns)
        sortino = self.calculate_sortino_ratio(returns)
        max_dd = self.calculate_max_drawdown(prices)
        volatility = self.calculate_volatility(returns)
        downside_dev = self.calculate_downside_deviation(returns)
        
        # Calculate beta and alpha if market data provided
        beta = None
        alpha = None
        
        if market_prices and len(market_prices) > 1:
            market_returns = self.calculate_returns(market_prices)
            
            if len(market_returns) == len(returns):
                beta = self.calculate_beta(returns, market_returns)
                alpha = self.calculate_alpha(returns, market_returns)
        
        return RiskMetrics(
            symbol=symbol,
            var_95=var_95,
            var_99=var_99,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            volatility=volatility,
            downside_deviation=downside_dev,
            beta=beta,
            alpha=alpha
        )
