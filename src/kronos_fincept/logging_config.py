"""Unified logging setup for KronosFinceptLab.

Enhanced with:
- Structured JSON / text dual-format logging
- Automatic secret redaction
- Request ID / Test Run ID context propagation
- Performance tracing decorator (@log_perf)
- Async batch log queue for high-throughput scenarios
- Runtime log level switching
- Metrics aggregation (counters, timers, gauges)
- System resource context injection
"""

from __future__ import annotations

import contextvars
import functools
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Callable, TextIO

from kronos_fincept.config import settings


# ---------------------------------------------------------------------------
# Context variables for distributed tracing
# ---------------------------------------------------------------------------
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_test_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("test_run_id", default=None)
_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)

_CONFIGURED = False
_LOG_LEVEL_OVERRIDES: dict[str, int] = {}
_LOG_LEVEL_LOCK = threading.RLock()

# ---------------------------------------------------------------------------
# Field sets for log formatting
# ---------------------------------------------------------------------------
_STANDARD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "message",
    "asctime", "taskName",
}
_RESERVED_OUTPUT_FIELDS = {
    "timestamp", "level", "logger", "event", "request_id", "test_run_id",
    "symbol", "market", "duration_ms", "error_type", "message", "exception",
    "user_id", "session_id", "trace_id", "span_id", "parent_span_id",
    "func", "func_module", "call_count", "avg_duration_ms", "p95_duration_ms",
    "memory_mb", "cpu_percent",
}

# ---------------------------------------------------------------------------
# Secret redaction patterns
# ---------------------------------------------------------------------------
_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|secret[_-]?key|access[_-]?token|token|cookie|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(LLM_API_KEY\s*=\s*)[^\s,;]+"),
    re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)(webhook[_-]?url\s*[:=]\s*)https?://[^\s,;]+"),
    re.compile(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
]


# =============================================================================
# Context variable helpers
# =============================================================================

def set_request_id(request_id: str | None) -> contextvars.Token:
    """Set the current request id for downstream log records."""
    return _request_id.set(request_id)


def reset_request_id(token: contextvars.Token) -> None:
    """Reset the current request id context variable."""
    _request_id.reset(token)


def get_request_id() -> str | None:
    """Return the current request id, if any."""
    return _request_id.get()


def set_test_run_id(test_run_id: str | None) -> contextvars.Token:
    """Set the current full-test-run id for downstream log records."""
    return _test_run_id.set(test_run_id)


def reset_test_run_id(token: contextvars.Token) -> None:
    """Reset the current full-test-run id context variable."""
    _test_run_id.reset(token)


def get_test_run_id() -> str | None:
    """Return the current full-test-run id, if any."""
    return _test_run_id.get()


def set_user_id(user_id: str | None) -> contextvars.Token:
    """Set the current user id for downstream log records."""
    return _user_id.set(user_id)


def reset_user_id(token: contextvars.Token) -> None:
    """Reset the current user id context variable."""
    _user_id.reset(token)


def get_user_id() -> str | None:
    """Return the current user id, if any."""
    return _user_id.get()


def set_session_id(session_id: str | None) -> contextvars.Token:
    """Set the current session id for downstream log records."""
    return _session_id.set(session_id)


def reset_session_id(token: contextvars.Token) -> None:
    """Reset the current session id context variable."""
    _session_id.reset(token)


def get_session_id() -> str | None:
    """Return the current session id, if any."""
    return _session_id.get()


# =============================================================================
# Secret redaction
# =============================================================================

