"""Finnhub data source adapter — optional, requires FINNHUB_API_KEY."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from kronos_fincept.data_sources import DataSource, DataSourceConfig


class FinnhubSource(DataSource):
    supported_endpoints = {"stock_quote", "company_profile", "financials", "earnings", "company_news", "forex", "crypto"}

    def __init__(self, priority: int = 8):
        config = DataSourceConfig(name="finnhub", priority=priority, max_retries=1, retry_delay=0.5, timeout=15.0, circuit_break_threshold=3,
                                   circuit_break_duration=120, health_check_interval=300)
        super().__init__(config)

    def is_available(self) -> bool:
        return bool(os.environ.get("FINNHUB_API_KEY", "").strip())

    def fetch(self, endpoint: str, **kwargs) -> dict[str, Any]:
        import requests
        api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
        if not api_key:
            return {"success": False, "data": None, "error": "FINNHUB_API_KEY not configured", "source": self.config.name, "timestamp": int(datetime.now().timestamp())}

        base = "https://finnhub.io/api/v1"
        endpoint_map = {
            "stock_quote": "/quote",
            "company_profile": "/stock/profile2",
            "financials": "/financials-reported",
            "earnings": "/calendar/earnings",
            "company_news": "/company-news",
            "forex": "/forex/rates",
            "crypto": "/crypto/candle",
        }
        path = endpoint_map.get(endpoint)
        if not path:
            return {"success": False, "data": None, "error": f"Unknown Finnhub endpoint: {endpoint}", "source": self.config.name, "timestamp": int(datetime.now().timestamp())}

        params = {k: v for k, v in kwargs.items() if k in ("symbol", "from", "to", "resolution")}
        params["token"] = api_key
        try:
            resp = requests.get(f"{base}{path}", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "data": data, "count": 1, "source": self.config.name, "timestamp": int(datetime.now().timestamp())}
        except Exception as e:
            return {"success": False, "data": None, "error": str(e), "source": self.config.name, "timestamp": int(datetime.now().timestamp())}
