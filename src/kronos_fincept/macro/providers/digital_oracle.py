"""Digital Oracle inspired macro providers.

The classes in this module intentionally expose the same provider names used by
the upstream Digital Oracle project while normalizing outputs to
``MacroSignal``. Providers never fabricate values: optional dependencies or
missing configuration produce an empty signal list, and hard failures are
handled by ``MacroDataManager``.
"""

from __future__ import annotations

import concurrent.futures
import csv
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider, MacroProviderUnavailable
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal
from kronos_fincept.web_search import WebSearchClient


CFTC_SODA_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
BIS_BULK_DOWNLOADS = {
    "policy_rates": "https://data.bis.org/api/v2/data/BIS,WS_CBPOL,1.0/all/all?format=csvfile",
    "credit_gap": "https://data.bis.org/api/v2/data/BIS,WS_CREDIT_GAP,1.0/all/all?format=csvfile",
    "global_liquidity": "https://data.bis.org/api/v2/data/BIS,WS_GLI,1.0/all/all?format=csvfile",
}
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


def _get_zip_csv_rows(url: str, *, timeout: int = 10) -> list[dict[str, Any]]:
    with urllib.request.urlopen(_request(url, accept="application/zip,*/*"), timeout=timeout) as response:
        raw = response.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        csv_name = next((name for name in archive.namelist() if name.lower().endswith(".csv")), None)
        if not csv_name:
            return []
        text = archive.read(csv_name).decode("utf-8-sig", errors="replace")
    return [dict(row) for row in csv.DictReader(io.StringIO(text)) if row]


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


def _infer_sec_ticker(query: MacroQuery) -> str | None:
    for raw in query.symbols or ():
        candidate = str(raw).strip().upper()
        if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", candidate):
            return candidate.replace(".", "-")
    text = query.question or ""
    matches = re.findall(r"\b[A-Z]{1,5}\b", text)
    ignored = {"GDP", "CPI", "PMI", "FOMC", "ETF", "USD", "BTC", "ETH", "VIX"}
    for match in matches:
        if match not in ignored:
            return match
    return None


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


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = row.get(key)
        if value is None:
            value = normalized.get(key.strip().lower())
        if value not in (None, ""):
            return value
    return None


def _row_text(row: dict[str, Any]) -> str:
    return " ".join(str(value or "") for value in row.values()).lower()


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
        ticker = _infer_sec_ticker(query)
        if not ticker:
            raise MacroProviderUnavailable("EDGAR requires a US ticker symbol to fetch company filings.")
        ticker_row = self._lookup_ticker(ticker)
        if not ticker_row:
            return []
        cik = f"{int(ticker_row['cik_str']):010d}"
        submissions = _get_json(SEC_SUBMISSIONS_URL.format(cik=cik), timeout=8)
        recent = (submissions.get("filings") or {}).get("recent") if isinstance(submissions, dict) else {}
        if not isinstance(recent, dict):
            return []

        forms = recent.get("form") or []
        filing_dates = recent.get("filingDate") or []
        accessions = recent.get("accessionNumber") or []
        documents = recent.get("primaryDocument") or []
        accepted = recent.get("acceptanceDateTime") or []
        company = str(submissions.get("name") or ticker_row.get("title") or ticker)
        signals: list[MacroSignal] = []
        for index, form in enumerate(forms):
            form_text = str(form or "")
            if form_text not in {"10-K", "10-Q", "8-K", "6-K", "20-F", "40-F", "S-1", "4", "13F-HR"}:
                continue
            accession = str(accessions[index] if index < len(accessions) else "")
            document = str(documents[index] if index < len(documents) else "")
            filing_date = str(filing_dates[index] if index < len(filing_dates) else "")
            clean_accession = accession.replace("-", "")
            source_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(ticker_row['cik_str'])}/{clean_accession}/{document}"
                if accession and document
                else None
            )
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="sec_recent_filing",
                    value=form_text,
                    interpretation=f"{company} 最近提交 {form_text}，用于核对公司披露、风险事件或基本面变化。",
                    time_horizon="mixed",
                    confidence=0.66,
                    observed_at=filing_date or (str(accepted[index]) if index < len(accepted) else None),
                    source_url=source_url,
                    metadata={
                        "ticker": ticker,
                        "cik": cik,
                        "company": company,
                        "form_type": form_text,
                        "filing_date": filing_date,
                        "accession_number": accession,
                        "data_quality": "official_sec_filing",
                    },
                )
            )
            if len(signals) >= max(1, query.limit):
                break
        return signals

    def _lookup_ticker(self, ticker: str) -> dict[str, Any] | None:
        payload = _get_json(SEC_COMPANY_TICKERS_URL, timeout=8)
        rows = payload.values() if isinstance(payload, dict) else payload
        if not isinstance(rows, list) and not hasattr(rows, "__iter__"):
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("ticker") or "").upper().replace(".", "-") == ticker:
                return row
        return None


