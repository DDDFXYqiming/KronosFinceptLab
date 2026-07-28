"""China government bond yield provider via AKShare (Sina Finance)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

BOND_TERMS = ("中国2年期国债", "中国5年期国债", "中国10年期国债", "中国30年期国债")


class ChinaBondYieldProvider(MacroProvider):
    provider_id = "china_bond_yield"
    display_name = "China Bond Yield"
    capabilities = ("rates", "china_bonds", "yield_curve")
    requires_api_key = False

    def _today(self) -> str:
        return date.today().isoformat()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        signals: list[MacroSignal] = []
        try:
            import akshare as ak
        except ImportError:
            return signals

        for term in BOND_TERMS:
            try:
                df = ak.bond_gb_zh_sina(symbol=term)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            last = df.iloc[-1]
            try:
                close = float(last.get("close", 0))
            except (TypeError, ValueError):
                continue
            date_val = last.get("date", "")
            if isinstance(date_val, str):
                try:
                    obs_date = datetime.strptime(date_val, "%Y-%m-%d").date()
                except ValueError:
                    obs_date = date.today()
            elif hasattr(date_val, "isoformat"):
                obs_date = date_val
            else:
                obs_date = date.today()

            prev = df.iloc[-2] if len(df) > 1 else None
            prev_close = float(prev.get("close", 0)) if prev is not None else close
            change_bp = (close - prev_close) * 100  # basis points

            label_map = {
                "中国2年期国债": "China 2Y Govt Bond Yield",
                "中国5年期国债": "China 5Y Govt Bond Yield",
                "中国10年期国债": "China 10Y Govt Bond Yield",
                "中国30年期国债": "China 30Y Govt Bond Yield",
            }

            signal = MacroSignal(
                source=self.provider_id,
                signal_type="rates",
                value=str(round(close, 3)),
                interpretation=f"{label_map.get(term, term)}: {round(close, 3)}% ({change_bp:+.1f}bp)",
                time_horizon="1d",
                confidence=0.85,
                observed_at=obs_date.isoformat(),
                metadata={
                    "term": term,
                    "yield_pct": round(close, 3),
                    "change_bp": round(change_bp, 1),
                },
            )
            signals.append(signal)

        return signals
