"""
Technical indicators module for quantitative analysis.
"""
from typing import List, Optional, Tuple
from dataclasses import dataclass
import numpy as np


@dataclass
class SMA:
    """Simple Moving Average result."""
    values: List[float]
    period: int
    
    @property
    def current(self) -> float:
        """Current SMA value."""
        return self.values[-1] if self.values else 0.0


@dataclass
class EMA:
    """Exponential Moving Average result."""
    values: List[float]
    period: int
    
    @property
    def current(self) -> float:
        """Current EMA value."""
        return self.values[-1] if self.values else 0.0


@dataclass
class RSI:
    """Relative Strength Index result."""
    values: List[float]
    period: int
    
    @property
    def current(self) -> float:
        """Current RSI value."""
        return self.values[-1] if self.values else 50.0
    
    @property
    def is_overbought(self) -> bool:
        """Check if overbought (>70)."""
        return self.current > 70
    
    @property
    def is_oversold(self) -> bool:
        """Check if oversold (<30)."""
        return self.current < 30


@dataclass
class MACD:
    """MACD indicator result."""
    macd_line: List[float]
    signal_line: List[float]
    histogram: List[float]
    
    @property
    def current_macd(self) -> float:
        """Current MACD line value."""
        return self.macd_line[-1] if self.macd_line else 0.0
    
    @property
    def current_signal(self) -> float:
        """Current signal line value."""
        return self.signal_line[-1] if self.signal_line else 0.0
    
    @property
    def current_histogram(self) -> float:
        """Current histogram value."""
        return self.histogram[-1] if self.histogram else 0.0
    
    @property
    def is_bullish(self) -> bool:
        """Check if bullish crossover."""
        return self.current_macd > self.current_signal
    
    @property
    def is_bearish(self) -> bool:
        """Check if bearish crossover."""
        return self.current_macd < self.current_signal


@dataclass
class BollingerBands:
    """Bollinger Bands result."""
    upper: List[float]
    middle: List[float]
    lower: List[float]
    period: int
    std_dev: float
    
    @property
    def current_upper(self) -> float:
        """Current upper band."""
        return self.upper[-1] if self.upper else 0.0
    
    @property
    def current_middle(self) -> float:
        """Current middle band."""
        return self.middle[-1] if self.middle else 0.0
    
    @property
    def current_lower(self) -> float:
        """Current lower band."""
        return self.lower[-1] if self.lower else 0.0
    
    @property
    def bandwidth(self) -> float:
        """Bandwidth percentage."""
        if self.current_middle == 0:
            return 0.0
        return (self.current_upper - self.current_lower) / self.current_middle * 100


@dataclass
class KDJ:
    """KDJ indicator result."""
    k: List[float]
    d: List[float]
    j: List[float]
    
    @property
    def current_k(self) -> float:
        """Current K value."""
        return self.k[-1] if self.k else 50.0
    
    @property
    def current_d(self) -> float:
        """Current D value."""
        return self.d[-1] if self.d else 50.0
    
    @property
    def current_j(self) -> float:
        """Current J value."""
        return self.j[-1] if self.j else 50.0


@dataclass
class ATR:
    """Average True Range result."""
    values: List[float]
    period: int
    
    @property
    def current(self) -> float:
        """Current ATR value."""
        return self.values[-1] if self.values else 0.0


@dataclass
class OBV:
    """On Balance Volume result."""
    values: List[float]
    
    @property
    def current(self) -> float:
        """Current OBV value."""
        return self.values[-1] if self.values else 0.0


