"""
Tests for technical indicators and strategies.
"""
import pytest
import numpy as np
from kronos_fincept.financial.indicators import TechnicalIndicators, SMA, EMA, RSI, MACD, BollingerBands, KDJ, ATR, OBV
from kronos_fincept.financial.strategies import QuantitativeStrategies, StrategyResult, Signal


class TestTechnicalIndicators:
    """Test TechnicalIndicators."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.indicators = TechnicalIndicators()
        
        # Sample price data
        np.random.seed(42)
        self.sample_prices = [100.0]
        for _ in range(99):
            self.sample_prices.append(self.sample_prices[-1] * (1 + np.random.normal(0.001, 0.02)))
        
        # Sample high/low data
        self.sample_highs = [p * 1.01 for p in self.sample_prices]
        self.sample_lows = [p * 0.99 for p in self.sample_prices]
        
        # Sample volume data
        self.sample_volumes = [1000000.0 + np.random.normal(0, 100000) for _ in range(100)]
    
    def test_sma(self):
        """Test Simple Moving Average."""
        sma = self.indicators.calculate_sma(self.sample_prices, 20)
        
        assert isinstance(sma, SMA)
        assert sma.period == 20
        assert len(sma.values) == 81  # 100 - 20 + 1
        assert sma.current > 0
    
    def test_ema(self):
        """Test Exponential Moving Average."""
        ema = self.indicators.calculate_ema(self.sample_prices, 20)
        
        assert isinstance(ema, EMA)
        assert ema.period == 20
        assert len(ema.values) == 81
        assert ema.current > 0
    
    def test_rsi(self):
        """Test Relative Strength Index."""
        rsi = self.indicators.calculate_rsi(self.sample_prices, 14)
        
        assert isinstance(rsi, RSI)
        assert rsi.period == 14
        assert len(rsi.values) > 0
        assert 0 <= rsi.current <= 100
    
    def test_rsi_overbought_oversold(self):
        """Test RSI overbought/oversold detection."""
        # Create oversold scenario
        oversold_prices = [100.0]
        for _ in range(20):
            oversold_prices.append(oversold_prices[-1] * 0.98)  # Strong downtrend
        
        rsi = self.indicators.calculate_rsi(oversold_prices, 14)
        assert rsi.is_oversold or rsi.current < 50  # Should be oversold or neutral
    
    def test_macd(self):
        """Test MACD indicator."""
        macd = self.indicators.calculate_macd(self.sample_prices)
        
        assert isinstance(macd, MACD)
        assert len(macd.macd_line) > 0
        assert len(macd.signal_line) > 0
        assert len(macd.histogram) > 0
    
    def test_bollinger_bands(self):
        """Test Bollinger Bands."""
        bollinger = self.indicators.calculate_bollinger_bands(self.sample_prices, 20, 2.0)
        
        assert isinstance(bollinger, BollingerBands)
        assert bollinger.period == 20
        assert bollinger.std_dev == 2.0
        assert len(bollinger.upper) > 0
        assert len(bollinger.middle) > 0
        assert len(bollinger.lower) > 0
        
        # Upper > Middle > Lower
        assert bollinger.current_upper > bollinger.current_middle
        assert bollinger.current_middle > bollinger.current_lower
    
    def test_kdj(self):
        """Test KDJ indicator."""
        kdj = self.indicators.calculate_kdj(
            self.sample_highs,
            self.sample_lows,
            self.sample_prices,
            9
        )
        
        assert len(kdj.k) > 0
        assert len(kdj.d) > 0
        assert len(kdj.j) > 0
        assert 0 <= kdj.current_k <= 100
        assert 0 <= kdj.current_d <= 100
    
    def test_atr(self):
        """Test Average True Range."""
        atr = self.indicators.calculate_atr(
            self.sample_highs,
            self.sample_lows,
            self.sample_prices,
            14
        )
        
        assert isinstance(atr, ATR)
        assert atr.period == 14
        assert len(atr.values) > 0
        assert atr.current > 0
    
    def test_obv(self):
        """Test On Balance Volume."""
        obv = self.indicators.calculate_obv(self.sample_prices, self.sample_volumes)
        
        assert isinstance(obv, OBV)
        assert len(obv.values) > 0
    
    def test_calculate_all_indicators(self):
        """Test calculate_all_indicators."""
        result = self.indicators.calculate_all_indicators(
            self.sample_prices,
            self.sample_highs,
            self.sample_lows,
            self.sample_volumes
        )
        
        assert 'sma_20' in result
        assert 'sma_50' in result
        assert 'ema_12' in result
        assert 'ema_26' in result
        assert 'rsi_14' in result
        assert 'macd' in result
        assert 'bollinger' in result
        assert 'kdj' in result
        assert 'atr' in result
        assert 'obv' in result


class TestQuantitativeStrategies:
    """Test QuantitativeStrategies."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.strategies = QuantitativeStrategies()
        
        # Sample price data with trend
        np.random.seed(42)
        self.uptrend_prices = [100.0]
        for _ in range(99):
            self.uptrend_prices.append(self.uptrend_prices[-1] * (1 + np.random.normal(0.002, 0.01)))
        
        self.downtrend_prices = [100.0]
        for _ in range(99):
            self.downtrend_prices.append(self.downtrend_prices[-1] * (1 + np.random.normal(-0.002, 0.01)))
    
    def test_ma_crossover_strategy(self):
        """Test Moving Average Crossover strategy."""
        result = self.strategies.ma_crossover_strategy(self.uptrend_prices)
        
        assert isinstance(result, StrategyResult)
        assert result.signal in [Signal.BUY, Signal.SELL, Signal.HOLD]
        assert 0 <= result.strength <= 1
        assert isinstance(result.reason, str)
    
    def test_rsi_strategy(self):
        """Test RSI strategy."""
        result = self.strategies.rsi_strategy(self.uptrend_prices)
        
        assert isinstance(result, StrategyResult)
        assert result.signal in [Signal.BUY, Signal.SELL, Signal.HOLD]
        assert 0 <= result.strength <= 1
    
    def test_macd_strategy(self):
        """Test MACD strategy."""
        result = self.strategies.macd_strategy(self.uptrend_prices)
        
        assert isinstance(result, StrategyResult)
        assert result.signal in [Signal.BUY, Signal.SELL, Signal.HOLD]
        assert 0 <= result.strength <= 1
    
    def test_bollinger_breakout_strategy(self):
        """Test Bollinger Bands Breakout strategy."""
        result = self.strategies.bollinger_breakout_strategy(self.uptrend_prices)
        
        assert isinstance(result, StrategyResult)
        assert result.signal in [Signal.BUY, Signal.SELL, Signal.HOLD]
        assert 0 <= result.strength <= 1
    
    def test_run_all_strategies(self):
        """Test running all strategies."""
        result = self.strategies.run_all_strategies(self.uptrend_prices)
        
        assert 'ma_crossover' in result
        assert 'rsi' in result
        assert 'macd' in result
        assert 'bollinger' in result
        
        for strategy_result in result.values():
            assert isinstance(strategy_result, StrategyResult)
            assert strategy_result.signal in [Signal.BUY, Signal.SELL, Signal.HOLD]
    
    def test_signal_properties(self):
        """Test Signal properties."""
        buy_result = StrategyResult(
            signal=Signal.BUY,
            strength=0.8,
            reason="Test buy",
            indicators={}
        )
        
        assert buy_result.is_buy
        assert not buy_result.is_sell
        assert not buy_result.is_hold
        
        sell_result = StrategyResult(
            signal=Signal.SELL,
            strength=0.6,
            reason="Test sell",
            indicators={}
        )
        
        assert not sell_result.is_buy
        assert sell_result.is_sell
        assert not sell_result.is_hold
