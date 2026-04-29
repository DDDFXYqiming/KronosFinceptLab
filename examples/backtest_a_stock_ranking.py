#!/usr/bin/env python3
"""A-Stock ranking backtest demo using Kronos predictions.

Fetches real A-stock OHLCV data via AkShare, runs Kronos predictions,
and generates a ranked signal table (BUY/HOLD).

Usage:
    # Dry-run (no model needed, fast)
    PYTHONPATH=src python examples/backtest_a_stock_ranking.py

    # Real Kronos inference (needs torch + model download)
    PYTHONPATH=src python examples/backtest_a_stock_ranking.py --real

    # Custom symbols
    PYTHONPATH=src python examples/backtest_a_stock_ranking.py --symbols 600519 000858 601318
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure project src is on path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "integrations" / "fincept_terminal" / "qlib_adapter"))

# Fix Windows console encoding for Unicode/emoji output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A-Stock Kronos ranking backtest")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["600519", "000858", "601318", "600036", "002594"],
        help="A-stock codes (default: 000001 600519 000858 601318 600036)",
    )
    parser.add_argument(
        "--start-date", default="20260101", help="Start date YYYYMMDD (default: 20260101)"
    )
    parser.add_argument(
        "--end-date", default="20261231", help="End date YYYYMMDD (default: 20261231)"
    )
    parser.add_argument(
        "--pred-len", type=int, default=5, help="Prediction horizon (default: 5 days)"
    )
    parser.add_argument(
        "--real", action="store_true", help="Use real Kronos model (default: dry-run)"
    )
    parser.add_argument(
        "--top-k", type=int, default=None, help="Show only top K ranked results"
    )
    args = parser.parse_args(argv)

    dry_run = not args.real

    # Step 1: Fetch A-stock data
    print("=" * 60)
    print("  KronosFinceptLab — A-Stock Ranking Backtest")
    print("=" * 60)
    print(f"\n📊 Fetching data for {len(args.symbols)} stocks...")
    print(f"   Period: {args.start_date} ~ {args.end_date}")
    print(f"   Mode: {'DRY-RUN (no model)' if dry_run else 'REAL Kronos inference'}")
    print()

    from kronos_fincept.akshare_adapter import fetch_multi_stock_ohlcv

    try:
        stock_data = fetch_multi_stock_ohlcv(
            symbols=args.symbols,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    except Exception as exc:
        print(f"❌ Failed to fetch data: {exc}")
        return 1

    for sym, rows in stock_data.items():
        print(f"   ✅ {sym}: {len(rows)} bars ({rows[0]['timestamp'][:10]} ~ {rows[-1]['timestamp'][:10]})")
    print()

    # Step 2: Run batch prediction
    print(f"🔮 Running Kronos predictions (pred_len={args.pred_len})...")
    start_time = time.time()

    from kronos_model_adapter import KronosModelAdapter

    adapter = KronosModelAdapter()
    adapter.fit()

    assets = [
        {"symbol": sym, "rows": rows}
        for sym, rows in stock_data.items()
    ]

    try:
        result = adapter.batch_predict(
            assets=assets,
            pred_len=args.pred_len,
            timeframe="daily",
            dry_run=dry_run,
            top_k=args.top_k,
        )
    except Exception as exc:
        print(f"❌ Prediction failed: {exc}")
        return 1

    elapsed = time.time() - start_time
    print(f"   Done in {elapsed:.1f}s")
    print()

    # Step 3: Print ranked results
    if not result.get("ok"):
        print(f"❌ Error: {result.get('error', 'unknown')}")
        return 1

    signals = result.get("signals", [])
    if not signals:
        print("⚠️  No signals generated.")
        return 1

    # Table header
    print("┌──────┬──────────┬───────────┬──────────────┬────────────┬─────────┬──────────┐")
    print("│ Rank │ Symbol   │ Last Close│ Pred Close   │ Pred Return│ Signal  │ Time(ms) │")
    print("├──────┼──────────┼───────────┼──────────────┼────────────┼─────────┼──────────┤")

    for sig in signals:
        ret_pct = sig["predicted_return"] * 100
        signal_emoji = "🟢" if sig["signal"] == "BUY" else "⚪"
        print(
            f"│ {sig['rank']:>4} │ {sig['symbol']:<8} │ {sig['last_close']:>9.2f} │"
            f" {sig['predicted_close']:>12.2f} │ {ret_pct:>+9.3f}% │ {signal_emoji} {sig['signal']:<5} │ {sig['elapsed_ms']:>8} │"
        )

    print("└──────┴──────────┴───────────┴──────────────┴────────────┴─────────┴──────────┘")
    print()

    # Summary
    buy_count = sum(1 for s in signals if s["signal"] == "BUY")
    hold_count = len(signals) - buy_count
    print(f"📈 BUY signals: {buy_count}  |  ⏸️  HOLD signals: {hold_count}")
    print(f"⚠️  {result['metadata']['warning']}")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
