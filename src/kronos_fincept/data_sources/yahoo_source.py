"""
Yahoo Finance data source adapter
Supports global stock market data
"""

import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from . import DataSource, DataSourceConfig, DataSourceStatus


class YahooFinanceSource(DataSource):
    """Yahoo Finance data source"""

    supported_endpoints = {
        "stock_zh_a_hist",
        "stock_individual_info_em",
    }

    def __init__(self, priority: int = 3):
        config = DataSourceConfig(
            name="yahoo_finance",
            priority=priority,
            max_retries=3,
            retry_delay=1.0,
            timeout=30.0,
            circuit_break_threshold=5,
            circuit_break_duration=300,
            health_check_interval=60
        )
        super().__init__(config)
        self._yf = None

    def _get_yf(self):
        """Lazy-load yfinance"""
        if self._yf is None:
            try:
                import yfinance as yf
                self._yf = yf
            except ImportError as e:
                raise ImportError(f"yfinance 未安装: {e}")
        return self._yf

    def _normalize_symbol(self, symbol: str, market: str = "auto") -> str:
        """
        Normalize stock symbol to Yahoo Finance format

        Args:
            symbol: Stock symbol (e.g. '601398')
            market: Market ('auto', 'cn', 'hk', 'us')

        Returns:
            Yahoo Finance formatted symbol
        """
        # If already has a suffix, return as-is
        if '.' in symbol or '-' in symbol:
            return symbol

        # Auto-detect market
        if market == "auto":
            if symbol.startswith('6'):
                market = 'cn_sh'
            elif symbol.startswith('0') or symbol.startswith('3'):
                market = 'cn_sz'
            elif symbol.isdigit() and len(symbol) == 5:
                market = 'hk'
            else:
                market = 'us'

        # Add suffix based on market
        if market == 'cn_sh':
            return f"{symbol}.SS"  # Shanghai
        elif market == 'cn_sz':
            return f"{symbol}.SZ"  # Shenzhen
        elif market == 'hk':
            return f"{symbol}.HK"  # Hong Kong
        else:
            return symbol  # US stocks need no suffix

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch data

        Args:
            endpoint: Data endpoint
            **kwargs: Parameters passed to yfinance

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str (if failed),
                "source": str,
                "timestamp": int
            }
        """
        try:
            yf = self._get_yf()
            start_time = time.time()
            data = None

            if endpoint == "stock_zh_a_hist":
                # Fetch historical K-line data
                symbol = kwargs.get("symbol", "")
                yahoo_symbol = self._normalize_symbol(symbol)

                start_date = kwargs.get("start_date", "2020-01-01")
                end_date = kwargs.get("end_date", datetime.now().strftime('%Y-%m-%d'))

                # Convert date format
                if len(start_date) == 8:
                    start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
                if len(end_date) == 8:
                    end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

                # Fetch data
                ticker = yf.Ticker(yahoo_symbol)
                hist = ticker.history(start=start_date, end=end_date)

                if hist.empty:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"未找到股票 {symbol} 的数据",
                        "source": self.config.name,
                        "timestamp": int(datetime.now().timestamp())
                    }

                # Convert to AkShare-compatible format
                data = []
                for index, row in hist.iterrows():
                    data.append({
                        "日期": index.strftime('%Y-%m-%d'),
                        "股票代码": symbol,
                        "开盘": round(row['Open'], 2),
                        "收盘": round(row['Close'], 2),
                        "最高": round(row['High'], 2),
                        "最低": round(row['Low'], 2),
                        "成交量": int(row['Volume']),
                        "成交额": round(row['Close'] * row['Volume'], 2),
                        "振幅": round((row['High'] - row['Low']) / row['Open'] * 100, 2),
                        "涨跌幅": round(row.get('Change', 0), 2),
                        "涨跌额": round(row['Close'] - row['Open'], 2),
                        "换手率": 0  # Not provided by Yahoo Finance
                    })

            elif endpoint == "stock_info_a_code_name":
                # Yahoo Finance does not support fetching A-share list
                return {
                    "success": False,
                    "data": None,
                    "error": "Yahoo Finance 不支持获取 A 股列表",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            elif endpoint == "stock_individual_info_em":
                # Fetch individual stock info
                symbol = kwargs.get("symbol", "")
                yahoo_symbol = self._normalize_symbol(symbol)

                ticker = yf.Ticker(yahoo_symbol)
                info = ticker.info

                if not info:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"未找到股票 {symbol} 的信息",
                        "source": self.config.name,
                        "timestamp": int(datetime.now().timestamp())
                    }

                data = {
                    "股票代码": symbol,
                    "股票名称": info.get('longName', info.get('shortName', '')),
                    "市场": info.get('market', ''),
                    "行业": info.get('industry', ''),
                    "板块": info.get('sector', ''),
                    "市值": info.get('marketCap', 0),
                    "市盈率": info.get('trailingPE', 0),
                    "市净率": info.get('priceToBook', 0),
                    "股息率": info.get('dividendYield', 0),
                    "52周最高": info.get('fiftyTwoWeekHigh', 0),
                    "52周最低": info.get('fiftyTwoWeekLow', 0)
                }

            else:
                return {
                    "success": False,
                    "data": None,
                    "error": f"未知的 Yahoo Finance 端点: {endpoint}",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            elapsed = time.time() - start_time

            if data is None:
                return {
                    "success": False,
                    "data": None,
                    "error": "返回数据为空",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            return {
                "success": True,
                "data": data,
                "count": len(data) if isinstance(data, list) else 1,
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
                "elapsed": round(elapsed, 2)
            }

        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": f"{type(e).__name__}: {str(e)}",
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp())
            }
