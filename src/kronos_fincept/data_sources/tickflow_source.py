"""Optional TickFlow data source.

TickFlow is not a required dependency. The source is registered only when the
package is installed and not explicitly disabled, so Linux deployments can skip
it without startup failures.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from typing import Any

from . import DataSource, DataSourceConfig


class TickFlowSource(DataSource):
    supported_endpoints = {
        "stock_zh_a_hist",
        "stock_info_a_code_name",
        "tickflow_stock_zh_a_hist",
        "tickflow_minute",
    }

    def __init__(self, priority: int = 6):
        config = DataSourceConfig(
            name="tickflow",
            priority=priority,
            max_retries=1,
            retry_delay=0.0,
            timeout=float(os.environ.get("TICKFLOW_TIMEOUT_SECONDS", "25") or 25),
            circuit_break_threshold=2,
            circuit_break_duration=300,
            health_check_interval=300,
        )
        super().__init__(config)
        self._client: Any | None = None

    @classmethod
    def configured(cls) -> bool:
        mode = os.environ.get("KRONOS_ENABLE_TICKFLOW", "auto").strip().lower()
        if mode in {"0", "false", "no", "off", "disabled"}:
            return False
        return importlib.util.find_spec("tickflow") is not None

    def is_available(self) -> bool:
        return self.configured() and super().is_available()

    def fetch(self, endpoint: str, **kwargs) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            if not self.is_available():
                return self._failure("TickFlow is not installed or is disabled")
            if endpoint in {"stock_zh_a_hist", "tickflow_stock_zh_a_hist"}:
                data = self._fetch_daily(**kwargs)
            elif endpoint == "tickflow_minute":
                data = self._fetch_minute(**kwargs)
            elif endpoint == "stock_info_a_code_name":
                data = self._fetch_stock_list()
            else:
                return self._failure(f"unsupported TickFlow endpoint: {endpoint}")

            if data is None or (isinstance(data, list) and not data):
                return self._failure("TickFlow returned no data")
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

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        with contextlib.redirect_stdout(io.StringIO()):
            from tickflow import TickFlow

            self._client = TickFlow.free()
        return self._client

    def _fetch_daily(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        count: int | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        full_code = _tickflow_code(symbol)
        frame = self._call(lambda: self._get_client().klines.get(full_code, period="1d", count=int(count or 800), as_dataframe=True))
        rows = _frame_to_rows(frame)
        return _filter_dates(rows, start_date, end_date)

    def _fetch_minute(self, *, symbol: str, period: str = "5min", count: int = 500, **_: Any) -> list[dict[str, Any]]:
        full_code = _tickflow_code(symbol)
        tf_period = {"1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m", "60min": "60m"}.get(str(period), str(period))
        frame = self._call(lambda: self._get_client().klines.get(full_code, period=tf_period, count=min(int(count), 5000), as_dataframe=True))
        return _frame_to_rows(frame)

    def _fetch_stock_list(self) -> list[dict[str, str]]:
        data = self._call(lambda: self._get_client().get_stock_list())
        if data is None:
            return []
        if hasattr(data, "to_dict"):
            records = data.to_dict(orient="records")
        elif isinstance(data, list):
            records = data
        else:
            return []
        rows: list[dict[str, str]] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or item.get("symbol") or item.get("ts_code") or "").split(".")[0]
            name = str(item.get("name") or item.get("名称") or item.get("stock_name") or "")
            if code:
                rows.append({"code": code, "name": name})
        return rows

    def _call(self, fn):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fn)
            try:
                return future.result(timeout=self.config.timeout)
            except TimeoutError:
                future.cancel()
                return None

    def _failure(self, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "data": None,
            "error": message,
            "source": self.config.name,
            "timestamp": int(datetime.now().timestamp()),
        }


def _tickflow_code(symbol: str) -> str:
    clean = str(symbol or "").strip().upper()
    if "." in clean:
        return clean
    if clean.startswith(("6", "5", "68")):
        return f"{clean}.SH"
    return f"{clean}.SZ"


def _frame_to_rows(frame: Any) -> list[dict[str, Any]]:
    if frame is None or not hasattr(frame, "empty") or frame.empty:
        return []
    frame = frame.loc[:, ~frame.columns.duplicated(keep="first")].copy()
    rename = {"trade_date": "date", "timestamp": "date", "vol": "volume"}
    frame = frame.rename(columns={old: new for old, new in rename.items() if old in frame.columns and new not in frame.columns})
    records = frame.to_dict(orient="records")
    rows: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        date_value = item.get("date") or item.get("datetime") or item.get("time")
        if date_value is None:
            continue
        rows.append(
            {
                "日期": str(date_value)[:10],
                "开盘": _number(item.get("open")),
                "收盘": _number(item.get("close")),
                "最高": _number(item.get("high")),
                "最低": _number(item.get("low")),
                "成交量": _number(item.get("volume")),
                "成交额": _number(item.get("amount")),
            }
        )
    rows.sort(key=lambda row: str(row["日期"]))
    return rows


def _filter_dates(rows: list[dict[str, Any]], start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
    if start_date:
        rows = [row for row in rows if str(row["日期"]).replace("-", "") >= str(start_date)]
    if end_date:
        rows = [row for row in rows if str(row["日期"]).replace("-", "") <= str(end_date)]
    return rows


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
