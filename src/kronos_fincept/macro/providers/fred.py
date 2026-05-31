"""FRED macro provider."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider, MacroProviderUnavailable
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal


FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


FRED_SERIES: dict[str, dict[str, str]] = {
    "DGS10": {"label": "U.S. 10Y Treasury yield", "unit": "%", "type": "rates"},
    "FEDFUNDS": {"label": "Effective federal funds rate", "unit": "%", "type": "rates"},
    "T10Y2Y": {"label": "10Y-2Y Treasury spread", "unit": "%", "type": "rates"},
    "T10YIE": {"label": "10Y breakeven inflation", "unit": "%", "type": "inflation"},
    "CPIAUCSL": {"label": "U.S. CPI index", "unit": "index", "type": "inflation"},
    "PCEPI": {"label": "U.S. PCE price index", "unit": "index", "type": "inflation"},
    "PAYEMS": {"label": "Nonfarm payrolls", "unit": "thousands", "type": "labor"},
    "UNRATE": {"label": "Unemployment rate", "unit": "%", "type": "labor"},
    "GDP": {"label": "U.S. GDP", "unit": "billions USD", "type": "growth"},
    "INDPRO": {"label": "Industrial production", "unit": "index", "type": "growth"},
    "RSAFS": {"label": "Retail sales", "unit": "millions USD", "type": "growth"},
    "WALCL": {"label": "Fed balance sheet assets", "unit": "millions USD", "type": "liquidity"},
    "M2SL": {"label": "M2 money supply", "unit": "billions USD", "type": "liquidity"},
    "DCOILWTICO": {"label": "WTI crude oil", "unit": "USD/barrel", "type": "commodities"},
    "DCOILBRENTEU": {"label": "Brent crude oil", "unit": "USD/barrel", "type": "commodities"},
    "VIXCLS": {"label": "VIX", "unit": "index", "type": "risk"},
    "BAMLH0A0HYM2": {"label": "U.S. high-yield spread", "unit": "%", "type": "credit"},
}


class FredProvider(MacroProvider):
    provider_id = "fred"
    display_name = "FRED"
    capabilities = ("us_macro", "rates", "inflation", "labor", "liquidity", "credit")
    requires_api_key = True

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        api_key = os.environ.get("FRED_API_KEY", "").strip()
        if not api_key:
            raise MacroProviderUnavailable("FRED_API_KEY is not configured")

        signals: list[MacroSignal] = []
        for series_id in self._select_series(query):
            observations = self._fetch_observations(series_id, api_key)
            latest = _latest_numeric_observation(observations)
            if latest is None:
                continue
            previous_year = _nearest_previous_year_observation(observations, latest["date"])
            metadata = {
                "series_id": series_id,
                "label": FRED_SERIES[series_id]["label"],
                "unit": FRED_SERIES[series_id]["unit"],
                "data_quality": "fred_observations",
            }
            if previous_year is not None and previous_year.get("value") not in (None, 0):
                metadata["year_ago_value"] = previous_year["value"]
                metadata["yoy_change"] = latest["value"] / previous_year["value"] - 1.0

            signals.append(
                MacroSignal(
                    source=self.provider_id,
                    signal_type=FRED_SERIES[series_id]["type"],
                    value=latest["value"],
                    interpretation=(
                        f"{FRED_SERIES[series_id]['label']} latest value is "
                        f"{latest['value']} {FRED_SERIES[series_id]['unit']}."
                    ),
                    time_horizon="mixed",
                    confidence=0.82,
                    observed_at=latest["date"],
                    source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                    metadata=metadata,
                )
            )
        return signals

    def _select_series(self, query: MacroQuery) -> list[str]:
        text = " ".join(
            [
                query.question or "",
                " ".join(query.symbols),
                str(query.market or ""),
            ]
        ).lower()
        selected: list[str] = []

        def add(*series: str) -> None:
            for item in series:
                if item not in selected:
                    selected.append(item)

        if re.search(r"yield|利率|收益率|fed|美联储|curve|spread|期限|降息|加息", text):
            add("DGS10", "FEDFUNDS", "T10Y2Y", "T10YIE")
        if re.search(r"inflation|通胀|cpi|pce|物价", text):
            add("CPIAUCSL", "PCEPI", "T10YIE")
        if re.search(r"payroll|nonfarm|employment|job|unemployment|就业|非农|失业", text):
            add("PAYEMS", "UNRATE")
        if re.search(r"gdp|growth|recession|增长|衰退|工业|消费|retail", text):
            add("GDP", "INDPRO", "RSAFS")
        if re.search(r"liquidity|m2|balance sheet|流动性|资产负债表|货币", text):
            add("M2SL", "WALCL")
        if re.search(r"oil|crude|brent|wti|原油|石油", text):
            add("DCOILWTICO", "DCOILBRENTEU")
        if re.search(r"vix|risk|credit|spread|高收益|信用|风险", text):
            add("VIXCLS", "BAMLH0A0HYM2")
        if not selected:
            add("DGS10", "FEDFUNDS", "CPIAUCSL", "UNRATE")
        return selected[: max(1, min(query.limit or 5, 8))]

    @staticmethod
    def _fetch_observations(series_id: str, api_key: str) -> list[dict[str, Any]]:
        start = (date.today() - timedelta(days=365 * 6)).isoformat()
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start,
            "sort_order": "asc",
            "limit": 2000,
        }
        url = f"{FRED_OBSERVATIONS_URL}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "KronosFinceptLab/10.9",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("observations") or []


def _latest_numeric_observation(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(observations):
        value = _number(item.get("value"))
        if value is not None:
            return {"date": str(item.get("date") or ""), "value": value}
    return None


def _nearest_previous_year_observation(
    observations: list[dict[str, Any]],
    latest_date: str,
) -> dict[str, Any] | None:
    try:
        latest = date.fromisoformat(latest_date)
        target = latest.replace(year=latest.year - 1)
    except Exception:
        return None
    best_distance: int | None = None
    best: dict[str, Any] | None = None
    for item in observations:
        item_date = str(item.get("date") or "")
        try:
            observed = date.fromisoformat(item_date)
        except ValueError:
            continue
        value = _number(item.get("value"))
        if value is None:
            continue
        distance = abs((observed - target).days)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = {"date": item_date, "value": value}
    return best


def _number(value: Any) -> float | None:
    if value in (None, "", ".", "-", "--"):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
