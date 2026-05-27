"""
Stooq data source adapter
Provides free CSV data for global stocks via stooq.com
URL pattern: https://stooq.com/q/d/l/?s={symbol}&d1={YYYYMMDD}&d2={YYYYMMDD}&i=daily
No API key required.
"""

import csv
import io
import time
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from . import DataSource, DataSourceConfig


class StooqSource(DataSource):
    """Stooq data source for free global stock price data.

    Supports A-shares (.SS / .SZ), Hong Kong (.HK), US (.US) markets.
    Priority: 4 (below Yahoo Finance).
    """

    supported_endpoints = {"stooq_hist"}

    BASE_URL = "https://stooq.com/q/d/l/"

    def __init__(self, priority: int = 4):
        config = DataSourceConfig(
            name="stooq",
            priority=priority,
            max_retries=3,
            retry_delay=1.0,
            timeout=30.0,
            circuit_break_threshold=5,
            circuit_break_duration=300,
            health_check_interval=60,
        )
        super().__init__(config)

    def _normalize_symbol(self, symbol: str, market: str = "auto") -> str:
        """
        Normalize stock symbol to Stooq format.

        Stooq uses Yahoo-compatible suffixes:
          - A-shares Shanghai: 601398.SS
          - A-shares Shenzhen: 000001.SZ
          - Hong Kong:         00700.HK
          - US:                AAPL.US  (or plain AAPL)

        Args:
            symbol: Raw symbol e.g. '601398', 'AAPL', '00700'
            market: Market identifier ('auto', 'cn_sh', 'cn_sz', 'hk', 'us')

        Returns:
            Stooq-compatible symbol string.
        """
        # If already has a recognised suffix, return as-is
        if any(suffix in symbol for suffix in (".SS", ".SZ", ".HK", ".US")):
            return symbol

        # Auto-detect market from symbol pattern
        # Important: HK (5-digit) check must come before cn_sz (6-digit starting with 0/3)
        if market == "auto":
            if symbol.startswith("6") and symbol.isdigit():
                market = "cn_sh"
            elif symbol.isdigit() and len(symbol) == 5:
                market = "hk"
            elif symbol.startswith(("0", "3")) and symbol.isdigit():
                market = "cn_sz"
            else:
                market = "us"

        suffix_map = {
            "cn_sh": ".SS",
            "cn_sz": ".SZ",
            "hk": ".HK",
            "us": ".US",
        }
        suffix = suffix_map.get(market, "")
        return f"{symbol}{suffix}"

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch data from Stooq.

        Args:
            endpoint: Must be 'stooq_hist'.
            **kwargs:
                symbol:      Stock symbol (raw, without suffix).
                start_date:  Start date in YYYYMMDD or YYYY-MM-DD format.
                end_date:    End date in YYYYMMDD or YYYY-MM-DD format.
                market:      Market ('auto', 'cn_sh', 'cn_sz', 'hk', 'us').

        Returns:
            Standardised result dict:
                success: bool
                data:    list[dict]  (parsed OHLCV rows)
                source:  str
                timestamp: int
                error:   str (if failed)
        """
        if endpoint != "stooq_hist":
            return {
                "success": False,
                "data": None,
                "error": f"未知的 Stooq 端点: {endpoint}",
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
            }

        try:
            start_time = time.perf_counter()

            symbol = kwargs.get("symbol", "")
            market = kwargs.get("market", "auto")
            start_date = kwargs.get("start_date", "")
            end_date = kwargs.get("end_date", "")

            if not symbol:
                return {
                    "success": False,
                    "data": None,
                    "error": "缺少 symbol 参数",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp()),
                }

            # Normalise symbol
            stooq_symbol = self._normalize_symbol(symbol, market)

            # Normalise dates to YYYYMMDD
            start_str = self._normalize_date(start_date) if start_date else "20000101"
            end_str = self._normalize_date(end_date) if end_date else datetime.now().strftime("%Y%m%d")

            # Build URL
            url = f"{self.BASE_URL}?s={stooq_symbol}&d1={start_str}&d2={end_str}&i=daily"

            # Download CSV
            csv_text = self._download(url)
            if csv_text is None:
                return {
                    "success": False,
                    "data": None,
                    "error": f"从 Stooq 下载 {stooq_symbol} 数据失败",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp()),
                }

            # Parse CSV
            data = self._parse_csv(csv_text, symbol)

            elapsed = time.perf_counter() - start_time

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
                "elapsed": round(elapsed, 2),
            }

        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": f"{type(e).__name__}: {str(e)}",
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Convert various date formats to YYYYMMDD."""
        cleaned = date_str.replace("-", "").replace("/", "").strip()
        # Already YYYYMMDD
        if len(cleaned) == 8 and cleaned.isdigit():
            return cleaned
        # Try to parse and reformat
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(date_str.strip(), fmt).strftime("%Y%m%d")
            except (ValueError, TypeError):
                continue
        # Fallback: return as-is
        return cleaned

    def _download(self, url: str) -> Optional[str]:
        """
        Download CSV from Stooq.

        Returns the raw CSV text, or None on failure.
        """
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=self.config.timeout) as resp:
                text = resp.read().decode("utf-8-sig")
            return text
        except (HTTPError, URLError, OSError) as e:
            self.record_failure()
            return None

    def _parse_csv(self, csv_text: str, original_symbol: str) -> list:
        """
        Parse Stooq CSV into standardised list of dicts.

        Stooq CSV format (header row):
            Date,Open,High,Low,Close,Volume

        Returns:
            list[dict] with keys:
                date, open, high, low, close, volume, symbol
        """
        # Strip UTF-8 BOM if present (handles \ufeff at start of stream)
        if csv_text.startswith("\ufeff"):
            csv_text = csv_text[1:]

        reader = csv.DictReader(io.StringIO(csv_text))
        rows = []
        for row in reader:
            # Stooq returns "2025-03-15" or similar date format
            raw_date = row.get("Date", "").strip()
            if not raw_date:
                continue

            # Skip lines where the data is empty (Stooq returns latest date
            # with all zeros when no data is available for the requested range)
            try:
                open_val = self._to_float(row.get("Open"))
                high_val = self._to_float(row.get("High"))
                low_val = self._to_float(row.get("Low"))
                close_val = self._to_float(row.get("Close"))
                volume_val = self._to_int(row.get("Volume"))
            except (ValueError, TypeError):
                continue

            # Normalise the date to YYYY-MM-DD
            norm_date = raw_date
            if len(normal_date := raw_date.replace("-", "")) == 8 and norm_date.isdigit():
                norm_date = f"{norm_date[:4]}-{norm_date[4:6]}-{norm_date[6:]}"

            rows.append({
                "date": norm_date,
                "symbol": original_symbol,
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": volume_val,
            })

        return rows

    @staticmethod
    def _to_float(val: Any) -> float:
        """Safely convert a value to float."""
        if val is None:
            return 0.0
        val = str(val).strip()
        if not val or val == "N/A":
            return 0.0
        return round(float(val), 2)

    @staticmethod
    def _to_int(val: Any) -> int:
        """Safely convert a value to int."""
        if val is None:
            return 0
        val = str(val).strip()
        if not val or val == "N/A":
            return 0
        return int(float(val))
