"""Compare Kronos runtime parameters on the production model (read-only).

Runs the same-day/same-symbol comparison behind decision gates G-A (T=0.5 vs
T=1.0 probabilistic sampling) and G-B (qfq vs raw input adjustment) using the
production junction weights (v3-cont epoch_2) and pred_len=10.

Usage:
    python examples/compare_runtime_params.py [--output output/compare_runtime_params_pred10.json]

This script performs model inference only; it never writes training state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PROJECT_ROOT / "src"))

A_SYMBOLS = ["600519", "601318", "000001"]
HK_SYMBOLS = ["00700", "09988"]
LOOKBACK = 90
PRED_LEN = 10


def _rows_to_frame(rows: list[dict[str, Any]]) -> Any:
    import pandas as pd

    if not rows:
        return None
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for col in ("open", "high", "low", "close", "volume", "amount"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume", "amount"])
    frame = frame.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    return frame


def _fetch_a(symbol: str, adjust: str) -> Any:
    """Fetch A-share daily OHLCV via the production pipeline (BaoStock first)."""
    from datetime import datetime, timedelta

    from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv

    end = datetime.now()
    start = end - timedelta(days=400)
    rows = fetch_a_stock_ohlcv(
        symbol=symbol,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust=adjust,
    )
    return _rows_to_frame(rows)


def _fetch_hk_akshare(symbol: str) -> Any:
    """Fetch HK daily OHLCV via AkShare qfq (the training-side source)."""
    import akshare as ak
    import pandas as pd

    base = str(symbol).strip().upper().removesuffix(".HK").zfill(5)
    frame = ak.stock_hk_daily(symbol=base, adjust="qfq")
    if frame is None or frame.empty:
        return None
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
    return _rows_to_frame(rows)


def _fetch_hk_yfinance(symbol: str) -> Any:
    """Fetch HK daily OHLCV via yfinance auto_adjust (the serving-side source)."""
    from kronos_fincept.financial import GlobalMarketSource

    frame = GlobalMarketSource().get_stock_data(symbol, market="hk", period="1y", interval="1d")
    if frame is None or frame.empty:
        return None
    return _rows_to_frame(frame.to_dict(orient="records"))


def _predict(
    wrapper: Any,
    frame: Any,
    pred_len: int,
    seed: int,
) -> dict[str, Any]:
    """Run probabilistic prediction and return summary statistics."""
    import torch

    x_frame = frame.iloc[-LOOKBACK:].copy()
    x_timestamp = x_frame["timestamp"].reset_index(drop=True)
    torch.manual_seed(seed)
    result = wrapper.predict_probabilistic(
        df=x_frame.drop(columns=["timestamp"]),
        x_timestamp=x_timestamp,
        pred_len=pred_len,
    )
    last_close = float(x_frame["close"].iloc[-1])
    final_closes = [float(sample.iloc[-1]["close"]) for sample in result.samples]
    return {
        "upside_probability": float(result.upside_probability),
        "range_width": float(max(final_closes) - min(final_closes)),
        "mean_final_close": float(result.mean_final_close),
        "last_close": last_close,
        "direction": "up" if result.mean_final_close > last_close else "down",
        "samples": final_closes,
    }


def _median_close_diff(base: Any, other: Any) -> dict[str, float]:
    """Median |base-other|/base close divergence over the shared recent window."""
    import pandas as pd

    if base is None or other is None:
        return {"n": 0, "median_pct": None}
    merged = pd.merge(
        base[["timestamp", "close"]],
        other[["timestamp", "close"]],
        on="timestamp",
        suffixes=("_base", "_other"),
    ).tail(LOOKBACK)
    if merged.empty:
        return {"n": 0, "median_pct": None}
    pct = ((merged["close_base"] - merged["close_other"]).abs() / merged["close_base"]).median()
    return {"n": int(len(merged)), "median_pct": float(pct)}


def _make_wrapper(model_id: str, tokenizer_id: str, temperature: float, sample_count: int, device: str) -> Any:
    from kronos_fincept.predictor import KronosPredictorWrapper

    return KronosPredictorWrapper(
        model_id=model_id,
        tokenizer_id=tokenizer_id,
        max_context=512,
        temperature=temperature,
        top_k=0,
        top_p=0.9,
        sample_count=sample_count,
        device=device,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="NeoQuasar/Kronos-small")
    parser.add_argument("--tokenizer-id", default="NeoQuasar/Kronos-Tokenizer-base")
    parser.add_argument("--device", default="directml")
    parser.add_argument("--pred-len", type=int, default=PRED_LEN)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "output" / "compare_runtime_params_pred10.json")
    args = parser.parse_args()

    seed = args.seed
    wrapper_t05 = _make_wrapper(args.model_id, args.tokenizer_id, 0.5, 16, args.device)
    wrapper_t10 = _make_wrapper(args.model_id, args.tokenizer_id, 1.0, 16, args.device)
    wrapper_t05_sc8 = _make_wrapper(args.model_id, args.tokenizer_id, 0.5, 8, args.device)

    reports: list[dict[str, Any]] = []
    for symbol in A_SYMBOLS + HK_SYMBOLS:
        market = "A" if symbol in A_SYMBOLS else "HK"
        try:
            if market == "A":
                qfq = _fetch_a(symbol, "qfq")
                alt = _fetch_a(symbol, "none")
            else:
                qfq = _fetch_hk_akshare(symbol)
                alt = _fetch_hk_yfinance(symbol)
        except Exception as exc:
            print(f"[fetch] {symbol} {market} failed: {exc}", flush=True)
            continue

        if qfq is None or len(qfq) < LOOKBACK + 2:
            print(f"[skip] {symbol} qfq data insufficient", flush=True)
            continue
        symbol_seed = int(hashlib.sha256(f"{seed}:{symbol}".encode()).hexdigest()[:8], 16)
        pred_t05 = _predict(wrapper_t05, qfq, args.pred_len, symbol_seed)
        pred_t10 = _predict(wrapper_t10, qfq, args.pred_len, symbol_seed + 1)
        adjust = {"median_pct": None, "n": 0}
        pred_alt: dict[str, Any] | None = None
        if alt is not None and len(alt) >= LOOKBACK + 2:
            adjust = _median_close_diff(qfq, alt)
            pred_alt = _predict(wrapper_t05_sc8, alt, args.pred_len, symbol_seed + 2)
        reports.append(
            {
                "symbol": symbol,
                "market": market,
                "last_date": str(qfq["timestamp"].iloc[-1].date()),
                "T0.5": pred_t05,
                "T1.0": pred_t10,
                "qfq_vs_alt_adjust": adjust,
                "alt_pred_T0.5": pred_alt,
            }
        )
        print(f"[done] {symbol} {market} last={qfq['timestamp'].iloc[-1].date()}", flush=True)

    payload = {
        "model_id": args.model_id,
        "pred_len": args.pred_len,
        "lookback": LOOKBACK,
        "seed": seed,
        "symbols": {"A": A_SYMBOLS, "HK": HK_SYMBOLS},
        "reports": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n## T comparison (qfq inputs, sample_count=16)")
    print("symbol market last_date T0.5_up T1.0_up T0.5_width T1.0_width width_ratio T0.5_dir T1.0_dir")
    for item in reports:
        r05, r10 = item["T0.5"], item["T1.0"]
        ratio = r10["range_width"] / r05["range_width"] if r05["range_width"] > 0 else float("nan")
        print(
            f"{item['symbol']} {item['market']} {item['last_date']} "
            f"{r05['upside_probability']:.3f} {r10['upside_probability']:.3f} "
            f"{r05['range_width']:.4f} {r10['range_width']:.4f} {ratio:.2f} "
            f"{r05['direction']} {r10['direction']}"
        )
    widths_t05 = [item["T0.5"]["range_width"] for item in reports if item["T0.5"]["range_width"] > 0]
    widths_t10 = [item["T1.0"]["range_width"] for item in reports if item["T1.0"]["range_width"] > 0]
    if widths_t05 and widths_t10:
        print(f"median width ratio T1.0/T0.5 = {sorted(r / b for r, b in zip(widths_t10, widths_t05))[len(widths_t05) // 2]:.2f}")
    ups_05 = [item["T0.5"]["upside_probability"] for item in reports]
    ups_10 = [item["T1.0"]["upside_probability"] for item in reports]
    print(f"mean upside prob: T0.5={sum(ups_05) / len(ups_05):.3f} T1.0={sum(ups_10) / len(ups_10):.3f}")

    print("\n## Adjustment comparison (qfq vs alt, T=0.5 sc8)")
    print("symbol market median_close_diff_pct alt_up qfq_up alt_dir qfq_dir")
    for item in reports:
        adjust = item["qfq_vs_alt_adjust"]
        alt = item["alt_pred_T0.5"]
        if alt is None:
            print(f"{item['symbol']} {item['market']} {adjust['median_pct']} n/a")
            continue
        print(
            f"{item['symbol']} {item['market']} "
            f"{(adjust['median_pct'] or 0) * 100:.3f} "
            f"{alt['upside_probability']:.3f} {item['T0.5']['upside_probability']:.3f} "
            f"{alt['direction']} {item['T0.5']['direction']}"
        )
    print(f"\nsaved={args.output}")


if __name__ == "__main__":
    main()