class BisProvider(MacroProvider):
    provider_id = "bis"
    display_name = "BIS"
    capabilities = ("policy_rates", "credit_gap")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        signals: list[MacroSignal] = []
        for topic, url in BIS_BULK_DOWNLOADS.items():
            rows = _get_zip_csv_rows(url, timeout=10)
            row = self._select_latest_us_row(rows)
            if not row:
                continue
            value = _row_number(row, "OBS_VALUE", "ObsValue", "value", "Value")
            period = str(_row_value(row, "TIME_PERIOD", "Time period", "time_period", "TIME") or "")
            label = _row_value(row, "series_name", "Series", "TITLE", "Indicator", "indicator") or topic
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type=f"bis_{topic}",
                    value=value,
                    interpretation=f"BIS {label} 最新观测值，用于观察政策利率、信用周期或全球流动性。",
                    time_horizon="long" if topic == "credit_gap" else "mixed",
                    confidence=0.67 if value is not None else 0.45,
                    observed_at=period or None,
                    source_url="https://data.bis.org/",
                    metadata={
                        "topic": topic,
                        "period": period,
                        "data_quality": "official_bis_statistics",
                        "raw_keys": list(row.keys())[:20],
                    },
                )
            )
            if len(signals) >= max(1, query.limit):
                break
        return signals

    def _select_latest_us_row(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        candidates = [
            row
            for row in rows
            if _row_number(row, "OBS_VALUE", "ObsValue", "value", "Value") is not None
            and re.search(r"\b(us|united states|usa)\b", _row_text(row), flags=re.IGNORECASE)
        ]
        if not candidates:
            candidates = [
                row
                for row in rows
                if _row_number(row, "OBS_VALUE", "ObsValue", "value", "Value") is not None
            ]
        if not candidates:
            return None
        return max(candidates, key=lambda row: str(_row_value(row, "TIME_PERIOD", "time_period", "TIME") or ""))


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
    capabilities = ("options_chain", "implied_volatility", "skew", "max_pain")

    def __init__(self, yfinance_loader: Any | None = None) -> None:
        self._yfinance_loader = yfinance_loader

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        yf = self._load_yfinance()
        symbol, label = _infer_yahoo_symbol(query)
        if yf is None or not symbol:
            return []
        ticker = yf.Ticker(symbol)
        expirations = getattr(ticker, "options", ()) or ()
        if not expirations:
            return []

        chains: list[tuple[str, Any, Any]] = []
        for expiration in list(expirations)[:2]:
            try:
                chain = ticker.option_chain(expiration)
            except Exception:
                continue
            chains.append((str(expiration), getattr(chain, "calls", None), getattr(chain, "puts", None)))
        if not chains:
            return []

        front_expiry, front_calls, front_puts = chains[0]
        spot = _latest_ticker_close(ticker)
        if spot is None:
            spot = _median(_option_strikes(front_calls) + _option_strikes(front_puts))

        front_call_iv = _mean_column(front_calls, "impliedVolatility")
        front_put_iv = _mean_column(front_puts, "impliedVolatility")
        front_iv = _mean_values([front_call_iv, front_put_iv])
        atm_iv = _mean_values(
            [
                _nearest_option_iv(front_calls, spot),
                _nearest_option_iv(front_puts, spot),
            ]
        )
        put_skew_iv = _nearest_option_iv(front_puts, spot * 0.95 if spot is not None else None)
        call_skew_iv = _nearest_option_iv(front_calls, spot * 1.05 if spot is not None else None)
        skew = round(put_skew_iv - call_skew_iv, 6) if put_skew_iv is not None and call_skew_iv is not None else None
        oi_ratio = _safe_ratio(_sum_column(front_puts, "openInterest"), _sum_column(front_calls, "openInterest"))
        volume_ratio = _safe_ratio(_sum_column(front_puts, "volume"), _sum_column(front_calls, "volume"))
        max_pain = _max_pain_strike(front_calls, front_puts)

        signals: list[MacroSignal] = []
        if atm_iv is not None:
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="options_atm_iv",
                    value=round(atm_iv, 6),
                    interpretation=f"{label}（{symbol}）近月平值期权隐含波动率。",
                    time_horizon="short",
                    confidence=0.68,
                    source_url="https://finance.yahoo.com/",
                    metadata={
                        "symbol": symbol,
                        "label": label,
                        "expiration": front_expiry,
                        "spot": spot,
                        "atm_iv": atm_iv,
                        "data_quality": "yfinance_options_chain",
                    },
                )
            )
        if skew is not None:
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="options_skew_proxy",
                    value=skew,
                    interpretation=f"{label}（{symbol}）近月 95% put 与 105% call 的 IV skew 代理。",
                    time_horizon="short",
                    confidence=0.62,
                    source_url="https://finance.yahoo.com/",
                    metadata={
                        "symbol": symbol,
                        "expiration": front_expiry,
                        "put_95_iv": put_skew_iv,
                        "call_105_iv": call_skew_iv,
                        "data_quality": "yfinance_options_chain",
                    },
                )
            )
        if len(chains) > 1:
            next_expiry, next_calls, next_puts = chains[1]
            next_iv = _mean_values(
                [
                    _mean_column(next_calls, "impliedVolatility"),
                    _mean_column(next_puts, "impliedVolatility"),
                ]
            )
            if front_iv is not None and next_iv is not None:
                signals.append(
                    _signal(
                        source=self.provider_id,
                        signal_type="options_iv_term_structure",
                        value=round(next_iv - front_iv, 6),
                        interpretation=f"{label}（{symbol}）近月与次近月期权 IV 期限结构。",
                        time_horizon="short",
                        confidence=0.61,
                        source_url="https://finance.yahoo.com/",
                        metadata={
                            "symbol": symbol,
                            "front_expiration": front_expiry,
                            "next_expiration": next_expiry,
                            "front_iv": front_iv,
                            "next_iv": next_iv,
                            "data_quality": "yfinance_options_chain",
                        },
                    )
                )
        if oi_ratio is not None:
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="options_put_call_open_interest",
                    value=round(oi_ratio, 6),
                    interpretation=f"{label}（{symbol}）近月期权 put/call open interest 比率。",
                    time_horizon="short",
                    confidence=0.6,
                    source_url="https://finance.yahoo.com/",
                    metadata={"symbol": symbol, "expiration": front_expiry, "data_quality": "yfinance_options_chain"},
                )
            )
        if volume_ratio is not None:
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="options_put_call_volume",
                    value=round(volume_ratio, 6),
                    interpretation=f"{label}（{symbol}）近月期权 put/call volume 比率。",
                    time_horizon="short",
                    confidence=0.58,
                    source_url="https://finance.yahoo.com/",
                    metadata={"symbol": symbol, "expiration": front_expiry, "data_quality": "yfinance_options_chain"},
                )
            )
        if max_pain is not None:
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="options_max_pain",
                    value=max_pain,
                    interpretation=f"{label}（{symbol}）近月期权 max pain 行权价估计。",
                    time_horizon="event",
                    confidence=0.55,
                    source_url="https://finance.yahoo.com/",
                    metadata={
                        "symbol": symbol,
                        "expiration": front_expiry,
                        "max_pain": max_pain,
                        "data_quality": "yfinance_options_chain",
                    },
                )
            )
        return signals

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
        try:
            payload = _get_json("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", timeout=3)
        except Exception:
            return self._vix_proxy_signal()
        data = payload.get("fear_and_greed") if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            return self._vix_proxy_signal()
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

    def _vix_proxy_signal(self) -> list[MacroSignal]:
        try:
            payload = _get_json(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
                params={"range": "1mo", "interval": "1d"},
                timeout=8,
            )
        except Exception:
            return []
        chart = payload.get("chart") if isinstance(payload, dict) else {}
        results = chart.get("result") if isinstance(chart, dict) else []
        first_result = results[0] if isinstance(results, list) and results else {}
        quote = (((first_result.get("indicators") or {}).get("quote") or [{}])[0]) if isinstance(first_result, dict) else {}
        closes = [_number(item) for item in (quote.get("close") or []) if _number(item) is not None]
        if len(closes) < 2:
            return []
        latest = closes[-1]
        first = closes[0]
        if latest is None or first in (None, 0):
            return []
        change = round(latest / first - 1.0, 6)
        observed_at = None
        timestamps = first_result.get("timestamp") if isinstance(first_result, dict) else []
        if isinstance(timestamps, list) and timestamps:
            try:
                observed_at = str(date.fromtimestamp(int(timestamps[-1])))
            except Exception:
                observed_at = None
        return [
            _signal(
                source=self.provider_id,
                signal_type="vix_fear_proxy",
                value=change,
                interpretation="CNN Fear & Greed 接口不可用时，使用 VIX 近 1 个月变化作为风险情绪代理；VIX 上行通常表示恐慌升温。",
                time_horizon="short",
                confidence=0.52,
                observed_at=observed_at,
                source_url="https://finance.yahoo.com/quote/%5EVIX/",
                metadata={
                    "proxy": "vix_1mo_change_yahoo_chart",
                    "latest": latest,
                    "first": first,
                    "data_quality": "fallback_yahoo_chart_vix",
                },
            )
        ]


