"""
DataSourceManager - 统一数据源管理器
支持多数据源自动降级、重试、健康检查和缓存
"""

import time
import json
import os
import logging
from collections import OrderedDict
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)


class DataSourceStatus(Enum):
    """数据源状态"""
    HEALTHY = "healthy"           # 健康
    DEGRADED = "degraded"         # 降级（部分失败）
    UNHEALTHY = "unhealthy"       # 不健康（连续失败）
    DISABLED = "disabled"         # 禁用（手动或熔断）


@dataclass
class DataSourceConfig:
    """数据源配置"""
    name: str                          # 数据源名称
    priority: int                      # 优先级（数字越小优先级越高）
    max_retries: int = 3               # 最大重试次数
    retry_delay: float = 1.0           # 初始重试延迟（秒）
    timeout: float = 30.0              # 超时时间（秒）
    circuit_break_threshold: int = 5   # 熔断阈值（连续失败次数）
    circuit_break_duration: int = 300  # 熔断持续时间（秒）
    health_check_interval: int = 60    # 健康检查间隔（秒）


class DataSource:
    """数据源基类"""

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.status = DataSourceStatus.HEALTHY
        self.consecutive_failures = 0
        self.last_success_time: Optional[datetime] = None
        self.last_failure_time: Optional[datetime] = None
        self.circuit_break_until: Optional[datetime] = None
        self.last_health_check: Optional[datetime] = None

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        # 检查是否被手动禁用
        if self.status == DataSourceStatus.DISABLED:
            return False

        # 检查是否在熔断期
        if self.circuit_break_until and datetime.now() < self.circuit_break_until:
            return False

        # 检查是否需要健康检查
        if self.last_health_check:
            elapsed = (datetime.now() - self.last_health_check).total_seconds()
            if elapsed > self.config.health_check_interval:
                # 需要健康检查，但仍然允许使用
                pass

        return True

    def record_success(self):
        """记录成功"""
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        self.status = DataSourceStatus.HEALTHY
        self.circuit_break_until = None

    def record_failure(self):
        """记录失败"""
        self.consecutive_failures += 1
        self.last_failure_time = datetime.now()

        # 检查是否需要熔断
        if self.consecutive_failures >= self.config.circuit_break_threshold:
            self.status = DataSourceStatus.UNHEALTHY
            self.circuit_break_until = datetime.now() + timedelta(
                seconds=self.config.circuit_break_duration
            )
            logger.debug(f" {self.config.name} 熔断，"
                  f"将在 {self.config.circuit_break_duration} 秒后恢复")

    def get_retry_delay(self, attempt: int) -> float:
        """获取重试延迟（指数退避）"""
        return self.config.retry_delay * (2 ** attempt)

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        获取数据（子类实现）

        Returns:
            {
                "success": bool,
                "data": Any,
                "error": str (if failed),
                "source": str,
                "timestamp": int
            }
        """
        raise NotImplementedError("子类必须实现 fetch 方法")


class DataSourceManager:
    """数据源管理器"""

    def __init__(self, cache_dir: str = ".cache"):
        self.data_sources: Dict[str, DataSource] = {}
        self.cache_dir = cache_dir
        self.memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.memory_cache_ttl = 300  # 5分钟
        try:
            self.memory_cache_max_size = max(
                1,
                int(os.environ.get("KRONOS_MEMORY_CACHE_MAX_SIZE", "256"))
            )
        except ValueError:
            self.memory_cache_max_size = 256

        # 创建缓存目录
        os.makedirs(cache_dir, exist_ok=True)

    def register(self, source: DataSource):
        """注册数据源"""
        self.data_sources[source.config.name] = source
        logger.debug(f" 注册数据源: {source.config.name} "
              f"(优先级: {source.config.priority})")

    def unregister(self, name: str):
        """注销数据源"""
        if name in self.data_sources:
            del self.data_sources[name]
            logger.debug(f" 注销数据源: {name}")

    def get_sorted_sources(self) -> List[DataSource]:
        """获取按优先级排序的数据源列表"""
        return sorted(
            self.data_sources.values(),
            key=lambda s: s.config.priority
        )

    def _get_cache_key(self, endpoint: str, **kwargs) -> str:
        """生成缓存键"""
        key_data = f"{endpoint}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _set_memory_cache(self, cache_key: str, cache_entry: Dict[str, Any]) -> None:
        """写入内存缓存并按 LRU 淘汰旧条目。"""
        self.memory_cache[cache_key] = cache_entry
        self.memory_cache.move_to_end(cache_key)

        while len(self.memory_cache) > self.memory_cache_max_size:
            evicted_key, _ = self.memory_cache.popitem(last=False)
            logger.debug(f" 内存缓存 LRU 淘汰: {evicted_key}")

    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """从缓存获取数据"""
        # 先检查内存缓存
        if cache_key in self.memory_cache:
            cache_entry = self.memory_cache[cache_key]
            if datetime.now().timestamp() < cache_entry["expire_at"]:
                self.memory_cache.move_to_end(cache_key)
                return cache_entry["data"]
            else:
                del self.memory_cache[cache_key]

        # 再检查文件缓存
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_entry = json.load(f)
                if datetime.now().timestamp() < cache_entry["expire_at"]:
                    # 加载到内存缓存
                    self._set_memory_cache(cache_key, cache_entry)
                    return cache_entry["data"]
                else:
                    os.remove(cache_file)
            except Exception:
                pass

        return None

    def _save_to_cache(self, cache_key: str, data: Dict[str, Any],
                       ttl: int = 86400):
        """保存数据到缓存"""
        cache_entry = {
            "data": data,
            "expire_at": datetime.now().timestamp() + ttl,
            "created_at": datetime.now().isoformat()
        }

        # 保存到内存缓存
        self._set_memory_cache(cache_key, cache_entry)

        # 保存到文件缓存
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_entry, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f" 缓存写入失败: {e}")

    def fetch(self, endpoint: str, use_cache: bool = True,
              cache_ttl: int = 86400, **kwargs) -> Dict[str, Any]:
        """
        获取数据（带自动降级）

        Args:
            endpoint: 数据端点
            use_cache: 是否使用缓存
            cache_ttl: 缓存 TTL（秒）
            **kwargs: 传递给数据源的参数

        Returns:
            {
                "success": bool,
                "data": Any,
                "source": str,
                "timestamp": int,
                "from_cache": bool
            }
        """
        # 检查缓存
        if use_cache:
            cache_key = self._get_cache_key(endpoint, **kwargs)
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                cached_data["from_cache"] = True
                return cached_data

        # 按优先级尝试数据源
        last_error = None
        for source in self.get_sorted_sources():
            if not source.is_available():
                logger.debug(f" 跳过不可用的数据源: {source.config.name}")
                continue

            logger.debug(f" 尝试数据源: {source.config.name}")

            # 带重试的请求
            for attempt in range(source.config.max_retries):
                try:
                    result = source.fetch(endpoint, **kwargs)

                    if result.get("success"):
                        # 成功
                        source.record_success()
                        result["from_cache"] = False

                        # 保存到缓存
                        if use_cache:
                            self._save_to_cache(cache_key, result, cache_ttl)

                        return result
                    else:
                        # 失败
                        last_error = result.get("error", "Unknown error")
                        source.record_failure()

                        # 等待重试
                        if attempt < source.config.max_retries - 1:
                            delay = source.get_retry_delay(attempt)
                            logger.debug(f" 重试 {attempt + 1}/"
                                  f"{source.config.max_retries}，等待 {delay} 秒...")
                            time.sleep(delay)

                except Exception as e:
                    last_error = str(e)
                    source.record_failure()

                    # 等待重试
                    if attempt < source.config.max_retries - 1:
                        delay = source.get_retry_delay(attempt)
                        logger.debug(f" 重试 {attempt + 1}/"
                              f"{source.config.max_retries}，等待 {delay} 秒...")
                        time.sleep(delay)

            logger.debug(f" 数据源 {source.config.name} 失败，"
                  f"尝试下一个...")

        # 所有数据源都失败
        return {
            "success": False,
            "data": None,
            "error": f"所有数据源都失败，最后错误: {last_error}",
            "source": "none",
            "timestamp": int(datetime.now().timestamp()),
            "from_cache": False
        }

    def get_status(self) -> Dict[str, Any]:
        """获取所有数据源状态"""
        status = {}
        for name, source in self.data_sources.items():
            status[name] = {
                "status": source.status.value,
                "priority": source.config.priority,
                "consecutive_failures": source.consecutive_failures,
                "last_success": source.last_success_time.isoformat()
                    if source.last_success_time else None,
                "last_failure": source.last_failure_time.isoformat()
                    if source.last_failure_time else None,
                "circuit_break_until": source.circuit_break_until.isoformat()
                    if source.circuit_break_until else None,
                "is_available": source.is_available()
            }
        return status

    def reset_all(self):
        """重置所有数据源状态"""
        for source in self.data_sources.values():
            source.status = DataSourceStatus.HEALTHY
            source.consecutive_failures = 0
            source.circuit_break_until = None
        logger.debug(" 已重置所有数据源状态")


# 全局数据源管理器实例
_manager: Optional[DataSourceManager] = None


def get_manager(cache_dir: str = ".cache") -> DataSourceManager:
    """获取全局数据源管理器实例"""
    global _manager
    if _manager is None:
        _manager = DataSourceManager(cache_dir)
    return _manager
