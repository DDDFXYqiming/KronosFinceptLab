"""Macro provider registry."""

from kronos_fincept.macro.providers.base import MacroProvider, MacroProviderError
from kronos_fincept.macro.providers.digital_oracle import (
    BisProvider,
    CMEFedWatchProvider,
    CftcCotProvider,
    CoinGeckoProvider,
    DeribitProvider,
    EdgarProvider,
    FearGreedProvider,
    KalshiProvider,
    PolymarketProvider,
    USTreasuryProvider,
    WebSearchProvider,
    WorldBankProvider,
    YFinanceProvider,
    YahooPriceProvider,
    create_default_providers,
)

__all__ = [
    "BisProvider",
    "CMEFedWatchProvider",
    "CftcCotProvider",
    "CoinGeckoProvider",
    "DeribitProvider",
    "EdgarProvider",
    "FearGreedProvider",
    "KalshiProvider",
    "MacroProvider",
    "MacroProviderError",
    "PolymarketProvider",
    "USTreasuryProvider",
    "WebSearchProvider",
    "WorldBankProvider",
    "YFinanceProvider",
    "YahooPriceProvider",
    "create_default_providers",
]
