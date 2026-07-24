"""Thin wrappers: Digital Oracle typed dataclass → KFL MacroSignal.

Each wrapper is a MacroProvider subclass that delegates to the DO pip package,
using DO's typed Query objects and typed return dataclasses directly.

Unlike KFL digital_oracle.py (hand-rolled HTTP + dict parsing), these wrappers
get compile-time safety from DO's 80+ typed dataclasses.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

from digital_oracle import (  # DO pip package — typed dataclasses
    # Providers
    BisProvider as DOBis,
    CMEFedWatchProvider as DOCME,
    CftcCotProvider as DOCftc,
    CoinGeckoProvider as DOCoinGecko,
    EdgarProvider as DOEdgar,
    FearGreedProvider as DOFearGreed,
    KalshiProvider as DOKalshi,
    PolymarketProvider as DOPoly,
    StooqProvider as DOStooq,
    USTreasuryProvider as DOTreasury,
    WebSearchProvider as DOWebSearch,
    WorldBankProvider as DOWorldBank,
    YahooPriceProvider as DOYahoo,
    YFinanceProvider as DOYFinanceOpt,
    # Query types
    CftcCotQuery,
    CoinGeckoPriceQuery,
    EdgarSearchQuery,
    ExchangeRateQuery,
    KalshiMarketQuery,
    OptionsChainQuery,
    PolymarketEventQuery,
    PriceHistoryQuery,
    WebSearchQuery,
    WorldBankQuery,
    YieldCurveQuery,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_signal(
    *,
    source: str,
    signal_type: str,
    value: str | int | float | bool | None,
    interpretation: str,
    time_horizon: str = "mixed",
    confidence: float = 0.55,
    observed_at: str | None = None,
    source_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> MacroSignal:
    return MacroSignal(
        source=source,
        signal_type=signal_type,
        value=value,
        interpretation=interpretation,
        time_horizon=time_horizon,
        confidence=max(0.0, min(1.0, confidence)),
        observed_at=observed_at or _now_iso(),
        source_url=source_url,
        metadata=metadata or {},
    )


def _dc_meta(dc: Any) -> dict[str, Any]:
    """dataclass → metadata dict, dropping None values."""
    if dc is None:
        return {}
    try:
        return {k: v for k, v in dataclasses.asdict(dc).items() if v is not None}
    except (TypeError, dataclasses.FrozenInstanceError):
        return {"raw": str(dc)[:500]}


# ===================================================================
# 1. Polymarket — prediction markets
# ===================================================================

class WrappedPolymarketProvider(MacroProvider):
    provider_id = "polymarket_do"
    display_name = "Polymarket (DO)"
    capabilities = ("prediction_market", "event_probability")

    def __init__(self) -> None:
        self._do = DOPoly()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        q = PolymarketEventQuery(
            title_contains=(query.question or "").strip()[:80],
            limit=max(1, min(query.limit, 20)),
            active=True,
        )
        try:
            events = self._do.list_events(q)
        except Exception as exc:
            logger.warning("Polymarket DO failed: %s", exc)
            return []

        signals: list[MacroSignal] = []
        for ev in events[: query.limit]:
            top = max(ev.markets, key=lambda m: m.volume or 0) if ev.markets else None
            prob = top.outcomes[0].probability if top and top.outcomes else None
            outcome_str = top.question if top else ""
            close_str = f" [CLOSED]" if ev.closed else ""
            signals.append(
                _make_signal(
                    source="polymarket_do",
                    signal_type="event_probability",
                    value=prob,
                    interpretation=f"{ev.title}{close_str}: {outcome_str} @ {prob:.1%}" if prob is not None else f"{ev.title}{close_str}",
                    confidence=0.65,
                    source_url=f"https://polymarket.com/event/{ev.slug}" if ev.slug else None,
                    metadata={**_dc_meta(ev), "_top_market": _dc_meta(top) if top else {}},
                )
            )
        return signals


# ===================================================================
# 2. Kalshi — binary event contracts
# ===================================================================

class WrappedKalshiProvider(MacroProvider):
    provider_id = "kalshi_do"
    display_name = "Kalshi (DO)"
    capabilities = ("prediction_market", "event_probability")

    def __init__(self) -> None:
        self._do = DOKalshi()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        q = KalshiMarketQuery(limit=max(1, min(query.limit, 20)))
        if query.question:
            q = KalshiMarketQuery(event_ticker=(query.question or "").strip()[:80])
        try:
            markets = self._do.list_markets(q)
        except Exception as exc:
            logger.warning("Kalshi DO failed: %s", exc)
            return []

        signals: list[MacroSignal] = []
        for mkt in markets[: query.limit]:
            price = mkt.last_price or mkt.yes_bid
            signals.append(
                _make_signal(
                    source="kalshi_do",
                    signal_type="event_probability",
                    value=price,
                    interpretation=f"{mkt.title} (yes={mkt.yes_bid}, no={mkt.no_bid}) [{mkt.status}]",
                    confidence=0.60,
                    source_url=f"https://kalshi.com/markets/{mkt.ticker}" if mkt.ticker else None,
                    metadata=_dc_meta(mkt),
                )
            )
        return signals


# ===================================================================
# 3. CME FedWatch — rate hike/cut probabilities
# ===================================================================

class WrappedCMEFedWatchProvider(MacroProvider):
    provider_id = "fedwatch_do"
    display_name = "CME FedWatch (DO)"
    capabilities = ("central_bank", "rate_probability")

    def __init__(self) -> None:
        self._do = DOCME()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        try:
            meetings = self._do.get_probabilities()
        except Exception as exc:
            logger.warning("CME FedWatch DO failed: %s", exc)
            return []

        signals: list[MacroSignal] = []
        for mtg in meetings[: query.limit]:
            top = max(mtg.probabilities, key=lambda p: p.probability) if mtg.probabilities else None
            interp = (
                f"Meeting {mtg.meeting_date}: "
                f"target {top.target_low:,.0f}-{top.target_high:,.0f}bp @ {top.probability:.1%}"
                if top else f"Meeting {mtg.meeting_date}: no probs"
            )
            signals.append(
                _make_signal(
                    source="fedwatch_do",
                    signal_type="rate_probability",
                    value=top.probability if top else None,
                    interpretation=interp,
                    time_horizon="short",
                    confidence=0.70,
                    metadata=_dc_meta(mtg),
                )
            )
        return signals


# ===================================================================
# 4. Fear & Greed Index
# ===================================================================

class WrappedFearGreedProvider(MacroProvider):
    provider_id = "feargreed_do"
    display_name = "Fear & Greed (DO)"
    capabilities = ("sentiment", "market_index")

    def __init__(self) -> None:
        self._do = DOFearGreed()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        try:
            snap = self._do.get_index()
        except Exception as exc:
            logger.warning("FearGreed DO failed: %s", exc)
            return []

        return [
            _make_signal(
                source="feargreed_do",
                signal_type="sentiment_index",
                value=snap.score,
                interpretation=f"{snap.rating} ({snap.score:.0f}/100)",
                time_horizon="short",
                confidence=0.60,
                metadata=_dc_meta(snap),
            )
        ]


# ===================================================================
# 5. BIS — Bank for International Settlements
# ===================================================================

class WrappedBisProvider(MacroProvider):
    provider_id = "bis_do"
    display_name = "BIS (DO)"
    capabilities = ("central_bank", "credit", "rate")

    def __init__(self) -> None:
        self._do = DOBis()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        signals: list[MacroSignal] = []

        try:
            gaps = self._do.get_credit_to_gdp()
            for g in gaps[: query.limit]:
                signals.append(
                    _make_signal(
                        source="bis_do",
                        signal_type="credit_gap",
                        value=g.gap_pct,
                        interpretation=f"{g.country} {g.period}: credit/GDP gap {g.gap_pct:+.1f}%",
                        time_horizon="long",
                        confidence=0.75,
                        metadata=_dc_meta(g),
                    )
                )
        except Exception as exc:
            logger.warning("BIS credit-gap failed: %s", exc)

        try:
            rates = self._do.get_policy_rates()
            for r in rates[: query.limit]:
                signals.append(
                    _make_signal(
                        source="bis_do",
                        signal_type="policy_rate",
                        value=r.rate,
                        interpretation=f"{r.country} {r.period}: policy rate {r.rate:.2f}%",
                        time_horizon="medium",
                        confidence=0.75,
                        metadata=_dc_meta(r),
                    )
                )
        except Exception as exc:
            logger.warning("BIS policy-rate failed: %s", exc)

        return signals


# ===================================================================
# 6. CFTC Commitment of Traders
# ===================================================================

class WrappedCftcCotProvider(MacroProvider):
    provider_id = "cftc_do"
    display_name = "CFTC COT (DO)"
    capabilities = ("commitment_of_traders", "positioning")

    def __init__(self) -> None:
        self._do = DOCftc()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        commodity = (query.question or "").strip() or None
        q = CftcCotQuery(commodity_name=commodity, limit=max(1, min(query.limit, 20)))
        try:
            reports = self._do.list_reports(q)
        except Exception as exc:
            logger.warning("CFTC DO failed: %s", exc)
            return []

        signals: list[MacroSignal] = []
        for r in reports[: query.limit]:
            net_spec = (r.mm_long or 0) - (r.mm_short or 0)
            signals.append(
                _make_signal(
                    source="cftc_do",
                    signal_type="cot_positioning",
                    value=net_spec,
                    interpretation=f"{r.market_name} {r.report_date}: spec net {net_spec:+} (OI={r.open_interest})",
                    time_horizon="medium",
                    confidence=0.70,
                    metadata=_dc_meta(r),
                )
            )
        return signals


# ===================================================================
# 7. CoinGecko — crypto prices
# ===================================================================

class WrappedCoinGeckoProvider(MacroProvider):
    provider_id = "coingecko_do"
    display_name = "CoinGecko (DO)"
    capabilities = ("crypto", "price")

    def __init__(self) -> None:
        self._do = DOCoinGecko()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        coin_ids = tuple(query.symbols) if query.symbols else ("bitcoin", "ethereum")
        q = CoinGeckoPriceQuery(coin_ids=coin_ids, include_market_cap=True, include_24h_vol=True)
        try:
            prices = self._do.get_prices(q)
        except Exception as exc:
            logger.warning("CoinGecko DO failed: %s", exc)
            return []

        signals: list[MacroSignal] = []
        for p in prices[: query.limit]:
            chg = f" ({p.price_change_24h_pct:+.1f}%)" if p.price_change_24h_pct is not None else ""
            mc = f" | MCap ${p.market_cap_usd:,.0f}" if p.market_cap_usd else ""
            signals.append(
                _make_signal(
                    source="coingecko_do",
                    signal_type="crypto_price",
                    value=p.price_usd,
                    interpretation=f"{p.coin_id}: ${p.price_usd:,.2f}{chg}{mc}",
                    time_horizon="short",
                    confidence=0.70,
                    metadata=_dc_meta(p),
                )
            )
        return signals


# ===================================================================
# 8. Yahoo Finance — price history
# ===================================================================

class WrappedYahooPriceProvider(MacroProvider):
    provider_id = "yahoo_price_do"
    display_name = "Yahoo Finance Price (DO)"
    capabilities = ("price", "history", "equity", "commodity", "fx")

    def __init__(self) -> None:
        self._do = DOYahoo()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        symbols = list(query.symbols) if query.symbols else ["SPY"]
        signals: list[MacroSignal] = []
        for sym in symbols[: query.limit]:
            q = PriceHistoryQuery(symbol=sym, interval="d")
            try:
                hist = self._do.get_history(q)
            except Exception as exc:
                logger.warning("Yahoo DO failed for %s: %s", sym, exc)
                continue
            if hist.bars:
                last = hist.bars[-1]
                signals.append(
                    _make_signal(
                        source="yahoo_price_do",
                        signal_type="price_close",
                        value=last.close,
                        interpretation=f"{sym}: ${last.close:,.2f} ({last.date})",
                        time_horizon="short",
                        confidence=0.75,
                        metadata={**_dc_meta(hist), "_last": _dc_meta(last)},
                    )
                )
        return signals


# ===================================================================
# 9. Stooq — free price history (no Yahoo rate limits)
# ===================================================================

class WrappedStooqPriceProvider(MacroProvider):
    provider_id = "stooq_do"
    display_name = "Stooq Price (DO)"
    capabilities = ("price", "equity", "commodity", "fx", "index")

    def __init__(self) -> None:
        self._do = DOStooq()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        symbols = list(query.symbols) if query.symbols else ["spy"]
        signals: list[MacroSignal] = []
        for sym in symbols[: query.limit]:
            q = PriceHistoryQuery(symbol=sym, interval="d")
            try:
                hist = self._do.get_history(q)
            except Exception as exc:
                logger.warning("Stooq DO failed for %s: %s", sym, exc)
                continue
            if hist.bars:
                last = hist.bars[-1]
                signals.append(
                    _make_signal(
                        source="stooq_do",
                        signal_type="price_close",
                        value=last.close,
                        interpretation=f"{sym}: ${last.close:,.2f} ({last.date})",
                        time_horizon="short",
                        confidence=0.75,
                        metadata={**_dc_meta(hist), "_last": _dc_meta(last)},
                    )
                )
        return signals


# ===================================================================
# 10. US Treasury — yield curve + FX rates (unified)
# ===================================================================

class WrappedUSTreasuryProvider(MacroProvider):
    provider_id = "treasury_do"
    display_name = "US Treasury (DO)"
    capabilities = ("rates", "yield_curve", "treasury", "fx")

    def __init__(self) -> None:
        self._do = DOTreasury()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        signals: list[MacroSignal] = []

        # --- Yield Curve ---
        for kind in ("nominal", "real"):
            try:
                curve = self._do.latest_yield_curve(YieldCurveQuery(year=2026, curve_kind=kind))
            except Exception as exc:
                logger.warning("Treasury yield curve (%s) failed: %s", kind, exc)
                continue
            if curve is None:
                continue
            tenor_map = {pt.tenor: pt.value for pt in curve.points}
            # 10y-2y spread
            if tenor_map.get("10y") and tenor_map.get("2y"):
                spread = tenor_map["10y"] - tenor_map["2y"]
                signals.append(
                    _make_signal(
                        source="treasury_do",
                        signal_type="yield_spread",
                        value=round(spread, 4),
                        interpretation=f"{kind} 10y-2y: {spread:+.2f}bp ({curve.date})",
                        time_horizon="medium",
                        confidence=0.65,
                        metadata={"date": curve.date, "kind": kind, "tenors": tenor_map},
                    )
                )

        # --- Exchange Rates ---
        try:
            rates = self._do.list_exchange_rates(ExchangeRateQuery(limit=max(1, min(query.limit, 10))))
        except Exception as exc:
            logger.warning("Treasury FX failed: %s", exc)
            return signals

        for r in rates[: query.limit]:
            signals.append(
                _make_signal(
                    source="treasury_do",
                    signal_type="exchange_rate",
                    value=r.exchange_rate,
                    interpretation=f"{r.country_currency_desc}: {r.exchange_rate} ({r.record_date})",
                    time_horizon="short",
                    confidence=0.75,
                    metadata=_dc_meta(r),
                )
            )
        return signals


# ===================================================================
# 11. SEC EDGAR — corporate filings
# ===================================================================

class WrappedEdgarProvider(MacroProvider):
    provider_id = "edgar_do"
    display_name = "SEC EDGAR (DO)"
    capabilities = ("sec_filings", "insider", "corporate")

    def __init__(self) -> None:
        self._do = DOEdgar()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        term = (query.question or "").strip()
        if not term:
            return []
        q = EdgarSearchQuery(query=term, limit=max(1, min(query.limit, 10)))
        try:
            hits = self._do.search_filings(q)
        except Exception as exc:
            logger.warning("EDGAR DO failed: %s", exc)
            return []

        return [
            _make_signal(
                source="edgar_do",
                signal_type="sec_filing",
                value=hit.entity_name,
                interpretation=f"{hit.entity_name}: {hit.form_type} filed {hit.file_date} — {hit.description[:120]}",
                time_horizon="mixed",
                confidence=0.55,
                metadata=_dc_meta(hit),
            )
            for hit in hits
        ]


# ===================================================================
# 12. World Bank — global development indicators
# ===================================================================

class WrappedWorldBankProvider(MacroProvider):
    provider_id = "worldbank_do"
    display_name = "World Bank (DO)"
    capabilities = ("economic_indicator", "development")

    def __init__(self) -> None:
        self._do = DOWorldBank()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        indicators = list(query.symbols) if query.symbols else ["NY.GDP.MKTP.CD", "FP.CPI.TOTL.ZG"]
        signals: list[MacroSignal] = []
        for ind_id in indicators[: query.limit]:
            q = WorldBankQuery(indicator=ind_id, per_page=5)
            try:
                result = self._do.get_indicator(q)
            except Exception as exc:
                logger.warning("WorldBank DO failed for %s: %s", ind_id, exc)
                continue
            if result.points:
                latest = result.points[-1]
                signals.append(
                    _make_signal(
                        source="worldbank_do",
                        signal_type="economic_indicator",
                        value=latest.value,
                        interpretation=f"{result.indicator_name}: {latest.value} ({latest.date})",
                        time_horizon="long",
                        confidence=0.70,
                        metadata=_dc_meta(result),
                    )
                )
        return signals


# ===================================================================
# 13. Web Search — aggregated macro news
# ===================================================================

class WrappedWebSearchProvider(MacroProvider):
    provider_id = "websearch_do"
    display_name = "Web Search (DO)"
    capabilities = ("web_search", "news")

    def __init__(self) -> None:
        self._do = DOWebSearch()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        term = (query.question or "").strip()
        if not term:
            return []
        q = WebSearchQuery(query=term, max_results=max(1, min(query.limit, 10)))
        try:
            result = self._do.search(q)
        except Exception as exc:
            logger.warning("WebSearch DO failed: %s", exc)
            return []

        return [
            _make_signal(
                source="websearch_do",
                signal_type="news_headline",
                value=s.title,
                interpretation=f"{s.title}: {s.snippet[:100]}",
                time_horizon="short",
                confidence=0.40,
                source_url=s.url,
                metadata=_dc_meta(s),
            )
            for s in result.snippets
        ]


# ===================================================================
# 14. YFinance Options — options chain + Greeks (NEW: DO advanced API)
# ===================================================================

class WrappedYFinanceOptionsProvider(MacroProvider):
    provider_id = "yfinance_options_do"
    display_name = "YFinance Options (DO)"
    capabilities = ("options", "greeks", "volatility")

    def __init__(self) -> None:
        self._do = DOYFinanceOpt()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        symbols = list(query.symbols) if query.symbols else ["SPY"]
        signals: list[MacroSignal] = []

        for ticker in symbols[: query.limit]:
            try:
                exps = self._do.get_expirations(ticker)
            except Exception as exc:
                logger.warning("YFinance options expirations failed for %s: %s", ticker, exc)
                continue
            if not exps.expirations:
                continue

            # Use the nearest expiration
            nearest = exps.expirations[0]
            q = OptionsChainQuery(ticker=ticker, expiration=nearest, compute_greeks=True)
            try:
                chain = self._do.get_chain(q)
            except Exception as exc:
                logger.warning("YFinance options chain failed for %s/%s: %s", ticker, nearest, exc)
                continue

            # ATM call
            if chain.underlying_price and chain.calls:
                atm = min(chain.calls, key=lambda c: abs(c.strike - (chain.underlying_price or 0)))
                greeks_str = ""
                if atm.greeks:
                    g = atm.greeks
                    greeks_str = f" Δ={g.delta:.3f} Γ={g.gamma:.4f} Θ={g.theta:.3f} ν={g.vega:.3f}"
                signals.append(
                    _make_signal(
                        source="yfinance_options_do",
                        signal_type="options_chain",
                        value=atm.last_price,
                        interpretation=(
                            f"{ticker} {nearest} C{atm.strike}: ${atm.last_price} "
                            f"(IV={atm.implied_volatility:.1%}){greeks_str}"
                            if atm.implied_volatility else
                            f"{ticker} {nearest} C{atm.strike}: ${atm.last_price}"
                        ),
                        time_horizon="short",
                        confidence=0.70,
                        metadata=_dc_meta(chain),
                    )
                )

            # Put/call ratio
            if chain.calls and chain.puts:
                total_call_oi = sum(c.open_interest or 0 for c in chain.calls)
                total_put_oi = sum(p.open_interest or 0 for p in chain.puts)
                if total_call_oi > 0:
                    pcr = total_put_oi / total_call_oi
                    signals.append(
                        _make_signal(
                            source="yfinance_options_do",
                            signal_type="put_call_ratio",
                            value=round(pcr, 3),
                            interpretation=f"{ticker} {nearest} P/C OI ratio: {pcr:.2f}",
                            time_horizon="short",
                            confidence=0.55,
                            metadata={"ticker": ticker, "expiration": nearest},
                        )
                    )
        return signals


# ===================================================================
# Registry — plug into manager.py
# ===================================================================

WRAPPED_PROVIDERS: dict[str, type[MacroProvider]] = {
    "polymarket_do": WrappedPolymarketProvider,
    "kalshi_do": WrappedKalshiProvider,
    "fedwatch_do": WrappedCMEFedWatchProvider,
    "feargreed_do": WrappedFearGreedProvider,
    "bis_do": WrappedBisProvider,
    "cftc_do": WrappedCftcCotProvider,
    "coingecko_do": WrappedCoinGeckoProvider,
    "yahoo_price_do": WrappedYahooPriceProvider,
    "stooq_do": WrappedStooqPriceProvider,
    "treasury_do": WrappedUSTreasuryProvider,
    "edgar_do": WrappedEdgarProvider,
    "worldbank_do": WrappedWorldBankProvider,
    "websearch_do": WrappedWebSearchProvider,
    "yfinance_options_do": WrappedYFinanceOptionsProvider,
}
