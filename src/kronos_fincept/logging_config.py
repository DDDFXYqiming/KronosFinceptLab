"""Unified logging setup for KronosFinceptLab."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, TextIO

from kronos_fincept.config import settings


_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_test_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("test_run_id", default=None)
_CONFIGURED = False
_STANDARD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "message",
    "asctime", "taskName",
}
_RESERVED_OUTPUT_FIELDS = {
    "timestamp", "level", "logger", "event", "request_id", "test_run_id", "symbol", "market",
    "duration_ms", "error_type", "message", "exception",
}
_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|secret[_-]?key|access[_-]?token|token|cookie|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)(DEEPSEEK_API_KEY\s*=\s*)[^\s,;]+"),
    re.compile(r"(?i)(OPENROUTER_API_KEY\s*=\s*)[^\s,;]+"),
    re.compile(r"(?i)(OPENAI_API_KEY\s*=\s*)[^\s,;]+"),
    re.compile(r"(?i)(ANTHROPIC_API_KEY\s*=\s*)[^\s,;]+"),
    re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)(webhook[_-]?url\s*[:=]\s*)https?://[^\s,;]+"),
    re.compile(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
]


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


def configure_logging(
    *,
    level: str | None = None,
    log_format: str | None = None,
    log_dir: str | os.PathLike[str] | None = None,
    stream: TextIO | None = None,
    enable_file: bool | None = None,
    force: bool = False,
) -> None:
    """Configure root logging once for API, CLI, jobs, and tests."""
    global _CONFIGURED
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

    root.setLevel(numeric_level)

    stream_handler = logging.StreamHandler(stream or sys.stderr)
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

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
        root.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a project logger."""
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str | None = None,
    **fields: Any,
) -> None:
    """Emit one structured event without leaking secrets."""
    exc_info = fields.pop("exc_info", None)
    extra = {"event": event}
    if get_request_id() and "request_id" not in fields:
        extra["request_id"] = get_request_id()
    if get_test_run_id() and "test_run_id" not in fields:
        extra["test_run_id"] = get_test_run_id()
    for key, value in fields.items():
        if key in _STANDARD_FIELDS:
            key = f"field_{key}"
        extra[key] = redact(value)
    logger.log(level, message or event, extra=extra, exc_info=exc_info)


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
            "symbol": getattr(record, "symbol", None),
            "market": getattr(record, "market", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "error_type": getattr(record, "error_type", None),
            "message": redact(record.getMessage()),
        }
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
        if symbol is not None:
            parts.append(f"symbol={redact(symbol)}")
        if market is not None:
            parts.append(f"market={redact(market)}")
        if duration_ms is not None:
            parts.append(f"duration_ms={duration_ms}")
        if test_run_id:
            parts.append(f"test_run_id={redact(test_run_id)}")
        message = redact(record.getMessage())
        if message and message != event:
            parts.append(f"message={message}")
        output = " ".join(str(item) for item in parts)
        if record.exc_info:
            output += "\n" + redact(self.formatException(record.exc_info))
        return output


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


def _iso_timestamp(created: float) -> str:
    return datetime.fromtimestamp(created, tz=timezone.utc).isoformat(timespec="milliseconds")
