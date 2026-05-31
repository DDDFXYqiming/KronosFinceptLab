"""Optional local TongDaXin data source for raw A-share daily bars."""

from __future__ import annotations

import os
import re
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import DataSource, DataSourceConfig


class TDXLocalSource(DataSource):
    """Read raw daily bars from a local TongDaXin ``vipdoc`` directory."""

    supported_endpoints = {"stock_zh_a_hist", "tdx_stock_zh_a_hist"}

    def __init__(self, priority: int = 2, tdx_path: str | None = None):
        config = DataSourceConfig(
            name="tdx_local",
            priority=priority,
            max_retries=1,
            retry_delay=0.0,
            timeout=5.0,
            circuit_break_threshold=3,
            circuit_break_duration=300,
            health_check_interval=300,
        )
        super().__init__(config)
        self.tdx_path = Path(tdx_path or os.environ.get("TDX_PATH", "")).expanduser()

    def is_available(self) -> bool:
        return _valid_tdx_path(self.tdx_path) and super().is_available()

    def fetch(self, endpoint: str, **kwargs) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            if endpoint not in self.supported_endpoints:
                return self._failure(f"unsupported TDX endpoint: {endpoint}")
            adjust = str(kwargs.get("adjust") or "").lower()
            if adjust:
                return self._failure("TDX local daily files are raw and do not support adjusted prices")
            if not self.is_available():
                return self._failure("TDX_PATH is not configured or vipdoc is unavailable")

            rows = self._fetch_hist(
                symbol=str(kwargs.get("symbol", "")),
                start_date=kwargs.get("start_date"),
                end_date=kwargs.get("end_date"),
            )
            if not rows:
                return self._failure("TDX local data returned no rows")
            return {
                "success": True,
                "data": rows,
                "count": len(rows),
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
                "elapsed": round(time.perf_counter() - started, 3),
            }
        except Exception as exc:
            return self._failure(f"{type(exc).__name__}: {exc}")

    def _fetch_hist(self, symbol: str, start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
        symbol = _normalize_symbol(symbol)
        path = _tdx_day_path(self.tdx_path, symbol)
        rows = _read_tdx_day_file(path)
        if start_date:
            rows = [row for row in rows if row["日期"].replace("-", "") >= str(start_date)]
        if end_date:
            rows = [row for row in rows if row["日期"].replace("-", "") <= str(end_date)]
        return rows

    def _failure(self, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "data": None,
            "error": message,
            "source": self.config.name,
            "timestamp": int(datetime.now().timestamp()),
        }


def _valid_tdx_path(path: Path) -> bool:
    return bool(path) and (path / "vipdoc").is_dir()


def _normalize_symbol(symbol: str) -> str:
    clean = re.sub(r"^(sh|sz|SH|SZ)", "", str(symbol).strip())
    clean = re.sub(r"\.(SH|SZ|sh|sz)$", "", clean)
    return clean


def _market_for_symbol(symbol: str) -> str:
    sh_indices = {"000001", "000016", "000300", "000905", "000852", "000688"}
    sz_indices = {"399001", "399006", "399300", "399005", "399673"}
    if symbol in sh_indices:
        return "sh"
    if symbol in sz_indices or symbol.startswith("399"):
        return "sz"
    if symbol.startswith(("6", "5", "68")):
        return "sh"
    return "sz"


def _tdx_day_path(tdx_path: Path, symbol: str) -> Path:
    market = _market_for_symbol(symbol)
    return tdx_path / "vipdoc" / market / "lday" / f"{market}{symbol}.day"


def _read_tdx_day_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return _parse_day_records(path.read_bytes())


def _parse_day_records(data: bytes) -> list[dict[str, Any]]:
    record_size = 32
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(data) - record_size + 1, record_size):
        date_raw, open_raw, high_raw, low_raw, close_raw, amount, volume, _reserved = struct.unpack(
            "<IIIIIfII",
            data[offset:offset + record_size],
        )
        if not _valid_date_int(date_raw) or min(open_raw, high_raw, low_raw, close_raw) <= 0:
            continue
        rows.append(
            {
                "日期": _format_date_int(date_raw),
                "开盘": round(open_raw / 100.0, 4),
                "收盘": round(close_raw / 100.0, 4),
                "最高": round(high_raw / 100.0, 4),
                "最低": round(low_raw / 100.0, 4),
                "成交量": int(volume),
                "成交额": float(amount),
            }
        )
    return rows


def _valid_date_int(value: int) -> bool:
    year = value // 10000
    month = value // 100 % 100
    day = value % 100
    return 1990 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31


def _format_date_int(value: int) -> str:
    raw = f"{value:08d}"
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
