"""
Derivatives pricing module.
"""
from typing import Optional
from dataclasses import dataclass
from datetime import date, timedelta
import math
import numpy as np
from scipy.stats import norm


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


# ── Bond Pricing ────────────────────────────────────────────────────

@dataclass
class BondResult:
    clean_price: float
    dirty_price: float
    accrued_interest: float
    duration: float       # Modified duration
    convexity: float
    ytm: float | None = None


def price_bond(
    issue_date: date,
    settle_date: date,
    maturity_date: date,
    coupon_rate: float,
    ytm: float,
    freq: int = 2,
    face: float = 100.0,
) -> BondResult:
    """Price a fixed-rate bond. Returns clean/dirty price, duration, convexity."""
    if settle_date >= maturity_date:
        raise ValueError("Settlement date must be before maturity")

    def _year_frac(d1: date, d2: date) -> float:
        return (d2 - d1).days / 365.0

    # Calculate periods
    remaining = _year_frac(settle_date, maturity_date)
    n = max(1, round(remaining * freq))
    period = 1.0 / freq
    rate = ytm / freq
    coupon = coupon_rate / freq * face

    # Dirty price: PV of coupons + PV of face
    pv_coupons = sum(coupon / (1 + rate) ** t for t in range(1, n + 1))
    pv_face = face / (1 + rate) ** n
    dirty_price = pv_coupons + pv_face

    # Accrued interest
    last_coupon_date = settle_date
    while last_coupon_date > issue_date:
        candidate = last_coupon_date - timedelta(days=int(365 / freq))
        if candidate < issue_date:
            break
        last_coupon_date = candidate
    accrued = coupon * _year_frac(last_coupon_date, settle_date) / period if period > 0 else 0.0
    clean_price = dirty_price - accrued

    # Duration (modified)
    macaulay = sum(t * period * coupon / (1 + rate) ** t for t in range(1, n + 1)) / dirty_price
    macaulay += n * period * face / (1 + rate) ** n / dirty_price
    modified_duration = macaulay / (1 + ytm / freq)

    # Convexity
    convexity = sum(t * period * (t * period + period) * coupon / (1 + rate) ** t for t in range(1, n + 1))
    convexity += n * period * (n * period + period) * face / (1 + rate) ** n
    convexity = convexity / dirty_price / (1 + ytm / freq) ** 2

    return BondResult(
        clean_price=round(clean_price, 4),
        dirty_price=round(dirty_price, 4),
        accrued_interest=round(accrued, 4),
        duration=round(modified_duration, 4),
        convexity=round(convexity, 4),
        ytm=ytm,
    )


def bond_ytm(
    issue_date: date,
    settle_date: date,
    maturity_date: date,
    coupon_rate: float,
    clean_price: float,
    freq: int = 2,
    face: float = 100.0,
    guess: float = 0.05,
) -> float:
    """Solve for YTM given clean price using Newton's method."""
    from scipy.optimize import newton
    def f(ytm: float) -> float:
        result = price_bond(issue_date, settle_date, maturity_date, coupon_rate, ytm, freq, face)
        return result.clean_price - clean_price
    try:
        return round(float(newton(f, guess, maxiter=100, tol=1e-8)), 6)
    except Exception:
        raise ValueError("YTM solver did not converge")


# ── CDS Pricing (Reduced-Form) ──────────────────────────────────────

@dataclass
class CdsResult:
    upfront: float        # Upfront premium (per notional)
    hazard_rate: float    # Implied hazard rate
    survival_prob: float  # Survival probability to maturity
    spread_bps: float     # CDS spread in bps


def price_cds(
    maturity_date: date,
    recovery_rate: float,
    spread_bps: float,
    risk_free_rate: float = 0.03,
    notional: float = 1.0,
) -> CdsResult:
    """Simple reduced-form CDS pricing model."""
    today = date.today()
    if maturity_date <= today:
        raise ValueError("Maturity must be in the future")
    T = (maturity_date - today).days / 365.0
    # Hazard rate from spread approximation: h ≈ s / (1 - R)
    hazard = spread_bps / 10000.0 / (1 - recovery_rate) if recovery_rate < 1 else 0.0
    survival = math.exp(-hazard * T)
    # Present value of premium leg
    dt = 0.25
    n = max(1, int(T / dt))
    premium_pv = sum(spread_bps / 10000.0 * notional * dt * math.exp(-risk_free_rate * t * dt) * math.exp(-hazard * t * dt) for t in range(1, n + 1))
    # Present value of protection leg
    protection_pv = (1 - recovery_rate) * notional * sum(
        math.exp(-risk_free_rate * t * dt) * (math.exp(-hazard * (t - 1) * dt) - math.exp(-hazard * t * dt))
        for t in range(1, n + 1)
    )
    upfront = protection_pv - premium_pv
    return CdsResult(
        upfront=round(upfront, 4),
        hazard_rate=round(hazard, 6),
        survival_prob=round(survival, 4),
        spread_bps=spread_bps,
    )


