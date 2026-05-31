"""ChinaDataLive macro provider.

This no-key fallback mirrors the verified ChinaDataLive source configuration
from the local Stock Analysis System project while normalizing responses to the
KronosFinceptLab MacroProvider contract.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal


CHINALIVE_INDICATORS: dict[str, dict[str, str]] = {
    "gdp": {"endpoint": "gdp", "label": "China GDP", "type": "growth"},
    "cpi_yoy": {"endpoint": "cpi", "label": "China CPI YoY", "type": "inflation"},
    "pmi": {"endpoint": "pmi", "label": "China manufacturing PMI", "type": "growth"},
    "industrial_value_added_yoy": {
        "endpoint": "industrial-value-added",
        "label": "China industrial value added YoY",
        "type": "growth",
    },
    "retail_sales_yoy": {
        "endpoint": "retail-sales",
        "label": "China retail sales YoY",
        "type": "growth",
    },
    "fixed_investment_yoy": {
        "endpoint": "fixed-asset-investment",
        "label": "China fixed asset investment YoY",
        "type": "growth",
    },
    "trade_yoy": {"endpoint": "trade", "label": "China trade YoY", "type": "trade"},
    "m2_yoy": {"endpoint": "m2", "label": "China M2 YoY", "type": "liquidity"},
}


class ChinaDataLiveProvider(MacroProvider):
    provider_id = "china_macro_chinalive"
    display_name = "ChinaDataLive"
    capabilities = ("china_macro", "growth", "inflation", "liquidity", "trade")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        if not _query_relevant(query):
            return []

        signals: list[MacroSignal] = []
        for indicator in _select_indicators(query):
            meta = CHINALIVE_INDICATORS.get(indicator)
            if meta is None:
                continue
            try:
                row = self._latest_row(str(meta["endpoint"]))
            except Exception:
                continue
            if row is None:
                continue
            signals.append(
                MacroSignal(
                    source=self.provider_id,
                    signal_type=meta["type"],
                    value=row["value"],
                    interpretation=f"{meta['label']} latest value is {row['value']:g}.",
                    time_horizon="mixed",
                    confidence=0.58,
                    observed_at=row["date"].date().isoformat(),
                    source_url=f"{_base_url().rstrip('/')}/{meta['endpoint']}",
                    metadata={
                        "indicator": indicator,
                        "label": meta["label"],
                        "data_quality": "chinadata_live",
                    },
                )
            )
        return signals

    def _latest_row(self, endpoint: str) -> dict[str, Any] | None:
        payload = _get_json(endpoint)
        rows = [_normalize_record(item) for item in _extract_data_array(payload)]
        rows = [row for row in rows if row is not None]
        if not rows:
            return None
        rows.sort(key=lambda item: item["date"])
        return rows[-1]


def _base_url() -> str:
    return os.environ.get("CHINALIVE_API_BASE_URL", "https://chinadata.live/api/v2/data").strip()


def _timeout() -> int:
    try:
        return max(1, int(float(os.environ.get("CHINALIVE_REQUEST_TIMEOUT", "15"))))
    except ValueError:
        return 15


def _get_json(endpoint: str) -> Any:
    url = f"{_base_url().rstrip('/')}/{endpoint.lstrip('/')}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "KronosFinceptLab/10.9",
        },
    )
    with urllib.request.urlopen(request, timeout=_timeout()) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_data_array(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("monthly", "yearly", "values", "observations"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data]
    return []


def _normalize_record(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    observed = None
    for key in ("date", "Date", "DATE", "time", "Time", "period", "Period", "month", "Month", "year", "Year"):
        if key in item:
            observed = _parse_date(item.get(key))
            if observed is not None:
                break
    if observed is None:
        return None

    value = None
    for key in ("value", "Value", "VALUE", "val", "rate", "Rate", "yoy", "YOY", "growth_rate", "growth", "amount", "Amount"):
        if key in item:
            value = _number(item.get(key))
            if value is not None:
                break
    if value is None:
        return None
    return {"date": observed, "value": value}


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime(int(value), 1, 1)
        except ValueError:
            return None
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d", "%Y/%m", "%Y年%m月", "%Y年%m月%d日", "%Y%m%d", "%b %Y", "%B %Y", "%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _number(value: Any) -> float | None:
    if value in (None, "", "-", "--", "."):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _query_relevant(query: MacroQuery) -> bool:
    text = " ".join([query.question or "", " ".join(query.symbols), str(query.market or "")]).lower()
    if query.market == "cn":
        return True
    return bool(re.search(r"china|中国|a股|pmi|cpi|m2|贸易|出口|消费|工业|gdp|增长|社融|宏观", text, re.IGNORECASE))


def _select_indicators(query: MacroQuery) -> list[str]:
    text = (query.question or "").lower()
    selected: list[str] = []

    def add(*items: str) -> None:
        for item in items:
            if item not in selected:
                selected.append(item)

    if re.search(r"pmi|制造业|景气", text, re.IGNORECASE):
        add("pmi")
    if re.search(r"cpi|通胀|物价|inflation", text, re.IGNORECASE):
        add("cpi_yoy")
    if re.search(r"m2|货币|流动性", text, re.IGNORECASE):
        add("m2_yoy")
    if re.search(r"工业|生产", text, re.IGNORECASE):
        add("industrial_value_added_yoy")
    if re.search(r"消费|零售", text, re.IGNORECASE):
        add("retail_sales_yoy")
    if re.search(r"投资|固定资产", text, re.IGNORECASE):
        add("fixed_investment_yoy")
    if re.search(r"贸易|出口|进口", text, re.IGNORECASE):
        add("trade_yoy")
    if re.search(r"gdp|增长|经济", text, re.IGNORECASE):
        add("gdp")
    if not selected:
        add("gdp", "cpi_yoy", "pmi")
    return selected[: max(1, min(query.limit or 5, 6))]
