"""
Derivatives pricing module.
"""
from typing import Optional
from dataclasses import dataclass
import numpy as np
from scipy.stats import norm

from kronos_fincept import native


@dataclass
class OptionResult:
    """Option pricing result."""
    option_type: str  # 'call' or 'put'
    underlying_price: float
    strike_price: float
    time_to_expiration: float
    risk_free_rate: float
    volatility: float
    option_price: float
    
    # Greeks
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    
    @property
    def intrinsic_value(self) -> float:
        """Intrinsic value of the option."""
        if self.option_type == 'call':
            return max(0, self.underlying_price - self.strike_price)
        else:
            return max(0, self.strike_price - self.underlying_price)
    
    @property
    def time_value(self) -> float:
        """Time value of the option."""
        return self.option_price - self.intrinsic_value


class DerivativesPricer:
    """
    Derivatives pricing using Black-Scholes model.
    
    Supports:
    - European call and put options
    - Greeks calculation (Delta, Gamma, Theta, Vega, Rho)
    - Binary options
    """
    
    def __init__(self, risk_free_rate: float = 0.03):
        self.risk_free_rate = risk_free_rate
    
    def black_scholes(
        self,
        underlying_price: float,
        strike_price: float,
        time_to_expiration: float,
        volatility: float,
        option_type: str = 'call'
    ) -> OptionResult:
        """
        Calculate option price using Black-Scholes model.
        
        Args:
            underlying_price: Current price of underlying asset
            strike_price: Strike price
            time_to_expiration: Time to expiration in years
            volatility: Volatility (annualized)
            option_type: 'call' or 'put'
            
        Returns:
            OptionResult with price and Greeks
        """
        rust_result = native.price_black_scholes(
            underlying_price,
            strike_price,
            time_to_expiration,
            volatility,
            self.risk_free_rate,
            option_type,
        )
        if rust_result is not None:
            return OptionResult(
                option_type=str(rust_result["option_type"]),
                underlying_price=float(rust_result["underlying_price"]),
                strike_price=float(rust_result["strike_price"]),
                time_to_expiration=float(rust_result["time_to_expiration"]),
                risk_free_rate=float(rust_result["risk_free_rate"]),
                volatility=float(rust_result["volatility"]),
                option_price=float(rust_result["option_price"]),
                delta=float(rust_result["delta"]),
                gamma=float(rust_result["gamma"]),
                theta=float(rust_result["theta"]),
                vega=float(rust_result["vega"]),
                rho=float(rust_result["rho"]),
            )

        # Handle edge cases
        if time_to_expiration <= 0:
            # Option expired
            if option_type == 'call':
                price = max(0, underlying_price - strike_price)
            else:
                price = max(0, strike_price - underlying_price)
            
            return OptionResult(
                option_type=option_type,
                underlying_price=underlying_price,
                strike_price=strike_price,
                time_to_expiration=0,
                risk_free_rate=self.risk_free_rate,
                volatility=volatility,
                option_price=price,
                delta=1.0 if option_type == 'call' and underlying_price > strike_price else 
                      -1.0 if option_type == 'put' and underlying_price < strike_price else 0.0,
                gamma=0.0,
                theta=0.0,
                vega=0.0,
                rho=0.0
            )
        
        if volatility <= 0:
            raise ValueError("Volatility must be positive")
        
        if underlying_price <= 0 or strike_price <= 0:
            raise ValueError("Prices must be positive")
        
        # Black-Scholes formula
        d1 = (np.log(underlying_price / strike_price) + 
              (self.risk_free_rate + 0.5 * volatility ** 2) * time_to_expiration) / \
             (volatility * np.sqrt(time_to_expiration))
        
        d2 = d1 - volatility * np.sqrt(time_to_expiration)
        
        if option_type == 'call':
            price = (underlying_price * norm.cdf(d1) - 
                    strike_price * np.exp(-self.risk_free_rate * time_to_expiration) * norm.cdf(d2))
        elif option_type == 'put':
            price = (strike_price * np.exp(-self.risk_free_rate * time_to_expiration) * norm.cdf(-d2) - 
                    underlying_price * norm.cdf(-d1))
        else:
            raise ValueError("option_type must be 'call' or 'put'")
        
        # Calculate Greeks
        delta = self._calculate_delta(underlying_price, strike_price, time_to_expiration, 
                                     volatility, option_type, d1)
        
        gamma = self._calculate_gamma(underlying_price, time_to_expiration, volatility, d1)
        
        theta = self._calculate_theta(underlying_price, strike_price, time_to_expiration, 
                                     volatility, option_type, d1, d2)
        
        vega = self._calculate_vega(underlying_price, time_to_expiration, volatility, d1)
        
        rho = self._calculate_rho(strike_price, time_to_expiration, option_type, d2)
        
        return OptionResult(
            option_type=option_type,
            underlying_price=underlying_price,
            strike_price=strike_price,
            time_to_expiration=time_to_expiration,
            risk_free_rate=self.risk_free_rate,
            volatility=volatility,
            option_price=price,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=rho
        )
    
    def _calculate_delta(
        self,
        underlying_price: float,
        strike_price: float,
        time_to_expiration: float,
        volatility: float,
        option_type: str,
        d1: float
    ) -> float:
        """Calculate delta."""
        if option_type == 'call':
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1
    
    def _calculate_gamma(
        self,
        underlying_price: float,
        time_to_expiration: float,
        volatility: float,
        d1: float
    ) -> float:
        """Calculate gamma."""
        if time_to_expiration <= 0:
            return 0.0
        
        return norm.pdf(d1) / (underlying_price * volatility * np.sqrt(time_to_expiration))
    
    def _calculate_theta(
        self,
        underlying_price: float,
        strike_price: float,
        time_to_expiration: float,
        volatility: float,
        option_type: str,
        d1: float,
        d2: float
    ) -> float:
        """Calculate theta."""
        if time_to_expiration <= 0:
            return 0.0
        
        common_term = (underlying_price * norm.pdf(d1) * volatility) / (2 * np.sqrt(time_to_expiration))
        
        if option_type == 'call':
            theta = (-common_term - 
                    self.risk_free_rate * strike_price * np.exp(-self.risk_free_rate * time_to_expiration) * norm.cdf(d2))
        else:
            theta = (-common_term + 
                    self.risk_free_rate * strike_price * np.exp(-self.risk_free_rate * time_to_expiration) * norm.cdf(-d2))
        
        # Convert to daily theta
        return theta / 365
    
    def _calculate_vega(
        self,
        underlying_price: float,
        time_to_expiration: float,
        volatility: float,
        d1: float
    ) -> float:
        """Calculate vega."""
        return underlying_price * np.sqrt(time_to_expiration) * norm.pdf(d1) / 100
    
    def _calculate_rho(
        self,
        strike_price: float,
        time_to_expiration: float,
        option_type: str,
        d2: float
    ) -> float:
        """Calculate rho."""
        if option_type == 'call':
            return (strike_price * time_to_expiration * 
                   np.exp(-self.risk_free_rate * time_to_expiration) * norm.cdf(d2)) / 100
        else:
            return (-strike_price * time_to_expiration * 
                   np.exp(-self.risk_free_rate * time_to_expiration) * norm.cdf(-d2)) / 100
    
    def price_european_call(
        self,
        underlying_price: float,
        strike_price: float,
        time_to_expiration: float,
        volatility: float
    ) -> OptionResult:
        """Price a European call option."""
        return self.black_scholes(
            underlying_price, strike_price, time_to_expiration, volatility, 'call'
        )
    
    def price_european_put(
        self,
        underlying_price: float,
        strike_price: float,
        time_to_expiration: float,
        volatility: float
    ) -> OptionResult:
        """Price a European put option."""
        return self.black_scholes(
            underlying_price, strike_price, time_to_expiration, volatility, 'put'
        )
    
    def put_call_parity(
        self,
        call_price: float,
        underlying_price: float,
        strike_price: float,
        time_to_expiration: float
    ) -> float:
        """
        Calculate put price using put-call parity.
        
        Put = Call - S + K * e^(-rT)
        
        Args:
            call_price: Call option price
            underlying_price: Current price
            strike_price: Strike price
            time_to_expiration: Time to expiration
            
        Returns:
            Implied put price
        """
        rust_price = native.calculate_put_call_parity(
            call_price,
            underlying_price,
            strike_price,
            time_to_expiration,
            self.risk_free_rate,
        )
        if rust_price is not None:
            return rust_price

        return call_price - underlying_price + strike_price * np.exp(-self.risk_free_rate * time_to_expiration)
    
    def implied_volatility(
        self,
        market_price: float,
        underlying_price: float,
        strike_price: float,
        time_to_expiration: float,
        option_type: str = 'call',
        initial_guess: float = 0.2,
        tolerance: float = 1e-6,
        max_iterations: int = 100
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson method.
        
        Args:
            market_price: Observed market price
            underlying_price: Current price
            strike_price: Strike price
            time_to_expiration: Time to expiration
            option_type: 'call' or 'put'
            initial_guess: Initial volatility guess
            tolerance: Convergence tolerance
            max_iterations: Maximum iterations
            
        Returns:
            Implied volatility
        """
        sigma = initial_guess
        
        for _ in range(max_iterations):
            result = self.black_scholes(
                underlying_price, strike_price, time_to_expiration, sigma, option_type
            )
            
            diff = result.option_price - market_price
            
            if abs(diff) < tolerance:
                return sigma
            
            # Newton-Raphson update
            sigma -= diff / (result.vega * 100)  # vega is per 1% change
        
        return sigma
