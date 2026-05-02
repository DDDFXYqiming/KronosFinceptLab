"""OKX DataSource for crypto market data.

Supports any timeframe (5m, 15m, 1h, 4h, 1d) for 45+ crypto pairs.
Uses OKX public API (no API key required for market data).
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from . import DataSource, DataSourceConfig, DataSourceStatus


class OKXSource(DataSource):
    """OKX data source for crypto market data."""

    supported_endpoints = {"binance_kline"}

    def __init__(self, priority: int = 4):
        config = DataSourceConfig(
            name="okx",
            priority=priority,
            max_retries=3,
            retry_delay=1.0,
            timeout=30.0,
            circuit_break_threshold=5,
            circuit_break_duration=300,
            health_check_interval=60
        )
        super().__init__(config)
        self._base_url = "https://www.okx.com"

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to OKX format (e.g., BTCUSDT -> BTC-USDT)."""
        symbol = symbol.upper()
        # Remove slash if present
        symbol = symbol.replace("/", "")
        # Add dash if not present
        if "-" not in symbol:
            # Find the quote currency
            for quote in ["USDT", "BUSD", "BTC", "ETH"]:
                if symbol.endswith(quote):
                    base = symbol[:-len(quote)]
                    return f"{base}-{quote}"
            # Default to USDT
            return f"{symbol}-USDT"
        return symbol

    def _normalize_timeframe(self, timeframe: str) -> str:
        """Convert timeframe to OKX bar format."""
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D",
            "1w": "1W",
        }
        return mapping.get(timeframe.lower(), timeframe.upper())

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Fetch data from OKX API."""
        try:
            # Only handle binance_kline endpoint (reuse same name for compatibility)
            if endpoint != "binance_kline":
                return {
                    "success": False,
                    "data": None,
                    "error": f"Unknown endpoint: {endpoint}",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            import requests

            symbol = kwargs.get("symbol", "BTCUSDT")
            symbol = self._normalize_symbol(symbol)
            timeframe = kwargs.get("timeframe", "1d")
            bar = self._normalize_timeframe(timeframe)
            limit = kwargs.get("limit", 100)

            # OKX candles endpoint
            url = f"{self._base_url}/api/v5/market/candles"
            params = {
                "instId": symbol,
                "bar": bar,
                "limit": min(limit, 300),  # Max 300 per request
            }

            start_time = time.time()
            response = requests.get(url, params=params, timeout=10)
            elapsed = time.time() - start_time

            if response.status_code != 200:
                return {
                    "success": False,
                    "data": None,
                    "error": f"OKX API error: {response.status_code} {response.text}",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            result = response.json()
            if result.get("code") != "0":
                return {
                    "success": False,
                    "data": None,
                    "error": f"OKX API error: {result.get('msg', 'Unknown error')}",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            # Parse OKX candles format:
            # [timestamp, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
            data = []
            for k in result.get("data", []):
                data.append({
                    "open_time": int(k[0]),
                    "timestamp": datetime.fromtimestamp(int(k[0]) / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "amount": float(k[7]),  # volCcyQuote
                })

            # Reverse to ascending order (OKX returns descending)
            data.reverse()

            return {
                "success": True,
                "data": data,
                "count": len(data),
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