def redact(value: Any) -> Any:
    """Redact secrets while preserving the original shape where possible."""
    if isinstance(value, str):
        redacted = value
        for pattern in _SENSITIVE_PATTERNS:
            redacted = pattern.sub(lambda match: _redact_match(match), redacted)
        return redacted
    if isinstance(value, dict):
        return {
            str(k): "***REDACTED***" if _is_sensitive_key(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def _redact_match(match: re.Match[str]) -> str:
    if "(sk-" in match.re.pattern:
        return "***REDACTED***"
    if match.lastindex:
        prefix = match.group(1)
        if match.re.pattern.startswith("(?i)(authorization"):
            bearer = match.group(2) or ""
            return f"{prefix}{bearer}***REDACTED***"
        return f"{prefix}***REDACTED***"
    return "***REDACTED***"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        token in lowered
        for token in ("key", "token", "secret", "authorization", "cookie", "password", "webhook")
    )


# =============================================================================
# System resource context
# =============================================================================

def _get_system_context() -> dict[str, Any]:
    """Capture lightweight system resource snapshot."""
    ctx: dict[str, Any] = {}
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        ctx["memory_mb"] = round(mem.rss / (1024 * 1024), 2)
        ctx["memory_percent"] = round(proc.memory_percent(), 2)
        ctx["cpu_percent"] = round(proc.cpu_percent(interval=None), 2)
        ctx["thread_count"] = proc.num_threads()
        ctx["open_files"] = len(proc.open_files())
    except Exception:
        pass
    return ctx


# =============================================================================
# Metrics aggregation
# =============================================================================

@dataclass
class _MetricSnapshot:
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    errors: int = 0
    _values: list[float] = field(default_factory=list, repr=False)

    def record(self, duration_ms: float, error: bool = False) -> None:
        self.count += 1
        self.total_ms += duration_ms
        self.min_ms = min(self.min_ms, duration_ms)
        self.max_ms = max(self.max_ms, duration_ms)
        if error:
            self.errors += 1
        self._values.append(duration_ms)
        # Keep last 1000 values for p95 calculation
        if len(self._values) > 1000:
            self._values = self._values[-1000:]

    @property
    def avg_ms(self) -> float:
        return round(self.total_ms / max(self.count, 1), 2)

    @property
    def p95_ms(self) -> float:
        if not self._values:
            return 0.0
        sorted_vals = sorted(self._values)
        idx = int(len(sorted_vals) * 0.95)
        return round(sorted_vals[min(idx, len(sorted_vals) - 1)], 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "avg_ms": self.avg_ms,
            "p95_ms": self.p95_ms,
            "min_ms": round(self.min_ms, 2) if self.min_ms != float("inf") else 0.0,
            "max_ms": round(self.max_ms, 2),
            "errors": self.errors,
            "error_rate": round(self.errors / max(self.count, 1), 4),
        }


_METRICS: dict[str, _MetricSnapshot] = defaultdict(_MetricSnapshot)
_METRICS_LOCK = threading.RLock()


def record_metric(name: str, duration_ms: float, error: bool = False) -> None:
    """Record a performance metric for aggregation."""
    with _METRICS_LOCK:
        _METRICS[name].record(duration_ms, error)


def get_metrics(name: str | None = None) -> dict[str, Any]:
    """Get aggregated metrics. If name is None, return all."""
    with _METRICS_LOCK:
        if name:
            snap = _METRICS.get(name)
            return {name: snap.to_dict()} if snap else {}
        return {k: v.to_dict() for k, v in _METRICS.items()}


def reset_metrics(name: str | None = None) -> None:
    """Reset metrics. If name is None, reset all."""
    with _METRICS_LOCK:
        if name:
            _METRICS.pop(name, None)
        else:
            _METRICS.clear()


# =============================================================================
# Async batch log queue
# =============================================================================

class _AsyncLogQueue:
    """Background thread that batches log writes for high-throughput scenarios."""

    def __init__(self, max_size: int = 10000, flush_interval_ms: float = 100.0) -> None:
        self._queue: Queue[logging.LogRecord] = Queue(maxsize=max_size)
        self._flush_interval_ms = flush_interval_ms
        self._handlers: list[logging.Handler] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._dropped = 0

    def add_handler(self, handler: logging.Handler) -> None:
        self._handlers.append(handler)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="async-log-queue", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
        self._flush()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(record)
        except Exception:
            self._dropped += 1

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._flush_batch()
            self._stop_event.wait(self._flush_interval_ms / 1000.0)
        self._flush_batch()

    def _flush_batch(self, max_batch: int = 100) -> None:
        batch: list[logging.LogRecord] = []
        for _ in range(max_batch):
            try:
                batch.append(self._queue.get_nowait())
            except Empty:
                break
        if not batch:
            return
        for handler in self._handlers:
            for record in batch:
                try:
                    handler.handle(record)
                except Exception:
                    pass

    def _flush(self) -> None:
        while not self._queue.empty():
            self._flush_batch()

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def pending(self) -> int:
        return self._queue.qsize()


_ASYNC_QUEUE: _AsyncLogQueue | None = None


def get_async_queue() -> _AsyncLogQueue | None:
    """Return the global async log queue if initialized."""
    return _ASYNC_QUEUE


# =============================================================================
# Log formatters
# =============================================================================

class JsonLogFormatter(logging.Formatter):
    """JSON Lines formatter with stable project fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _iso_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", None) or record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_request_id(),
            "test_run_id": getattr(record, "test_run_id", None) or get_test_run_id(),
            "user_id": getattr(record, "user_id", None) or get_user_id(),
            "session_id": getattr(record, "session_id", None) or get_session_id(),
            "symbol": getattr(record, "symbol", None),
            "market": getattr(record, "market", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "error_type": getattr(record, "error_type", None),
            "message": redact(record.getMessage()),
        }
        # Inject system context for ERROR+ levels
        if record.levelno >= logging.ERROR:
            payload.update(_get_system_context())
        for key, value in record.__dict__.items():
            if key in _STANDARD_FIELDS or key in _RESERVED_OUTPUT_FIELDS:
                continue
            payload[key] = redact(value)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
            if payload["error_type"] is None and record.exc_info[0] is not None:
                payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextLogFormatter(logging.Formatter):
    """Human-readable formatter that still carries key fields."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = _iso_timestamp(record.created)
        event = getattr(record, "event", None) or record.getMessage()
        request_id = getattr(record, "request_id", None) or get_request_id() or "-"
        test_run_id = getattr(record, "test_run_id", None) or get_test_run_id()
        user_id = getattr(record, "user_id", None) or get_user_id()
        session_id = getattr(record, "session_id", None) or get_session_id()
        symbol = getattr(record, "symbol", None)
        market = getattr(record, "market", None)
        duration_ms = getattr(record, "duration_ms", None)
        parts = [
            timestamp,
            record.levelname,
            record.name,
            f"event={redact(event)}",
            f"request_id={request_id}",
        ]
        if user_id:
            parts.append(f"user_id={user_id}")
        if session_id:
            parts.append(f"session_id={session_id}")
        if symbol is not None:
            parts.append(f"symbol={redact(symbol)}")
        if market is not None:
            parts.append(f"market={redact(market)}")
        if duration_ms is not None:
            parts.append(f"duration_ms={duration_ms}")
        if test_run_id:
            parts.append(f"test_run_id={redact(test_run_id)}")
        # Inject memory info for ERROR+ levels
        if record.levelno >= logging.ERROR:
            sys_ctx = _get_system_context()
            if "memory_mb" in sys_ctx:
                parts.append(f"mem={sys_ctx['memory_mb']}MB")
        message = redact(record.getMessage())
        if message and message != event:
            parts.append(f"message={message}")
        output = " ".join(str(item) for item in parts)
        if record.exc_info:
            output += "\n" + redact(self.formatException(record.exc_info))
        return output


# =============================================================================
# Core configuration
# =============================================================================

def configure_logging(
    *,
    level: str | None = None,
    log_format: str | None = None,
    log_dir: str | os.PathLike[str] | None = None,
    stream: TextIO | None = None,
    enable_file: bool | None = None,
    enable_async: bool = False,
    force: bool = False,
) -> None:
    """Configure root logging once for API, CLI, jobs, and tests.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: "json" or "text"
        log_dir: Directory for log files
        stream: Stream for console output (default: sys.stderr)
        enable_file: Whether to write to rotating log files
        enable_async: Whether to use async batch queue for file writes
        force: Force reconfiguration even if already configured
    """
    global _CONFIGURED, _ASYNC_QUEUE
    if _CONFIGURED and not force:
        return

    level_name = (level or settings.logging.level or "INFO").upper()
    numeric_level = getattr(logging, level_name, logging.INFO)
    format_name = (log_format or settings.logging.format or "text").lower()
    formatter: logging.Formatter
    formatter = JsonLogFormatter() if format_name == "json" else TextLogFormatter()

    root = logging.getLogger()
    if force:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        if _ASYNC_QUEUE:
            _ASYNC_QUEUE.stop()
            _ASYNC_QUEUE = None

    root.setLevel(numeric_level)

    # Console handler
    stream_handler = logging.StreamHandler(stream or sys.stderr)
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # File handler
    file_logging_enabled = settings.logging.enable_file if enable_file is None else enable_file
    if file_logging_enabled:
        directory = Path(log_dir or settings.logging.directory)
        directory.mkdir(parents=True, exist_ok=True)
        cleanup_old_logs(directory, settings.logging.retention_days)
        log_file = directory / f"kronos-{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max(1024, int(settings.logging.max_bytes)),
            backupCount=max(1, int(settings.logging.retention_days)),
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)

        if enable_async:
            _ASYNC_QUEUE = _AsyncLogQueue()
            _ASYNC_QUEUE.add_handler(file_handler)
            _ASYNC_QUEUE.start()
            # Replace direct file handler with async wrapper
            root.removeHandler(stream_handler)
            root.addHandler(stream_handler)  # Keep console direct
            # Add a proxy handler that routes to async queue
            async_handler = _AsyncHandler(_ASYNC_QUEUE)
            async_handler.setLevel(numeric_level)
            async_handler.setFormatter(formatter)
            root.addHandler(async_handler)
        else:
            root.addHandler(file_handler)

    # Quiet down noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _CONFIGURED = True


