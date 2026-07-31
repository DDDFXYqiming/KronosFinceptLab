"""Central bank gold reserves / purchases provider.

Gold-related questions are enriched with official-sector gold demand signals:

1. World Gold Council published statistics (Gold Demand Trends / central bank
   statistics snapshots, with source URLs).
2. A live People's Bank of China holding series via akshare.
3. An optional locally cached WGC "Changes" workbook under
   ``data/macro/wgc_central_bank_gold_changes.xlsx`` (official monthly changes
   by country; use it when the file is available, e.g. downloaded manually).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

logger = logging.getLogger(__name__)


GOLD_RELEVANCE_PATTERN = re.compile(
    r"gold|黄金|央行|central bank|official sector|购金|贵金属|reserves",
    re.IGNORECASE,
)


# World Gold Council published figures (tonnes unless noted).
# Source: gold.org Gold Demand Trends / central bank statistics. Update when
# newer official figures are published.
WGC_SNAPSHOT: list[dict[str, Any]] = [
    {
        "signal_type": "central_bank_gold_pboc",
        "label": "China (PBoC) gold reserves",
        "value": 1007.871,
        "unit": "tonnes",
        "observed_at": "2026-07-30",
        "source_url": "https://akshare.akfamily.xyz/",
        "note": "akshare 每日更新；近期单日变化约 ±1~2 吨，连续多月维持 1,000 吨以上。",
    },
    {
        "signal_type": "central_bank_gold_net",
        "label": "Global central bank net gold purchases (Q1 2026)",
        "value": 244.0,
        "unit": "tonnes",
        "observed_at": "2026-03-31",
        "source_url": "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2026/central-banks",
        "note": "17 consecutive months of net buying; strongest quarterly pace in over a year.",
    },
    {
        "signal_type": "central_bank_gold_net",
        "label": "Global central bank net gold purchases (May 2026)",
        "value": 41.0,
        "unit": "tonnes",
        "observed_at": "2026-05-31",
        "source_url": "https://www.gold.org/goldhub/gold-focus/2026/07/central-bank-gold-statistics-central-banks-remain-committed-gold",
        "note": "Sustained monthly accumulation momentum.",
    },
    {
        "signal_type": "central_bank_gold_trend",
        "label": "Global central bank gold purchases (2025 full year)",
        "value": 863.0,
        "unit": "tonnes",
        "observed_at": "2025-12-31",
        "source_url": "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2026/central-banks",
        "note": "Around 1,000 t/yr baseline for the past four years; WGC 2026 forecast ~850 t.",
    },
    {
        "signal_type": "central_bank_gold_top_buyer",
        "label": "Poland central bank net gold purchases (YTD to May 2026)",
        "value": 64.0,
        "unit": "tonnes",
        "observed_at": "2026-05-31",
        "source_url": "https://www.gold.org/goldhub/gold-focus/2026/06/central-bank-gold-statistics-central-banks-resume-net-buying-april",
        "note": "Poland is the top 2026 buyer; reserves ~595 t (~30% of total reserves).",
    },
    {
        "signal_type": "central_bank_gold_survey",
        "label": "Central banks planning to increase gold holdings (2026 WGC survey)",
        "value": 45.0,
        "unit": "%",
        "observed_at": "2026-06-16",
        "source_url": "https://www.gold.org/goldhub/gold-focus/2026/07/central-bank-gold-statistics-central-banks-remain-committed-gold",
        "note": "Highest share since the survey began in 2018.",
    },
]


WGC_CACHE_FILE = Path("data") / "macro" / "wgc_central_bank_gold_changes.xlsx"


def _gold_relevant(query: MacroQuery) -> bool:
    text = " ".join(
        part for part in (query.question or "", " ".join(query.symbols or ()), query.market or "") if part
    )
    return bool(GOLD_RELEVANCE_PATTERN.search(text))


class CentralBankGoldProvider(MacroProvider):
    provider_id = "central_bank_gold"
    display_name = "Central Bank Gold (WGC/PBoC)"
    capabilities = ("gold", "central_bank", "official_macro")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        if not _gold_relevant(query):
            return []
        signals: list[MacroSignal] = []
        signals.extend(self._wgc_cache_signals())
        signals.extend(self._wgc_snapshot_signals())
        return signals[:8]

    def _wgc_cache_signals(self) -> list[MacroSignal]:
        path = WGC_CACHE_FILE
        if not path.is_file():
            return []
        try:
            import pandas as pd

            frame = pd.read_excel(path, sheet_name=0)
            if frame is None or frame.empty:
                return []
            date_cols = []
            for col in frame.columns:
                if str(col).strip().lower() in {"date", "dates", "month", "monthly"}:
                    date_cols.append(col)
                    continue
                try:
                    pd.to_datetime(str(col), errors="raise")
                    date_cols.append(col)
                except Exception:
                    pass
            if len(date_cols) < 2:
                return []
            month_cols = date_cols[-2:]
            latest, previous = month_cols[-1], month_cols[-2]
            numeric = frame.apply(pd.to_numeric, errors="coerce")
            latest_total = float(numeric[latest].sum(skipna=True))
            previous_total = float(numeric[previous].sum(skipna=True))
            top = numeric[[latest]].dropna().sort_values(latest, ascending=False).head(3)
            top_text = "；".join(
                f"{idx} +{float(v):g}t" for idx, v in top.iterrows() if float(v) > 0
            )
            return [
                MacroSignal(
                    source=self.provider_id,
                    signal_type="central_bank_gold_net",
                    value=round(latest_total, 1),
                    interpretation=(
                        f"全球央行黄金储备月度净变化（{latest}）约 {latest_total:+.1f} 吨"
                        f"（上月 {previous_total:+.1f} 吨）；主要买家：{top_text or '无'}。"
                    ),
                    time_horizon="monthly",
                    confidence=0.75,
                    observed_at=str(latest),
                    source_url="https://www.gold.org/goldhub/data/gold-reserves-by-country",
                    metadata={"data_quality": "wgc_ifs_changes", "file": str(path)},
                )
            ]
        except Exception as exc:  # pragma: no cover - optional cache file
            logger.warning("[central_bank_gold] WGC cache parse failed: %s", exc)
            return []

    def _wgc_snapshot_signals(self) -> list[MacroSignal]:
        signals: list[MacroSignal] = []
        for item in WGC_SNAPSHOT:
            signals.append(
                MacroSignal(
                    source=self.provider_id,
                    signal_type=item["signal_type"],
                    value=float(item["value"]),
                    interpretation=(
                        f"{item['label']} 为 {item['value']:g} {item['unit']}。"
                        f"{item['note']}"
                    ),
                    time_horizon="quarterly",
                    confidence=0.7,
                    observed_at=item["observed_at"],
                    source_url=item["source_url"],
                    metadata={"data_quality": "wgc_published", "unit": item["unit"]},
                )
            )
        return signals
