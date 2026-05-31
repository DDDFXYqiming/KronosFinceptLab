"""
DataSourceManager - Unified Data Source Manager
Supports multi-source auto-degradation, retry, health checks, and caching
"""

import time
import json
import os
import logging
import copy
from collections import OrderedDict
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import hashlib

from kronos_fincept.logging_config import log_event

logger = logging.getLogger(__name__)


class DataSourceStatus(Enum):
    """Data source status"""
    HEALTHY = "healthy"           # Healthy
    DEGRADED = "degraded"         # Degraded (partial failure)
    UNHEALTHY = "unhealthy"       # Unhealthy (consecutive failures)
    DISABLED = "disabled"         # Disabled (manual or circuit break)


@dataclass
class DataSourceConfig:
    """Data source configuration"""
    name: str                          # Data source name
    priority: int                      # Priority (lower number = higher priority)
    max_retries: int = 3               # Maximum retry count
    retry_delay: float = 1.0           # Initial retry delay (seconds)
    timeout: float = 30.0              # Timeout (seconds)
    circuit_break_threshold: int = 5   # Circuit break threshold (consecutive failures)
    circuit_break_duration: int = 300  # Circuit break duration (seconds)
    health_check_interval: int = 60    # Health check interval (seconds)


class DataSource:
    """Base class for data sources"""

    supported_endpoints: set[str] | None = None

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.status = DataSourceStatus.HEALTHY
        self.consecutive_failures = 0
        self.last_success_time: Optional[datetime] = None
        self.last_failure_time: Optional[datetime] = None
        self.circuit_break_until: Optional[datetime] = None
        self.last_health_check: Optional[datetime] = None

    def supports_endpoint(self, endpoint: str) -> bool:
        """Return whether this source can serve the requested endpoint."""
        return self.supported_endpoints is None or endpoint in self.supported_endpoints

    def is_available(self) -> bool:
        """Check whether the data source is available"""
        # Check if manually disabled
        if self.status == DataSourceStatus.DISABLED:
            return False

        # Check if in circuit break period
        if self.circuit_break_until and datetime.now() < self.circuit_break_until:
            return False

        # Check if health check is needed
        if self.last_health_check:
            elapsed = (datetime.now() - self.last_health_check).total_seconds()
            if elapsed > self.config.health_check_interval:
                # Health check needed, but still allow usage
                pass

        return True

    def record_success(self):
        """Record a successful request"""
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        self.status = DataSourceStatus.HEALTHY
        self.circuit_break_until = None

    def record_failure(self):
        """Record a failed request"""
        self.consecutive_failures += 1
        self.last_failure_time = datetime.now()

        # Check if circuit break is needed
        if self.consecutive_failures >= self.config.circuit_break_threshold:
            self.status = DataSourceStatus.UNHEALTHY
            self.circuit_break_until = datetime.now() + timedelta(
                seconds=self.config.circuit_break_duration
            )
            logger.debug(f" {self.config.name} 熔断，"
                  f"将在 {self.config.circuit_break_duration} 秒后恢复")

    def get_retry_delay(self, attempt: int) -> float:
        """Get retry delay (exponential backoff)"""
        return self.config.retry_delay * (2 ** attempt)

    def fetch(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch data (subclass implementation)

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
    """Data source manager"""

    def __init__(self, cache_dir: str = ".cache"):
        self.data_sources: Dict[str, DataSource] = {}
        self.cache_dir = cache_dir
        self.memory_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.memory_cache_ttl = 300  # 5 minutes
        try:
            self.memory_cache_max_size = max(
                1,
                int(os.environ.get("KRONOS_MEMORY_CACHE_MAX_SIZE", "256"))
            )
        except ValueError:
            self.memory_cache_max_size = 256

        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)

    def register(self, source: DataSource):
        """Register a data source"""
        self.data_sources[source.config.name] = source
        logger.debug(f" 注册数据源: {source.config.name} "
              f"(优先级: {source.config.priority})")

    def unregister(self, name: str):
        """Unregister a data source"""
        if name in self.data_sources:
            del self.data_sources[name]
            logger.debug(f" 注销数据源: {name}")

    def get_sorted_sources(self) -> List[DataSource]:
        """Get data sources sorted by priority"""
        return sorted(
            self.data_sources.values(),
            key=lambda s: s.config.priority
        )

    def _get_cache_key(self, endpoint: str, **kwargs) -> str:
        """Generate a cache key"""
        key_data = f"{endpoint}:{json.dumps(kwargs, sort_keys=True, default=str)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _set_memory_cache(self, cache_key: str, cache_entry: Dict[str, Any]) -> None:
        """Write to memory cache and evict old entries via LRU."""
        self.memory_cache[cache_key] = cache_entry
        self.memory_cache.move_to_end(cache_key)

        while len(self.memory_cache) > self.memory_cache_max_size:
            evicted_key, _ = self.memory_cache.popitem(last=False)
            logger.debug(f" 内存缓存 LRU 淘汰: {evicted_key}")

    def _cache_file_path(self, cache_key: str) -> str:
        return os.path.join(self.cache_dir, f"{cache_key}.json")

    @staticmethod
    def _cache_entry_is_fresh(cache_entry: Dict[str, Any]) -> bool:
        try:
            return datetime.now().timestamp() < float(cache_entry["expire_at"])
        except (KeyError, TypeError, ValueError):
            return False

    @staticmethod
    def _cache_entry_age_seconds(cache_entry: Dict[str, Any]) -> int | None:
        created_at = cache_entry.get("created_at")
        if not created_at:
            return None
        try:
            created = datetime.fromisoformat(str(created_at))
        except ValueError:
            return None
        return max(0, int((datetime.now() - created).total_seconds()))

    def _read_file_cache_entry(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cache_file = self._cache_file_path(cache_key)
        if not os.path.exists(cache_file):
            return None
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                entry = json.load(f)
            if isinstance(entry, dict) and "data" in entry:
                return entry
        except Exception as exc:
            logger.debug(f" 缓存读取失败: {exc}")
            try:
                os.remove(cache_file)
            except OSError:
                pass
        return None

    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get fresh data from cache."""
        if cache_key in self.memory_cache:
            cache_entry = self.memory_cache[cache_key]
            if self._cache_entry_is_fresh(cache_entry):
                self.memory_cache.move_to_end(cache_key)
                log_event(
                    logger,
                    logging.DEBUG,
                    "data_source.cache_hit",
                    "Memory cache hit",
                    cache_key=cache_key,
                )
                return copy.deepcopy(cache_entry["data"])
            else:
                del self.memory_cache[cache_key]

        cache_entry = self._read_file_cache_entry(cache_key)
        if cache_entry and self._cache_entry_is_fresh(cache_entry):
            self._set_memory_cache(cache_key, cache_entry)
            log_event(
                logger,
                logging.DEBUG,
                "data_source.cache_hit",
                "File cache hit",
                cache_key=cache_key,
            )
            return copy.deepcopy(cache_entry["data"])

        return None

    def _get_stale_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Return expired cache data as a last-resort fallback."""
        try:
            max_age_seconds = max(0, int(os.environ.get("KRONOS_STALE_CACHE_MAX_AGE_SECONDS", "604800")))
        except ValueError:
            max_age_seconds = 604800
        if max_age_seconds <= 0:
            return None

        cache_entry = self.memory_cache.get(cache_key) or self._read_file_cache_entry(cache_key)
        if not cache_entry or self._cache_entry_is_fresh(cache_entry):
            return None

        age_seconds = self._cache_entry_age_seconds(cache_entry)
        if age_seconds is not None and age_seconds > max_age_seconds:
            return None

        data = copy.deepcopy(cache_entry.get("data"))
        if not isinstance(data, dict):
            return None
        data["from_cache"] = True
        data["from_stale_cache"] = True
        data["cache_age_seconds"] = age_seconds
        data["cache_expired_at"] = cache_entry.get("expire_at")
        return data

    def _save_to_cache(self, cache_key: str, data: Dict[str, Any],
                       ttl: int = 86400):
        """Save data to cache"""
        cache_entry = {
            "data": data,
            "expire_at": datetime.now().timestamp() + ttl,
            "created_at": datetime.now().isoformat()
        }

        # Save to memory cache
        self._set_memory_cache(cache_key, cache_entry)

        # Save to file cache
        cache_file = self._cache_file_path(cache_key)
        tmp_file = f"{cache_file}.tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(cache_entry, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, cache_file)
        except Exception as e:
            logger.debug(f" 缓存写入失败: {e}")
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            except OSError:
                pass

    def fetch(self, endpoint: str, use_cache: bool = True,
              cache_ttl: int = 86400, **kwargs) -> Dict[str, Any]:
        """
        Fetch data (with auto-degradation)

        Args:
            endpoint: Data endpoint
            use_cache: Whether to use cache
            cache_ttl: Cache TTL (seconds)
            **kwargs: Arguments to pass to data sources

        Returns:
            {
                "success": bool,
                "data": Any,
                "source": str,
                "timestamp": int,
                "from_cache": bool
            }
        """
        # Check cache
        cache_key = ""
        if use_cache:
            cache_key = self._get_cache_key(endpoint, **kwargs)
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                cached_data["from_cache"] = True
                cached_data["from_stale_cache"] = False
                return cached_data

        # Try data sources by priority
        last_error = None
        errors_by_source: Dict[str, str] = {}
        for source in self.get_sorted_sources():
            if not source.supports_endpoint(endpoint):
                log_event(
                    logger,
                    logging.DEBUG,
                    "data_source.skip_unsupported",
                    "Skipping source that does not support endpoint",
                    source=source.config.name,
                    endpoint=endpoint,
                )
                continue

            if not source.is_available():
                log_event(
                    logger,
                    logging.DEBUG,
                    "data_source.skip_unavailable",
                    "Skipping unavailable data source",
                    source=source.config.name,
                )
                continue

            log_event(
                logger,
                logging.DEBUG,
                "data_source.try",
                "Trying data source",
                source=source.config.name,
                endpoint=endpoint,
            )

            # Request with retry
            for attempt in range(source.config.max_retries):
                try:
                    started = time.perf_counter()
                    result = source.fetch(endpoint, **kwargs)

                    if result.get("success"):
                        # Success
                        source.record_success()
                        result["from_cache"] = False

                        # Save to cache
                        if use_cache:
                            self._save_to_cache(cache_key, result, cache_ttl)

                        log_event(
                            logger,
                            logging.INFO,
                            "data_source.success",
                            "Data source returned data",
                            source=source.config.name,
                            endpoint=endpoint,
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                        return result
                    else:
                        # Failure
                        last_error = result.get("error", "Unknown error")
                        errors_by_source[source.config.name] = str(last_error)
                        source.record_failure()
                        log_event(
                            logger,
                            logging.WARNING,
                            "data_source.failure",
                            "Data source returned failure",
                            source=source.config.name,
                            endpoint=endpoint,
                            attempt=attempt + 1,
                            error=last_error,
                        )

                        # Wait for retry
                        if attempt < source.config.max_retries - 1:
                            delay = source.get_retry_delay(attempt)
                            logger.debug(f" 重试 {attempt + 1}/"
                                  f"{source.config.max_retries}，等待 {delay} 秒...")
                            time.sleep(delay)

                except Exception as e:
                    last_error = str(e)
                    errors_by_source[source.config.name] = last_error
                    source.record_failure()
                    log_event(
                        logger,
                        logging.WARNING,
                        "data_source.failure",
                        "Data source request failed",
                        source=source.config.name,
                        endpoint=endpoint,
                        attempt=attempt + 1,
                        error_type=type(e).__name__,
                        error=str(e),
                    )

                    # Wait for retry
                    if attempt < source.config.max_retries - 1:
                        delay = source.get_retry_delay(attempt)
                        logger.debug(f" 重试 {attempt + 1}/"
                              f"{source.config.max_retries}，等待 {delay} 秒...")
                        time.sleep(delay)

            logger.debug(f" 数据源 {source.config.name} 失败，"
                  f"尝试下一个...")

        # All sources supporting this endpoint failed
        if errors_by_source:
            error_detail = "; ".join(
                f"{source}={error}" for source, error in errors_by_source.items()
            )
        else:
            error_detail = f"endpoint unsupported by registered sources: {endpoint}"

        if use_cache and cache_key:
            stale_data = self._get_stale_from_cache(cache_key)
            if stale_data is not None:
                stale_data["stale_reason"] = error_detail
                log_event(
                    logger,
                    logging.WARNING,
                    "data_source.stale_cache_fallback",
                    "Returning stale cache after all data sources failed",
                    endpoint=endpoint,
                    error=error_detail,
                )
                return stale_data

        return {
            "success": False,
            "data": None,
            "error": f"所有数据源都失败: {error_detail}",
            "source": "none",
            "timestamp": int(datetime.now().timestamp()),
            "from_cache": False
        }

    def get_status(self) -> Dict[str, Any]:
        """Get status of all data sources"""
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
        """Reset all data source states"""
        for source in self.data_sources.values():
            source.status = DataSourceStatus.HEALTHY
            source.consecutive_failures = 0
            source.circuit_break_until = None
        logger.debug(" 已重置所有数据源状态")


# Global data source manager instance
_manager: Optional[DataSourceManager] = None


def get_manager(cache_dir: str = ".cache") -> DataSourceManager:
    """Get the global data source manager instance"""
    global _manager
    if _manager is None:
        _manager = DataSourceManager(cache_dir)
    return _manager
