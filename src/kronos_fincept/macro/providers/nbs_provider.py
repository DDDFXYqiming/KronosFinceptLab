"""NBS (National Bureau of Statistics of China) macro provider.

Uses the nbsc library to fetch official Chinese macroeconomic indicators
directly from the NBS public API. No API key required.
"""

from __future__ import annotations

import logging
from datetime import datetime

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

logger = logging.getLogger(__name__)

try:
    import nbsc
    HAS_NBSC = True
except ImportError:
    HAS_NBSC = False


def _extract_latest(data) -> tuple[str, float] | None:
    """Extract latest (date, value) from Series or DataFrame."""
    if data is None:
        return None
    import pandas as pd
    if isinstance(data, pd.Series):
        # nbsc returns Series with date index
        if len(data) < 1:
            return None
        date = str(data.index[-1])
        value = float(data.iloc[-1])
        return date, value
    if isinstance(data, pd.DataFrame):
        if data.empty:
            return None
        row = data.iloc[-1]
        # Find first numeric column
        for col in reversed(data.columns):
            val = row[col]
            try:
                return str(row.iloc[0]), float(val)
            except (TypeError, ValueError):
                continue
    return None


class NBSMacroProvider(MacroProvider):
    provider_id = "china_macro_nbs"
    display_name = "NBS Official China Macro"
    capabilities = ("china_macro", "growth", "inflation", "liquidity", "trade", "pmi")

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        if not HAS_NBSC:
            return []
        signals: list[MacroSignal] = []
        current_year = datetime.now().year

        fetchers = [
            ("inflation", "CPI YoY", lambda: nbsc.get_annual_inflation(str(current_year - 1))),
            ("pmi", "Manufacturing PMI", lambda: nbsc.get_manufacturing_pmi(str(current_year - 1))),
            ("liquidity", "M2 YoY", lambda: nbsc.get_m2_yoy(str(current_year - 1))),
            ("growth", "GDP Nominal", lambda: nbsc.get_gdp_nominal(str(current_year - 1))),
        ]

        for signal_type, label, fetcher in fetchers:
            try:
                data = fetcher()
                extracted = _extract_latest(data)
                if extracted is None:
                    continue
                date, value = extracted
                signals.append(MacroSignal(
                    source=self.provider_id,
                    signal_type=signal_type,
                    value=value,
                    interpretation=f"China {label}: {value:.2f}" if isinstance(value, float) and abs(value) < 1000 else f"China {label}: {value:.2f}",
                    time_horizon="medium",
                    confidence=0.8,
                    observed_at=str(date),
                ))
            except Exception as e:
                logger.debug("NBS %s fetch failed: %s", signal_type, e)

        return signals
