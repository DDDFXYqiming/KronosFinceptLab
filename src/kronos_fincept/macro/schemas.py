"""Shared macro signal schemas for Digital Oracle style providers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MacroQuery:
    question: str = ""
    symbols: tuple[str, ...] = ()
    market: str | None = None
    time_horizon: str = "mixed"
    limit: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)

    def cache_key(self) -> str:
        symbols = ",".join(self.symbols)
        return f"{self.question.strip().lower()}|{symbols}|{self.market or ''}|{self.time_horizon}|{self.limit}"


@dataclass(frozen=True)
class MacroSignal:
    source: str
    signal_type: str
    value: str | int | float | bool | None
    interpretation: str
    time_horizon: str
    confidence: float
    observed_at: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MacroProviderMetadata:
    provider_id: str
    display_name: str
    capabilities: tuple[str, ...]
    requires_api_key: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MacroProviderResult:
    provider_id: str
    status: str
    signals: list[MacroSignal] = field(default_factory=list)
    elapsed_ms: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signals"] = [item.to_dict() for item in self.signals]
        return payload


@dataclass(frozen=True)
class MacroGatherResult:
    signals: list[MacroSignal]
    provider_results: dict[str, MacroProviderResult]

    @property
    def ok(self) -> bool:
        return all(item.status in {"completed", "empty", "skipped", "unavailable"} for item in self.provider_results.values())

    @property
    def errors(self) -> dict[str, str]:
        return {
            provider_id: result.error or "provider failed"
            for provider_id, result in self.provider_results.items()
            if result.status == "failed"
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "signals": [item.to_dict() for item in self.signals],
            "provider_results": {key: value.to_dict() for key, value in self.provider_results.items()},
            "errors": self.errors,
        }
