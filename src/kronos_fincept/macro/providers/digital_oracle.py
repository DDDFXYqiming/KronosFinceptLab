"""Digital Oracle inspired macro providers.

The classes in this module intentionally expose the same provider names used by
the upstream Digital Oracle project while normalizing outputs to
``MacroSignal``. Providers never fabricate values: optional dependencies or
missing configuration produce an empty signal list, and hard failures are
handled by ``MacroDataManager``.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal
from kronos_fincept.web_search import WebSearchClient


def _get_json(url: str, *, params: dict[str, Any] | None = None, timeout: int = 8) -> Any:
    if params:
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "KronosFinceptLab/10.1 (+https://github.com/DDDFXYqiming/KronosFinceptLab)",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _signal(
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
        observed_at=observed_at,
        source_url=source_url,
        metadata=metadata or {},
    )


class PolymarketProvider(MacroProvider):
    provider_id = "polymarket"
    display_name = "Polymarket"
    capabilities = ("prediction_market", "event_probability")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        term = (query.question or "macro").strip()[:80]
        payload = _get_json(
            "https://gamma-api.polymarket.com/events",
            params={"active": "true", "closed": "false", "limit": max(1, min(query.limit, 10)), "search": term},
        )
        events = payload if isinstance(payload, list) else []
        signals: list[MacroSignal] = []
        for event in events[: query.limit]:
            markets = event.get("markets") if isinstance(event, dict) else None
            if not isinstance(markets, list) or not markets:
                continue
            market = markets[0]
            probability = _extract_probability(market)
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="prediction_market_probability",
                    value=probability,
                    interpretation=str(event.get("title") or market.get("question") or "Polymarket event"),
                    time_horizon="event",
                    confidence=0.62 if probability is not None else 0.45,
                    source_url=f"https://polymarket.com/event/{event.get('slug')}" if event.get("slug") else None,
                    metadata={"market": market.get("question"), "volume": market.get("volume")},
                )
            )
        return signals


class KalshiProvider(MacroProvider):
    provider_id = "kalshi"
    display_name = "Kalshi"
    capabilities = ("regulated_prediction_market", "event_probability")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        payload = _get_json(
            "https://api.elections.kalshi.com/trade-api/v2/markets",
            params={"limit": max(1, min(query.limit, 20)), "status": "open"},
        )
        markets = payload.get("markets") if isinstance(payload, dict) else []
        signals: list[MacroSignal] = []
        if not isinstance(markets, list):
            return signals
        for market in markets[: query.limit]:
            yes_bid = _number(market.get("yes_bid"))
            yes_ask = _number(market.get("yes_ask"))
            probability = ((yes_bid + yes_ask) / 2.0 / 100.0) if yes_bid is not None and yes_ask is not None else None
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="regulated_event_probability",
                    value=probability,
                    interpretation=str(market.get("title") or market.get("ticker") or "Kalshi market"),
                    time_horizon="event",
                    confidence=0.6 if probability is not None else 0.45,
                    source_url="https://kalshi.com/markets",
                    metadata={"ticker": market.get("ticker"), "volume": market.get("volume")},
                )
            )
        return signals


class USTreasuryProvider(MacroProvider):
    provider_id = "us_treasury"
    display_name = "U.S. Treasury"
    capabilities = ("yield_curve", "rates")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        year = date.today().year
        url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all"
        text = urllib.request.urlopen(url, timeout=8).read().decode("utf-8", errors="replace")
        import csv
        from io import StringIO

        reader = csv.DictReader(StringIO(text))
        latest = next(reader, None)
        if not latest:
            return []
        ten_year = _number(latest.get("10 Yr") or latest.get("10 YR"))
        two_year = _number(latest.get("2 Yr") or latest.get("2 YR"))
        spread = (ten_year - two_year) if ten_year is not None and two_year is not None else None
        return [
            _signal(
                source=self.provider_id,
                signal_type="yield_curve_10y_2y_spread",
                value=spread,
                interpretation="美国 10Y-2Y 国债收益率曲线斜率，负值通常提示衰退定价或货币政策压力。",
                time_horizon="medium",
                confidence=0.72 if spread is not None else 0.4,
                observed_at=latest.get("Date"),
                source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
                metadata={"10y": ten_year, "2y": two_year},
            )
        ]


class CftcCotProvider(MacroProvider):
    provider_id = "cftc_cot"
    display_name = "CFTC COT"
    capabilities = ("futures_positioning", "institutional_flow")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        payload = _get_json(
            "https://publicreporting.cftc.gov/resource/6dca-aqww.json",
            params={"$limit": 1, "$order": "report_date_as_yyyy_mm_dd DESC", "commodity_name": "GOLD"},
        )
        row = payload[0] if isinstance(payload, list) and payload else None
        if not isinstance(row, dict):
            return []
        long_value = _number(row.get("m_money_positions_long_all"))
        short_value = _number(row.get("m_money_positions_short_all"))
        net = (long_value - short_value) if long_value is not None and short_value is not None else None
        return [
            _signal(
                source=self.provider_id,
                signal_type="managed_money_net_position",
                value=net,
                interpretation="CFTC 管理基金黄金净仓位，代表期货市场趋势资金方向。",
                time_horizon="medium",
                confidence=0.64 if net is not None else 0.4,
                observed_at=row.get("report_date_as_yyyy_mm_dd"),
                source_url="https://publicreporting.cftc.gov/",
                metadata={"commodity": row.get("commodity_name"), "long": long_value, "short": short_value},
            )
        ]


class CoinGeckoProvider(MacroProvider):
    provider_id = "coingecko"
    display_name = "CoinGecko"
    capabilities = ("crypto_market", "risk_appetite")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        payload = _get_json("https://api.coingecko.com/api/v3/global")
        data = payload.get("data") if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            return []
        dominance = _number((data.get("market_cap_percentage") or {}).get("btc"))
        change = _number(data.get("market_cap_change_percentage_24h_usd"))
        return [
            _signal(
                source=self.provider_id,
                signal_type="crypto_global_risk_appetite",
                value=change,
                interpretation="全球加密资产总市值 24h 变化，辅助判断风险偏好。",
                time_horizon="short",
                confidence=0.6 if change is not None else 0.4,
                source_url="https://www.coingecko.com/",
                metadata={"btc_dominance_pct": dominance},
            )
        ]


class EdgarProvider(MacroProvider):
    provider_id = "edgar"
    display_name = "SEC EDGAR"
    capabilities = ("sec_filings", "insider_activity")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        return []


class BisProvider(MacroProvider):
    provider_id = "bis"
    display_name = "BIS"
    capabilities = ("policy_rates", "credit_gap")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        return []


class WorldBankProvider(MacroProvider):
    provider_id = "worldbank"
    display_name = "World Bank"
    capabilities = ("macro_economy", "growth")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        payload = _get_json(
            "https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.KD.ZG",
            params={"format": "json", "per_page": 1, "mrv": 1},
        )
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        row = rows[0] if isinstance(rows, list) and rows else None
        if not isinstance(row, dict):
            return []
        value = _number(row.get("value"))
        return [
            _signal(
                source=self.provider_id,
                signal_type="real_gdp_growth",
                value=value,
                interpretation="美国实际 GDP 年增长率，反映宏观增长背景。",
                time_horizon="long",
                confidence=0.68 if value is not None else 0.4,
                observed_at=str(row.get("date") or ""),
                source_url="https://data.worldbank.org/",
            )
        ]


class YFinanceProvider(MacroProvider):
    provider_id = "yfinance_options"
    display_name = "YFinance Options"
    capabilities = ("options_chain", "implied_volatility")

    def __init__(self, yfinance_loader: Any | None = None) -> None:
        self._yfinance_loader = yfinance_loader

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        yf = self._load_yfinance()
        symbol = (query.symbols[0] if query.symbols else "").strip().upper()
        if yf is None or not symbol:
            return []
        ticker = yf.Ticker(symbol)
        expirations = getattr(ticker, "options", ()) or ()
        if not expirations:
            return []
        chain = ticker.option_chain(expirations[0])
        calls = getattr(chain, "calls", None)
        puts = getattr(chain, "puts", None)
        call_iv = _mean_column(calls, "impliedVolatility")
        put_iv = _mean_column(puts, "impliedVolatility")
        if call_iv is None and put_iv is None:
            return []
        return [
            _signal(
                source=self.provider_id,
                signal_type="options_implied_volatility",
                value=round(((call_iv or 0.0) + (put_iv or 0.0)) / (2 if call_iv is not None and put_iv is not None else 1), 4),
                interpretation=f"{symbol} 最近到期期权链平均隐含波动率。",
                time_horizon="short",
                confidence=0.58,
                source_url="https://finance.yahoo.com/",
                metadata={"expiration": expirations[0], "call_iv": call_iv, "put_iv": put_iv},
            )
        ]

    def _load_yfinance(self) -> Any | None:
        if self._yfinance_loader is not None:
            return self._yfinance_loader()
        try:
            import yfinance as yf  # type: ignore

            return yf
        except Exception:
            return None


class FearGreedProvider(MacroProvider):
    provider_id = "fear_greed"
    display_name = "CNN Fear & Greed"
    capabilities = ("market_sentiment",)

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        payload = _get_json("https://production.dataviz.cnn.io/index/fearandgreed/graphdata")
        data = payload.get("fear_and_greed") if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            return []
        score = _number(data.get("score"))
        rating = str(data.get("rating") or "")
        return [
            _signal(
                source=self.provider_id,
                signal_type="market_sentiment",
                value=score,
                interpretation=f"CNN Fear & Greed 指数：{rating or 'unknown'}。",
                time_horizon="short",
                confidence=0.63 if score is not None else 0.4,
                observed_at=str(data.get("timestamp") or ""),
                source_url="https://www.cnn.com/markets/fear-and-greed",
            )
        ]


class CMEFedWatchProvider(MacroProvider):
    provider_id = "cme_fedwatch"
    display_name = "CME FedWatch"
    capabilities = ("fomc_probability", "rates")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        return []


class WebSearchProvider(MacroProvider):
    provider_id = "web_search"
    display_name = "Configured Web Search"
    capabilities = ("public_web", "news")
    requires_api_key = True

    def __init__(self, search_client_factory: Any | None = None) -> None:
        self._search_client_factory = search_client_factory

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        client = self._create_client()
        if client is None or not getattr(client, "is_configured", False):
            return []
        response = client.search(query.question or "macro financial market signals")
        if response.status not in {"completed", "skipped"}:
            return []
        return [
            _signal(
                source=self.provider_id,
                signal_type="public_web_result",
                value=item.title,
                interpretation=item.snippet,
                time_horizon="mixed",
                confidence=0.5,
                source_url=item.url,
                metadata={"search_provider": response.provider},
            )
            for item in response.results[: query.limit]
        ]

    def _create_client(self) -> WebSearchClient | None:
        if self._search_client_factory is not None:
            return self._search_client_factory()
        return WebSearchClient()


class YahooPriceProvider(MacroProvider):
    provider_id = "yahoo_price"
    display_name = "Yahoo Finance Prices"
    capabilities = ("asset_price", "trend")

    def __init__(self, yfinance_loader: Any | None = None) -> None:
        self._yfinance_loader = yfinance_loader

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        yf = self._load_yfinance()
        symbol = query.symbols[0] if query.symbols else "SPY"
        if yf is None:
            return []
        history = yf.Ticker(symbol).history(period="1mo")
        if history is None or getattr(history, "empty", True):
            return []
        close = history["Close"]
        latest = float(close.iloc[-1])
        first = float(close.iloc[0])
        change = (latest / first - 1.0) if first else None
        return [
            _signal(
                source=self.provider_id,
                signal_type="price_trend_1m",
                value=change,
                interpretation=f"{symbol} 最近 1 个月价格趋势。",
                time_horizon="short",
                confidence=0.62 if change is not None else 0.4,
                source_url="https://finance.yahoo.com/",
                metadata={"symbol": symbol, "latest": latest, "first": first},
            )
        ]

    def _load_yfinance(self) -> Any | None:
        if self._yfinance_loader is not None:
            return self._yfinance_loader()
        try:
            import yfinance as yf  # type: ignore

            return yf
        except Exception:
            return None


class DeribitProvider(MacroProvider):
    provider_id = "deribit"
    display_name = "Deribit"
    capabilities = ("crypto_derivatives", "futures_curve")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        payload = _get_json(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
            params={"currency": "BTC", "kind": "future"},
        )
        rows = payload.get("result") if isinstance(payload, dict) else []
        if not isinstance(rows, list) or not rows:
            return []
        perpetual = next((row for row in rows if "PERPETUAL" in str(row.get("instrument_name", ""))), rows[0])
        mark = _number(perpetual.get("mark_price"))
        return [
            _signal(
                source=self.provider_id,
                signal_type="btc_derivatives_mark_price",
                value=mark,
                interpretation="Deribit BTC 衍生品市场价格信号，辅助判断加密风险偏好。",
                time_horizon="short",
                confidence=0.58 if mark is not None else 0.4,
                source_url="https://www.deribit.com/",
                metadata={"instrument": perpetual.get("instrument_name")},
            )
        ]


def create_default_providers() -> list[MacroProvider]:
    return [
        PolymarketProvider(),
        KalshiProvider(),
        USTreasuryProvider(),
        CftcCotProvider(),
        CoinGeckoProvider(),
        EdgarProvider(),
        BisProvider(),
        WorldBankProvider(),
        YFinanceProvider(),
        FearGreedProvider(),
        CMEFedWatchProvider(),
        WebSearchProvider(),
        YahooPriceProvider(),
        DeribitProvider(),
    ]


def _extract_probability(market: dict[str, Any]) -> float | None:
    for key in ("yes_price", "last_trade_price", "best_ask", "best_bid"):
        value = _number(market.get(key))
        if value is not None:
            return value
    outcomes = market.get("outcomePrices")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except json.JSONDecodeError:
            outcomes = None
    if isinstance(outcomes, list) and outcomes:
        return _number(outcomes[0])
    return None


def _mean_column(frame: Any, column: str) -> float | None:
    try:
        series = frame[column].dropna()
        if len(series) == 0:
            return None
        return float(series.mean())
    except Exception:
        return None
