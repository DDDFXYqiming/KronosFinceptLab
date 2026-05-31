import logging
logger = logging.getLogger(__name__)

"""
数据源初始化模块
自动注册所有可用的数据源
"""

from typing import Optional

import kronos_fincept.config  # noqa: F401 - load project .env before provider registration

from . import DataSourceManager, get_manager
from .eastmoney_source import EastMoneySource
from .source_market_cache import SourceProjectMarketCacheSource
from .tdx_source import TDXLocalSource
from .tdx_network_source import TDXNetworkSource
from .tickflow_source import TickFlowSource
from .akshare_source import AkShareSource
from .baostock_source import BaoStockSource
from .tushare_source import TushareSource
from .yahoo_source import YahooFinanceSource
from .binance_source import BinanceSource
from .stooq_source import StooqSource
from .okx_source import OKXSource


def init_data_sources(cache_dir: str = ".cache",
                      enable_eastmoney: bool = True,
                      enable_source_market_cache: bool = True,
                      enable_tdx: bool = True,
                      enable_tdx_network: bool = True,
                      enable_tickflow: bool = True,
                      enable_akshare: bool = True,
                      enable_baostock: bool = True,
                      enable_tushare: bool = True,
                      enable_yahoo: bool = True,
                      enable_stooq: bool = True,
                      enable_binance: bool = True,
                      enable_okx: bool = True) -> DataSourceManager:
    """
    初始化数据源管理器

    Args:
        cache_dir: 缓存目录
        enable_eastmoney: 是否启用东方财富 Push2 直连
        enable_source_market_cache: 是否启用源项目市场复盘缓存
        enable_tdx: 是否启用本地通达信日线文件
        enable_tdx_network: 是否启用已配置的 TDX Go 后端 HTTP 数据源
        enable_tickflow: 是否启用可选 TickFlow 网络数据源（依赖存在时注册）
        enable_akshare: 是否启用 AkShare
        enable_baostock: 是否启用 BaoStock
        enable_tushare: 是否启用 Tushare Pro（仅 TUSHARE_TOKEN 配置后注册）
        enable_yahoo: 是否启用 Yahoo Finance
        enable_binance: 是否启用 Binance (加密货币)
        enable_okx: 是否启用 OKX (加密货币，中国可用)

    Returns:
        数据源管理器实例
    """
    manager = get_manager(cache_dir)

    # Register data sources by priority
    # Lower priority number = higher priority

    if enable_eastmoney:
        try:
            eastmoney_source = EastMoneySource(priority=1)
            manager.register(eastmoney_source)
        except Exception as e:
            logger.debug(f"EastMoney 注册失败: {e}")

    if enable_source_market_cache:
        try:
            source_market_cache = SourceProjectMarketCacheSource(priority=20)
            if source_market_cache.is_available():
                manager.register(source_market_cache)
        except Exception as e:
            logger.debug(f"Source market cache 注册失败: {e}")

    if enable_tdx:
        try:
            tdx_source = TDXLocalSource(priority=2)
            if tdx_source.is_available():
                manager.register(tdx_source)
        except Exception as e:
            logger.debug(f"TDX local 注册失败: {e}")

    if enable_tdx_network and TDXNetworkSource.configured():
        try:
            tdx_network_source = TDXNetworkSource(priority=2)
            if tdx_network_source.is_available():
                manager.register(tdx_network_source)
        except Exception as e:
            logger.debug(f"TDX network 注册失败: {e}")

    if enable_akshare:
        try:
            akshare_source = AkShareSource(priority=3)
            manager.register(akshare_source)
        except Exception as e:
            logger.debug(f"AkShare 注册失败: {e}")

    if enable_baostock:
        try:
            baostock_source = BaoStockSource(priority=4)
            manager.register(baostock_source)
        except Exception as e:
            logger.debug(f"BaoStock 注册失败: {e}")

    if enable_tushare and TushareSource.configured():
        try:
            tushare_source = TushareSource(priority=5)
            manager.register(tushare_source)
        except Exception as e:
            logger.debug(f"Tushare 注册失败: {e}")

    if enable_tickflow and TickFlowSource.configured():
        try:
            tickflow_source = TickFlowSource(priority=6)
            if tickflow_source.is_available():
                manager.register(tickflow_source)
        except Exception as e:
            logger.debug(f"TickFlow 注册失败: {e}")

    if enable_yahoo:
        try:
            yahoo_source = YahooFinanceSource(priority=6)
            manager.register(yahoo_source)
        except Exception as e:
            logger.debug(f"Yahoo Finance 注册失败: {e}")

    if enable_stooq:
        try:
            stooq_source = StooqSource(priority=7)
            manager.register(stooq_source)
        except Exception as e:
            logger.debug(f"Stooq 注册失败: {e}")

    if enable_binance:
        try:
            binance_source = BinanceSource(priority=4)
            manager.register(binance_source)
        except Exception as e:
            logger.debug(f"Binance 注册失败: {e}")

    if enable_okx:
        try:
            okx_source = OKXSource(priority=5)
            manager.register(okx_source)
        except Exception as e:
            logger.debug(f"OKX 注册失败: {e}")

    logger.debug(f"已注册 {len(manager.data_sources)} 个数据源")
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

    # Default dates
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
    """Reset all data source status"""
    manager = get_manager()
    manager.reset_all()