# ── Interest Rate Swap (IRS) Pricing ────────────────────────────────

@dataclass
class SwapResult:
    swap_value: float
    fixed_leg_pv: float
    floating_leg_pv: float
    par_rate: float  # Fair swap rate


def price_irs(
    notional: float,
    fixed_rate: float,
    tenor_years: int,
    freq: int = 2,
    discount_curve: list[float] | None = None,
) -> SwapResult:
    """Simple IRS pricing with flat or custom discount curve."""
    n = tenor_years * freq
    period = 1.0 / freq
    if discount_curve is None:
        discount_curve = [0.03] * n  # flat 3%
    fixed_leg = sum(notional * fixed_rate * period * math.exp(-discount_curve[t] * (t + 1) * period) for t in range(n))
    floating_leg = sum(notional * discount_curve[t] * period * math.exp(-discount_curve[t] * (t + 1) * period) for t in range(n))
    swap_value = floating_leg - fixed_leg
    par_rate = sum(discount_curve[t] * period * math.exp(-discount_curve[t] * (t + 1) * period) for t in range(n))
    par_rate /= sum(period * math.exp(-discount_curve[t] * (t + 1) * period) for t in range(n))
    return SwapResult(
        swap_value=round(swap_value, 4),
        fixed_leg_pv=round(fixed_leg, 4),
        floating_leg_pv=round(floating_leg, 4),
        par_rate=round(par_rate, 6),
    )


# ── FX Option (Garman-Kohlhagen) ────────────────────────────────────

@dataclass
class FxOptionResult:
    premium: float
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    implied_vol: float | None = None


def price_fx_option(
    spot: float,
    strike: float,
    time_years: float,
    vol: float,
    domestic_rate: float,
    foreign_rate: float,
    option_type: str = "call",
) -> FxOptionResult:
    """Price FX option using Garman-Kohlhagen model."""
    if time_years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        raise ValueError("All parameters must be positive")
    d1 = (math.log(spot / strike) + (domestic_rate - foreign_rate + 0.5 * vol * vol) * time_years) / (vol * math.sqrt(time_years))
    d2 = d1 - vol * math.sqrt(time_years)
    from scipy.stats import norm
    if option_type == "call":
        premium = spot * math.exp(-foreign_rate * time_years) * norm.cdf(d1) - strike * math.exp(-domestic_rate * time_years) * norm.cdf(d2)
        delta = math.exp(-foreign_rate * time_years) * norm.cdf(d1)
    else:
        premium = strike * math.exp(-domestic_rate * time_years) * norm.cdf(-d2) - spot * math.exp(-foreign_rate * time_years) * norm.cdf(-d1)
        delta = -math.exp(-foreign_rate * time_years) * norm.cdf(-d1)
    gamma = math.exp(-foreign_rate * time_years) * norm.pdf(d1) / (spot * vol * math.sqrt(time_years))
    vega = spot * math.exp(-foreign_rate * time_years) * norm.pdf(d1) * math.sqrt(time_years) / 100.0
    theta = -(
        spot * math.exp(-foreign_rate * time_years) * norm.pdf(d1) * vol / (2 * math.sqrt(time_years))
        + domestic_rate * strike * math.exp(-domestic_rate * time_years) * norm.cdf(d2 if option_type == "call" else -d2)
        - foreign_rate * spot * math.exp(-foreign_rate * time_years) * norm.cdf(d1 if option_type == "call" else -d1)
    ) / 365.0
    rho = strike * time_years * math.exp(-domestic_rate * time_years) * (norm.cdf(d2) if option_type == "call" else -norm.cdf(-d2)) / 100.0
    return FxOptionResult(
        premium=round(premium, 4),
        delta=round(delta, 4),
        gamma=round(gamma, 4),
        vega=round(vega, 4),
        theta=round(theta, 4),
        rho=round(rho, 4),
    )