class CMEFedWatchProvider(MacroProvider):
    provider_id = "cme_fedwatch"
    display_name = "CME FedWatch"
    capabilities = ("fomc_probability", "rates")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        payload = self._fetch_payload()
        rows = self._extract_probability_rows(payload)
        if not rows:
            return []
        signals: list[MacroSignal] = []
        for row in rows[: max(1, query.limit)]:
            probability = _number(row.get("probability"))
            label = str(row.get("target_rate") or row.get("rate_range") or row.get("scenario") or "FOMC outcome")
            meeting_date = str(row.get("meeting_date") or row.get("meetingDate") or "")
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="fomc_rate_probability",
                    value=probability,
                    interpretation=f"CME FedWatch 隐含 {meeting_date or '下一次 FOMC'} {label} 概率。",
                    time_horizon="event",
                    confidence=0.7 if probability is not None else 0.45,
                    observed_at=meeting_date or None,
                    source_url="https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
                    metadata={
                        "meeting_date": meeting_date,
                        "target_rate": label,
                        "data_quality": "cme_fedwatch_api" if os.getenv("CME_FEDWATCH_ENDPOINT") else "compatible_fedwatch_payload",
                    },
                )
            )
        return signals

    def _fetch_payload(self) -> Any:
        endpoint = os.getenv("CME_FEDWATCH_ENDPOINT")
        if endpoint:
            params: dict[str, Any] = {}
            api_key = os.getenv("CME_FEDWATCH_API_KEY")
            if api_key:
                params[os.getenv("CME_FEDWATCH_API_KEY_PARAM", "apiKey")] = api_key
            return _get_json(endpoint, params=params or None, timeout=8)
        try:
            from cme_fedwatch import get_probabilities  # type: ignore
        except Exception as exc:
            raise MacroProviderUnavailable(
                "CME FedWatch requires CME_FEDWATCH_ENDPOINT or optional cme_fedwatch package."
            ) from exc
        return get_probabilities(meeting="next")

    def _extract_probability_rows(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        meetings = payload.get("meetings") or payload.get("data") or payload.get("probabilities") or []
        if isinstance(meetings, dict):
            meetings = [meetings]
        rows: list[dict[str, Any]] = []
        if not isinstance(meetings, list):
            return rows
        for meeting in meetings:
            if not isinstance(meeting, dict):
                continue
            meeting_date = meeting.get("meeting_date") or meeting.get("meetingDate") or meeting.get("date")
            probabilities = meeting.get("probabilities") or meeting.get("outcomes") or []
            if isinstance(probabilities, dict):
                probabilities = [
                    {"target_rate": key, "probability": value}
                    for key, value in probabilities.items()
                ]
            if not isinstance(probabilities, list):
                continue
            for item in probabilities:
                if not isinstance(item, dict):
                    continue
                probability = _number(
                    item.get("probability")
                    if item.get("probability") is not None
                    else item.get("prob")
                    if item.get("prob") is not None
                    else item.get("pct")
                )
                if probability is not None and probability > 1.0:
                    probability = probability / 100.0
                rows.append(
                    {
                        "meeting_date": meeting_date,
                        "target_rate": item.get("target_rate") or item.get("targetRate") or item.get("range"),
                        "probability": probability,
                    }
                )
        return sorted(rows, key=lambda row: float(row.get("probability") or 0.0), reverse=True)


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
    capabilities = ("crypto_derivatives", "options_iv", "futures_curve")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        currency = _infer_deribit_currency(query)
        options_payload = _get_json(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
            params={"currency": currency, "kind": "option"},
        )
        futures_payload = _get_json(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
            params={"currency": currency, "kind": "future"},
        )
        option_rows = options_payload.get("result") if isinstance(options_payload, dict) else []
        future_rows = futures_payload.get("result") if isinstance(futures_payload, dict) else []
        option_rows = option_rows if isinstance(option_rows, list) else []
        future_rows = future_rows if isinstance(future_rows, list) else []
        signals: list[MacroSignal] = []

        option_points = _deribit_option_points(option_rows)
        underlying = _deribit_underlying_price(option_rows) or _deribit_underlying_price(future_rows)
        if option_points and underlying is not None:
            atm_iv = _mean_values(
                [
                    _nearest_deribit_iv(option_points, underlying, option_type="C"),
                    _nearest_deribit_iv(option_points, underlying, option_type="P"),
                ]
            )
            if atm_iv is not None:
                signals.append(
                    _signal(
                        source=self.provider_id,
                        signal_type="deribit_atm_iv",
                        value=round(atm_iv, 6),
                        interpretation=f"Deribit {currency} 平值期权隐含波动率。",
                        time_horizon="short",
                        confidence=0.66,
                        source_url="https://www.deribit.com/",
                        metadata={
                            "currency": currency,
                            "underlying_price": underlying,
                            "data_quality": "deribit_public_api",
                        },
                    )
                )
            put_iv = _nearest_deribit_iv(option_points, underlying * 0.95, option_type="P")
            call_iv = _nearest_deribit_iv(option_points, underlying * 1.05, option_type="C")
            if put_iv is not None and call_iv is not None:
                signals.append(
                    _signal(
                        source=self.provider_id,
                        signal_type="deribit_skew_proxy",
                        value=round(put_iv - call_iv, 6),
                        interpretation=f"Deribit {currency} 95% put 与 105% call 的 IV skew 代理。",
                        time_horizon="short",
                        confidence=0.6,
                        source_url="https://www.deribit.com/",
                        metadata={
                            "currency": currency,
                            "underlying_price": underlying,
                            "put_95_iv": put_iv,
                            "call_105_iv": call_iv,
                            "data_quality": "deribit_public_api",
                        },
                    )
                )
            term = _deribit_term_structure(option_points)
            if term is not None:
                front_expiry, next_expiry, front_iv, next_iv = term
                signals.append(
                    _signal(
                        source=self.provider_id,
                        signal_type="deribit_iv_term_structure",
                        value=round(next_iv - front_iv, 6),
                        interpretation=f"Deribit {currency} 期权 IV 期限结构。",
                        time_horizon="short",
                        confidence=0.6,
                        source_url="https://www.deribit.com/",
                        metadata={
                            "currency": currency,
                            "front_expiry": front_expiry,
                            "next_expiry": next_expiry,
                            "front_iv": front_iv,
                            "next_iv": next_iv,
                            "data_quality": "deribit_public_api",
                        },
                    )
                )

        basis = _deribit_futures_basis(future_rows)
        if basis is not None:
            instrument, perpetual, basis_value = basis
            signals.append(
                _signal(
                    source=self.provider_id,
                    signal_type="crypto_futures_basis",
                    value=round(basis_value, 6),
                    interpretation=f"Deribit {currency} 远期期货相对永续/现货的 basis。",
                    time_horizon="short",
                    confidence=0.58,
                    source_url="https://www.deribit.com/",
                    metadata={
                        "currency": currency,
                        "instrument": instrument,
                        "reference": perpetual,
                        "data_quality": "deribit_public_api",
                    },
                )
            )
        return signals


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
        return _normalise_iv(float(series.mean())) if column == "impliedVolatility" else float(series.mean())
    except Exception:
        return None


def _mean_values(values: list[float | None]) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _normalise_iv(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 100.0 if value > 3.0 else value


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _sum_column(frame: Any, column: str) -> float | None:
    try:
        series = frame[column].dropna()
        if len(series) == 0:
            return None
        return float(series.sum())
    except Exception:
        return None


def _latest_ticker_close(ticker: Any) -> float | None:
    try:
        history = ticker.history(period="5d")
        if history is None or getattr(history, "empty", True):
            return None
        return _number(history["Close"].dropna().iloc[-1])
    except Exception:
        return None


def _option_rows(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    try:
        return [row.to_dict() for _, row in frame.iterrows()]
    except Exception:
        return []


def _option_row_number(row: dict[str, Any], key: str) -> float | None:
    return _number(row.get(key))


def _option_strikes(frame: Any) -> list[float]:
    return [strike for row in _option_rows(frame) if (strike := _option_row_number(row, "strike")) is not None]


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _nearest_option_iv(frame: Any, target_strike: float | None) -> float | None:
    if target_strike is None:
        return None
    best_row: dict[str, Any] | None = None
    best_distance: float | None = None
    for row in _option_rows(frame):
        strike = _option_row_number(row, "strike")
        iv = _normalise_iv(_option_row_number(row, "impliedVolatility"))
        if strike is None or iv is None:
            continue
        distance = abs(strike - target_strike)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_row = row
    if best_row is None:
        return None
    return _normalise_iv(_option_row_number(best_row, "impliedVolatility"))


def _max_pain_strike(calls: Any, puts: Any) -> float | None:
    call_rows = _option_rows(calls)
    put_rows = _option_rows(puts)
    strikes = sorted({strike for strike in _option_strikes(calls) + _option_strikes(puts)})
    if not strikes:
        return None
    best_strike: float | None = None
    best_payout: float | None = None
    for settlement in strikes:
        call_payout = sum(
            max(0.0, settlement - strike) * (oi or 0.0)
            for row in call_rows
            if (strike := _option_row_number(row, "strike")) is not None
            for oi in [_option_row_number(row, "openInterest")]
        )
        put_payout = sum(
            max(0.0, strike - settlement) * (oi or 0.0)
            for row in put_rows
            if (strike := _option_row_number(row, "strike")) is not None
            for oi in [_option_row_number(row, "openInterest")]
        )
        payout = call_payout + put_payout
        if best_payout is None or payout < best_payout:
            best_payout = payout
            best_strike = settlement
    return best_strike


def _infer_deribit_currency(query: MacroQuery) -> str:
    text = _query_text(query)
    if re.search(r"\beth\b|ethereum|以太坊", text, flags=re.IGNORECASE):
        return "ETH"
    return "BTC"


def _deribit_underlying_price(rows: list[dict[str, Any]]) -> float | None:
    for row in rows:
        for key in ("underlying_price", "estimated_delivery_price", "index_price", "mark_price"):
            value = _number(row.get(key))
            if value is not None and value > 0:
                return value
    return None


def _parse_deribit_option(row: dict[str, Any]) -> dict[str, Any] | None:
    instrument = str(row.get("instrument_name") or "")
    parts = instrument.split("-")
    if len(parts) < 4:
        return None
    strike = _number(parts[2])
    option_type = parts[3].upper()[:1]
    iv = _normalise_iv(
        _number(row.get("mark_iv"))
        or _mean_values([_number(row.get("bid_iv")), _number(row.get("ask_iv"))])
    )
    if strike is None or option_type not in {"C", "P"} or iv is None:
        return None
    return {
        "instrument": instrument,
        "expiry": parts[1],
        "strike": strike,
        "type": option_type,
        "iv": iv,
        "underlying_price": _number(row.get("underlying_price")),
    }


def _deribit_option_points(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        parsed = _parse_deribit_option(row)
        if parsed is not None:
            points.append(parsed)
    return points


def _nearest_deribit_iv(points: list[dict[str, Any]], target_strike: float, *, option_type: str) -> float | None:
    candidates = [point for point in points if point.get("type") == option_type]
    if not candidates:
        return None
    best = min(candidates, key=lambda point: abs(float(point["strike"]) - target_strike))
    return _number(best.get("iv"))


def _deribit_term_structure(points: list[dict[str, Any]]) -> tuple[str, str, float, float] | None:
    by_expiry: dict[str, list[float]] = {}
    for point in points:
        expiry = str(point.get("expiry") or "")
        iv = _number(point.get("iv"))
        if not expiry or iv is None:
            continue
        by_expiry.setdefault(expiry, []).append(iv)
    expiries = sorted(by_expiry)
    if len(expiries) < 2:
        return None
    front, next_expiry = expiries[0], expiries[1]
    front_iv = _mean_values(by_expiry[front])
    next_iv = _mean_values(by_expiry[next_expiry])
    if front_iv is None or next_iv is None:
        return None
    return front, next_expiry, front_iv, next_iv


def _deribit_futures_basis(rows: list[dict[str, Any]]) -> tuple[str, str, float] | None:
    perpetual = next((row for row in rows if "PERPETUAL" in str(row.get("instrument_name", ""))), None)
    dated = next((row for row in rows if "PERPETUAL" not in str(row.get("instrument_name", ""))), None)
    if perpetual is None or dated is None:
        return None
    perpetual_mark = _number(perpetual.get("mark_price"))
    dated_mark = _number(dated.get("mark_price"))
    if perpetual_mark in (None, 0) or dated_mark is None:
        return None
    return (
        str(dated.get("instrument_name") or ""),
        str(perpetual.get("instrument_name") or ""),
        dated_mark / perpetual_mark - 1.0,
    )
