"""Optional TDX network source backed by a configured Go HTTP backend."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from . import DataSource, DataSourceConfig


KTYPE_MAP = {
    "1min": 0,
    "1m": 0,
    "5min": 1,
    "5m": 1,
    "15min": 2,
    "15m": 2,
    "30min": 3,
    "30m": 3,
    "60min": 4,
    "60m": 4,
    "daily": 5,
    "day": 5,
    "weekly": 6,
    "monthly": 7,
}


class TDXNetworkSource(DataSource):
    """Fetch TDX remote quotes/K-lines through a pre-running Go backend.

    The source never starts a Go process. This keeps Zeabur/Linux deployment safe:
    without an explicit backend URL it is simply not registered.
    """

    supported_endpoints = {
        "stock_zh_a_hist",
        "stock_info_a_code_name",
        "tdx_network_kline",
        "tdx_quote",
        "tdx_codes",
        "tdx_callauction",
        "tdx_gbbq",
        "tdx_network_health",
    }

    def __init__(self, priority: int = 2, base_url: str | None = None):
        config = DataSourceConfig(
            name="tdx_network",
            priority=priority,
            max_retries=1,
            retry_delay=0.0,
            timeout=8.0,
            circuit_break_threshold=3,
            circuit_break_duration=300,
            health_check_interval=300,
        )
        super().__init__(config)
        self.base_url = (base_url or _configured_base_url() or "").rstrip("/")

    @classmethod
    def configured(cls) -> bool:
        return bool(_configured_base_url())

    def is_available(self) -> bool:
        return bool(self.base_url) and super().is_available()

    def fetch(self, endpoint: str, **kwargs) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            if not self.is_available():
                return self._failure("TDX network backend is not configured")
            if endpoint in {"stock_zh_a_hist", "tdx_network_kline"}:
                data = self._fetch_kline(**kwargs)
            elif endpoint == "tdx_quote":
                data = self._fetch_quote(**kwargs)
            elif endpoint in {"tdx_codes", "stock_info_a_code_name"}:
                data = self._fetch_codes(**kwargs)
            elif endpoint == "tdx_callauction":
                data = self._request_json("/tdx/callauction", {"code": _normalize_code(str(kwargs.get("symbol") or kwargs.get("code") or ""))})
            elif endpoint == "tdx_gbbq":
                data = self._request_json("/tdx/gbbq", {"code": _normalize_code(str(kwargs.get("symbol") or kwargs.get("code") or ""))})
            elif endpoint == "tdx_network_health":
                data = self._request_json("/tdx/health")
            else:
                return self._failure(f"unsupported TDX network endpoint: {endpoint}")

            if data is None or (isinstance(data, list) and not data):
                return self._failure("TDX network returned no data")
            return {
                "success": True,
                "data": data,
                "count": len(data) if isinstance(data, list) else 1,
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
                "elapsed": round(time.perf_counter() - started, 3),
            }
        except Exception as exc:
            return self._failure(f"{type(exc).__name__}: {exc}")

    def _fetch_kline(
        self,
        *,
        symbol: str,
        period: str = "daily",
        start_date: str | None = None,
        end_date: str | None = None,
        adjust: str = "",
        count: int | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        if str(adjust or "").strip():
            return []
        limit = max(1, min(int(count or 800), 800))
        payload = self._request_json(
            "/tdx/kline",
            {"code": _normalize_code(symbol), "type": KTYPE_MAP.get(str(period).lower(), 5), "count": limit},
        )
        rows = [_kline_row(item) for item in _as_list(payload)]
        rows = [row for row in rows if row]
        if start_date:
            rows = [row for row in rows if str(row["日期"]).replace("-", "") >= str(start_date)]
        if end_date:
            rows = [row for row in rows if str(row["日期"]).replace("-", "") <= str(end_date)]
        rows.sort(key=lambda row: str(row["日期"]))
        return rows

    def _fetch_quote(self, *, symbol: str | None = None, symbols: list[str] | str | None = None, **_: Any) -> list[dict[str, Any]]:
        raw_symbols = symbols if symbols is not None else symbol
        codes = _normalize_code_list(raw_symbols)
        if not codes:
            return []
        return _as_list(self._request_json("/tdx/quote", {"code": codes}))

    def _fetch_codes(self, *, exchange: str = "all", **_: Any) -> list[dict[str, Any]]:
        rows = _as_list(self._request_json("/tdx/codes", {"exchange": exchange or "all"}))
        return [{"code": str(item.get("code") or ""), "name": str(item.get("name") or "")} for item in rows if isinstance(item, dict)]

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = urllib.parse.urlencode(params or {}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "KronosFinceptLab/tdx-network"})
        with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("TDX backend returned non-object response")
        if not payload.get("success") and payload.get("status") != "ok":
            raise RuntimeError(str(payload.get("error") or payload.get("message") or "TDX backend error"))
        return payload.get("data", payload)

    def _failure(self, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "data": None,
            "error": message,
            "source": self.config.name,
            "timestamp": int(datetime.now().timestamp()),
        }


def _configured_base_url() -> str | None:
    for name in ("KRONOS_TDX_NETWORK_BASE_URL", "TDX_NETWORK_BASE_URL", "GO_BACKEND_URL"):
        raw = os.environ.get(name, "").strip()
        if raw:
            return raw
    if os.environ.get("KRONOS_ENABLE_TDX_NETWORK", "").strip().lower() in {"1", "true", "yes", "on"}:
        port = os.environ.get("GO_BACKEND_PORT", "9100").strip() or "9100"
        return f"http://127.0.0.1:{port}"
    return None


def _normalize_code(symbol: str) -> str:
    clean = str(symbol or "").strip().upper()
    if not clean:
        return clean
    if clean.startswith(("SZ", "SH")) and len(clean) == 8:
        return clean
    if "." in clean:
        left, right = clean.split(".", 1)
        if right in {"SZ", "SH"}:
            return f"{right}{left}"
        clean = left
    if clean.startswith(("6", "5", "68")):
        return f"SH{clean}"
    return f"SZ{clean}"


def _normalize_code_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
    else:
        parts = [str(item).strip() for item in value]
    return [_normalize_code(item) for item in parts if item]


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _kline_row(item: dict[str, Any]) -> dict[str, Any]:
    timestamp = str(item.get("time") or item.get("date") or item.get("timestamp") or "")
    if not timestamp:
        return {}
    return {
        "日期": timestamp[:10],
        "开盘": _number(item.get("open")),
        "收盘": _number(item.get("close")),
        "最高": _number(item.get("high")),
        "最低": _number(item.get("low")),
        "成交量": _number(item.get("volume")),
        "成交额": _number(item.get("amount")),
    }


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
