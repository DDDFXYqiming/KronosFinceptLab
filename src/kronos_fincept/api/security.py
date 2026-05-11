"""FastAPI security enforcement for public deployments."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from kronos_fincept.security_utils import env_bool, env_int, split_env_list


PUBLIC_PATHS = {"/api/health", "/api/health/"}
AUTH_HEADER = "authorization"
API_KEY_HEADER = "x-kronos-api-key"
INTERNAL_KEY_HEADER = "x-kronos-internal-key"

_RATE_BUCKETS: dict[tuple[str, str, int], int] = {}


@dataclass(frozen=True)
class SecurityDecision:
    allowed: bool
    status_code: int = 200
    error: str = ""
    error_type: str = ""
    role: str = "anonymous"
    key_id: str = "anonymous"
    auth_result: str = "public"
    rate_limit: str = ""
    rate_category: str = "public"


def api_docs_enabled() -> bool:
    return env_bool("KRONOS_ENABLE_API_DOCS", False)


def max_body_bytes() -> int:
    return max(1024, env_int("KRONOS_MAX_BODY_BYTES", 1_048_576))


def check_request_security(request: Request) -> SecurityDecision:
    """Authenticate and rate-limit one inbound request."""
    path = request.url.path
    if path in PUBLIC_PATHS:
        return SecurityDecision(allowed=True, role="public", key_id="public", auth_result="public")
    if not _is_api_path(path):
        return SecurityDecision(allowed=True, role="public", key_id="public", auth_result="public")

    body_decision = _check_content_length(request)
    if body_decision is not None:
        return body_decision

    if env_bool("KRONOS_AUTH_DISABLED", False):
        return _check_rate_limit("auth-disabled", "admin", path, auth_result="disabled")

    key = _extract_key(request)
    if not key:
        return SecurityDecision(
            allowed=False,
            status_code=401,
            error="API key is required",
            error_type="auth_required",
            auth_result="missing",
            rate_category=_rate_category(path),
        )

    role = _role_for_key(key)
    if role is None:
        return SecurityDecision(
            allowed=False,
            status_code=401,
            error="Invalid API key",
            error_type="invalid_api_key",
            auth_result="invalid",
            key_id=_key_id(key),
            rate_category=_rate_category(path),
        )
    if _requires_admin(path) and role != "admin":
        return SecurityDecision(
            allowed=False,
            status_code=403,
            error="Admin API key is required",
            error_type="admin_required",
            role=role,
            auth_result="forbidden",
            key_id=_key_id(key),
            rate_category=_rate_category(path),
        )
    return _check_rate_limit(_key_id(key), role, path, auth_result="ok")


def clear_rate_limits() -> None:
    _RATE_BUCKETS.clear()


def _is_api_path(path: str) -> bool:
    return path.startswith("/api/")


def _requires_admin(path: str) -> bool:
    return path.startswith("/api/alert")


def _extract_key(request: Request) -> str | None:
    internal_key = request.headers.get(INTERNAL_KEY_HEADER)
    if internal_key:
        return internal_key.strip()
    header_key = request.headers.get(API_KEY_HEADER)
    if header_key:
        return header_key.strip()
    auth = request.headers.get(AUTH_HEADER, "")
    prefix = "bearer "
    if auth.lower().startswith(prefix):
        return auth[len(prefix):].strip()
    return None


def _role_for_key(key: str) -> str | None:
    if _matches_any(key, split_env_list("KRONOS_ADMIN_API_KEYS")):
        return "admin"
    if _matches_any(key, split_env_list("KRONOS_INTERNAL_API_KEYS")):
        return "admin"
    single_internal = os.environ.get("KRONOS_INTERNAL_API_KEY", "").strip()
    if single_internal and hmac.compare_digest(key, single_internal):
        return "admin"
    if _matches_any(key, split_env_list("KRONOS_API_KEYS")):
        return "user"
    return None


def _matches_any(key: str, candidates: list[str]) -> bool:
    return any(hmac.compare_digest(key, candidate) for candidate in candidates if candidate)


def _key_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _check_content_length(request: Request) -> SecurityDecision | None:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return None
    raw = request.headers.get("content-length")
    if not raw:
        return None
    try:
        length = int(raw)
    except ValueError:
        return None
    limit = max_body_bytes()
    if length > limit:
        return SecurityDecision(
            allowed=False,
            status_code=413,
            error=f"Request body too large; limit is {limit} bytes",
            error_type="body_too_large",
            auth_result="body_rejected",
            rate_category=_rate_category(request.url.path),
        )
    return None


def _check_rate_limit(key_id: str, role: str, path: str, *, auth_result: str) -> SecurityDecision:
    category = _rate_category(path)
    limit, window = _rate_policy(category)
    if limit <= 0 or env_bool("KRONOS_RATE_LIMIT_DISABLED", False):
        return SecurityDecision(
            allowed=True,
            role=role,
            key_id=key_id,
            auth_result=auth_result,
            rate_category=category,
            rate_limit="disabled",
        )
    now = int(time.time())
    bucket = now // window
    storage_key = (key_id, category, bucket)
    count = _RATE_BUCKETS.get(storage_key, 0) + 1
    _RATE_BUCKETS[storage_key] = count
    label = f"{count}/{limit};w={window}"
    if count > limit:
        return SecurityDecision(
            allowed=False,
            status_code=429,
            error="Rate limit exceeded",
            error_type="rate_limited",
            role=role,
            key_id=key_id,
            auth_result=auth_result,
            rate_category=category,
            rate_limit=label,
        )
    return SecurityDecision(
        allowed=True,
        role=role,
        key_id=key_id,
        auth_result=auth_result,
        rate_category=category,
        rate_limit=label,
    )


def _rate_category(path: str) -> str:
    if path.startswith("/api/forecast"):
        return "forecast"
    if path.startswith("/api/batch"):
        return "batch"
    if path.startswith("/api/backtest"):
        return "backtest"
    if path.startswith("/api/v1/suggestions"):
        return "suggestions"
    if path.startswith("/api/v1/analyze"):
        return "llm"
    if path.startswith("/api/data"):
        return "data"
    if path.startswith("/api/alert"):
        return "alert"
    return "default"


def _rate_policy(category: str) -> tuple[int, int]:
    defaults: dict[str, tuple[int, int]] = {
        "forecast": (30, 60),
        "batch": (10, 60),
        "backtest": (6, 60),
        "llm": (20, 3600),
        "suggestions": (10, 3600),
        "data": (60, 60),
        "alert": (20, 60),
        "default": (120, 60),
    }
    raw = os.environ.get(f"KRONOS_RATE_LIMIT_{category.upper()}", "")
    if raw:
        try:
            left, right = raw.replace(":", "/").split("/", 1)
            return max(0, int(left)), max(1, int(right))
        except (ValueError, TypeError):
            pass
    return defaults.get(category, defaults["default"])
