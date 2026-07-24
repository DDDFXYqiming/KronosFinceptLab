"""Advanced signal providers: OrderBook depth + Options Greeks.

Polyfills KFL's missing capabilities by thin-wrapping DO's typed dataclasses:
  - Polymarket OrderBook       → bid/ask depth, spread, midpoint
  - Kalshi OrderBook           → yes/no order book depth
  - Deribit Options Chain      → strike-level IV + Greeks
  - YFinance Options + BS      → per-contract Greeks via black_scholes_greeks

Each provider is a MacroProvider subclass, drop-in compatible with KFL's
concurrent pipeline (manager.py SIGNAL_SOURCE_PRIORITY + gather_all).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import dataclasses

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

from digital_oracle import (
    # Providers
    DeribitProvider as DODeribit,
    KalshiProvider as DOKalshi,
    PolymarketProvider as DOPoly,
    YFinanceProvider as DOYFinanceOpt,
    # Query types
    DeribitOptionChainQuery,
    KalshiMarketQuery,
    OptionsChainQuery,
    PolymarketEventQuery,
    # Data classes
    DeribitOptionQuote,
    DeribitOptionStrike,
    KalshiOrderBook,
    KalshiOrderLevel,
    OptionContract,
    OptionGreeks,
    OptionsChain,
    OrderBook,
    OrderLevel,
    # Util
    black_scholes_greeks,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers (same as wrapper.py)
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
    if dc is None:
        return {}
    try:
        return {k: v for k, v in dataclasses.asdict(dc).items() if v is not None}
    except (TypeError, dataclasses.FrozenInstanceError):
        return {"raw": str(dc)[:500]}


# ===================================================================
# 1. Polymarket OrderBook — depth + bid/ask spread
# ===================================================================

class WrappedPolymarketOrderBookProvider(MacroProvider):
    """Polymarket CLOB order book depth signals.

    For each active event with liquidity, fetches the full order book
    and emits: best bid/ask, spread (%), midprice, total depth (top-N sides).
    """

    provider_id = "polymarket_orderbook_do"
    display_name = "Polymarket OrderBook (DO)"
    capabilities = ("order_book", "market_depth", "prediction_market")

    def __init__(self) -> None:
        self._do = DOPoly()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        q = PolymarketEventQuery(
            title_contains=(query.question or "").strip()[:80],
            limit=max(1, min(query.limit, 10)),
            active=True,
        )
        try:
            events = self._do.list_events(q)
        except Exception as exc:
            logger.warning("Polymarket DO events failed: %s", exc)
            return []

        signals: list[MacroSignal] = []
        for ev in events[: query.limit]:
            # Pick the top market by volume
            top_mkt = max(ev.markets, key=lambda m: m.volume or 0) if ev.markets else None
            if not top_mkt:
                continue

            token_id = top_mkt.condition_id  # CLOB conditional token ID
            try:
                ob: OrderBook = self._do.get_order_book(token_id)
            except Exception as exc:
                logger.debug("Polymarket OB fetch failed for %s: %s", token_id, exc)
                continue

            if not ob.bids or not ob.asks:
                continue

            best_bid = ob.bids[0]
            best_ask = ob.asks[0]
            mid = (best_bid.price + best_ask.price) / 2
            spread_pct = ((best_ask.price - best_bid.price) / mid * 100) if mid > 0 else 0

            # Depth: sum of top N levels (both sides)
            top_n = min(5, len(ob.bids), len(ob.asks))
            bid_depth = sum(l.size for l in ob.bids[:top_n])
            ask_depth = sum(l.size for l in ob.asks[:top_n])

            interpretation = (
                f"{ev.title}: bid={best_bid.price:.4f}×{best_bid.size:.1f} "
                f"ask={best_ask.price:.4f}×{best_ask.size:.1f} "
                f"mid={mid:.4f} spread={spread_pct:.2f}% "
                f"depth(bid={bid_depth:.0f}/ask={ask_depth:.0f})"
            )

            signals.append(
                _make_signal(
                    source="polymarket_orderbook_do",
                    signal_type="order_book_depth",
                    value=mid,
                    interpretation=interpretation,
                    confidence=0.60,
                    source_url=(
                        f"https://polymarket.com/event/{ev.slug}"
                        if ev.slug else None
                    ),
                    metadata={
                        **_dc_meta(ob),
                        "best_bid": best_bid.price,
                        "best_bid_size": best_bid.size,
                        "best_ask": best_ask.price,
                        "best_ask_size": best_ask.size,
                        "mid": mid,
                        "spread_pct": round(spread_pct, 3),
                        "bid_depth_top5": bid_depth,
                        "ask_depth_top5": ask_depth,
                        "num_bids": len(ob.bids),
                        "num_asks": len(ob.asks),
                        "event_title": ev.title,
                        "token_id": token_id,
                    },
                )
            )
        return signals


# ===================================================================
# 2. Kalshi OrderBook — yes/no order book depth
# ===================================================================

class WrappedKalshiOrderBookProvider(MacroProvider):
    """Kalshi binary event order book depth signals.

    For each active market, fetches full yes/no order book and emits:
    best bid/ask for both yes & no sides, spread, midpoint, depth.
    """

    provider_id = "kalshi_orderbook_do"
    display_name = "Kalshi OrderBook (DO)"
    capabilities = ("order_book", "market_depth", "prediction_market")

    def __init__(self) -> None:
        self._do = DOKalshi()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        mq = KalshiMarketQuery(limit=max(1, min(query.limit, 10)))
        if query.question:
            mq = KalshiMarketQuery(event_ticker=(query.question or "").strip()[:80])
        try:
            markets = self._do.list_markets(mq)
        except Exception as exc:
            logger.warning("Kalshi DO markets failed: %s", exc)
            return []

        signals: list[MacroSignal] = []
        for mkt in markets[: query.limit]:
            try:
                ob: KalshiOrderBook = self._do.get_order_book(mkt.ticker, depth=5)
            except Exception as exc:
                logger.debug("Kalshi OB fetch failed for %s: %s", mkt.ticker, exc)
                continue

            if not ob.yes_bids and not ob.no_bids:
                continue

            def _side_stats(levels: tuple[KalshiOrderLevel, ...]) -> dict[str, Any]:
                if not levels:
                    return {"best": None, "best_size": 0, "depth": 0}
                return {
                    "best": levels[0].price,
                    "best_size": levels[0].size,
                    "depth": sum(l.size for l in levels[: min(5, len(levels))]),
                }

            yes_stats = _side_stats(ob.yes_bids)
            no_stats = _side_stats(ob.no_bids)

            # Midpoint estimated from best yes_bid (proxy for P(yes)) vs no_bid
            yes_mid = yes_stats["best"]
            spread = (
                (yes_stats["best"] - no_stats["best"]) if yes_stats["best"] is not None and no_stats["best"] is not None else None
            )

            interpretation = (
                f"{mkt.title}: YES bid={yes_stats['best']}×{yes_stats['best_size']} "
                f"depth={yes_stats['depth']:.0f} | NO bid={no_stats['best']}×{no_stats['best_size']} "
                f"depth={no_stats['depth']:.0f}"
            )
            if spread is not None:
                interpretation += f" spread={spread:.4f}"

            signals.append(
                _make_signal(
                    source="kalshi_orderbook_do",
                    signal_type="order_book_depth",
                    value=yes_mid,
                    interpretation=interpretation,
                    confidence=0.58,
                    source_url=(
                        f"https://kalshi.com/markets/{mkt.ticker}"
                        if mkt.ticker else None
                    ),
                    metadata={
                        "ticker": mkt.ticker,
                        "market_title": mkt.title,
                        "yes_best": yes_stats["best"],
                        "yes_best_size": yes_stats["best_size"],
                        "yes_depth_top5": yes_stats["depth"],
                        "no_best": no_stats["best"],
                        "no_best_size": no_stats["best_size"],
                        "no_depth_top5": no_stats["depth"],
                        "spread": round(spread, 4) if spread is not None else None,
                        "num_yes_bids": len(ob.yes_bids),
                        "num_no_bids": len(ob.no_bids),
                        **_dc_meta(mkt),
                    },
                )
            )
        return signals


# ===================================================================
# 3. Deribit Options Chain — strike-level IV + Greeks
# ===================================================================

class WrappedDeribitOptionGreeksProvider(MacroProvider):
    """Deribit options chain with implied volatility and Greeks.

    Fetches the full option chain for BTC (default) and emits per-strike
    signals: IV, bid/ask, open interest, volume for calls & puts.

    Note: Deribit does NOT return Delta/Gamma/Theta/Vega in its standard
    API — those are present on YFinance. This provider focuses on
    IV structure + market depth that Deribit uniquely provides.
    """

    provider_id = "deribit_options_do"
    display_name = "Deribit Options (DO)"
    capabilities = ("options_chain", "implied_volatility", "derivatives")

    def __init__(self) -> None:
        self._do = DODeribit()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        currency = query.metadata.get("currency", "BTC")
        expiration_label = query.metadata.get("expiration_label") or None

        dq = DeribitOptionChainQuery(
            currency=currency,
            expiration_label=expiration_label,
        )
        try:
            chain = self._do.get_option_chain(dq)
        except Exception as exc:
            logger.warning("Deribit options chain failed: %s", exc)
            return []

        if chain is None:
            return []

        signals: list[MacroSignal] = []
        for strike_item in chain.strikes[: query.limit]:
            strike = strike_item.strike

            def _emit_side(
                quote: DeribitOptionQuote | None,
                side: str,
            ) -> None:
                if quote is None:
                    return
                iv = quote.mark_iv
                signals.append(
                    _make_signal(
                        source="deribit_options_do",
                        signal_type="option_iv",
                        value=iv,
                        interpretation=(
                            f"Deribit {currency} {side} K={strike} "
                            f"{quote.expiration_label}: "
                            f"IV={iv:.1%}" if iv is not None else f"{iv}"
                            + (f" bid={quote.bid_price} ask={quote.ask_price}"
                               if quote.bid_price is not None else "")
                            + (f" OI={quote.open_interest:.0f}"
                               if quote.open_interest is not None else "")
                        ),
                        confidence=0.65,
                        source_url=f"https://www.deribit.com/futures/{currency}",
                        metadata={
                            "currency": currency,
                            "strike": strike,
                            "side": side,
                            "instrument_name": quote.instrument_name,
                            "expiration_label": quote.expiration_label,
                            "expiration_timestamp": quote.expiration_timestamp,
                            "mark_iv": iv,
                            "bid": quote.bid_price,
                            "ask": quote.ask_price,
                            "mid": quote.mid_price,
                            "last": quote.last_price,
                            "mark": quote.mark_price,
                            "open_interest": quote.open_interest,
                            "volume": quote.volume,
                            "underlying_price": quote.underlying_price,
                            "underlying_index": quote.underlying_index,
                        },
                    )
                )

            _emit_side(strike_item.call, "CALL")
            _emit_side(strike_item.put, "PUT")

        return signals


# ===================================================================
# 4. YFinance Options + black_scholes_greeks — per-contract Greeks
# ===================================================================

class WrappedYfOptionGreeksProvider(MacroProvider):
    """YFinance options chain with Black-Scholes Greeks.

    For each ticker symbol, fetches the full options chain (calls + puts)
    and computes delta/gamma/theta/vega via DO's black_scholes_greeks().
    Falls back to YFinance's built-in computed Greeks if available.
    """

    provider_id = "yf_options_do"
    display_name = "YFinance Options Greeks (DO)"
    capabilities = ("options_chain", "option_greeks", "derivatives")

    def __init__(self) -> None:
        self._do = DOYFinanceOpt()

    def _compute_greeks(
        self,
        contract: OptionContract,
        underlying_price: float,
        risk_free_rate: float,
    ) -> OptionGreeks | None:
        """Compute BS Greeks if not present on the contract."""
        if contract.greeks and contract.greeks.delta is not None:
            return contract.greeks  # Already computed upstream

        T = max(0.001, contract.time_to_expiry or 0.25) if hasattr(contract, "time_to_expiry") else 0.25
        sigma = contract.implied_volatility or 0.30
        K = contract.strike
        opt_type = contract.option_type.lower()

        try:
            return black_scholes_greeks(
                S=underlying_price,
                K=K,
                T=T,
                r=risk_free_rate,
                sigma=sigma,
                option_type=opt_type,
            )
        except Exception:
            return None

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        symbols = query.symbols or ("SPY",)
        risk_free_rate = float(query.metadata.get("risk_free_rate", 0.045))
        expiration = query.metadata.get("expiration") or None

        signals: list[MacroSignal] = []
        for symbol in symbols[: query.limit]:
            ocq = OptionsChainQuery(
                ticker=str(symbol),
                expiration=expiration,
                risk_free_rate=risk_free_rate,
                compute_greeks=True,
            )
            try:
                chain: OptionsChain = self._do.get_chain(ocq)
            except Exception as exc:
                logger.warning("YFinance options chain failed for %s: %s", symbol, exc)
                continue

            underlying = chain.underlying_price

            def _emit_contracts(
                contracts: tuple[OptionContract, ...],
                side: str,
            ) -> None:
                for c in contracts[: max(1, query.limit)]:
                    greeks = self._compute_greeks(c, underlying, risk_free_rate)
                    meta_greeks = {
                        "delta": greeks.delta if greeks else None,
                        "gamma": greeks.gamma if greeks else None,
                        "theta": greeks.theta if greeks else None,
                        "vega": greeks.vega if greeks else None,
                    }

                    delta_str = f" Δ={greeks.delta:.4f}" if greeks and greeks.delta is not None else ""
                    gamma_str = f" Γ={greeks.gamma:.4f}" if greeks and greeks.gamma is not None else ""

                    signals.append(
                        _make_signal(
                            source="yf_options_do",
                            signal_type="option_greeks",
                            value=greeks.delta if greeks else None,
                            interpretation=(
                                f"{symbol} {side} K={c.strike} {c.expiration}: "
                                f"IV={c.implied_volatility:.1%}" if c.implied_volatility else "IV=N/A"
                                + delta_str + gamma_str
                                + (f" bid={c.bid} ask={c.ask}" if c.bid else "")
                                + (f" OI={c.open_interest}" if c.open_interest else "")
                            ),
                            confidence=0.60,
                            source_url=f"https://finance.yahoo.com/quote/{symbol}/options",
                            metadata={
                                "symbol": symbol,
                                "contract_symbol": c.contract_symbol,
                                "option_type": c.option_type,
                                "strike": c.strike,
                                "expiration": c.expiration,
                                "implied_volatility": c.implied_volatility,
                                "last_price": c.last_price,
                                "bid": c.bid,
                                "ask": c.ask,
                                "mid": c.mid,
                                "volume": c.volume,
                                "open_interest": c.open_interest,
                                "in_the_money": c.in_the_money,
                                "underlying_price": underlying,
                                **meta_greeks,
                            },
                        )
                    )

            _emit_contracts(chain.calls, "CALL")
            _emit_contracts(chain.puts, "PUT")

        return signals
