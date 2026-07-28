"""Polygon.io data source adapter — optional, requires POLYGON_API_KEY."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from kronos_fincept.data_sources import DataSource, DataSourceConfig


class PolygonSource(DataSource):
    supported_endpoints = {"aggregates", "daily", "grouped", "details", "status", "crypto"}

    def __init__(self, priority: int = 8):
        config = DataSourceConfig(name="polygon", priority=priority, max_retries=1, retry_delay=0.5, timeout=15.0, circuit_break_threshold=3,
                                   circuit_break_duration=120, health_check_interval=300)
        super().__init__(config)

    def is_available(self) -> bool:
        return bool(os.environ.get("POLYGON_API_KEY", "").strip())

    def fetch(self, endpoint: str, **kwargs) -> dict[str, Any]:
        import requests
        api_key = os.environ.get("POLYGON_API_KEY", "").strip()
        if not api_key:
            return {"success": False, "data": None, "error": "POLYGON_API_KEY not configured", "source": self.config.name, "timestamp": int(datetime.now().timestamp())}

        symbol = kwargs.get("symbol", "")
        from_date = kwargs.get("from", kwargs.get("start_date", ""))
        to_date = kwargs.get("to", kwargs.get("end_date", ""))
        timespan = kwargs.get("timespan", "day")
        multiplier = kwargs.get("multiplier", 1)

        urls = {
            "aggregates": f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}",
            "daily": f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev",
            "grouped": f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{from_date}",
            "details": f"https://api.polygon.io/v3/reference/tickers/{symbol}",
            "status": "https://api.polygon.io/v1/marketstatus/now",
            "crypto": f"https://api.polygon.io/v2/aggs/ticker/X:{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}",
        }
        url = urls.get(endpoint)
        if not url:
            return {"success": False, "data": None, "error": f"Unknown Polygon endpoint: {endpoint}", "source": self.config.name, "timestamp": int(datetime.now().timestamp())}

        try:
            resp = requests.get(url, params={"apiKey": api_key, "adjusted": "true"}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "data": data, "count": 1, "source": self.config.name, "timestamp": int(datetime.now().timestamp())}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e), "source": self.config.name, "timestamp": int(datetime.now().timestamp())}
