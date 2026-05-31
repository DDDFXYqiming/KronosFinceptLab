"""EastMoney Push2 data source.

This adapter is based on the Push2 direct HTTP client pattern from the local
``Stock Analysis System`` project. It adds a no-key A-share fallback that avoids
AkShare's heavier wrapper path for common quote, kline, sector-flow, and
money-flow calls.
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from . import DataSource, DataSourceConfig


PUSH2_HOST = "push2.eastmoney.com"
PUSH2_HIS_HOST = "push2his.eastmoney.com"
EASTMONEY_UT = "fa5fd1943c7b386f172d6893dbfba10b"
EASTMONEY_QUOTE_UT = "8a7e6c2fafe43a70f3a3e7a4e6eaf6d3"


class EastMoneySource(DataSource):
    """EastMoney Push2 data source for A-share market data."""

    supported_endpoints = {
        "stock_zh_a_hist",
        "stock_zh_a_spot_em",
        "eastmoney_sector_flow",
        "eastmoney_money_flow",
    }

    def __init__(self, priority: int = 1):
        config = DataSourceConfig(
            name="eastmoney",
            priority=priority,
            max_retries=2,
            retry_delay=0.8,
            timeout=15.0,
            circuit_break_threshold=4,
            circuit_break_duration=180,
            health_check_interval=60,
        )
        super().__init__(config)

    def fetch(self, endpoint: str, **kwargs) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            if endpoint == "stock_zh_a_hist":
                data = self._fetch_hist(**kwargs)
            elif endpoint == "stock_zh_a_spot_em":
                data = self._fetch_spot(**kwargs)
            elif endpoint == "eastmoney_sector_flow":
                data = self._fetch_sector_flow(**kwargs)
            elif endpoint == "eastmoney_money_flow":
                data = self._fetch_money_flow(**kwargs)
            else:
                return self._failure(f"未知的 EastMoney 端点: {endpoint}")

            if not data:
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

    def _fetch_hist(
        self,
        *,
        symbol: str,
        period: str = "daily",
        start_date: str | None = None,
        end_date: str | None = None,
        adjust: str = "",
        **_: Any,
    ) -> list[dict[str, Any]]:
        secid = self._secid(symbol)
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": self._period_to_klt(period),
            "fqt": self._adjust_to_fqt(adjust),
            "beg": self._date_or_default(start_date, "19700101"),
            "end": self._date_or_default(end_date, datetime.now().strftime("%Y%m%d")),
            "ut": EASTMONEY_UT,
        }
        payload = self._request_json(PUSH2_HIS_HOST, "/api/qt/stock/kline/get", params)
        klines = ((payload or {}).get("data") or {}).get("klines") or []
        rows: list[dict[str, Any]] = []
        for item in klines:
            parts = str(item).split(",")
            if len(parts) < 7:
                continue
            rows.append(
                {
                    "日期": parts[0],
                    "开盘": self._number(parts[1]),
                    "收盘": self._number(parts[2]),
                    "最高": self._number(parts[3]),
                    "最低": self._number(parts[4]),
                    "成交量": self._number(parts[5]),
                    "成交额": self._number(parts[6]),
                    "振幅": self._number(parts[7]) if len(parts) > 7 else None,
                    "涨跌幅": self._number(parts[8]) if len(parts) > 8 else None,
                    "涨跌额": self._number(parts[9]) if len(parts) > 9 else None,
                    "换手率": self._number(parts[10]) if len(parts) > 10 else None,
                }
            )
        return rows

    def _fetch_spot(self, *, page_size: int = 6000, **_: Any) -> list[dict[str, Any]]:
        params = {
            "pn": 1,
            "pz": min(max(int(page_size), 1), 10000),
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
            "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f15,f16,f17,f18,f20,f21,f8",
            "ut": EASTMONEY_QUOTE_UT,
        }
        payload = self._request_json(PUSH2_HOST, "/api/qt/clist/get", params)
        diffs = ((payload or {}).get("data") or {}).get("diff") or []
        return [self._parse_spot_row(item) for item in diffs if isinstance(item, dict)]

    def _fetch_sector_flow(
        self,
        *,
        sector_type: str = "industry",
        page_size: int = 500,
        **_: Any,
    ) -> list[dict[str, Any]]:
        fs_map = {
            "industry": "m:90+t:2",
            "concept": "m:90+t:3",
            "region": "m:90+t:1",
        }
        fs = fs_map.get(str(sector_type).lower(), sector_type)
        fields = "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205"
        rows: list[dict[str, Any]] = []
        page = 1
        total = 0
        while True:
            params = {
                "pn": page,
                "pz": min(max(int(page_size), 1), 1000),
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f62",
                "fs": fs,
                "fields": fields,
                "ut": EASTMONEY_QUOTE_UT,
            }
            payload = self._request_json(PUSH2_HOST, "/api/qt/clist/get", params)
            result = (payload or {}).get("data") or {}
            diff = result.get("diff") or []
            rows.extend(self._parse_sector_row(item) for item in diff if isinstance(item, dict))
            total = int(result.get("total") or total or 0)
            if not diff or len(diff) < int(params["pz"]) or (total and len(rows) >= total):
                break
            page += 1
        return rows

    def _fetch_money_flow(
        self,
        *,
        symbol: str,
        limit: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        params = {
            "secid": self._secid(symbol),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
            "klt": 101,
            "lmt": min(max(int(limit), 1), 5000),
            "ut": EASTMONEY_QUOTE_UT,
        }
        payload = self._request_json(PUSH2_HOST, "/api/qt/stock/fflow/daykline/get", params)
        klines = ((payload or {}).get("data") or {}).get("klines") or []
        start = self._date_or_default(start_date, "")
        end = self._date_or_default(end_date, "")
        rows: list[dict[str, Any]] = []
        for item in klines:
            row = self._parse_money_flow_row(str(item))
            if not row:
                continue
            compact_date = str(row["日期"]).replace("-", "")
            if start and compact_date < start:
                continue
            if end and compact_date > end:
                continue
            rows.append(row)
        return rows

    def _request_json(self, host: str, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        query = urlencode(params, safe="+,:")
        full_path = f"{path}?{query}" if query else path
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36",
            "Referer": "https://data.eastmoney.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
        }
        ip = self._resolve_ipv4(host)
        context = ssl.create_default_context()
        sock = socket.create_connection((ip, 443), timeout=self.config.timeout)
        try:
            wrapped = context.wrap_socket(sock, server_hostname=host)
            conn = http.client.HTTPSConnection(host, 443, timeout=self.config.timeout)
            conn.sock = wrapped
            conn.request("GET", full_path, headers=headers)
            response = conn.getresponse()
            body = response.read().decode("utf-8", errors="replace")
            conn.close()
        finally:
            try:
                sock.close()
            except OSError:
                pass
        if response.status != 200:
            raise RuntimeError(f"EastMoney HTTP {response.status}")
        return json.loads(body)

    @staticmethod
    def _resolve_ipv4(host: str) -> str:
        for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
            family, _, _, _, address = item
            if family == socket.AF_INET:
                return str(address[0])
        return "101.226.30.206"

    @staticmethod
    def _secid(symbol: str) -> str:
        cleaned = str(symbol).strip().upper()
        if "." in cleaned and cleaned.split(".", 1)[0].isdigit():
            base, suffix = cleaned.split(".", 1)
            market = 1 if suffix in {"SH", "SS"} else 0
            return f"{market}.{base}"
        base = cleaned.removeprefix("SH").removeprefix("SZ").removeprefix("BJ")
        market = 1 if base.startswith(("5", "6", "9")) else 0
        return f"{market}.{base}"

    @staticmethod
    def _period_to_klt(period: str) -> int:
        return {
            "daily": 101,
            "1d": 101,
            "weekly": 102,
            "1wk": 102,
            "monthly": 103,
            "1mo": 103,
        }.get(str(period).lower(), 101)

    @staticmethod
    def _adjust_to_fqt(adjust: str | None) -> int:
        return {"": 0, "none": 0, "qfq": 1, "hfq": 2}.get(str(adjust or "").lower(), 0)

    @staticmethod
    def _date_or_default(value: str | None, default: str) -> str:
        cleaned = str(value or "").strip().replace("-", "").replace("/", "")
        return cleaned if len(cleaned) == 8 and cleaned.isdigit() else default

    @staticmethod
    def _parse_spot_row(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "代码": str(item.get("f12") or ""),
            "名称": str(item.get("f14") or ""),
            "最新价": EastMoneySource._scaled_price(item.get("f2")),
            "涨跌幅": EastMoneySource._number(item.get("f3")),
            "涨跌额": EastMoneySource._number(item.get("f4")),
            "成交量": EastMoneySource._number(item.get("f5")),
            "成交额": EastMoneySource._number(item.get("f6")),
            "振幅": EastMoneySource._number(item.get("f7")),
            "最高": EastMoneySource._scaled_price(item.get("f15")),
            "最低": EastMoneySource._scaled_price(item.get("f16")),
            "开盘": EastMoneySource._scaled_price(item.get("f17")),
            "昨收": EastMoneySource._scaled_price(item.get("f18")),
            "总市值": EastMoneySource._number(item.get("f20")),
            "流通市值": EastMoneySource._number(item.get("f21")),
            "换手率": EastMoneySource._number(item.get("f8")),
        }

    @staticmethod
    def _parse_sector_row(item: dict[str, Any]) -> dict[str, Any]:
        row = {
            "代码": item.get("f12") or "",
            "名称": item.get("f14") or "",
            "最新价": EastMoneySource._scaled_price(item.get("f2")),
            "涨跌幅": EastMoneySource._number(item.get("f3")),
            "主力净流入": EastMoneySource._money_yuan_to_yi(item.get("f62")),
            "主力净流入占比": EastMoneySource._number(item.get("f184")),
            "超大单净流入": EastMoneySource._money_yuan_to_yi(item.get("f66")),
            "超大单净流入占比": EastMoneySource._number(item.get("f69")),
            "中单净流入": EastMoneySource._money_yuan_to_yi(item.get("f72")),
            "中单净流入占比": EastMoneySource._number(item.get("f75")),
            "大单净流入": EastMoneySource._money_yuan_to_yi(item.get("f78")),
            "大单净流入占比": EastMoneySource._number(item.get("f81")),
            "小单净流入": EastMoneySource._money_yuan_to_yi(item.get("f84")),
            "小单净流入占比": EastMoneySource._number(item.get("f87")),
            "领涨股": item.get("f204") or "",
            "领涨股涨跌幅": EastMoneySource._number(item.get("f205")),
        }
        for key in ("主力净流入", "超大单净流入", "中单净流入", "大单净流入", "小单净流入"):
            row[f"{key}(亿)"] = row[key]
        return row

    @staticmethod
    def _parse_money_flow_row(item: str) -> dict[str, Any] | None:
        parts = item.split(",")
        if len(parts) < 6:
            return None
        labels = [
            ("主力净流入", 1),
            ("超大单净流入", 2),
            ("大单净流入", 3),
            ("中单净流入", 4),
            ("小单净流入", 5),
        ]
        row: dict[str, Any] = {"日期": parts[0]}
        for label, index in labels:
            value = EastMoneySource._number(parts[index])
            row[label] = value
            row[f"{label}(万元)"] = round(value / 10000, 2) if value is not None else None
        percent_labels = [
            ("主力净流入占比", 6),
            ("超大单净流入占比", 7),
            ("大单净流入占比", 8),
            ("中单净流入占比", 9),
            ("小单净流入占比", 10),
        ]
        for label, index in percent_labels:
            if len(parts) > index:
                row[label] = EastMoneySource._number(parts[index])
        if len(parts) > 11:
            row["收盘价"] = EastMoneySource._number(parts[11])
        if len(parts) > 12:
            row["涨跌幅"] = EastMoneySource._number(parts[12])
        return row

    @staticmethod
    def _scaled_price(value: Any) -> float | None:
        return EastMoneySource._number(value)

    @staticmethod
    def _money_yuan_to_yi(value: Any) -> float | None:
        number = EastMoneySource._number(value)
        return round(number / 100000000, 2) if number is not None else None

    @staticmethod
    def _number(value: Any) -> float | None:
        if value in (None, "", "-", "--"):
            return None
        try:
            return float(str(value).replace(",", "").strip())
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