class _AsyncHandler(logging.Handler):
    """Handler that routes records to the async queue."""

    def __init__(self, queue: _AsyncLogQueue) -> None:
        super().__init__()
        self._queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        self._queue.emit(record)


# =============================================================================
# Logger factory
# =============================================================================

def get_logger(name: str) -> logging.Logger:
    """Return a project logger."""
    return logging.getLogger(name)


# =============================================================================
# Structured event logging
# =============================================================================

def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str | None = None,
    **fields: Any,
) -> None:
    """Emit one structured event without leaking secrets."""
    exc_info = fields.pop("exc_info", None)
    extra: dict[str, Any] = {"event": event}
    if get_request_id() and "request_id" not in fields:
        extra["request_id"] = get_request_id()
    if get_test_run_id() and "test_run_id" not in fields:
        extra["test_run_id"] = get_test_run_id()
    if get_user_id() and "user_id" not in fields:
        extra["user_id"] = get_user_id()
    if get_session_id() and "session_id" not in fields:
        extra["session_id"] = get_session_id()
    for key, value in fields.items():
        if key in _STANDARD_FIELDS:
            key = f"field_{key}"
        extra[key] = redact(value)
    logger.log(level, message or event, extra=extra, exc_info=exc_info)


# =============================================================================
# Performance tracing decorator
# =============================================================================

