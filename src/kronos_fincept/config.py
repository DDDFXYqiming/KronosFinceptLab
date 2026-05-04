"""Unified configuration loader for KronosFinceptLab.

Loads .env file and provides typed access to all config values.
Supports three tiers of configuration:
  1. Environment variables (highest priority)
  2. .env file
  3. Default values (lowest priority)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


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
class OpenAIConfig:
    """OpenAI / compatible API config."""
    api_key: str = field(default_factory=lambda: _get("OPENAI_API_KEY"))
    base_url: str = field(default_factory=lambda: _get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    model: str = field(default_factory=lambda: _get("OPENAI_MODEL", "gpt-4o"))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("sk-xxxx"))


@dataclass(frozen=True)
class AnthropicConfig:
    """Anthropic Claude config."""
    api_key: str = field(default_factory=lambda: _get("ANTHROPIC_API_KEY"))
    model: str = field(default_factory=lambda: _get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("sk-ant-xxxx"))


@dataclass(frozen=True)
class DeepSeekConfig:
    """DeepSeek config."""
    api_key: str = field(default_factory=lambda: _get("DEEPSEEK_API_KEY"))
    base_url: str = field(default_factory=lambda: _get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
    model: str = field(default_factory=lambda: _get("DEEPSEEK_MODEL", "deepseek-chat"))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("sk-xxxx"))


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
class ServerConfig:
    """API server config."""
    host: str = field(default_factory=lambda: _get("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _get_int("API_PORT", 8000))
    log_level: str = field(default_factory=lambda: _get("LOG_LEVEL", "INFO"))


@dataclass(frozen=True)
class LoggingConfig:
    """Application logging config."""
    level: str = field(default_factory=lambda: _get("KRONOS_LOG_LEVEL", _get("LOG_LEVEL", "INFO")))
    format: str = field(default_factory=lambda: _get("KRONOS_LOG_FORMAT", "text"))
    enable_file: bool = field(default_factory=lambda: _get_bool("KRONOS_LOG_ENABLE_FILE", True))
    directory: str = field(default_factory=lambda: _get("KRONOS_LOG_DIR", "logs"))
    retention_days: int = field(default_factory=lambda: _get_int("KRONOS_LOG_RETENTION_DAYS", 14))
    max_bytes: int = field(default_factory=lambda: _get_int("KRONOS_LOG_MAX_BYTES", 10 * 1024 * 1024))


@dataclass(frozen=True)
class LLMConfig:
    """Aggregated LLM provider configs."""
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)

    def get_active_provider(self) -> str | None:
        """Return the first configured provider name, or None."""
        if self.openai.is_configured:
            return "openai"
        if self.anthropic.is_configured:
            return "anthropic"
        if self.deepseek.is_configured:
            return "deepseek"
        return None


# ---------------------------------------------------------------------------
# Singleton settings instance
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    """Top-level application settings."""
    kronos: KronosConfig = field(default_factory=KronosConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


settings = Settings()
