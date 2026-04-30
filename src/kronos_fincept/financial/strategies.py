"""
Quantitative trading strategies module.
"""
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

from .indicators import TechnicalIndicators, SMA, EMA, RSI, MACD, BollingerBands


class Signal(Enum):
    """Trading signal."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class StrategyResult:
    """Strategy result."""
    signal: Signal
    strength: float  # 0-1, signal strength
    reason: str
    indicators: dict
    
    @property
    def is_buy(self) -> bool:
        """Check if buy signal."""
        return self.signal == Signal.BUY
    
    @property
    def is_sell(self) -> bool:
        """Check if sell signal."""
        return self.signal == Signal.SELL
    
    @property
    def is_hold(self) -> bool:
        """Check if hold signal."""
        return self.signal == Signal.HOLD


class QuantitativeStrategies:
    """
    Quantitative trading strategies.
    
    Supports:
    - Moving Average Crossover
    - RSI Overbought/Oversold
    - MACD Crossover
    - Bollinger Bands Breakout
    """
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
    
    def ma_crossover_strategy(
        self,
        closes: List[float],
        fast_period: int = 20,
        slow_period: int = 50
    ) -> StrategyResult:
        """
        Moving Average Crossover strategy.
        
        Buy when fast MA crosses above slow MA.
        Sell when fast MA crosses below slow MA.
        
        Args:
            closes: List of close prices
            fast_period: Fast MA period
            slow_period: Slow MA period
            
        Returns:
            StrategyResult with signal
        """
        if len(closes) < slow_period + 2:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="Insufficient data",
                indicators={}
            )
        
        # Calculate MAs
        fast_ma = self.indicators.calculate_sma(closes, fast_period)
        slow_ma = self.indicators.calculate_sma(closes, slow_period)
        
        if not fast_ma.values or not slow_ma.values:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="MA calculation failed",
                indicators={'fast_ma': fast_ma, 'slow_ma': slow_ma}
            )
        
        # Align MA values
        fast_values = fast_ma.values[slow_period - fast_period:]
        slow_values = slow_ma.values
        
        if len(fast_values) < 2 or len(slow_values) < 2:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="Insufficient MA data",
                indicators={'fast_ma': fast_ma, 'slow_ma': slow_ma}
            )
        
        # Check crossover
        fast_prev = fast_values[-2]
        fast_curr = fast_values[-1]
        slow_prev = slow_values[-2]
        slow_curr = slow_values[-1]
        
        # Calculate signal strength
        strength = min(1.0, abs(fast_curr - slow_curr) / slow_curr * 10)
        
        # Generate signal
        if fast_prev <= slow_prev and fast_curr > slow_curr:
            return StrategyResult(
                signal=Signal.BUY,
                strength=strength,
                reason=f"Fast MA ({fast_period}) crossed above Slow MA ({slow_period})",
                indicators={'fast_ma': fast_ma, 'slow_ma': slow_ma}
            )
        elif fast_prev >= slow_prev and fast_curr < slow_curr:
            return StrategyResult(
                signal=Signal.SELL,
                strength=strength,
                reason=f"Fast MA ({fast_period}) crossed below Slow MA ({slow_period})",
                indicators={'fast_ma': fast_ma, 'slow_ma': slow_ma}
            )
        else:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="No crossover detected",
                indicators={'fast_ma': fast_ma, 'slow_ma': slow_ma}
            )
    
    def rsi_strategy(
        self,
        closes: List[float],
        period: int = 14,
        overbought: float = 70,
        oversold: float = 30
    ) -> StrategyResult:
        """
        RSI Overbought/Oversold strategy.
        
        Buy when RSI crosses above oversold level.
        Sell when RSI crosses below overbought level.
        
        Args:
            closes: List of close prices
            period: RSI period
            overbought: Overbought threshold
            oversold: Oversold threshold
            
        Returns:
            StrategyResult with signal
        """
        if len(closes) < period + 2:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="Insufficient data",
                indicators={}
            )
        
        # Calculate RSI
        rsi = self.indicators.calculate_rsi(closes, period)
        
        if len(rsi.values) < 2:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="RSI calculation failed",
                indicators={'rsi': rsi}
            )
        
        # Check crossover
        rsi_prev = rsi.values[-2]
        rsi_curr = rsi.values[-1]
        
        # Calculate signal strength
        if rsi_curr < oversold:
            strength = (oversold - rsi_curr) / oversold
        elif rsi_curr > overbought:
            strength = (rsi_curr - overbought) / (100 - overbought)
        else:
            strength = 0.0
        
        strength = min(1.0, strength)
        
        # Generate signal
        if rsi_prev <= oversold and rsi_curr > oversold:
            return StrategyResult(
                signal=Signal.BUY,
                strength=strength,
                reason=f"RSI crossed above oversold level ({oversold})",
                indicators={'rsi': rsi}
            )
        elif rsi_prev >= overbought and rsi_curr < overbought:
            return StrategyResult(
                signal=Signal.SELL,
                strength=strength,
                reason=f"RSI crossed below overbought level ({overbought})",
                indicators={'rsi': rsi}
            )
        elif rsi_curr < oversold:
            return StrategyResult(
                signal=Signal.BUY,
                strength=strength,
                reason=f"RSI in oversold territory ({rsi_curr:.1f})",
                indicators={'rsi': rsi}
            )
        elif rsi_curr > overbought:
            return StrategyResult(
                signal=Signal.SELL,
                strength=strength,
                reason=f"RSI in overbought territory ({rsi_curr:.1f})",
                indicators={'rsi': rsi}
            )
        else:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="RSI in neutral zone",
                indicators={'rsi': rsi}
            )
    
    def macd_strategy(
        self,
        closes: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> StrategyResult:
        """
        MACD Crossover strategy.
        
        Buy when MACD crosses above signal line.
        Sell when MACD crosses below signal line.
        
        Args:
            closes: List of close prices
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period
            
        Returns:
            StrategyResult with signal
        """
        if len(closes) < slow_period + signal_period + 2:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="Insufficient data",
                indicators={}
            )
        
        # Calculate MACD
        macd = self.indicators.calculate_macd(closes, fast_period, slow_period, signal_period)
        
        if len(macd.macd_line) < 2 or len(macd.signal_line) < 2:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="MACD calculation failed",
                indicators={'macd': macd}
            )
        
        # Check crossover
        macd_prev = macd.macd_line[-2]
        macd_curr = macd.macd_line[-1]
        signal_prev = macd.signal_line[-2]
        signal_curr = macd.signal_line[-1]
        
        # Calculate signal strength
        strength = min(1.0, abs(macd_curr - signal_curr) / abs(signal_curr) if signal_curr != 0 else 0)
        
        # Generate signal
        if macd_prev <= signal_prev and macd_curr > signal_curr:
            return StrategyResult(
                signal=Signal.BUY,
                strength=strength,
                reason="MACD crossed above signal line",
                indicators={'macd': macd}
            )
        elif macd_prev >= signal_prev and macd_curr < signal_curr:
            return StrategyResult(
                signal=Signal.SELL,
                strength=strength,
                reason="MACD crossed below signal line",
                indicators={'macd': macd}
            )
        else:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="No MACD crossover detected",
                indicators={'macd': macd}
            )
    
    def bollinger_breakout_strategy(
        self,
        closes: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> StrategyResult:
        """
        Bollinger Bands Breakout strategy.
        
        Buy when price breaks above upper band.
        Sell when price breaks below lower band.
        
        Args:
            closes: List of close prices
            period: Bollinger period
            std_dev: Standard deviation multiplier
            
        Returns:
            StrategyResult with signal
        """
        if len(closes) < period + 1:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="Insufficient data",
                indicators={}
            )
        
        # Calculate Bollinger Bands
        bollinger = self.indicators.calculate_bollinger_bands(closes, period, std_dev)
        
        if not bollinger.upper or not bollinger.lower:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="Bollinger calculation failed",
                indicators={'bollinger': bollinger}
            )
        
        # Current price and bands
        current_price = closes[-1]
        upper = bollinger.current_upper
        lower = bollinger.current_lower
        middle = bollinger.current_middle
        
        # Calculate signal strength
        if current_price > upper:
            strength = min(1.0, (current_price - upper) / (upper - middle) if (upper - middle) != 0 else 0)
        elif current_price < lower:
            strength = min(1.0, (lower - current_price) / (middle - lower) if (middle - lower) != 0 else 0)
        else:
            strength = 0.0
        
        # Generate signal
        if current_price > upper:
            return StrategyResult(
                signal=Signal.BUY,
                strength=strength,
                reason=f"Price ({current_price:.2f}) broke above upper band ({upper:.2f})",
                indicators={'bollinger': bollinger}
            )
        elif current_price < lower:
            return StrategyResult(
                signal=Signal.SELL,
                strength=strength,
                reason=f"Price ({current_price:.2f}) broke below lower band ({lower:.2f})",
                indicators={'bollinger': bollinger}
            )
        else:
            return StrategyResult(
                signal=Signal.HOLD,
                strength=0.0,
                reason="Price within Bollinger Bands",
                indicators={'bollinger': bollinger}
            )
    
    def run_all_strategies(
        self,
        closes: List[float],
        highs: Optional[List[float]] = None,
        lows: Optional[List[float]] = None,
        volumes: Optional[List[float]] = None
    ) -> dict:
        """
        Run all strategies at once.
        
        Args:
            closes: List of close prices
            highs: List of high prices
            lows: List of low prices
            volumes: List of volumes
            
        Returns:
            Dictionary with all strategy results
        """
        result = {}
        
        # MA Crossover
        result['ma_crossover'] = self.ma_crossover_strategy(closes)
        
        # RSI
        result['rsi'] = self.rsi_strategy(closes)
        
        # MACD
        result['macd'] = self.macd_strategy(closes)
        
        # Bollinger Breakout
        result['bollinger'] = self.bollinger_breakout_strategy(closes)
        
        return result
