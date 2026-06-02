"""Unified logging for KronosFinceptLab.

Design: high-entropy, minimal verbosity. Every log line carries maximum
information density. Structured JSON for machines, compact text for humans.

Features:
- Dual format: JSON (prod) / compact text (dev)
- Secret redaction (auto)
- Context propagation: request_id, test_run_id, user_id, session_id
- @log_perf decorator: function-level tracing with zero boilerplate
- Metrics aggregation: counters, timers, p95
- Async batch queue for high-throughput file writes
- Runtime log level switching
- Log query API (JSON files only)
- System resource snapshot on ERROR+
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
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, TextIO

from kronos_fincept.config import settings


# ── Context vars ────────────────────────────────────────────────────────────
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_test_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("test_run_id", default=None)
_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)

_CONFIGURED = False
_LOG_LEVEL_OVERRIDES: dict[str, int] = {}
_LOG_LEVEL_LOCK = threading.RLock()

# ── Field allowlists ────────────────────────────────────────────────────────
_STD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "message",
    "asctime", "taskName",
}
_RESERVED = {
    "timestamp", "level", "logger", "event", "request_id", "test_run_id",
    "user_id", "session_id", "symbol", "market", "duration_ms", "error_type",
    "message", "exception", "mem_mb", "cpu_pct",
}

# ── Secret patterns ─────────────────────────────────────────────────────────
_SECRET_RE = [
    re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|secret[_-]?key|access[_-]?token|token|cookie|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(LLM_API_KEY\s*=\s*)[^\s,;]+"),
    re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)(webhook[_-]?url\s*[:=]\s*)https?://[^\s,;]+"),
    re.compile(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
]


# ═════════════════════════════════════════════════════════════════════════════
# Context helpers
# ═════════════════════════════════════════════════════════════════════════════

def set_request_id(v: str | None) -> contextvars.Token:
    return _request_id.set(v)


def reset_request_id(t: contextvars.Token) -> None:
    _request_id.reset(t)


def get_request_id() -> str | None:
    return _request_id.get()


def set_test_run_id(v: str | None) -> contextvars.Token:
    return _test_run_id.set(v)


def reset_test_run_id(t: contextvars.Token) -> None:
    _test_run_id.reset(t)


def get_test_run_id() -> str | None:
    return _test_run_id.get()


def set_user_id(v: str | None) -> contextvars.Token:
    return _user_id.set(v)


def reset_user_id(t: contextvars.Token) -> None:
    _user_id.reset(t)


def get_user_id() -> str | None:
    return _user_id.get()


def set_session_id(v: str | None) -> contextvars.Token:
    return _session_id.set(v)


def reset_session_id(t: contextvars.Token) -> None:
    _session_id.reset(t)


def get_session_id() -> str | None:
    return _session_id.get()


# ═════════════════════════════════════════════════════════════════════════════
# Redaction
# ═════════════════════════════════════════════════════════════════════════════

def redact(value: Any) -> Any:
    """Redact secrets while preserving structure."""
    if isinstance(value, str):
        out = value
        for pat in _SECRET_RE:
            out = pat.sub(_redact_match, out)
        return out
    if isinstance(value, dict):
        return {
            str(k): "***" if _is_sensitive_key(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(i) for i in value]
    return value


def _redact_match(m: re.Match[str]) -> str:
    if "(sk-" in m.re.pattern:
        return "***REDACTED***"
    if m.lastindex:
        prefix = m.group(1)
        if m.re.pattern.startswith("(?i)(authorization"):
            bearer = m.group(2) or ""
            return f"{prefix}{bearer}***REDACTED***"
        return f"{prefix}***REDACTED***"
    return "***REDACTED***"


def _is_sensitive_key(k: str) -> bool:
    return any(t in k.lower() for t in ("key", "token", "secret", "authorization", "cookie", "password", "webhook"))


# ═════════════════════════════════════════════════════════════════════════════
# System context (lightweight)
# ═════════════════════════════════════════════════════════════════════════════

def _sys_ctx() -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    try:
        import psutil
        p = psutil.Process()
        m = p.memory_info()
        ctx["mem_mb"] = round(m.rss / (1024 * 1024), 1)
        ctx["mem_pct"] = round(p.memory_percent(), 1)
        ctx["cpu_pct"] = round(p.cpu_percent(interval=None), 1)
        ctx["threads"] = p.num_threads()
    except Exception:
        pass
    return ctx


# ═════════════════════════════════════════════════════════════════════════════
# Metrics aggregation
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class _MetricSnap:
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    errors: int = 0
    _vals: list[float] = field(default_factory=list, repr=False)

    def record(self, ms: float, err: bool = False) -> None:
        self.count += 1
        self.total_ms += ms
        self.min_ms = min(self.min_ms, ms)
        self.max_ms = max(self.max_ms, ms)
        if err:
            self.errors += 1
        self._vals.append(ms)
        if len(self._vals) > 1000:
            self._vals = self._vals[-1000:]

    @property
    def avg_ms(self) -> float:
        return round(self.total_ms / max(self.count, 1), 2)

    @property
    def p95_ms(self) -> float:
        if not self._vals:
            return 0.0
        s = sorted(self._vals)
        return round(s[int(len(s) * 0.95)], 2)

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


_METRICS: dict[str, _MetricSnap] = defaultdict(_MetricSnap)
_METRICS_LOCK = threading.RLock()


def record_metric(name: str, duration_ms: float, error: bool = False) -> None:
    with _METRICS_LOCK:
        _METRICS[name].record(duration_ms, error)


def get_metrics(name: str | None = None) -> dict[str, Any]:
    with _METRICS_LOCK:
        if name:
            snap = _METRICS.get(name)
            return {name: snap.to_dict()} if snap else {}
        return {k: v.to_dict() for k, v in _METRICS.items()}


def reset_metrics(name: str | None = None) -> None:
    with _METRICS_LOCK:
        if name:
            _METRICS.pop(name, None)
        else:
            _METRICS.clear()


# ═════════════════════════════════════════════════════════════════════════════
# Async log queue
# ═════════════════════════════════════════════════════════════════════════════

class _AsyncQueue:
    def __init__(self, max_size: int = 10000, flush_ms: float = 100.0) -> None:
        self._q: Queue[logging.LogRecord] = Queue(maxsize=max_size)
        self._flush_ms = flush_ms
        self._handlers: list[logging.Handler] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._dropped = 0

    def add_handler(self, h: logging.Handler) -> None:
        self._handlers.append(h)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="async-log", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
        self._flush()

    def emit(self, r: logging.LogRecord) -> None:
        try:
            self._q.put_nowait(r)
        except Exception:
            self._dropped += 1

    def _run(self) -> None:
        while not self._stop.is_set():
            self._flush_batch()
            self._stop.wait(self._flush_ms / 1000.0)
        self._flush_batch()

    def _flush_batch(self, max_batch: int = 100) -> None:
        batch: list[logging.LogRecord] = []
        for _ in range(max_batch):
            try:
                batch.append(self._q.get_nowait())
            except Empty:
                break
        if not batch:
            return
        for h in self._handlers:
            for r in batch:
                try:
                    h.handle(r)
                except Exception:
                    pass

    def _flush(self) -> None:
        while not self._q.empty():
            self._flush_batch()

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def pending(self) -> int:
        return self._q.qsize()


_ASYNC_Q: _AsyncQueue | None = None


def get_async_queue() -> _AsyncQueue | None:
    return _ASYNC_Q


# ═════════════════════════════════════════════════════════════════════════════
# Formatters
# ═════════════════════════════════════════════════════════════════════════════

class JsonFormatter(logging.Formatter):
    """JSON Lines: dense, machine-readable."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "t": _iso(record.created),
            "lv": record.levelname,
            "level": record.levelname,
            "lg": record.name,
            "logger": record.name,
            "event": getattr(record, "event", None) or record.getMessage(),
            "ev": getattr(record, "event", None) or record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_request_id(),
            "rid": getattr(record, "request_id", None) or get_request_id(),
            "test_run_id": getattr(record, "test_run_id", None) or get_test_run_id(),
            "trid": getattr(record, "test_run_id", None) or get_test_run_id(),
            "user_id": getattr(record, "user_id", None) or get_user_id(),
            "uid": getattr(record, "user_id", None) or get_user_id(),
            "session_id": getattr(record, "session_id", None) or get_session_id(),
            "sid": getattr(record, "session_id", None) or get_session_id(),
            "symbol": getattr(record, "symbol", None),
            "sym": getattr(record, "symbol", None),
            "market": getattr(record, "market", None),
            "mkt": getattr(record, "market", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "ms": getattr(record, "duration_ms", None),
            "error_type": getattr(record, "error_type", None),
            "et": getattr(record, "error_type", None),
            "message": redact(record.getMessage()),
            "msg": redact(record.getMessage()),
        }
        # Compact: drop None values
        payload = {k: v for k, v in payload.items() if v is not None}
        if record.levelno >= logging.ERROR:
            payload.update(_sys_ctx())
        for k, v in record.__dict__.items():
            if k in _STD_FIELDS or k in _RESERVED:
                continue
            payload[k] = redact(v)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
            payload["ex"] = payload["exception"]
            if "error_type" not in payload and record.exc_info[0] is not None:
                payload["error_type"] = record.exc_info[0].__name__
                payload["et"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    """Compact text: human-readable, high density."""

    def format(self, record: logging.LogRecord) -> str:
        t = _iso(record.created)
        ev = getattr(record, "event", None) or record.getMessage()
        rid = getattr(record, "request_id", None) or get_request_id() or "-"
        parts = [t, record.levelname, record.name.split(".")[-1], ev]
        # Add condensed context
        uid = getattr(record, "user_id", None) or get_user_id()
        if uid:
            parts.append(f"u={uid}")
        sym = getattr(record, "symbol", None)
        if sym:
            parts.append(f"sym={sym}")
        mkt = getattr(record, "market", None)
        if mkt:
            parts.append(f"mkt={mkt}")
        ms = getattr(record, "duration_ms", None)
        if ms is not None:
            parts.append(f"{ms}ms")
        if record.levelno >= logging.ERROR:
            ctx = _sys_ctx()
            if "mem_mb" in ctx:
                parts.append(f"mem={ctx['mem_mb']}M")
        msg = redact(record.getMessage())
        if msg and msg != ev:
            parts.append(msg)
        out = " ".join(str(p) for p in parts)
        if record.exc_info:
            out += "\n" + redact(self.formatException(record.exc_info))
        return out


# ═════════════════════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════════════════════

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
    """Configure root logging once."""
    global _CONFIGURED, _ASYNC_Q
    if _CONFIGURED and not force:
        return

    lvl = (level or settings.logging.level or "INFO").upper()
    numeric = getattr(logging, lvl, logging.INFO)
    fmt = (log_format or settings.logging.format or "text").lower()
    formatter: logging.Formatter = JsonFormatter() if fmt == "json" else TextFormatter()

    root = logging.getLogger()
    if force:
        for h in list(root.handlers):
            root.removeHandler(h)
            h.close()
        if _ASYNC_Q:
            _ASYNC_Q.stop()
            _ASYNC_Q = None

    root.setLevel(numeric)

    sh = logging.StreamHandler(stream or sys.stderr)
    sh.setLevel(numeric)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    file_on = settings.logging.enable_file if enable_file is None else enable_file
    if file_on:
        directory = Path(log_dir or settings.logging.directory)
        directory.mkdir(parents=True, exist_ok=True)
        cleanup_old_logs(directory, settings.logging.retention_days)
        lf = directory / f"kronos-{datetime.now().strftime('%Y%m%d')}.log"
        fh = RotatingFileHandler(
            lf,
            maxBytes=max(1024, int(settings.logging.max_bytes)),
            backupCount=max(1, int(settings.logging.retention_days)),
            encoding="utf-8",
        )
        fh.setLevel(numeric)
        fh.setFormatter(formatter)

        if enable_async:
            _ASYNC_Q = _AsyncQueue()
            _ASYNC_Q.add_handler(fh)
            _ASYNC_Q.start()
            ah = _AsyncHandler(_ASYNC_Q)
            ah.setLevel(numeric)
            ah.setFormatter(formatter)
            root.addHandler(ah)
        else:
            root.addHandler(fh)

    # Quiet noisy deps
    for name in ("uvicorn.access", "httpx", "huggingface_hub", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    _CONFIGURED = True


class _AsyncHandler(logging.Handler):
    def __init__(self, q: _AsyncQueue) -> None:
        super().__init__()
        self._q = q

    def emit(self, r: logging.LogRecord) -> None:
        self._q.emit(r)


# ═════════════════════════════════════════════════════════════════════════════
# Logger factory + structured events
# ═════════════════════════════════════════════════════════════════════════════

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str | None = None,
    **fields: Any,
) -> None:
    """Emit one structured event. Secrets auto-redacted."""
    exc_info = fields.pop("exc_info", None)
    extra: dict[str, Any] = {"event": event}
    for getter, key in ((get_request_id, "request_id"), (get_test_run_id, "test_run_id"),
                        (get_user_id, "user_id"), (get_session_id, "session_id")):
        v = getter()
        if v and key not in fields:
            extra[key] = v
    for k, v in fields.items():
        if k in _STD_FIELDS:
            k = f"f_{k}"
        extra[k] = redact(v)
    logger.log(level, message or event, extra=extra, exc_info=exc_info)


# ═════════════════════════════════════════════════════════════════════════════
# @log_perf decorator
# ═════════════════════════════════════════════════════════════════════════════

def log_perf(
    event: str | None = None,
    level: int = logging.DEBUG,
    log_args: bool = False,
    log_result: bool = False,
    track_metric: bool = True,
    logger_name: str | None = None,
) -> Callable:
    """Decorator: auto-trace function duration. Sync + async support.

    Usage:
        @log_perf(event="forecast.run", level=logging.INFO)
        def run_forecast(symbol: str, days: int) -> dict: ...
    """
    def decorator(func: Callable) -> Callable:
        _ev = event or f"{func.__module__}.{func.__qualname__}"
        _lg = logging.getLogger(logger_name or func.__module__)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                if log_args:
                    log_event(_lg, logging.DEBUG, f"{_ev}.start",
                              args=redact(args) if args else None,
                              kwargs=redact(kwargs) if kwargs else None)
                result = func(*args, **kwargs)
                ms = round((time.perf_counter() - start) * 1000, 2)
                extra: dict[str, Any] = {"duration_ms": ms}
                if log_result:
                    extra["result"] = redact(result)
                log_event(_lg, level, _ev, **extra)
                if track_metric:
                    record_metric(_ev, ms)
                return result
            except Exception as exc:
                ms = round((time.perf_counter() - start) * 1000, 2)
                log_event(_lg, logging.ERROR, f"{_ev}.error",
                          duration_ms=ms, error_type=type(exc).__name__, exc_info=True)
                if track_metric:
                    record_metric(_ev, ms, error=True)
                raise

        @functools.wraps(func)
        async def awrapper(*args: Any, **kwargs: Any) -> Any:
            import asyncio
            start = time.perf_counter()
            try:
                if log_args:
                    log_event(_lg, logging.DEBUG, f"{_ev}.start",
                              args=redact(args) if args else None,
                              kwargs=redact(kwargs) if kwargs else None)
                result = await func(*args, **kwargs)
                ms = round((time.perf_counter() - start) * 1000, 2)
                extra: dict[str, Any] = {"duration_ms": ms}
                if log_result:
                    extra["result"] = redact(result)
                log_event(_lg, level, _ev, **extra)
                if track_metric:
                    record_metric(_ev, ms)
                return result
            except Exception as exc:
                ms = round((time.perf_counter() - start) * 1000, 2)
                log_event(_lg, logging.ERROR, f"{_ev}.error",
                          duration_ms=ms, error_type=type(exc).__name__, exc_info=True)
                if track_metric:
                    record_metric(_ev, ms, error=True)
                raise

        import asyncio
        return awrapper if asyncio.iscoroutinefunction(func) else wrapper
    return decorator


# ═════════════════════════════════════════════════════════════════════════════
# Log level management
# ═════════════════════════════════════════════════════════════════════════════

def set_log_level(level: str | int, logger_name: str | None = None) -> None:
    if isinstance(level, str):
        numeric = getattr(logging, level.upper(), None)
        if numeric is None:
            raise ValueError(f"Unknown log level: {level}")
        level = numeric
    target = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    target.setLevel(level)
    for h in target.handlers:
        h.setLevel(level)
    with _LOG_LEVEL_LOCK:
        _LOG_LEVEL_OVERRIDES[logger_name or "root"] = level


def get_log_level(logger_name: str | None = None) -> int:
    return logging.getLogger(logger_name).level


def get_log_level_overrides() -> dict[str, int]:
    with _LOG_LEVEL_LOCK:
        return dict(_LOG_LEVEL_OVERRIDES)


# ═════════════════════════════════════════════════════════════════════════════
# Log file utilities
# ═════════════════════════════════════════════════════════════════════════════

def cleanup_old_logs(log_dir: str | os.PathLike[str], retention_days: int) -> None:
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
    directory = Path(log_dir or settings.logging.directory)
    if not directory.exists():
        return []

    import re as _re

    ev_re = _re.compile(event_pattern) if event_pattern else None
    results: list[dict[str, Any]] = []

    for log_file in sorted(directory.glob("kronos-*.log*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(results) >= limit:
            break
        try:
            with open(log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if level and rec.get("lv") != level:
                        continue
                    if request_id and rec.get("rid") != request_id:
                        continue
                    if ev_re and not ev_re.search(rec.get("ev", "")):
                        continue
                    if start_time:
                        ts = rec.get("t", "")
                        if ts and ts < start_time.isoformat():
                            continue
                    if end_time:
                        ts = rec.get("t", "")
                        if ts and ts > end_time.isoformat():
                            continue
                    results.append(rec)
                    if len(results) >= limit:
                        break
        except OSError:
            continue

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _iso(created: float) -> str:
    return datetime.fromtimestamp(created, tz=timezone.utc).isoformat(timespec="milliseconds")
