"""Macro provider registry."""

from kronos_fincept.macro.providers.base import MacroProvider, MacroProviderError, MacroProviderUnavailable
from kronos_fincept.macro.providers.china_macro import ChinaMacroAkshareProvider
from kronos_fincept.macro.providers.chinalive import ChinaDataLiveProvider
from kronos_fincept.macro.providers.dbnomics import DBnomicsProvider
from kronos_fincept.macro.providers.fred import FredProvider
from kronos_fincept.macro.providers.nbs_live import ChinaNBSLiveProvider
from kronos_fincept.macro.providers.source_project_cache import SourceProjectMacroCacheProvider
from kronos_fincept.macro.providers.digital_oracle import (
    AnySearchProvider,
    AlternativeMeFearGreedProvider,
    BisProvider,
    CMEFedWatchProvider,
    CftcCotProvider,
    CoinGeckoProvider,
    CurrencyProvider,
    DeribitProvider,
    EdgarProvider,
    FearGreedProvider,
    KalshiProvider,
    PolymarketProvider,
    RssNewsProvider,
    StooqProvider,
    USTreasuryProvider,
    WebSearchProvider,
    WorldBankProvider,
    YFinanceProvider,
    YahooPriceProvider,
    create_default_providers,
)

# DO thin-wrapper providers — lazy-imported in create_all_providers() to avoid circular imports
# (provider_wrapper → macro.providers.base → macro.__init__ → manager → providers → wrapper 💥)

__all__ = [
    "AnySearchProvider",
    "AlternativeMeFearGreedProvider",
    "BisProvider",
    "CMEFedWatchProvider",
    "CftcCotProvider",
    "ChinaMacroAkshareProvider",
    "ChinaDataLiveProvider",
    "CoinGeckoProvider",
    "CurrencyProvider",
    "DBnomicsProvider",
    "DeribitProvider",
    "EdgarProvider",
    "FearGreedProvider",
    "FredProvider",
    "ChinaNBSLiveProvider",
    "KalshiProvider",
    "MacroProvider",
    "MacroProviderError",
    "MacroProviderUnavailable",
    "PolymarketProvider",
    "RssNewsProvider",
    "StooqProvider",
    "SourceProjectMacroCacheProvider",
    "USTreasuryProvider",
    "WebSearchProvider",
    "WorldBankProvider",
    "YFinanceProvider",
    "YahooPriceProvider",
    "create_default_providers",
    # DO thin-wrapper providers
    "WrappedPolymarketProvider",
    "WrappedKalshiProvider",
    "WrappedCMEFedWatchProvider",
    "WrappedFearGreedProvider",
    "WrappedBisProvider",
    "WrappedCftcCotProvider",
    "WrappedCoinGeckoProvider",
    "WrappedYahooPriceProvider",
    "WrappedStooqPriceProvider",
    "WrappedUSTreasuryProvider",
    "WrappedEdgarProvider",
    "WrappedWorldBankProvider",
    "WrappedWebSearchProvider",
    "WrappedYFinanceOptionsProvider",
    "create_all_providers",
]


def create_all_providers() -> list:
    """Return native + DO thin-wrapper providers for enhanced signal coverage."""
    from kronos_fincept.macro.providers import MacroProvider
    # Lazy import to avoid circular import (wrapper → macro.providers.base → macro.__init__ → manager → providers)
    from integrations.digital_oracle.provider_wrapper import (
        WrappedPolymarketProvider,
        WrappedKalshiProvider,
        WrappedCMEFedWatchProvider,
        WrappedFearGreedProvider,
        WrappedBisProvider,
        WrappedCftcCotProvider,
        WrappedCoinGeckoProvider,
        WrappedYahooPriceProvider,
        WrappedStooqPriceProvider,
        WrappedUSTreasuryProvider,
        WrappedEdgarProvider,
        WrappedWorldBankProvider,
        WrappedWebSearchProvider,
        WrappedYFinanceOptionsProvider,
    )
    from integrations.digital_oracle.advanced import (
        WrappedPolymarketOrderBookProvider,
        WrappedKalshiOrderBookProvider,
        WrappedDeribitOptionGreeksProvider,
        WrappedYfOptionGreeksProvider,
    )

    wrapped = [
        WrappedPolymarketProvider(),
        WrappedKalshiProvider(),
        WrappedCMEFedWatchProvider(),
        WrappedFearGreedProvider(),
        WrappedBisProvider(),
        WrappedCftcCotProvider(),
        WrappedCoinGeckoProvider(),
        WrappedYahooPriceProvider(),
        WrappedStooqPriceProvider(),
        WrappedUSTreasuryProvider(),
        WrappedEdgarProvider(),
        WrappedWorldBankProvider(),
        WrappedWebSearchProvider(),
        WrappedYFinanceOptionsProvider(),
        WrappedPolymarketOrderBookProvider(),
        WrappedKalshiOrderBookProvider(),
        WrappedDeribitOptionGreeksProvider(),
        WrappedYfOptionGreeksProvider(),
    ]
    return create_default_providers() + [p for p in wrapped if isinstance(p, MacroProvider)]
