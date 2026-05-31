"""Optional lightweight National Bureau of Statistics V3.2 live provider."""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider, MacroProviderUnavailable
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal


FETCH_DATA_URL = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/getEsDataByCidAndDt"
ROOT_ID = "fc982599aa684be7969d7b90b1bd0e84"

NBS_SERIES = {
    "pmi": {
        "cid": "93ffbb1aa85740d3aa2618371508b606",
        "indicator_id": "a09aa989bdcf4cffa2021795722eb916",
        "label": "China manufacturing PMI",
        "type": "growth",
        "unit": "index",
        "keywords": ("pmi", "采购经理", "制造业", "景气"),
    },
    "cpi_yoy": {
        "cid": "5c7452825c7c4dcba391db5ca7f335c5",
        "indicator_id": "53180dfb9c14411ba4b762307c85920c",
        "label": "China CPI YoY index",
        "type": "inflation",
        "unit": "index",
        "keywords": ("cpi", "通胀", "物价", "居民消费"),
    },
    "ppi_yoy": {
        "cid": "60e8b361f11c4a878c652a6487a25561",
        "indicator_id": "150633e52b9a470a9a9fd1b296dd6c5b",
        "label": "China PPI YoY index",
        "type": "inflation",
        "unit": "index",
        "keywords": ("ppi", "工业品", "出厂", "生产者"),
    },
}


class ChinaNBSLiveProvider(MacroProvider):
    provider_id = "china_nbs_live"
    display_name = "China NBS V3.2 Live"
    capabilities = ("china_macro", "official_macro", "pmi", "inflation")
    requires_api_key = False

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        if not _enabled():
            raise MacroProviderUnavailable("KRONOS_ENABLE_NBS_LIVE is disabled")
        if not _query_relevant(query):
            return []

        signals: list[MacroSignal] = []
        for series_id in _select_series(query):
            meta = NBS_SERIES[series_id]
            payload = _fetch_series(meta["cid"], meta["indicator_id"])
            latest = _latest_point(payload, meta["indicator_id"])
            if latest is None:
                continue
            signals.append(
                MacroSignal(
                    source=self.provider_id,
                    signal_type=str(meta["type"]),
                    value=latest["value"],
                    interpretation=f"{meta['label']} latest NBS V3.2 value is {latest['value']:g} {meta['unit']}.",
                    time_horizon="mixed",
                    confidence=0.68,
                    observed_at=latest["date"],
                    source_url=FETCH_DATA_URL,
                    metadata={
                        "series_id": series_id,
                        "label": meta["label"],
                        "market": "cn",
                        "unit": meta["unit"],
                        "data_quality": "nbs_v32_live_optional",
                    },
                )
            )
        return signals


def _enabled() -> bool:
    return os.environ.get("KRONOS_ENABLE_NBS_LIVE", "").strip().lower() in {"1", "true", "yes", "on"}


def _query_relevant(query: MacroQuery) -> bool:
    text = " ".join([query.question or "", " ".join(query.symbols), query.market or ""]).lower()
    return (query.market or "").lower() == "cn" or any(
        needle in text
        for needle in ("china", "中国", "a股", "pmi", "cpi", "ppi", "通胀", "物价", "制造业", "宏观")
    )


def _select_series(query: MacroQuery) -> list[str]:
    text = " ".join([query.question or "", " ".join(query.symbols), query.market or ""]).lower()
    selected: list[str] = []
    for series_id, meta in NBS_SERIES.items():
        if any(str(keyword).lower() in text for keyword in meta["keywords"]):
            selected.append(series_id)
    if selected:
        return selected[: max(1, min(query.limit or 5, len(selected)))]
    return ["pmi", "cpi_yoy", "ppi_yoy"][: max(1, min(query.limit or 5, 3))]


def _fetch_series(cid: str, indicator_id: str) -> dict[str, Any]:
    body = {
        "cid": cid,
        "indicatorIds": [indicator_id],
        "das": [{"text": "National", "value": "000000000000"}],
        "showType": "1",
        "dts": "",
        "rootId": ROOT_ID,
    }
    request = urllib.request.Request(
        FETCH_DATA_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://data.stats.gov.cn",
            "Referer": "https://data.stats.gov.cn/dg/website/publicrelease/web/external",
            "User-Agent": "Mozilla/5.0 KronosFinceptLab NBS optional client",
            "client": "pc",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def _latest_point(payload: dict[str, Any], indicator_id: str) -> dict[str, Any] | None:
    rows = []
    for item in payload.get("data") or payload.get("datalist") or []:
        if not isinstance(item, dict):
            continue
        date_value = _parse_date(str(item.get("code") or item.get("dot") or ""))
        values = item.get("values") if isinstance(item.get("values"), list) else []
        value = _extract_value(values, indicator_id)
        if date_value and value is not None:
            rows.append({"date": date_value, "value": value})
    if not rows:
        return None
    rows.sort(key=lambda row: row["date"])
    return rows[-1]


def _extract_value(values: list[Any], indicator_id: str) -> float | None:
    for item in values:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("_id") or item.get("id") or item.get("indicator_id") or "")
        if item_id and indicator_id not in item_id:
            continue
        for key in ("data", "value", "val", "_value"):
            try:
                return float(item[key])
            except (KeyError, TypeError, ValueError):
                continue
    for item in values:
        if isinstance(item, dict):
            for key, value in item.items():
                if key.startswith("_") or key in {"i_showname", "is_economy_chart_show_text"}:
                    continue
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
    return None


def _parse_date(value: str) -> str | None:
    raw = value.replace("MM", "").replace("SS", "").replace("YY", "")
    for fmt in ("%Y%m", "%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None
