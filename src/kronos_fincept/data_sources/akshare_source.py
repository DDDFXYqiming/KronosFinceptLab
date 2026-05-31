"""
AkShare data source adapter
Supports A-shares, Hong Kong stocks, US stocks and other market data
"""

import time
import os
import random
from typing import Dict, Any, Optional
from datetime import datetime

from . import DataSource, DataSourceConfig, DataSourceStatus


class AkShareSource(DataSource):
    """AkShare data source"""

    supported_endpoints = {
        "stock_zh_a_hist",
        "stock_zh_a_spot_em",
        "stock_info_a_code_name",
        "stock_individual_info_em",
    }

    def __init__(self, priority: int = 1):
        config = DataSourceConfig(
            name="akshare",
            priority=priority,
            max_retries=_env_int("AKSHARE_MAX_RETRIES", 3),
            retry_delay=_env_float("AKSHARE_MIN_DELAY", 1.0),
            timeout=30.0,
            circuit_break_threshold=5,
            circuit_break_duration=300,
            health_check_interval=60
        )
        super().__init__(config)
        self._ak = None
        self._last_call_ts = 0.0
        self._min_delay = max(0.0, _env_float("AKSHARE_MIN_DELAY", 0.0))
        self._max_delay = max(self._min_delay, _env_float("AKSHARE_MAX_DELAY", self._min_delay))

    def _get_ak(self):
        """Lazy-load AkShare"""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError as e:
                raise ImportError(f"AkShare 未安装: {e}")
        return self._ak

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch data

        Args:
            endpoint: Data endpoint (e.g. 'stock_zh_a_hist')
            **kwargs: Parameters passed to the AkShare function

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str (if failed),
                "source": str,
                "timestamp": int
            }
        """
        try:
            ak = self._get_ak()

            # Get the AkShare function
            func = getattr(ak, endpoint, None)
            if func is None:
                return {
                    "success": False,
                    "data": None,
                    "error": f"未知的 AkShare 端点: {endpoint}",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            # Call the function
            self._throttle()
            start_time = time.time()
            result = func(**kwargs)
            elapsed = time.time() - start_time

            # Process the result
            if result is None:
                return {
                    "success": False,
                    "data": None,
                    "error": "返回数据为空",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            # Convert DataFrame to dict
            if hasattr(result, 'to_dict'):
                # Handle DataFrame
                import pandas as pd
                # Replace NaN/Infinity with None
                result = result.replace([float("inf"), float("-inf")], None)
                result = result.where(pd.notna(result), None)
                data = result.to_dict(orient='records')
            elif isinstance(result, (list, dict)):
                data = result
            else:
                data = str(result)

            return {
                "success": True,
                "data": data,
                "count": len(data) if isinstance(data, list) else 1,
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

    def _throttle(self) -> None:
        """Apply optional AkShare request pacing from the source project's config."""
        if self._max_delay <= 0:
            return
        elapsed = time.time() - self._last_call_ts if self._last_call_ts else self._max_delay
        target = random.uniform(self._min_delay, self._max_delay)
        if elapsed < target:
            time.sleep(target - elapsed)
        self._last_call_ts = time.time()


# Convenience functions
def get_stock_history(symbol: str, period: str = "daily",
                      start_date: str = None, end_date: str = None,
                      adjust: str = "") -> Dict[str, Any]:
    """
    Get stock historical data

    Args:
        symbol: Stock code (e.g. '601398')
        period: Period ('daily', 'weekly', 'monthly')
        start_date: Start date ('YYYYMMDD')
        end_date: End date ('YYYYMMDD')
        adjust: Adjustment method ('qfq', 'hfq', '')

    Returns:
        Result from the data source manager
    """
    from . import get_manager

    # Default dates
    if not end_date:
        end_date = datetime.now().strftime('%Y%m%d')
    if not start_date:
        start_date = '19700101'

    manager = get_manager()
    return manager.fetch(
        endpoint='stock_zh_a_hist',
        symbol=symbol,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust
    )


def get_stock_realtime(symbol: str = None) -> Dict[str, Any]:
    """
    Get stock real-time data

    Args:
        symbol: Stock code (optional, gets all if omitted)

    Returns:
        Result from the data source manager
    """
    from . import get_manager

    manager = get_manager()

    if symbol:
        # Get single stock
        return manager.fetch(
            endpoint='stock_zh_a_spot_em'
        )
    else:
        # Get all stocks
        return manager.fetch(
            endpoint='stock_zh_a_spot_em'
        )


def get_stock_info(symbol: str) -> Dict[str, Any]:
    """
    Get stock basic information

    Args:
        symbol: Stock code

    Returns:
        Result from the data source manager
    """
    from . import get_manager

    manager = get_manager()
    return manager.fetch(
        endpoint='stock_individual_info_em',
        symbol=symbol
    )


def _env_int(key: str, default: int) -> int:
    try:
        return int(float(os.environ.get(key, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default
