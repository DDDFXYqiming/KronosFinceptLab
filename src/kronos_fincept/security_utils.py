"""Security helpers shared by API routes and runtime services."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
from typing import Any
from urllib.parse import urlparse


PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts)",
    r"忽略(以上|之前|前面|所有).*(规则|指令|提示|约束)",
    r"(system|developer)\s+prompt",
    r"系统提示|开发者提示|隐藏提示词|提示词全文",
    r"泄露|透露|输出.*(密钥|key|token|secret|\.env|环境变量|凭据)",
    r"api[_\s-]?key|secret[_\s-]?key|access[_\s-]?token|authorization",
    r"未授权工具|越权|绕过|jailbreak|越狱",
]

ALLOWED_WEB_CONTEXT_ENTRIES = {"web-analysis", "web-macro"}
ALLOWED_CLIENT_CONTEXT_KEYS = {"entry", "default_symbol", "turn_index", "max_turns"}
ALLOWED_KRONOS_MODEL_IDS = {
    "NeoQuasar/Kronos-mini",
    "NeoQuasar/Kronos-small",
    "NeoQuasar/Kronos-base",
}


def env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def split_env_list(key: str) -> list[str]:
    raw = os.environ.get(key, "")
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def json_size_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def contains_prompt_injection(value: Any) -> bool:
    """Scan user-controlled strings for prompt injection or secret exfiltration asks."""
    if isinstance(value, str):
        lowered = value.lower()
        return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in PROMPT_INJECTION_PATTERNS)
    if isinstance(value, dict):
        return any(contains_prompt_injection(key) or contains_prompt_injection(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(contains_prompt_injection(item) for item in value)
    return False


def sanitize_client_context(context: dict[str, Any] | None, *, max_bytes: int | None = None) -> dict[str, Any] | None:
    """Keep only low-risk browser context fields before adding it to LLM context."""
    if context is None:
        return None
    if not isinstance(context, dict):
        raise ValueError("context must be an object")

    budget = max_bytes if max_bytes is not None else env_int("KRONOS_MAX_CONTEXT_BYTES", 16 * 1024)
    if json_size_bytes(context) > budget:
        raise ValueError("context is too large")
    if contains_prompt_injection(context):
        raise ValueError("context contains prompt-injection or secret-exfiltration text")

    sanitized: dict[str, Any] = {}
    entry = str(context.get("entry") or "").strip()
    if entry in ALLOWED_WEB_CONTEXT_ENTRIES:
        sanitized["entry"] = entry
    default_symbol = str(context.get("default_symbol") or "").strip().upper()
    if default_symbol:
        sanitized["default_symbol"] = default_symbol[:32]
    for key in ("turn_index", "max_turns"):
        value = context.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            sanitized[key] = max(0, min(20, int(value)))
    return sanitized


def validate_kronos_model_id(model_id: str | None) -> str:
    model = str(model_id or "").strip()
    if not model:
        raise ValueError("model_id is required")
    if model not in ALLOWED_KRONOS_MODEL_IDS:
        raise ValueError(f"model_id is not allowed: {model}")
    return model


def safe_configured_model_id(model_id: str | None, default: str) -> str:
    model = str(model_id or "").strip() or default
    return model if model in ALLOWED_KRONOS_MODEL_IDS else default


def validate_webhook_url(webhook_url: str) -> str:
    """Validate an outbound alert webhook URL against SSRF-prone targets."""
    text = str(webhook_url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme != "https":
        raise ValueError("webhook_url must use https")
    if parsed.username or parsed.password:
        raise ValueError("webhook_url must not include credentials")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("webhook_url host is required")

    allowed_hosts = split_env_list("KRONOS_ALERT_WEBHOOK_HOSTS") or ["open.feishu.cn"]
    if host not in {item.lower() for item in allowed_hosts}:
        raise ValueError("webhook_url host is not allowed")
    if _is_forbidden_hostname(host):
        raise ValueError("webhook_url host is not allowed")

    if env_bool("KRONOS_ALERT_VALIDATE_DNS", True):
        for _, _, _, _, sockaddr in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM):
            ip_text = sockaddr[0]
            if _is_forbidden_ip(ip_text):
                raise ValueError("webhook_url resolves to a forbidden address")
    return text


def _is_forbidden_hostname(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    if lowered in {"localhost", "metadata.google.internal"} or lowered.endswith(".local"):
        return True
    try:
        return _is_forbidden_ip(lowered)
    except ValueError:
        return False


def _is_forbidden_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
