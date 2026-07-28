from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from typing import Any

import urllib.request

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

VIX_CSV_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"
VIX_FUTURES_URL = "https://cdn.cboe.com/api/global/futures/vx_{type}_curve.json"

VIX_INDICES: dict[str, dict[str, str]] = {
    "VIX": {"label": "CBOE Volatility Index", "unit": "index", "type": "risk"},
    "VIX3M": {"label": "3-Month Volatility Index", "unit": "index", "type": "risk"},
    "VVIX": {"label": "Volatility of Volatility", "unit": "index", "type": "risk"},
    "SKEW": {"label": "CBOE Skew Index", "unit": "index", "type": "risk"},
    "GVZ": {"label": "Gold Volatility Index", "unit": "index", "type": "commodities"},
    "OVX": {"label": "Crude Oil Volatility Index", "unit": "index", "type": "commodities"},
    "TYVIX": {"label": "Treasury Volatility Index", "unit": "index", "type": "rates"},
}


def _fetch_csv(name: str) -> list[dict[str, str]]:
    url = VIX_CSV_URL.format(name=name)
    resp = urllib.request.urlopen(url, timeout=15)
    text = resp.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


class CboeVixProvider(MacroProvider):
    provider_id = "cboe_vix"
    display_name = "CBOE VIX"
    capabilities = ("risk", "volatility", "vix", "skew")
    requires_api_key = False

    def _today(self) -> str:
        return date.today().isoformat()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        signals: list[MacroSignal] = []
        for idx_name, meta in VIX_INDICES.items():
            try:
                rows = _fetch_csv(idx_name)
            except Exception:
                continue
            if not rows:
                continue
            latest = rows[-1]
            try:
                close = float(latest.get("CLOSE", latest.get("close", latest.get("Close", 0))))
            except (TypeError, ValueError):
                continue
            obs_date = latest.get("DATE", latest.get("date", latest.get("Date", ""))).strip()
            prev = rows[-2] if len(rows) > 1 else None
            prev_close = float(prev.get("CLOSE", prev.get("close", prev.get("Close", 0)))) if prev else close
            change_pct = (close / prev_close - 1) * 100 if prev_close else 0.0
            signal = MacroSignal(
                source=self.provider_id,
                signal_type=meta["type"],
                value=str(round(close, 2)),
                interpretation=f"{meta['label']}: {round(close, 2)} ({round(change_pct, 2):+.2f}%)",
                time_horizon="1d", confidence=0.9,
                observed_at=obs_date or self._today(),
                metadata={"change_pct": round(change_pct, 2), "series": idx_name},
            )
            signals.append(signal)

        try:
            url = VIX_FUTURES_URL.format(type="eod")
            resp = urllib.request.urlopen(url, timeout=15)
            futures_data = json.loads(resp.read().decode("utf-8"))
            curve = futures_data.get("data", {}).get("vx_curve", [])
            if curve:
                latest_f = curve[-1]
                fut_close = float(latest_f.get("close", 0))
                fut_date = latest_f.get("trade_date", "")
                signal = MacroSignal(
                    source=self.provider_id,
                    signal_type="risk",
                    value=str(round(fut_close, 2)),
                    interpretation=f"VIX Futures (Current Month): {round(fut_close, 2)}",
                    time_horizon="1d", confidence=0.85,
                    observed_at=fut_date or self._today(),
                    metadata={"contracts": len(curve), "contracts_data": curve},
                )
                signals.append(signal)
        except Exception:
            pass

        return signals


class CboeOptionsProvider(MacroProvider):
    provider_id = "cboe_options"
    display_name = "CBOE Options"
    capabilities = ("options", "implied_volatility", "greeks")
    requires_api_key = False

    def _today(self) -> str:
        return date.today().isoformat()

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        signals: list[MacroSignal] = []
        symbols = query.symbols or ("SPX",)
        symbol = str(symbols[0]).strip().upper()
        option_url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
        try:
            resp = urllib.request.urlopen(option_url, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return signals

        options = data.get("data", {}).get("options", [])
        if not options:
            return signals

        try:
            current_price = float(data.get("data", {}).get("current_price", 0))
        except (TypeError, ValueError):
            current_price = 0.0

        for opt in options[:20]:
            try:
                strike = float(opt.get("strike", 0))
                iv = float(opt.get("iv", opt.get("implied_volatility", 0)))
            except (TypeError, ValueError):
                continue
            opt_type = opt.get("option_type", "call").lower()
            exp = opt.get("expiration", "")
            bid = float(opt.get("bid", 0))
            ask = float(opt.get("ask", 0))
            mid_price = (bid + ask) / 2

            signal = MacroSignal(
                source=self.provider_id,
                signal_type="options",
                value=str(round(iv * 100, 2)),
                interpretation=f"{symbol} {opt_type.upper()} {strike} IV: {round(iv * 100, 2)}%",
                time_horizon="1d", confidence=0.85,
                observed_at=self._today(),
                metadata={
                    "symbol": symbol,
                    "strike": strike,
                    "option_type": opt_type,
                    "expiration": exp,
                    "mid_price": round(mid_price, 2),
                    "bid": round(bid, 2),
                    "ask": round(ask, 2),
                    "current_price": current_price,
                    "moneyness": round(current_price / strike, 4) if strike else 0,
                },
            )
            signals.append(signal)

        return signals
