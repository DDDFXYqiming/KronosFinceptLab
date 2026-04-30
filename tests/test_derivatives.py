"""
Tests for derivatives pricing.
"""
import pytest
import numpy as np
from kronos_fincept.financial.derivatives import DerivativesPricer, OptionResult


class TestDerivativesPricer:
    """Test DerivativesPricer."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.pricer = DerivativesPricer(risk_free_rate=0.05)
    
    def test_black_scholes_call(self):
        """Test Black-Scholes call option pricing."""
        result = self.pricer.black_scholes(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2,
            option_type='call'
        )
        
        assert isinstance(result, OptionResult)
        assert result.option_type == 'call'
        assert result.option_price > 0
        assert result.delta > 0
        assert result.gamma > 0
        assert result.vega > 0
    
    def test_black_scholes_put(self):
        """Test Black-Scholes put option pricing."""
        result = self.pricer.black_scholes(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2,
            option_type='put'
        )
        
        assert isinstance(result, OptionResult)
        assert result.option_type == 'put'
        assert result.option_price > 0
        assert result.delta < 0
        assert result.gamma > 0
        assert result.vega > 0
    
    def test_put_call_parity(self):
        """Test put-call parity."""
        # Price call
        call_result = self.pricer.price_european_call(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        # Calculate put using put-call parity
        put_price = self.pricer.put_call_parity(
            call_price=call_result.option_price,
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0
        )
        
        # Price put directly
        put_result = self.pricer.price_european_put(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        # Should be equal (within numerical precision)
        assert abs(put_price - put_result.option_price) < 1e-6
    
    def test_greeks_relationships(self):
        """Test Greek relationships."""
        call = self.pricer.price_european_call(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        put = self.pricer.price_european_put(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        # Call delta + Put delta = 1 (for European options)
        # Actually, call delta - put delta = 1 for same strike/expiry
        # More precisely: call delta - put delta = 1 for European options
        assert abs(call.delta - put.delta - 1.0) < 0.1  # Within tolerance
        
        # Gamma should be the same for call and put with same parameters
        assert abs(call.gamma - put.gamma) < 1e-6
    
    def test_in_the_money_call(self):
        """Test in-the-money call."""
        result = self.pricer.price_european_call(
            underlying_price=110.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        assert result.option_price > 10.0  # Intrinsic value is 10
        assert result.intrinsic_value == 10.0
        assert result.time_value > 0
        assert result.delta > 0.5  # Deep ITM call has delta close to 1
    
    def test_out_of_the_money_call(self):
        """Test out-of-the-money call."""
        result = self.pricer.price_european_call(
            underlying_price=90.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        assert result.option_price < 10.0  # Less than intrinsic value if it were ITM
        assert result.intrinsic_value == 0.0
        assert result.time_value == result.option_price
        assert result.delta < 0.5
    
    def test_time_decay(self):
        """Test time decay (theta)."""
        result = self.pricer.price_european_call(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        # Theta should be negative (time decay)
        assert result.theta < 0
    
    def test_volatility_sensitivity(self):
        """Test vega (volatility sensitivity)."""
        result = self.pricer.price_european_call(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        # Vega should be positive (higher vol = higher price)
        assert result.vega > 0
        
        # Price should increase with volatility
        result_high_vol = self.pricer.price_european_call(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.3
        )
        
        assert result_high_vol.option_price > result.option_price
    
    def test_expired_option(self):
        """Test expired option."""
        result = self.pricer.price_european_call(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=0.0,
            volatility=0.2
        )
        
        assert result.option_price == 0.0
        assert result.theta == 0.0
        assert result.vega == 0.0
    
    def test_implied_volatility(self):
        """Test implied volatility calculation."""
        # Price an option with known volatility
        target_vol = 0.25
        result = self.pricer.price_european_call(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=target_vol
        )
        
        # Calculate implied volatility from the price
        implied_vol = self.pricer.implied_volatility(
            market_price=result.option_price,
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            option_type='call'
        )
        
        # Should recover the original volatility
        assert abs(implied_vol - target_vol) < 1e-4
    
    def test_deep_in_the_money_delta(self):
        """Test deep in-the-money delta."""
        result = self.pricer.price_european_call(
            underlying_price=150.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        # Deep ITM call should have delta close to 1
        assert result.delta > 0.9
    
    def test_deep_out_of_the_money_delta(self):
        """Test deep out-of-the-money delta."""
        result = self.pricer.price_european_call(
            underlying_price=50.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        # Deep OTM call should have delta close to 0
        assert result.delta < 0.1
    
    def test_at_the_money_call_put_symmetry(self):
        """Test ATM call and put symmetry."""
        call = self.pricer.price_european_call(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        put = self.pricer.price_european_put(
            underlying_price=100.0,
            strike_price=100.0,
            time_to_expiration=1.0,
            volatility=0.2
        )
        
        # For ATM options, call and put prices should be similar
        # (not exactly equal due to interest rate)
        assert abs(call.option_price - put.option_price) < 5.0
