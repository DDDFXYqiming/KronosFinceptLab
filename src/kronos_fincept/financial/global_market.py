"""
Global market data sources (US, HK stocks).
"""
import logging
from collections import OrderedDict
from typing import Optional, List, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


class GlobalMarketSource:
    """
    Global market data source using Yahoo Finance.
    
    Supports:
    - US stocks (AAPL, MSFT, GOOGL, etc.)
    - HK stocks (0700.HK, 9988.HK, etc.)
    - Crypto (BTC-USD, ETH-USD, etc.)
    """

    _instance: "GlobalMarketSource | None" = None

    def __new__(cls) -> "GlobalMarketSource":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.cache: OrderedDict[tuple[str, str, str], pd.DataFrame] = OrderedDict()
        self.cache_max_size = 128
        self._initialized = True

    def _get_cached(self, cache_key: tuple[str, str, str]) -> Optional[pd.DataFrame]:
        cached = self.cache.get(cache_key)
        if cached is None:
            return None
        self.cache.move_to_end(cache_key)
        return cached.copy()

    def _save_cached(self, cache_key: tuple[str, str, str], df: pd.DataFrame) -> None:
        self.cache[cache_key] = df.copy()
        self.cache.move_to_end(cache_key)
        while len(self.cache) > self.cache_max_size:
            self.cache.popitem(last=False)

    def _convert_symbol(self, symbol: str, market: str = 'auto') -> str:
        """
        Convert symbol to Yahoo Finance format.
        
        Args:
            symbol: Stock symbol
            market: Market type ('us', 'hk', 'auto')
            
        Returns:
            Yahoo Finance symbol format
        """
        if market == 'us':
            # US stocks - no suffix needed
            return symbol.upper()
        elif market == 'hk':
            # HK stocks - add .HK suffix
            if '.HK' not in symbol:
                return f"{symbol}.HK"
            return symbol
        elif market == 'crypto':
            # Crypto - add -USD suffix
            if '-USD' not in symbol:
                return f"{symbol}-USD"
            return symbol
        else:
            # Auto detect
            if symbol.startswith('0') and len(symbol) == 5:
                # HK stock (e.g., 0700)
                return f"{symbol}.HK"
            elif '-' in symbol:
                # Crypto
                return symbol
            else:
                # US stock
                return symbol.upper()
    
    def get_stock_data(
        self,
        symbol: str,
        market: str = 'auto',
        period: str = '1y',
        interval: str = '1d'
    ) -> Optional[pd.DataFrame]:
        """
        Get stock data from Yahoo Finance.
        
        Args:
            symbol: Stock symbol
            market: Market type ('us', 'hk', 'auto')
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            import yfinance as yf
            
            yahoo_symbol = self._convert_symbol(symbol, market)
            cache_key = (yahoo_symbol, period, interval)
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached
            
            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                return None
            
            # Standardize column names
            df = df.rename(columns={
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            # Add timestamp column
            df['timestamp'] = df.index
            
            result = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            self._save_cached(cache_key, result)
            return result.copy()
            
        except Exception as e:
            logger.warning("Error getting data for %s: %s", symbol, e)
            return None
    
    def get_us_stock_data(
        self,
        symbol: str,
        period: str = '1y',
        interval: str = '1d'
    ) -> Optional[pd.DataFrame]:
        """Get US stock data."""
        return self.get_stock_data(symbol, market='us', period=period, interval=interval)
    
    def get_hk_stock_data(
        self,
        symbol: str,
        period: str = '1y',
        interval: str = '1d'
    ) -> Optional[pd.DataFrame]:
        """Get HK stock data."""
        return self.get_stock_data(symbol, market='hk', period=period, interval=interval)
    
    def get_crypto_data(
        self,
        symbol: str,
        period: str = '1y',
        interval: str = '1d'
    ) -> Optional[pd.DataFrame]:
        """Get crypto data."""
        return self.get_stock_data(symbol, market='crypto', period=period, interval=interval)
    
    def get_multiple_stocks(
        self,
        symbols: List[str],
        market: str = 'auto',
        period: str = '1y',
        interval: str = '1d'
    ) -> Dict[str, pd.DataFrame]:
        """
        Get data for multiple stocks.
        
        Args:
            symbols: List of stock symbols
            market: Market type
            period: Data period
            interval: Data interval
            
        Returns:
            Dictionary of symbol -> DataFrame
        """
        result = {}
        
        for symbol in symbols:
            df = self.get_stock_data(symbol, market, period, interval)
            if df is not None:
                result[symbol] = df
        
        return result
    
    def get_market_summary(self) -> Dict[str, Any]:
        """
        Get major market indices summary.
        
        Returns:
            Dictionary with market data
        """
        indices = {
            'SP500': '^GSPC',      # S&P 500
            'NASDAQ': '^IXIC',     # NASDAQ
            'DOW': '^DJI',         # Dow Jones
            'HSI': '^HSI',         # Hang Seng
            'SSE': '000001.SS',    # Shanghai Composite
        }
        
        result = {}
        
        for name, symbol in indices.items():
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                result[name] = {
                    'symbol': symbol,
                    'price': info.get('regularMarketPrice', 0),
                    'change': info.get('regularMarketChange', 0),
                    'change_pct': info.get('regularMarketChangePercent', 0)
                }
            except Exception:
                result[name] = {'symbol': symbol, 'error': 'Failed to fetch'}
        
        return result
