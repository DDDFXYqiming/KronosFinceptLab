"""Load fine-tuned Kronos-small model and find trading positions/signals."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("KRONOS_REPO_PATH", str(PROJECT_ROOT / "external" / "Kronos"))
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("KRONOS_DEVICE", "dml")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ── Patch: resolve fine-tuned model from external/Kronos-small ──
from kronos_fincept.predictor import _resolve_pretrained_source
from kronos_fincept.schemas import DEFAULT_MODEL_ID, resolve_tokenizer_id, resolve_max_context

# ── Load Kronos ──
from kronos_fincept.predictor import _ensure_kronos_on_syspath
_ensure_kronos_on_syspath()

import torch
from model import Kronos, KronosPredictor, KronosTokenizer

# ── Device ──
import torch_directml
device = torch_directml.device()
print(f"[device] DirectML (AMD Radeon RX 7800 XT)")


def load_model():
    model_id = "NeoQuasar/Kronos-small"
    tokenizer_id = resolve_tokenizer_id(model_id)
    max_context = resolve_max_context(model_id)

    # Model path: our fine-tuned checkpoint in external/Kronos-small
    model_path, model_src = _resolve_pretrained_source(model_id)
    # Tokenizer path: HF cache
    tokenizer_path, tokenizer_src = _resolve_pretrained_source(tokenizer_id)

    print(f"[model] source={model_src} path={model_path}")
    print(f"[tokenizer] source={tokenizer_src} path={tokenizer_path}")

    if model_path is None:
        raise RuntimeError("Fine-tuned model not found at external/Kronos-small/")

    if tokenizer_path is not None:
        tokenizer = KronosTokenizer.from_pretrained(str(tokenizer_path))
    else:
        tokenizer = KronosTokenizer.from_pretrained(tokenizer_id)

    model = Kronos.from_pretrained(str(model_path))
    model.to(device)
    model.eval()

    predictor = KronosPredictor(model, tokenizer, max_context=max_context, device=device)
    return predictor, tokenizer, max_context


def load_stock_data(data_dir: Path, n_stocks: int = 30) -> dict[str, pd.DataFrame]:
    csv_files = sorted(data_dir.glob("cn_*.csv"))
    print(f"[data] Found {len(csv_files)} CSV files in {data_dir}")

    stocks = {}
    for f in csv_files[:n_stocks]:
        df = pd.read_csv(f, parse_dates=["timestamp"])
        df.sort_values("timestamp", inplace=True)
        symbol = f.stem.replace("cn_", "")
        stocks[symbol] = df
    return stocks


def prepare_input(df: pd.DataFrame, lookback: int = 90) -> tuple[pd.DataFrame, pd.Series] | None:
    if len(df) < lookback + 1:
        return None
    recent = df.tail(lookback).copy()
    timestamps = pd.to_datetime(recent["timestamp"], utc=True)
    features = recent[["open", "high", "low", "close", "volume", "amount"]].astype(float)
    return features, pd.Series(timestamps)


def run_inference(predictor, stocks: dict[str, pd.DataFrame], pred_len: int = 10, lookback: int = 90):
    results = []
    for symbol, df in stocks.items():
        inp = prepare_input(df, lookback)
        if inp is None:
            continue
        features, timestamps = inp
        last_close = float(df.iloc[-1]["close"])
        try:
            frame = predictor.predict(
                df=features,
                x_timestamp=timestamps,
                y_timestamp=pd.Series(pd.date_range(
                    start=timestamps.iloc[-1] + pd.Timedelta(days=1),
                    periods=pred_len, freq="D"
                )),
                pred_len=pred_len,
                T=1.0, top_k=0, top_p=0.9, sample_count=1, verbose=False,
            )
            frame = frame.reset_index(drop=False)
            forecast_close = float(frame.iloc[-1]["close"])
            predicted_return = forecast_close / last_close - 1.0
            results.append({
                "symbol": symbol,
                "last_close": last_close,
                "predicted_close": forecast_close,
                "predicted_return": predicted_return,
                "forecast": frame.to_dict(orient="records"),
            })
        except Exception as e:
            print(f"  [skip] {symbol}: {e}")

    results.sort(key=lambda r: r["predicted_return"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
    return results


def plot_results(results: list[dict], top_n: int = 9, output_path: Path | None = None):
    top = results[:top_n]
    n = len(top)
    cols = 3
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(16, 4 * rows))
    axes = axes.flatten() if n > 1 else [axes]

    for i, r in enumerate(top):
        ax = axes[i]
        fcast = pd.DataFrame(r["forecast"])
        if "timestamp" in fcast.columns:
            ts = pd.to_datetime(fcast["timestamp"], utc=True)
        else:
            ts = range(len(fcast))
        ax.plot(ts, fcast["close"], "b-o", linewidth=1.5, markersize=3, label="Predicted")
        ax.axhline(y=r["last_close"], color="gray", linestyle="--", alpha=0.6, label=f"Last={r['last_close']:.2f}")
        return_pct = r["predicted_return"] * 100
        color = "green" if r["predicted_return"] > 0 else "red"
        ax.set_title(f"#{r['rank']} {r['symbol']}  +{return_pct:.1f}%" if r["predicted_return"] > 0
                     else f"#{r['rank']} {r['symbol']}  {return_pct:.1f}%",
                     color=color, fontweight="bold")
        ax.set_ylabel("Close")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        if "timestamp" in fcast.columns and len(ts) > 1:
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(ts)//5)))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle("Fine-tuned Kronos-small — Top Ranked Positions", fontsize=14, fontweight="bold")
    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"[plot] Saved to {output_path}")
    plt.close(fig)


def main():
    data_dir = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv" / "data_v2"
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    # ── Load model ──
    t0 = time.perf_counter()
    print("=" * 60)
    print("Loading fine-tuned Kronos-small model...")
    predictor, tokenizer, max_context = load_model()
    print(f"  Loaded in {time.perf_counter()-t0:.1f}s")

    # ── Load data ──
    print("Loading stock data...")
    stocks = load_stock_data(data_dir, n_stocks=385)
    print(f"  Loaded {len(stocks)} stocks")

    # ── Run inference ──
    print("Running inference (this may take a while)...")
    t0 = time.perf_counter()
    results = run_inference(predictor, stocks, pred_len=10, lookback=90)
    elapsed = time.perf_counter() - t0
    print(f"  Completed {len(results)} stocks in {elapsed:.1f}s ({elapsed/max(len(results),1):.2f}s/stock)")

    # ── Print rank table ──
    print("\n" + "=" * 80)
    print(f"{'Rank':<5} {'Symbol':<8} {'LastClose':>10} {'PredClose':>10} {'Return%':>8} {'Signal':>6}")
    print("-" * 80)
    top_signals = []
    for r in results:
        ret_pct = r["predicted_return"] * 100
        signal = "BUY" if r["rank"] <= 3 else ("SELL" if r["predicted_return"] < -0.02 else "HOLD")
        if r["rank"] <= 20:
            print(f"{r['rank']:<5} {r['symbol']:<8} {r['last_close']:>10.2f} {r['predicted_close']:>10.2f} {ret_pct:>+7.2f}% {signal:>6}")
        top_signals.append(r)

    # ── Summary ──
    n_buy = sum(1 for r in results if r["predicted_return"] > 0.01)
    n_strong_buy = sum(1 for r in results if r["predicted_return"] > 0.03)
    print(f"\nSummary: {len(results)} stocks")
    print(f"  BUY signals (return >1%):  {n_buy}")
    print(f"  Strong BUY (return >3%):   {n_strong_buy}")
    print(f"  Top 1: {results[0]['symbol']}  +{results[0]['predicted_return']*100:.2f}%")
    print(f"  Top 3: {', '.join(r['symbol'] for r in results[:3])}")

    # ── Plot ──
    plot_results(results, top_n=9, output_path=output_dir / "finetuned_positions.png")

    # ── Save JSON ──
    json_path = output_dir / "finetuned_signals.json"
    json.dump(results, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print(f"[json] Saved to {json_path}")

    print("\nDone!  Positions found and plotted.")


if __name__ == "__main__":
    main()
