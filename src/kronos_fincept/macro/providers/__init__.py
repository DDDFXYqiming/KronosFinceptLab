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
    StooqProvider,
    USTreasuryProvider,
    WebSearchProvider,
    WorldBankProvider,
    YFinanceProvider,
    YahooPriceProvider,
    create_default_providers,
)

__all__ = [
    "AnySearchProvider",
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
    "StooqProvider",
    "SourceProjectMacroCacheProvider",
    "USTreasuryProvider",
    "WebSearchProvider",
    "WorldBankProvider",
    "YFinanceProvider",
    "YahooPriceProvider",
    "create_default_providers",
]
