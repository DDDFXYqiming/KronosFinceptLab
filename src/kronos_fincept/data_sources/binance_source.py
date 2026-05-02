"""Binance DataSource for crypto market data.

Supports any timeframe (5m, 15m, 1h, 4h, 1d) for 45+ crypto pairs.
Uses Binance public API (no API key required for market data).
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from . import DataSource, DataSourceConfig, DataSourceStatus


class BinanceSource(DataSource):
    """Binance data source for crypto market data."""

    supported_endpoints = {"binance_kline"}

    def __init__(self, priority: int = 4):
        config = DataSourceConfig(
            name="binance",
            priority=priority,
            max_retries=3,
            retry_delay=1.0,
            timeout=30.0,
            circuit_break_threshold=5,
            circuit_break_duration=300,
            health_check_interval=60
        )
        super().__init__(config)
        self._base_url = "https://api.binance.com"

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to Binance format (e.g., BTC/USDT -> BTCUSDT)."""
        # Remove slash if present
        symbol = symbol.replace("/", "").upper()
        # Add USDT suffix if not present
        if not any(quote in symbol for quote in ["USDT", "BUSD", "BTC", "ETH"]):
            symbol = symbol + "USDT"
        return symbol

    def _normalize_timeframe(self, timeframe: str) -> str:
        """Convert timeframe to Binance interval format."""
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
            "1w": "1w",
        }
        return mapping.get(timeframe.lower(), timeframe.lower())

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Fetch data from Binance API."""
        try:
            # Only handle binance_kline endpoint
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
            interval = self._normalize_timeframe(timeframe)
            limit = kwargs.get("limit", 100)

            # Binance Kline endpoint
            url = f"{self._base_url}/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": min(limit, 1000),  # Max 1000 per request
            }

            start_time = time.time()
            response = requests.get(url, params=params, timeout=10)
            elapsed = time.time() - start_time

            if response.status_code != 200:
                return {
                    "success": False,
                    "data": None,
                    "error": f"Binance API error: {response.status_code} {response.text}",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            # Parse Binance klines format:
            # [open_time, open, high, low, close, volume, close_time, quote_volume, ...]
            klines = response.json()
            data = []
            for k in klines:
                data.append({
                    "open_time": int(k[0]),
                    "timestamp": datetime.fromtimestamp(int(k[0]) / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "amount": float(k[7]),  # quote_asset_volume
                })

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