def log_perf(
    event: str | None = None,
    level: int = logging.DEBUG,
    log_args: bool = False,
    log_result: bool = False,
    track_metric: bool = True,
    logger_name: str | None = None,
) -> Callable:
    """Decorator that logs function entry, exit, and execution time.

    Args:
        event: Event name (default: function qualified name)
        level: Log level for the perf record
        log_args: Whether to log function arguments (redacted)
        log_result: Whether to log return value (redacted)
        track_metric: Whether to record in metrics aggregation
        logger_name: Logger name (default: function module)

    Example:
        @log_perf(event="forecast.run", level=logging.INFO)
        def run_forecast(symbol: str, days: int) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        nonlocal event, logger_name
        _event = event or f"{func.__module__}.{func.__qualname__}"
        _logger_name = logger_name or func.__module__
        _logger = logging.getLogger(_logger_name)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            error = False
            try:
                if log_args:
                    log_event(
                        _logger, logging.DEBUG, f"{_event}.start",
                        args=redact(args) if args else None,
                        kwargs=redact(kwargs) if kwargs else None,
                    )
                result = func(*args, **kwargs)
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                extra_fields: dict[str, Any] = {"duration_ms": duration_ms}
                if log_result:
                    extra_fields["result"] = redact(result)
                log_event(_logger, level, _event, **extra_fields)
                if track_metric:
                    record_metric(_event, duration_ms, error=False)
                return result
            except Exception as exc:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                error = True
                log_event(
                    _logger, logging.ERROR, f"{_event}.error",
                    duration_ms=duration_ms,
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                if track_metric:
                    record_metric(_event, duration_ms, error=True)
                raise

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            error = False
            try:
                if log_args:
                    log_event(
                        _logger, logging.DEBUG, f"{_event}.start",
                        args=redact(args) if args else None,
                        kwargs=redact(kwargs) if kwargs else None,
                    )
                result = await func(*args, **kwargs)
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                extra_fields: dict[str, Any] = {"duration_ms": duration_ms}
                if log_result:
                    extra_fields["result"] = redact(result)
                log_event(_logger, level, _event, **extra_fields)
                if track_metric:
                    record_metric(_event, duration_ms, error=False)
                return result
            except Exception as exc:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                error = True
                log_event(
                    _logger, logging.ERROR, f"{_event}.error",
                    duration_ms=duration_ms,
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                if track_metric:
                    record_metric(_event, duration_ms, error=True)
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper
    return decorator


# Need to import asyncio here for the decorator check
import asyncio  # noqa: E402


# =============================================================================
# Log level management
# =============================================================================

def set_log_level(level: str | int, logger_name: str | None = None) -> None:
    """Set log level at runtime for a specific logger or root.

    Args:
        level: Level name (DEBUG, INFO, etc.) or numeric level
        logger_name: Logger name, or None for root logger
    """
    if isinstance(level, str):
        numeric = getattr(logging, level.upper(), None)
        if numeric is None:
            raise ValueError(f"Unknown log level: {level}")
        level = numeric
    target = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    target.setLevel(level)
    for handler in target.handlers:
        handler.setLevel(level)
    with _LOG_LEVEL_LOCK:
        name = logger_name or "root"
        _LOG_LEVEL_OVERRIDES[name] = level


def get_log_level(logger_name: str | None = None) -> int:
    """Get current log level for a logger."""
    target = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    return target.level


def get_log_level_overrides() -> dict[str, int]:
    """Return all runtime log level overrides."""
    with _LOG_LEVEL_LOCK:
        return dict(_LOG_LEVEL_OVERRIDES)


# =============================================================================
# Log file utilities
# =============================================================================

def cleanup_old_logs(log_dir: str | os.PathLike[str], retention_days: int) -> None:
    """Remove old log files based on modification time."""
    directory = Path(log_dir)
    if not directory.exists():
        return
    cutoff = datetime.now().timestamp() - max(1, retention_days) * 86400
    for path in directory.glob("kronos-*.log*"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def query_logs(
    log_dir: str | os.PathLike[str] | None = None,
    *,
    level: str | None = None,
    event_pattern: str | None = None,
    request_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query log files with simple filtering.

    Args:
        log_dir: Directory to search (default: settings.logging.directory)
        level: Filter by level name (e.g., "ERROR")
        event_pattern: Regex pattern to match event field
        request_id: Exact request_id match
        start_time: Filter records after this time
        end_time: Filter records before this time
        limit: Maximum records to return

    Returns:
        List of parsed log records (newest first)
    """
    directory = Path(log_dir or settings.logging.directory)
    if not directory.exists():
        return []

    import re as re_module

    event_re = re_module.compile(event_pattern) if event_pattern else None
    results: list[dict[str, Any]] = []

    # Get all log files sorted by modification time (newest first)
    log_files = sorted(directory.glob("kronos-*.log*"), key=lambda p: p.stat().st_mtime, reverse=True)

    for log_file in log_files:
        if len(results) >= limit:
            break
        try:
            with open(log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        # Skip non-JSON lines (text format not queryable)
                        continue

                    # Apply filters
                    if level and record.get("level") != level:
                        continue
                    if request_id and record.get("request_id") != request_id:
                        continue
                    if event_re and not event_re.search(record.get("event", "")):
                        continue
                    if start_time:
                        ts = record.get("timestamp", "")
                        if ts and ts < start_time.isoformat():
                            continue
                    if end_time:
                        ts = record.get("timestamp", "")
                        if ts and ts > end_time.isoformat():
                            continue

                    results.append(record)
                    if len(results) >= limit:
                        break
        except OSError:
            continue

    return results


# =============================================================================
# Helpers
# =============================================================================

def _iso_timestamp(created: float) -> str:
    return datetime.fromtimestamp(created, tz=timezone.utc).isoformat(timespec="milliseconds")
