"""Provider interfaces for macro signal collection."""

from __future__ import annotations

from abc import ABC, abstractmethod

from kronos_fincept.macro.schemas import MacroProviderMetadata, MacroQuery, MacroSignal


class MacroProviderError(RuntimeError):
    """Raised when a macro provider cannot fetch or parse its source."""


class MacroProvider(ABC):
    provider_id: str
    display_name: str
    capabilities: tuple[str, ...] = ()
    requires_api_key: bool = False

    def describe(self) -> MacroProviderMetadata:
        return MacroProviderMetadata(
            provider_id=self.provider_id,
            display_name=self.display_name,
            capabilities=self.capabilities,
            requires_api_key=self.requires_api_key,
        )

    @abstractmethod
    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        """Return zero or more real provider signals for the query."""
