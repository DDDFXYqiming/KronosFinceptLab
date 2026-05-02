"""
AkShare 数据源适配器
支持 A 股、港股、美股等市场数据
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime

from . import DataSource, DataSourceConfig, DataSourceStatus


class AkShareSource(DataSource):
    """AkShare 数据源"""

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
            max_retries=3,
            retry_delay=1.0,
            timeout=30.0,
            circuit_break_threshold=5,
            circuit_break_duration=300,
            health_check_interval=60
        )
        super().__init__(config)
        self._ak = None

    def _get_ak(self):
        """懒加载 AkShare"""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError as e:
                raise ImportError(f"AkShare 未安装: {e}")
        return self._ak

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        获取数据

        Args:
            endpoint: 数据端点（如 'stock_zh_a_hist'）
            **kwargs: 传递给 AkShare 函数的参数

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

            # 获取 AkShare 函数
            func = getattr(ak, endpoint, None)
            if func is None:
                return {
                    "success": False,
                    "data": None,
                    "error": f"未知的 AkShare 端点: {endpoint}",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            # 调用函数
            start_time = time.time()
            result = func(**kwargs)
            elapsed = time.time() - start_time

            # 处理结果
            if result is None:
                return {
                    "success": False,
                    "data": None,
                    "error": "返回数据为空",
                    "source": self.config.name,
                    "timestamp": int(datetime.now().timestamp())
                }

            # 转换 DataFrame 为字典
            if hasattr(result, 'to_dict'):
                # 处理 DataFrame
                import pandas as pd
                # 替换 NaN/Infinity 为 None
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


# 便捷函数
def get_stock_history(symbol: str, period: str = "daily",
                      start_date: str = None, end_date: str = None,
                      adjust: str = "") -> Dict[str, Any]:
    """
    获取股票历史数据

    Args:
        symbol: 股票代码（如 '601398'）
        period: 周期（'daily', 'weekly', 'monthly'）
        start_date: 开始日期（'YYYYMMDD'）
        end_date: 结束日期（'YYYYMMDD'）
        adjust: 复权方式（'qfq', 'hfq', ''）

    Returns:
        数据源管理器返回的结果
    """
    from . import get_manager

    # 默认日期
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
    获取股票实时数据

    Args:
        symbol: 股票代码（可选，不传则获取所有）

    Returns:
        数据源管理器返回的结果
    """
    from . import get_manager

    manager = get_manager()

    if symbol:
        # 获取单个股票
        return manager.fetch(
            endpoint='stock_zh_a_spot_em'
        )
    else:
        # 获取所有股票
        return manager.fetch(
            endpoint='stock_zh_a_spot_em'
        )


def get_stock_info(symbol: str) -> Dict[str, Any]:
    """
    获取股票基本信息

    Args:
        symbol: 股票代码

    Returns:
        数据源管理器返回的结果
    """
    from . import get_manager

    manager = get_manager()
    return manager.fetch(
        endpoint='stock_individual_info_em',
        symbol=symbol
    )
