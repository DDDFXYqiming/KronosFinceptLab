"""Unified configuration loader for KronosFinceptLab.

Loads .env file and provides typed access to all config values.
Supports three tiers of configuration:
  1. Environment variables (highest priority)
  2. .env file
  3. Default values (lowest priority)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Mapping

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hermes gateway model auto-detection
# ---------------------------------------------------------------------------

def _read_env_value(env_path: Path, key: str) -> str:
    """Read a single value from a .env file."""
    if not env_path.is_file():
        return ""
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and line.startswith(key + "="):
                    return line.split("=", 1)[1]
    except Exception:
        pass
    return ""


def _safe_hermes_home(raw_home: str) -> Path | None:
    """Return a safe absolute Hermes home path, rejecting relative traversal."""
    if not raw_home:
        return None
    candidate = Path(raw_home).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        return None
    try:
        return candidate.resolve(strict=False)
    except OSError:
        return None


@lru_cache(maxsize=8)
def _load_hermes_yaml(config_path: str, mtime_ns: int) -> dict:
    """Load Hermes YAML config, cached by path and mtime."""
    del mtime_ns  # included in the cache key
    try:
        import yaml
    except ImportError:
        return {}
    try:
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _read_hermes_model_config() -> dict[str, str]:
    """Read the current model config from the Hermes gateway.

    Looks for HERMES_HOME env var, then falls back to ~/.hermes/config.yaml.
    Returns dict with keys: api_key, base_url, model, or empty dict on failure.
    """
    hermes_home_raw = os.environ.get("HERMES_HOME", "")
    hermes_dir = _safe_hermes_home(hermes_home_raw)
    if hermes_home_raw and hermes_dir is None:
        return {}
    if hermes_dir is None:
        candidate = Path.home() / ".hermes" / "config.yaml"
        if candidate.is_file():
            hermes_dir = candidate.parent.resolve(strict=False)
        else:
            return {}
    config_path = hermes_dir / "config.yaml"
    if not config_path.is_file():
        return {}
    cfg = _load_hermes_yaml(str(config_path), config_path.stat().st_mtime_ns)
    if not cfg:
        return {}

    model_cfg = cfg.get("model", {})
    model_name = model_cfg.get("default", "")
    base_url = model_cfg.get("base_url", "")
    provider_name = model_cfg.get("provider", "")

    if not (model_name and base_url and provider_name):
        return {}

    # Resolve API key from providers section
    api_key = ""
    providers = cfg.get("providers", [])
    if isinstance(providers, list):
        for p in providers:
            if isinstance(p, dict) and p.get("name", "").lower() == provider_name.lower():
                api_key = p.get("key_env", "")
                break
    elif isinstance(providers, dict):
        for name, p in providers.items():
            if name.lower() == provider_name.lower():
                api_key = p.get("key_env", "")
                break

    # key_env is an env var name — try os.environ first, then Hermes .env
    if api_key:
        key_name = api_key  # rename for clarity
        api_key = os.environ.get(key_name, "")
        if not api_key:
            hermes_env = hermes_dir / ".env"
            api_key = _read_env_value(hermes_env, key_name)

    if not (api_key and base_url and model_name):
        return {}

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model_name,
    }




def _load_dotenv(env_path: Path | None = None) -> None:
    """Minimal .env loader — no external dependency needed."""
    if env_path is None:
        # Walk up from this file to project root
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.is_file():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Remove surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            # Only set if not already in environment (env vars win)
            if key not in os.environ:
                os.environ[key] = value


# Load .env on module import
_load_dotenv()


def _ensure_ssl_trust_store() -> None:
    """Auto-set SSL trust store (certifi) when not explicitly configured.

    Keeps HTTPS working across Python environments (e.g. venv311 vs system
    Python) without hard-coding a certifi path in .env. An explicit
    SSL_CERT_FILE / REQUESTS_CA_BUNDLE in .env or the environment wins.
    """
    try:
        import certifi
        ca = certifi.where()
    except Exception:
        return
    for _k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        if not os.environ.get(_k):
            os.environ[_k] = ca


_ensure_ssl_trust_store()


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _get_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KronosConfig:
    """Kronos model configuration."""
    repo_path: str = field(default_factory=lambda: _get("KRONOS_REPO_PATH"))
    hf_home: str = field(default_factory=lambda: _get("HF_HOME"))
    model_id: str = field(default_factory=lambda: _get("KRONOS_MODEL_ID", "NeoQuasar/Kronos-base"))
    tokenizer_id: str = "NeoQuasar/Kronos-Tokenizer-base"
    enable_real_model: bool = field(default_factory=lambda: _get_bool("KRONOS_ENABLE_REAL_MODEL", True))
    allow_dry_run: bool = field(default_factory=lambda: _get_bool("KRONOS_ALLOW_DRY_RUN", True))
    prewarm_on_startup: bool = field(default_factory=lambda: _get_bool("KRONOS_PREWARM_ON_STARTUP", False))


@dataclass(frozen=True)
class LLMProviderConfig:
    """OpenAI-compatible LLM API config (primary provider)."""
    api_key: str = field(default_factory=lambda: _get("LLM_API_KEY"))
    base_url: str = field(default_factory=lambda: _get("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions"))
    model: str = field(default_factory=lambda: _get("LLM_MODEL", "gpt-4o-mini"))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith(("sk-xxxx", "xxxx")))


@dataclass(frozen=True)
class LLMProviderEntry:
    """Single LLM provider entry in the fallback chain."""
    name: str
    api_key: str
    base_url: str
    model: str
    enabled: bool = True
    priority: int = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith(("sk-xxxx", "xxxx")))

    @property
    def display_name(self) -> str:
        return self.name


@dataclass(frozen=True)
class LLMFallbackChainConfig:
    """LLM fallback chain: ordered list of providers with priority-based fallback."""
    providers: list[LLMProviderEntry] = field(default_factory=list)
    order: tuple[str, ...] = ()
    enabled: bool = False
    max_attempts: int = 3

    def get_ordered_providers(self) -> list[LLMProviderEntry]:
        """Return enabled, configured providers in fallback order."""
        available = {p.name: p for p in self.providers if p.enabled and p.is_configured}
        ordered: list[LLMProviderEntry] = []
        for name in self.order:
            if name in available:
                ordered.append(available.pop(name))
        # Append remaining by priority
        remaining = sorted(available.values(), key=lambda p: p.priority)
        return ordered + remaining

    @classmethod
    def from_env(cls, env: "Mapping[str, str] | None" = None) -> "LLMFallbackChainConfig":
        """Build fallback chain from environment variables.

        Supports:
          - LLM_API_KEY / LLM_BASE_URL / LLM_MODEL  (primary)
          - LLM_FALLBACK_{N}_API_KEY / BASE_URL / MODEL  (N = 1,2,3,...)
            * LLM_FALLBACK_{N}_API_KEY is OPTIONAL: when blank, the shared
              ``LLM_API_KEY`` is reused — same K, different base/model.
          - LLM_FALLBACK_ORDER  (comma-separated names, e.g. "primary,fallback_1")
          - LLM_ENABLE_FALLBACK_CHAIN  (0/1)
          - LLM_MAX_PROVIDER_ATTEMPTS  (default 3)

        ``env`` is an optional override mapping. When supplied, reads go
        through it instead of ``os.environ``. This makes the class
        testable without monkeypatching global env state — important
        because ``_load_dotenv()`` runs at import time and would
        otherwise leak the developer-machine ``.env`` into unit tests.
        """
        def _g(key: str, default: str = "") -> str:
            if env is not None:
                return env.get(key, default)
            return _get(key, default)

        def _gi(key: str, default: int = 0) -> int:
            raw = _g(key, str(default))
            try:
                return int(raw)
            except (TypeError, ValueError):
                return default

        def _gb(key: str, default: bool = False) -> bool:
            return _g(key, str(default)).lower() in ("1", "true", "yes")

        shared_key = _g("LLM_API_KEY")
        shared_base = _g("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions")
        shared_model = _g("LLM_MODEL", "gpt-4o-mini")

        # Auto-detect: if no LLM_API_KEY set, read from Hermes gateway config
        if not shared_key:
            hermes_cfg = _read_hermes_model_config()
            if hermes_cfg:
                shared_key = hermes_cfg["api_key"]
                shared_base = hermes_cfg["base_url"]
                shared_model = hermes_cfg["model"]

        providers: list[LLMProviderEntry] = []

        # Primary provider
        primary = LLMProviderEntry(
            name="primary",
            api_key=shared_key,
            base_url=shared_base,
            model=shared_model,
            priority=0,
        )
        providers.append(primary)

        # Fallback providers (1-9). A fallback entry only requires a base URL
        # or model to exist — the API key inherits the shared LLM_API_KEY when
        # LLM_FALLBACK_{N}_API_KEY is blank, so users can rotate providers
        # without rotating keys.
        for i in range(1, 10):
            n_key = _g(f"LLM_FALLBACK_{i}_API_KEY")
            n_base = _g(f"LLM_FALLBACK_{i}_BASE_URL")
            n_model = _g(f"LLM_FALLBACK_{i}_MODEL")
            if not (n_base or n_model):
                # Nothing configured for this slot — skip.
                continue
            # Warn when a fallback provider inherits the primary API key across
            # different providers (different base_url), because most LLM
            # providers reject keys issued by a different vendor.
            if not n_key and n_base and n_base != shared_base:
                _logger.warning(
                    "Fallback %d has no dedicated API key and its base_url (%s) "
                    "differs from the primary (%s). Inheriting the primary key "
                    "will likely fail — set LLM_FALLBACK_%d_API_KEY to a key "
                    "issued by the fallback provider.",
                    i, n_base, shared_base, i,
                )
            providers.append(
                LLMProviderEntry(
                    name=f"fallback_{i}",
                    api_key=(n_key or shared_key),
                    base_url=(n_base or shared_base),
                    model=(n_model or shared_model),
                    priority=i,
                )
            )

        order_raw = _g("LLM_FALLBACK_ORDER", "")
        order = tuple(p.strip() for p in order_raw.split(",") if p.strip()) if order_raw else ()

        return cls(
            providers=providers,
            order=order,
            enabled=_gb("LLM_ENABLE_FALLBACK_CHAIN", False),
            max_attempts=_gi("LLM_MAX_PROVIDER_ATTEMPTS", 3),
        )


@dataclass(frozen=True)
class WebSearchConfig:
    """Generic web search provider config for the stateless agent."""
    provider: str = field(default_factory=lambda: _get("WEB_SEARCH_PROVIDER").strip().lower())
    api_key: str = field(default_factory=lambda: _get("WEB_SEARCH_API_KEY"))
    endpoint: str = field(default_factory=lambda: _get("WEB_SEARCH_ENDPOINT"))
    timeout_seconds: int = field(default_factory=lambda: _get_int("WEB_SEARCH_TIMEOUT_SECONDS", 8))
    max_results: int = field(default_factory=lambda: _get_int("WEB_SEARCH_MAX_RESULTS", 4))

    @property
    def is_configured(self) -> bool:
        if self.provider in {"", "none", "disabled", "off"}:
            return False
        if self.provider == "custom":
            return bool(self.endpoint)
        return bool(self.api_key and not self.api_key.startswith("xxxx"))


@dataclass(frozen=True)
class AnySearchConfig:
    """Anonymous AnySearch REST API config."""
    enabled: bool = field(default_factory=lambda: _get_bool("ANYSEARCH_ENABLED", False))
    endpoint: str = field(default_factory=lambda: _get("ANYSEARCH_ENDPOINT", "https://api.anysearch.com/v1/search"))
    timeout_seconds: int = field(default_factory=lambda: _get_int("ANYSEARCH_TIMEOUT_SECONDS", 8))
    max_results: int = field(default_factory=lambda: _get_int("ANYSEARCH_MAX_RESULTS", 4))

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.endpoint)


@dataclass(frozen=True)
class ServerConfig:
    """API server config."""
    host: str = field(default_factory=lambda: _get("API_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _get_int("API_PORT", 8000))
    log_level: str = field(default_factory=lambda: _get("LOG_LEVEL", "INFO"))


@dataclass(frozen=True)
class LoggingConfig:
    """Application logging config."""
    level: str = field(default_factory=lambda: _get("KRONOS_LOG_LEVEL", _get("LOG_LEVEL", "INFO")))
    format: str = field(default_factory=lambda: _get("KRONOS_LOG_FORMAT", "text"))
    enable_file: bool = field(default_factory=lambda: _get_bool("KRONOS_LOG_ENABLE_FILE", True))
    enable_async: bool = field(default_factory=lambda: _get_bool("KRONOS_LOG_ENABLE_ASYNC", False))
    directory: str = field(default_factory=lambda: _get("KRONOS_LOG_DIR", "logs"))
    retention_days: int = field(default_factory=lambda: _get_int("KRONOS_LOG_RETENTION_DAYS", 14))
    max_bytes: int = field(default_factory=lambda: _get_int("KRONOS_LOG_MAX_BYTES", 10 * 1024 * 1024))


@dataclass(frozen=True)
class LLMConfig:
    """Unified OpenAI-compatible LLM provider config with fallback chain support."""
    provider: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    fallback_chain: LLMFallbackChainConfig = field(default_factory=LLMFallbackChainConfig.from_env)

    def get_active_provider(self) -> str | None:
        """Return the first configured provider name, or None."""
        if self.provider.is_configured:
            return "llm"
        return None

    def get_fallback_providers(self) -> list[LLMProviderEntry]:
        """Return ordered fallback providers (empty if fallback chain disabled)."""
        if not self.fallback_chain.enabled:
            if self.provider.is_configured:
                return [
                    LLMProviderEntry(
                        name="primary",
                        api_key=self.provider.api_key,
                        base_url=self.provider.base_url,
                        model=self.provider.model,
                    )
                ]
            return []
        return self.fallback_chain.get_ordered_providers()


# ---------------------------------------------------------------------------
# Singleton settings instance
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    """Top-level application settings."""
    kronos: KronosConfig = field(default_factory=KronosConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    anysearch: AnySearchConfig = field(default_factory=AnySearchConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


settings = Settings()
