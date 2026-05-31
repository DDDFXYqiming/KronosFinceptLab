"""Tushare Pro data source.

Tushare requires a user token. The source is registered only when
``TUSHARE_TOKEN`` is present, so normal local and deployment runs do not fail or
slow down when the optional provider is not configured.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from typing import Any

from . import DataSource, DataSourceConfig


class TushareSource(DataSource):
    """Optional Tushare Pro source for A-share and cross-border flow data."""

    supported_endpoints = {
        "stock_zh_a_hist",
        "stock_info_a_code_name",
        "tushare_call",
        "tushare_hsgt_flow",
    }

    def __init__(self, priority: int = 3):
        config = DataSourceConfig(
            name="tushare",
            priority=priority,
            max_retries=2,
            retry_delay=1.5,
            timeout=30.0,
            circuit_break_threshold=3,
            circuit_break_duration=300,
            health_check_interval=300,
        )
        super().__init__(config)
        self._client: Any | None = None

    @classmethod
    def configured(cls) -> bool:
        return bool(os.environ.get("TUSHARE_TOKEN", "").strip())

    def fetch(self, endpoint: str, **kwargs) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            if endpoint == "stock_zh_a_hist":
                data = self._fetch_daily(**kwargs)
            elif endpoint == "stock_info_a_code_name":
                data = self._fetch_stock_basic()
            elif endpoint == "tushare_hsgt_flow":
                data = self._fetch_hsgt_flow(**kwargs)
            elif endpoint == "tushare_call":
                data = self._call_api(**kwargs)
            else:
                return self._failure(f"未知的 Tushare 端点: {endpoint}")

            if data is None or (isinstance(data, list) and not data):
                return self._failure("返回数据为空")

            return {
                "success": True,
                "data": data,
                "count": len(data) if isinstance(data, list) else 1,
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
                "elapsed": round(time.perf_counter() - started, 2),
            }
        except Exception as exc:
            return self._failure(f"{type(exc).__name__}: {exc}")

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        token = os.environ.get("TUSHARE_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TUSHARE_TOKEN 未配置")
        try:
            import tushare as ts
        except ImportError as exc:
            raise RuntimeError("tushare 未安装，请安装 kronos-fincept-lab[astock] 或 pip install tushare") from exc
        ts.set_token(token)
        self._client = ts.pro_api()
        return self._client

    def _fetch_daily(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        frame = client.daily(
            ts_code=self._ts_code(symbol),
            start_date=self._date_or_default(start_date, "19700101"),
            end_date=self._date_or_default(end_date, datetime.now().strftime("%Y%m%d")),
        )
        if frame is None or frame.empty:
            return []
        frame = frame.sort_values("trade_date")
        rows: list[dict[str, Any]] = []
        for row in frame.to_dict(orient="records"):
            rows.append(
                {
                    "日期": self._format_trade_date(row.get("trade_date")),
                    "开盘": self._number(row.get("open")),
                    "收盘": self._number(row.get("close")),
                    "最高": self._number(row.get("high")),
                    "最低": self._number(row.get("low")),
                    "成交量": self._number(row.get("vol")),
                    "成交额": self._number(row.get("amount")),
                    "涨跌幅": self._number(row.get("pct_chg")),
                    "涨跌额": self._number(row.get("change")),
                }
            )
        return rows

    def _fetch_stock_basic(self) -> list[dict[str, Any]]:
        client = self._get_client()
        frame = client.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,list_date",
        )
        if frame is None or frame.empty:
            return []
        return frame.to_dict(orient="records")

    def _fetch_hsgt_flow(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        frame = self._get_client().moneyflow_hsgt(
            start_date=self._date_or_default(start_date, ""),
            end_date=self._date_or_default(end_date, ""),
        )
        return self._frame_to_records(frame)

    def _call_api(self, *, func_name: str, **kwargs) -> list[dict[str, Any]] | dict[str, Any] | None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,64}", str(func_name)):
            raise ValueError("invalid Tushare API name")
        client = self._get_client()
        func = getattr(client, func_name, None)
        if func is None:
            raise ValueError(f"unknown Tushare API: {func_name}")
        frame = func(**kwargs)
        import pandas as pd

        if isinstance(frame, pd.DataFrame):
            return self._frame_to_records(frame)
        return frame

    @staticmethod
    def _ts_code(symbol: str) -> str:
        cleaned = str(symbol).strip().upper()
        if "." in cleaned:
            base, suffix = cleaned.split(".", 1)
            if suffix in {"SH", "SZ", "BJ"}:
                return f"{base}.{suffix}"
            if suffix == "SS":
                return f"{base}.SH"
        base = cleaned.removeprefix("SH").removeprefix("SZ").removeprefix("BJ")
        if base.startswith(("6", "5", "9")):
            suffix = "SH"
        elif base.startswith(("4", "8")):
            suffix = "BJ"
        else:
            suffix = "SZ"
        return f"{base}.{suffix}"

    @staticmethod
    def _date_or_default(value: str | None, default: str) -> str:
        cleaned = str(value or "").strip().replace("-", "").replace("/", "")
        return cleaned if len(cleaned) == 8 and cleaned.isdigit() else default

    @staticmethod
    def _format_trade_date(value: Any) -> str:
        text = str(value or "")
        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        return text

    @staticmethod
    def _frame_to_records(frame: Any) -> list[dict[str, Any]]:
        import pandas as pd

        if frame is None:
            return []
        if isinstance(frame, pd.DataFrame):
            frame = frame.replace([float("inf"), float("-inf")], None)
            frame = frame.where(pd.notna(frame), None)
            return frame.to_dict(orient="records")
        if isinstance(frame, list):
            return frame
        if isinstance(frame, dict):
            return [frame]
        return []

    @staticmethod
    def _number(value: Any) -> float | None:
        if value in (None, "", "-", "--"):
            return None
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return None

    def _failure(self, error: str) -> dict[str, Any]:
        return {
            "success": False,
            "data": None,
            "error": error,
            "source": self.config.name,
            "timestamp": int(datetime.now().timestamp()),
        }