class TechnicalIndicators:
    """
    Technical indicators calculator.
    
    Supports: SMA, EMA, RSI, MACD, Bollinger Bands, KDJ, ATR, OBV
    """
    
    def __init__(self):
        pass
    
    def calculate_sma(self, prices: List[float], period: int) -> SMA:
        """
        Calculate Simple Moving Average.
        
        Args:
            prices: List of prices
            period: SMA period
            
        Returns:
            SMA result
        """
        if len(prices) < period:
            return SMA(values=[], period=period)
        
        sma_values = []
        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1:i + 1]
            sma_values.append(sum(window) / period)
        
        return SMA(values=sma_values, period=period)
    
    def calculate_ema(self, prices: List[float], period: int) -> EMA:
        """
        Calculate Exponential Moving Average.
        
        Args:
            prices: List of prices
            period: EMA period
            
        Returns:
            EMA result
        """
        if len(prices) < period:
            return EMA(values=[], period=period)
        
        multiplier = 2 / (period + 1)
        
        # Start with SMA for first value
        ema_values = [sum(prices[:period]) / period]
        
        # Calculate EMA
        for i in range(period, len(prices)):
            ema = (prices[i] - ema_values[-1]) * multiplier + ema_values[-1]
            ema_values.append(ema)
        
        return EMA(values=ema_values, period=period)
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> RSI:
        """
        Calculate Relative Strength Index.
        
        Args:
            prices: List of prices
            period: RSI period (default: 14)
            
        Returns:
            RSI result
        """
        if len(prices) < period + 1:
            return RSI(values=[], period=period)
        
        # Calculate price changes
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Separate gains and losses
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        # Calculate initial average gain/loss
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        rsi_values = []
        
        # Calculate RSI
        for i in range(period, len(deltas)):
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            rsi_values.append(rsi)
            
            # Update averages
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        return RSI(values=rsi_values, period=period)
    
    def calculate_macd(
        self,
        prices: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> MACD:
        """
        Calculate MACD.
        
        Args:
            prices: List of prices
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line period (default: 9)
            
        Returns:
            MACD result
        """
        if len(prices) < slow_period + signal_period:
            return MACD(macd_line=[], signal_line=[], histogram=[])
        
        # Calculate fast and slow EMAs
        fast_ema = self.calculate_ema(prices, fast_period)
        slow_ema = self.calculate_ema(prices, slow_period)
        
        # Align EMAs
        fast_values = fast_ema.values[slow_period - fast_period:]
        slow_values = slow_ema.values
        
        # Calculate MACD line
        macd_line = [fast - slow for fast, slow in zip(fast_values, slow_values)]
        
        # Calculate signal line
        signal_line = self.calculate_ema(macd_line, signal_period).values
        
        # Calculate histogram
        min_len = min(len(macd_line), len(signal_line))
        histogram = [macd_line[i] - signal_line[i] for i in range(signal_period - 1, min_len)]
        
        return MACD(
            macd_line=macd_line[signal_period - 1:],
            signal_line=signal_line,
            histogram=histogram
        )
    
    def calculate_bollinger_bands(
        self,
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> BollingerBands:
        """
        Calculate Bollinger Bands.
        
        Args:
            prices: List of prices
            period: SMA period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)
            
        Returns:
            BollingerBands result
        """
        if len(prices) < period:
            return BollingerBands(upper=[], middle=[], lower=[], period=period, std_dev=std_dev)
        
        upper = []
        middle = []
        lower = []
        
        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1:i + 1]
            sma = sum(window) / period
            variance = sum((x - sma) ** 2 for x in window) / period
            std = variance ** 0.5
            
            middle.append(sma)
            upper.append(sma + std_dev * std)
            lower.append(sma - std_dev * std)
        
        return BollingerBands(
            upper=upper,
            middle=middle,
            lower=lower,
            period=period,
            std_dev=std_dev
        )
    
    def calculate_kdj(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 9
    ) -> KDJ:
        """
        Calculate KDJ indicator.
        
        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices
            period: KDJ period (default: 9)
            
        Returns:
            KDJ result
        """
        if len(closes) < period:
            return KDJ(k=[], d=[], j=[])
        
        k_values = []
        d_values = []
        j_values = []
        
        # Initial values
        k_prev = 50.0
        d_prev = 50.0
        
        for i in range(period - 1, len(closes)):
            # Calculate RSV (Raw Stochastic Value)
            period_high = max(highs[i - period + 1:i + 1])
            period_low = min(lows[i - period + 1:i + 1])
            
            if period_high == period_low:
                rsv = 50.0
            else:
                rsv = (closes[i] - period_low) / (period_high - period_low) * 100
            
            # Calculate K, D, J
            k = (2/3) * k_prev + (1/3) * rsv
            d = (2/3) * d_prev + (1/3) * k
            j = 3 * k - 2 * d
            
            k_values.append(k)
            d_values.append(d)
            j_values.append(j)
            
            k_prev = k
            d_prev = d
        
        return KDJ(k=k_values, d=d_values, j=j_values)
    
    def calculate_atr(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> ATR:
        """
        Calculate Average True Range.
        
        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices
            period: ATR period (default: 14)
            
        Returns:
            ATR result
        """
        if len(closes) < period + 1:
            return ATR(values=[], period=period)
        
        # Calculate True Range
        true_ranges = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        
        # Calculate ATR using Wilder's smoothing
        atr_values = [sum(true_ranges[:period]) / period]
        
        for i in range(period, len(true_ranges)):
            atr = (atr_values[-1] * (period - 1) + true_ranges[i]) / period
            atr_values.append(atr)
        
        return ATR(values=atr_values, period=period)
    
    def calculate_obv(
        self,
        closes: List[float],
        volumes: List[float]
    ) -> OBV:
        """
        Calculate On Balance Volume.
        
        Args:
            closes: List of close prices
            volumes: List of volumes
            
        Returns:
            OBV result
        """
        if len(closes) < 2 or len(volumes) < 2:
            return OBV(values=[])
        
        obv_values = [0.0]
        
        for i in range(1, len(closes)):
            if closes[i] > closes[i-1]:
                obv_values.append(obv_values[-1] + volumes[i])
            elif closes[i] < closes[i-1]:
                obv_values.append(obv_values[-1] - volumes[i])
            else:
                obv_values.append(obv_values[-1])
        
        return OBV(values=obv_values)
    
    def calculate_all_indicators(
        self,
        closes: List[float],
        highs: Optional[List[float]] = None,
        lows: Optional[List[float]] = None,
        volumes: Optional[List[float]] = None
    ) -> dict:
        """
        Calculate all indicators at once.
        
        Args:
            closes: List of close prices
            highs: List of high prices (optional)
            lows: List of low prices (optional)
            volumes: List of volumes (optional)
            
        Returns:
            Dictionary with all indicators
        """
        result = {}
        
        # SMA
        result['sma_20'] = self.calculate_sma(closes, 20)
        result['sma_50'] = self.calculate_sma(closes, 50)
        
        # EMA
        result['ema_12'] = self.calculate_ema(closes, 12)
        result['ema_26'] = self.calculate_ema(closes, 26)
        
        # RSI
        result['rsi_14'] = self.calculate_rsi(closes, 14)
        
        # MACD
        result['macd'] = self.calculate_macd(closes)
        
        # Bollinger Bands
        result['bollinger'] = self.calculate_bollinger_bands(closes)
        
        # KDJ (if high/low available)
        if highs and lows and len(highs) == len(closes) and len(lows) == len(closes):
            result['kdj'] = self.calculate_kdj(highs, lows, closes)
        
        # ATR (if high/low available)
        if highs and lows and len(highs) == len(closes) and len(lows) == len(closes):
            result['atr'] = self.calculate_atr(highs, lows, closes)
        
        # OBV (if volume available)
        if volumes and len(volumes) == len(closes):
            result['obv'] = self.calculate_obv(closes, volumes)
        
        return result
