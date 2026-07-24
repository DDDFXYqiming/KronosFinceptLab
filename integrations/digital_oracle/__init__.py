"""Digital Oracle integration for KronosFinceptLab.

Wraps Digital Oracle providers (Polymarket, Kalshi, EDGAR, CMEFedWatch,
YFinance Options, CoinGecko, BIS, WorldBank, FearGreed, Stooq, Treasury,
CFTC, WebSearch) as KFL MacroProvider implementations.
"""

__version__ = "0.1.0"

from .provider_wrapper import (  # noqa: F401
    WRAPPED_PROVIDERS,
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
