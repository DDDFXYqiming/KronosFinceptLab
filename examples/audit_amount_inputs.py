"""Audit amount/volume validity of model inputs for US and HK market paths.

The analysis agent feeds rows from GlobalMarketSource (US/HK) and the AkShare
HK fallback into the Kronos model. This script samples symbols from both paths
and verifies that amount is never silently zero before it reaches the model
(the model boundary backfills close*volume only when amount is all-zero).

Usage:
    python examples/audit_amount_inputs.py [--output output/amount_audit.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))

US_SYMBOLS = ["AAPL", "MSFT", "NVDA"]
HK_SYMBOLS = ["00700", "09988", "00005"]


def _fetch_global_rows(symbol: str, market: str) -> list[dict[str, Any]]:
    """Fetch rows through GlobalMarketSource (the analysis-page US/HK path)."""
    from kronos_fincept.financial import GlobalMarketSource

    frame = GlobalMarketSource().get_stock_data(symbol, market=market, period="1y", interval="1d")
    if frame is None or frame.empty:
        return []
    return [
        {
            "timestamp": str(row.get("timestamp")),
            "open": float(row.get("open") or 0),
            "high": float(row.get("high") or 0),
            "low": float(row.get("low") or 0),
            "close": float(row.get("close") or 0),
            "volume": float(row.get("volume") or 0),
            "amount": float(row.get("amount") or 0),
        }
        for row in frame.to_dict(orient="records")
    ]


def _fetch_hk_akshare_rows(symbol: str) -> list[dict[str, Any]]:
    """Fetch HK daily rows through the AkShare qfq fallback path."""
    import akshare as ak
    import pandas as pd

    base = str(symbol).strip().upper().removesuffix(".HK").zfill(5)
    frame = ak.stock_hk_daily(symbol=base, adjust="qfq")
    if frame is None or frame.empty:
        return []
    frame = frame.reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    for idx in range(len(frame)):
        close = float(frame.at[idx, "close"]) if pd.notna(frame.at[idx, "close"]) else 0.0
        volume = float(frame.at[idx, "volume"]) if pd.notna(frame.at[idx, "volume"]) else 0.0
        amount = (
            float(frame.at[idx, "amount"])
            if "amount" in frame.columns and pd.notna(frame.at[idx, "amount"])
            else close * volume
        )
        rows.append(
            {
                "timestamp": str(frame.at[idx, "date"]),
                "open": float(frame.at[idx, "open"]) if pd.notna(frame.at[idx, "open"]) else 0.0,
                "high": float(frame.at[idx, "high"]) if pd.notna(frame.at[idx, "high"]) else 0.0,
                "low": float(frame.at[idx, "low"]) if pd.notna(frame.at[idx, "low"]) else 0.0,
                "close": close,
                "volume": volume,
                "amount": amount,
            }
        )
    return rows


def _summarize(symbol: str, market: str, source: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    amounts = [float(row["amount"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    return {
        "symbol": symbol,
        "market": market,
        "source": source,
        "rows": len(rows),
        "zero_amount_rows": sum(value == 0 for value in amounts),
        "zero_volume_rows": sum(value == 0 for value in volumes),
        "amount_min": min(amounts) if amounts else 0.0,
        "amount_max": max(amounts) if amounts else 0.0,
        "pass": bool(rows) and all(value > 0 for value in amounts) and all(value > 0 for value in volumes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "output" / "amount_audit.json")
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for symbol in US_SYMBOLS:
        rows = _fetch_global_rows(symbol, "us")
        results.append(_summarize(symbol, "us", "GlobalMarketSource(yfinance)", rows))
    for symbol in HK_SYMBOLS:
        rows = _fetch_global_rows(symbol, "hk")
        results.append(_summarize(symbol, "hk", "GlobalMarketSource(yfinance)", rows))
        rows_ak = _fetch_hk_akshare_rows(symbol)
        results.append(_summarize(symbol, "hk", "AkShare stock_hk_daily qfq", rows_ak))

    payload = {"seed_symbols": {"us": US_SYMBOLS, "hk": HK_SYMBOLS}, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("symbol market source rows zero_amount zero_volume amount_min amount_max pass")
    for item in results:
        print(
            f"{item['symbol']} {item['market']} {item['source']} {item['rows']} "
            f"{item['zero_amount_rows']} {item['zero_volume_rows']} "
            f"{item['amount_min']:.2f} {item['amount_max']:.2f} {item['pass']}"
        )
    all_pass = all(item["pass"] for item in results)
    print(f"ALL_PASS={all_pass}")
    print(f"saved={args.output}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
