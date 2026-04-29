"""
数据源初始化模块
自动注册所有可用的数据源
"""

from typing import Optional
from . import DataSourceManager, get_manager
from .akshare_source import AkShareSource
from .baostock_source import BaoStockSource
from .yahoo_source import YahooFinanceSource


def init_data_sources(cache_dir: str = ".cache",
                      enable_akshare: bool = True,
                      enable_baostock: bool = True,
                      enable_yahoo: bool = True) -> DataSourceManager:
    """
    初始化数据源管理器

    Args:
        cache_dir: 缓存目录
        enable_akshare: 是否启用 AkShare
        enable_baostock: 是否启用 BaoStock
        enable_yahoo: 是否启用 Yahoo Finance

    Returns:
        数据源管理器实例
    """
    manager = get_manager(cache_dir)

    # 按优先级注册数据源
    # 优先级数字越小，优先级越高

    if enable_akshare:
        try:
            akshare_source = AkShareSource(priority=1)
            manager.register(akshare_source)
        except Exception as e:
            print(f"[DataSource] AkShare 注册失败: {e}")

    if enable_baostock:
        try:
            baostock_source = BaoStockSource(priority=2)
            manager.register(baostock_source)
        except Exception as e:
            print(f"[DataSource] BaoStock 注册失败: {e}")

    if enable_yahoo:
        try:
            yahoo_source = YahooFinanceSource(priority=3)
            manager.register(yahoo_source)
        except Exception as e:
            print(f"[DataSource] Yahoo Finance 注册失败: {e}")

    print(f"[DataSource] 已注册 {len(manager.data_sources)} 个数据源")
    return manager


def get_stock_history(symbol: str, period: str = "daily",
                      start_date: str = None, end_date: str = None,
                      adjust: str = "") -> dict:
    """
    获取股票历史数据（便捷函数）

    Args:
        symbol: 股票代码（如 '601398'）
        period: 周期（'daily', 'weekly', 'monthly'）
        start_date: 开始日期（'YYYYMMDD'）
        end_date: 结束日期（'YYYYMMDD'）
        adjust: 复权方式（'qfq', 'hfq', ''）

    Returns:
        {
            "success": bool,
            "data": list,
            "source": str,
            "timestamp": int,
            "from_cache": bool
        }
    """
    manager = get_manager()

    # 默认日期
    if not end_date:
        from datetime import datetime
        end_date = datetime.now().strftime('%Y%m%d')
    if not start_date:
        start_date = '19700101'

    return manager.fetch(
        endpoint='stock_zh_a_hist',
        use_cache=True,
        cache_ttl=3600,  # 缓存1小时
        symbol=symbol,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust
    )


def get_stock_info(symbol: str) -> dict:
    """
    获取股票基本信息（便捷函数）

    Args:
        symbol: 股票代码

    Returns:
        {
            "success": bool,
            "data": dict,
            "source": str,
            "timestamp": int,
            "from_cache": bool
        }
    """
    manager = get_manager()
    return manager.fetch(
        endpoint='stock_individual_info_em',
        use_cache=True,
        cache_ttl=86400,  # 缓存24小时
        symbol=symbol
    )


def get_data_source_status() -> dict:
    """
    获取所有数据源状态

    Returns:
        数据源状态字典
    """
    manager = get_manager()
    return manager.get_status()


def reset_data_sources():
    """重置所有数据源状态"""
    manager = get_manager()
    manager.reset_all()
