"""Digital Oracle inspired macro providers.

The classes in this module intentionally expose the same provider names used by
the upstream Digital Oracle project while normalizing outputs to
``MacroSignal``. Providers never fabricate values: optional dependencies or
missing configuration produce an empty signal list, and hard failures are
handled by ``MacroDataManager``.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal
from kronos_fincept.web_search import WebSearchClient


CFTC_SODA_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
TREASURY_RATES_CSV_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv"
)
TREASURY_CURVE_TYPES = {
    "nominal": "daily_treasury_yield_curve",
    "real": "daily_treasury_real_yield_curve",
}
YAHOO_ASSET_SYMBOLS = (
    (r"黄金|gold|xau|gc=/?f", "GC=F", "黄金期货"),
    (r"白银|silver|xag|si=/?f", "SI=F", "白银期货"),
    (r"brent|布伦特|bz=/?f", "BZ=F", "Brent 原油期货"),
    (r"原油|石油|wti|crude|oil|cl=/?f", "CL=F", "WTI 原油期货"),
    (r"铜|copper|hg=/?f", "HG=F", "铜期货"),
    (r"vix|恐慌", "^VIX", "VIX 波动率指数"),
)
CFTC_COMMODITY_PATTERNS = (
    (r"黄金|gold|xau|gc=/?f", "GOLD"),
    (r"白银|silver|xag|si=/?f", "SILVER"),
    (r"原油|石油|wti|crude|oil|cl=/?f|brent|布伦特|bz=/?f", "CRUDE"),
    (r"铜|copper|hg=/?f", "COPPER"),
)


_HTTP_USER_AGENT = "Mozilla/5.0 (compatible; KronosFinceptLab/10.5; +https://github.com/DDDFXYqiming/KronosFinceptLab)"


def _encode_params(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def _request_headers(accept: str) -> dict[str, str]:
    return {
        "Accept": accept,
        "User-Agent": _HTTP_USER_AGENT,
        "Connection": "close",
    }


def _request(url: str, *, params: dict[str, Any] | None = None, accept: str = "application/json") -> urllib.request.Request:
    return urllib.request.Request(
        _encode_params(url, params),
        headers=_request_headers(accept),
    )


def _get_json(url: str, *, params: dict[str, Any] | None = None, timeout: int = 8) -> Any:
    with urllib.request.urlopen(_request(url, params=params), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_text(url: str, *, params: dict[str, Any] | None = None, timeout: int = 8) -> str:
    full_url = _encode_params(url, params)
    accept = "text/csv,text/plain,*/*"
    try:
        import requests  # type: ignore
    except Exception:
        with urllib.request.urlopen(_request(url, params=params, accept=accept), timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    response = requests.get(full_url, headers=_request_headers(accept), timeout=timeout)
    response.raise_for_status()
    return str(response.text)


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _query_text(query: MacroQuery) -> str:
    parts = [query.question or "", query.market or "", " ".join(query.symbols or ())]
    return " ".join(part for part in parts if part).lower()


def _infer_yahoo_symbol(query: MacroQuery, *, default: str = "SPY") -> tuple[str, str]:
    if query.symbols:
        raw_symbol = str(query.symbols[0]).strip()
        text = raw_symbol.lower()
        for pattern, symbol, label in YAHOO_ASSET_SYMBOLS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return symbol, label
        return raw_symbol.upper(), raw_symbol.upper()
    text = _query_text(query)
    for pattern, symbol, label in YAHOO_ASSET_SYMBOLS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return symbol, label
    return default, default


def _infer_cftc_commodity(query: MacroQuery, *, default: str = "GOLD") -> str:
    text = _query_text(query)
    for pattern, commodity in CFTC_COMMODITY_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return commodity
    return default


def _soql_like(value: str) -> str:
    return value.upper().replace("'", "''")


def _date_prefix(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if text else None


def _row_number(row: dict[str, Any], *keys: str) -> float | None:
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = row.get(key)
        if value is None:
            value = normalized.get(key.strip().lower())
        number = _number(value)
        if number is not None:
            return number
    return None


def _latest_curve_row(year: int, curve_kind: str, *, timeout: int | float = 8) -> dict[str, Any] | None:
    curve_type = TREASURY_CURVE_TYPES[curve_kind]
    text = _get_text(f"{TREASURY_RATES_CSV_URL}/{year}/all", params={"type": curve_type}, timeout=timeout)
    import csv
    from io import StringIO

    reader = csv.DictReader(StringIO(text))
    for row in reader:
        if row and row.get("Date"):
            return dict(row)
    return None


def _primary_cot_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    first_date = _date_prefix(rows[0].get("report_date_as_yyyy_mm_dd"))
    candidates = [row for row in rows if _date_prefix(row.get("report_date_as_yyyy_mm_dd")) == first_date] or rows[:1]
    return max(candidates, key=lambda row: _row_number(row, "open_interest_all") or 0.0)


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
    capabilities = ("yield_curve", "rates", "real_yields", "breakeven_inflation")

    def _fetch_curve_rows(self, year: int, *, timeout_seconds: float) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, str]]:
        errors: dict[str, str] = {}
        rows: dict[str, dict[str, Any] | None] = {
            "nominal": None,
            "real": None,
        }
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        futures = {
            executor.submit(_latest_curve_row, year, curve_type, timeout=timeout_seconds): curve_type
            for curve_type in rows
        }
        try:
            done, pending = concurrent.futures.wait(
                futures.keys(),
                timeout=timeout_seconds,
                return_when=concurrent.futures.ALL_COMPLETED,
            )
            for future in done:
                curve_type = futures[future]
                try:
                    rows[curve_type] = future.result(timeout=0)
                except Exception as exc:
                    errors[curve_type] = str(exc)
            for future in pending:
                curve_type = futures[future]
                errors[curve_type] = f"timeout while fetching {curve_type} curve after {timeout_seconds:g}s"
                future.cancel()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return rows["nominal"], rows["real"], errors

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        year = date.today().year
        nominal_row, real_row, errors = self._fetch_curve_rows(year, timeout_seconds=12.0)

        signals: list[MacroSignal] = []
        nominal_10y = _row_number(nominal_row or {}, "10 Yr", "10 YR", "10Y")
        nominal_2y = _row_number(nominal_row or {}, "2 Yr", "2 YR", "2Y")
        real_10y = _row_number(real_row or {}, "10 Yr", "10 YR", "10Y")
        spread = round(nominal_10y - nominal_2y, 4) if nominal_10y is not None and nominal_2y is not None else None
        if nominal_row:
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="yield_curve_10y_2y_spread",
                    value=spread,
                    interpretation="美国 10Y-2Y 名义国债收益率曲线斜率，负值通常提示衰退定价或货币政策压力。",
                    time_horizon="medium",
                    confidence=0.72 if spread is not None else 0.4,
                    observed_at=str(nominal_row.get("Date") or ""),
                    source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
                    metadata={"10y": nominal_10y, "2y": nominal_2y, "curve_kind": "nominal", "degraded_errors": errors},
                )
            )
        if real_row:
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="real_yield_10y",
                    value=real_10y,
                    interpretation="美国 10Y TIPS 实际收益率，黄金通常对实际利率上行承压、对实际利率下行受益。",
                    time_horizon="medium",
                    confidence=0.74 if real_10y is not None else 0.42,
                    observed_at=str(real_row.get("Date") or ""),
                    source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
                    metadata={"10y_real": real_10y, "curve_kind": "real", "degraded_errors": errors},
                )
            )
        if nominal_10y is not None and real_10y is not None:
            breakeven = round(nominal_10y - real_10y, 4)
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="breakeven_10y",
                    value=breakeven,
                    interpretation="美国 10Y 盈亏平衡通胀率，由名义 10Y 收益率减实际 10Y 收益率得到，反映长期通胀预期。",
                    time_horizon="medium",
                    confidence=0.7,
                    observed_at=str((real_row or nominal_row or {}).get("Date") or ""),
                    source_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
                    metadata={"10y_nominal": nominal_10y, "10y_real": real_10y, "degraded_errors": errors},
                )
            )
        return signals


class CftcCotProvider(MacroProvider):
    provider_id = "cftc_cot"
    display_name = "CFTC COT"
    capabilities = ("futures_positioning", "institutional_flow")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        commodity = _infer_cftc_commodity(query)
        payload = _get_json(
            CFTC_SODA_URL,
            params={
                "$limit": max(1, min(max(query.limit, 5), 20)),
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$where": f"commodity_name like '%{_soql_like(commodity)}%'",
            },
        )
        rows = [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
        row = _primary_cot_row(rows)
        if not isinstance(row, dict):
            return []
        long_value = _row_number(row, "m_money_positions_long_all")
        short_value = _row_number(row, "m_money_positions_short_all")
        prod_long = _row_number(row, "prod_merc_positions_long_all")
        prod_short = _row_number(row, "prod_merc_positions_short_all")
        open_interest = _row_number(row, "open_interest_all")
        net = round(long_value - short_value, 4) if long_value is not None and short_value is not None else None
        commercial_net = round(prod_long - prod_short, 4) if prod_long is not None and prod_short is not None else None
        observed_at = _date_prefix(row.get("report_date_as_yyyy_mm_dd"))
        return [
            _signal(
                source=self.provider_id,
                signal_type="managed_money_net_position",
                value=net,
                interpretation="CFTC 管理基金黄金/商品净仓位，代表期货市场趋势资金方向。",
                time_horizon="medium",
                confidence=0.66 if net is not None else 0.4,
                observed_at=observed_at,
                source_url="https://publicreporting.cftc.gov/",
                metadata={
                    "commodity_query": commodity,
                    "commodity": row.get("commodity_name"),
                    "market_name": row.get("market_and_exchange_names"),
                    "long": long_value,
                    "short": short_value,
                    "open_interest": open_interest,
                    "commercial_net": commercial_net,
                },
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
        symbol, label = _infer_yahoo_symbol(query)
        if yf is None or not symbol:
            return []
        history = yf.Ticker(symbol).history(period="1mo")
        if history is None or getattr(history, "empty", True):
            return []
        close = history["Close"]
        latest = float(close.iloc[-1])
        first = float(close.iloc[0])
        change = round(latest / first - 1.0, 6) if first else None
        return [
            _signal(
                source=self.provider_id,
                signal_type="price_trend_1m",
                value=change,
                interpretation=f"{label}（{symbol}）最近 1 个月价格趋势。",
                time_horizon="short",
                confidence=0.64 if change is not None else 0.4,
                source_url="https://finance.yahoo.com/",
                metadata={"symbol": symbol, "label": label, "latest": latest, "first": first},
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
