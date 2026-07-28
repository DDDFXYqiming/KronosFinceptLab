"""Parameter grid evaluation: find what causes the gap between old eval and prod pipeline.

Tests combinations of pred_len, sample_count, temperature, top_p across pretrained
and finetuned Kronos-small models through the full KronosPredictor.predict() pipeline.
"""

import os
import json, os, sys, time, warnings, copy
from pathlib import Path
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJ = Path(__file__).resolve().parents[1]
os.environ.setdefault("KRONOS_REPO_PATH", str(PROJ / "external" / "Kronos"))
sys.path.insert(0, str(PROJ / "src"))
sys.path.insert(0, str(PROJ / "external" / "Kronos"))

from model import Kronos, KronosPredictor, KronosTokenizer
import torch

device = torch.device("cpu")
print(f"Device: CPU (DirectML hits page file limit)")

# ── Data ──
DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
hub =  os.environ.get("HF_HUB_CACHE", os.path.expanduser("~/.cache/huggingface/hub"))

TOK_PATH = os.path.join(hub, "models--NeoQuasar--Kronos-Tokenizer-base", "snapshots", "0e0117387f39004a9016484a186a908917e22426")

@dataclass
class TrialResult:
    model: str
    pred_len: int
    sample_count: int
    temperature: float
    top_p: float
    dir_accuracy: float
    loss: float
    perplexity: float
    n_samples: int
    elapsed_s: float


def load_data(n_stocks: int = 30) -> tuple[dict, list]:
    csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:n_stocks]
    stocks = {}
    for f in csv_files:
        df = pd.read_csv(f, parse_dates=["timestamp"])
        df.sort_values("timestamp", inplace=True)
        stocks[f.stem.replace("cn_", "")] = df

    samples = []
    for symbol, df in stocks.items():
        n = len(df)
        test_start = int(n * 0.95)
        window = 100
        if n - test_start < window:
            test_start = n - window
        if test_start < 0:
            continue
        for start in range(test_start, n - window, 3):
            samples.append({
                "symbol": symbol,
                "df": df.iloc[start:start+90],
                "x_ts": pd.to_datetime(df.iloc[start:start+90]["timestamp"], utc=True),
                "y_ts": pd.to_datetime(df.iloc[start+90:start+100]["timestamp"], utc=True),
                "true_5": float(df.iloc[start+94]["close"]),
                "true_10": float(df.iloc[start+99]["close"]),
                "last_c": float(df.iloc[start+89]["close"]),
            })
    return stocks, samples


def run_trial(
    model_key: str, model_path: str,
    samples: list, tokenizer: KronosTokenizer,
    pred_len: int, sample_count: int, temperature: float, top_p: float,
) -> TrialResult:
    t0 = time.perf_counter()
    print(f"  Loading {model_key}...", end=" ", flush=True)
    model = Kronos.from_pretrained(model_path).to(device)
    model.eval()
    predictor = KronosPredictor(model, tokenizer, max_context=512, device=device)
    print(f"pre {time.perf_counter()-t0:.1f}s  eval...", flush=True)

    correct = 0
    total = 0
    mse = 0.0
    B = 32

    # Filter samples to match pred_len
    if pred_len == 5:
        filtered = [s for s in samples if not np.isnan(s["true_5"])]
    else:
        filtered = samples

    for i in range(0, len(filtered), B):
        batch = filtered[i:i+B]
        n_b = len(batch)

        if pred_len == 5:
            y_ts_list = [pd.date_range(start=s["x_ts"].iloc[-1] + pd.Timedelta(days=1), periods=5, freq="D", tz="UTC") for s in batch]
        else:
            y_ts_list = [s["y_ts"] for s in batch]

        try:
            frames = predictor.predict_batch(
                [s["df"] for s in batch],
                [s["x_ts"] for s in batch],
                y_ts_list,
                pred_len,
                T=temperature, top_k=0, top_p=top_p,
                sample_count=sample_count, verbose=False,
            )
        except Exception as e:
            print(f"    batch fail {i}: {e}", flush=True)
            continue

        for j, frame in enumerate(frames):
            try:
                pred_c = float(frame.iloc[-1]["close"])
            except (IndexError, KeyError):
                continue
            true_c = batch[j]["true_10"] if pred_len == 10 else batch[j]["true_5"]
            last_c = batch[j]["last_c"]
            total += 1
            if (pred_c > last_c) == (true_c > last_c):
                correct += 1
            mse += (pred_c - true_c) ** 2

    loss = mse / max(total, 1)
    acc = correct / max(total, 1)
    elapsed = time.perf_counter() - t0
    ppl = float(np.exp(loss)) if loss < 50 else float("inf")
    print(f"  done  acc={acc*100:.1f}%  loss={loss:.4f}  ppl={ppl:.2f}  ({elapsed:.0f}s)  {total} samples")

    return TrialResult(
        model=model_key, pred_len=pred_len, sample_count=sample_count,
        temperature=temperature, top_p=top_p,
        dir_accuracy=round(acc*100, 1), loss=round(float(loss), 4),
        perplexity=round(ppl, 2), n_samples=total, elapsed_s=round(elapsed, 1),
    )


def print_table(label: str, results: list[TrialResult]):
    print()
    print("=" * 100)
    print(f" {label}")
    print("=" * 100)
    hdr = f"{'Model':<28} {'Pred':>4} {'Samp':>4} {'T':>4} {'TopP':>4} {'Acc%':>6} {'Loss':>8} {'PPL':>8} {'N':>5} {'Time':>5}"
    print(hdr)
    print("-" * 100)
    for r in results:
        print(f"{r.model:<28} {r.pred_len:>4} {r.sample_count:>4} {r.temperature:>4.1f} {r.top_p:>4.1f} {r.dir_accuracy:>5.1f}% {r.loss:>8.4f} {r.perplexity:>8.2f} {r.n_samples:>5} {r.elapsed_s:>5.0f}s")


def main():
    stocks, samples = load_data(30)
    print(f"{len(stocks)} stocks, {len(samples)} test samples (last 5%)")

    tok = KronosTokenizer.from_pretrained(TOK_PATH).to(device)

    models_cfg = {
        "pretrained_small": os.path.join(hub, "models--NeoQuasar--Kronos-small", "snapshots", "901c26c1332695a2a8f243eb2f37243a37bea320"),
        "finetuned_small": str(PROJ / "external" / "Kronos-small"),
    }

    # ── 10 test groups ──
    grid = [
        # (pred_len, sample_count, temperature, top_p, note)
        (10, 1, 1.0, 0.9,  "A: baseline"),
        (5,  1, 1.0, 0.9,  "B: pred_len=5"),
        (2,  1, 1.0, 0.9,  "C: pred_len=2"),
        (10, 8, 1.0, 0.9,  "D: sample_count=8"),
        (10, 32, 1.0, 0.9, "E: sample_count=32"),
        (5,  8, 1.0, 0.9,  "F: pred5+samp8"),
        (5,  8, 0.5, 0.9,  "G: pred5+samp8+T0.5"),
        (5,  32, 0.5, 0.8, "H: pred5+samp32+T0.5+P0.8"),
        (5,  8, 0.3, 0.9,  "I: pred5+samp8+T0.3"),
        (10, 1, 0.5, 0.9,  "J: pred10+T0.5"),
    ]

    all_results = []
    out_path = PROJ / "output" / "eval_grid_results.json"
    out_path.parent.mkdir(exist_ok=True)

    for group_label, (pred_len, sc, T, p, note) in enumerate(grid):
        print(f"\n{'='*60}")
        print(f"Group {group_label+1}: pred_len={pred_len} sc={sc} T={T} top_p={p} — {note}")
        print(f"{'='*60}")

        for model_key, model_path in models_cfg.items():
            r = run_trial(model_key, model_path, samples, tok,
                          pred_len, sc, T, p)
            all_results.append(r)
            json.dump([asdict(x) for x in all_results], open(out_path, "w", encoding="utf-8"), indent=2)

    # ── Results ──
    print_table("ALL RESULTS", all_results)

    # Key comparisons
    print_table("BASELINE (A) vs PRED_LEN (B, C)", [r for r in all_results if r.pred_len in (10,5,2) and r.sample_count==1 and r.temperature==1.0])
    print_table("BASELINE (A) vs SAMPLE_COUNT (D, E)", [r for r in all_results if r.pred_len==10 and r.top_p==0.9 and r.temperature==1.0])
    print_table("RECOMMENDED COMBOS (F, G, H, I)", [r for r in all_results if r.pred_len==5 and r.sample_count>=8])

    # Save
    json.dump([asdict(r) for r in all_results], open(out_path, "w", encoding="utf-8"), indent=2)
    print(f"\nSaved to {out_path}")

    # Analysis
    print()
    print("=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    ft = [r for r in all_results if "finetuned" in r.model]
    pre = [r for r in all_results if "pretrained" in r.model]

    if ft and pre:
        # Best combo for finetuned
        best_ft = max(ft, key=lambda r: r.dir_accuracy)
        best_pre = max(pre, key=lambda r: r.dir_accuracy)
        print(f"Best finetuned:  acc={best_ft.dir_accuracy}%  params: pred_len={best_ft.pred_len} sc={best_ft.sample_count} T={best_ft.temperature} top_p={best_ft.top_p}")
        print(f"Best pretrained: acc={best_pre.dir_accuracy}%  params: pred_len={best_pre.pred_len} sc={best_pre.sample_count} T={best_pre.temperature} top_p={best_pre.top_p}")
        print(f"Improvement: +{best_ft.dir_accuracy - best_pre.dir_accuracy}pp")

        # Baseline (A) for finetuned
        baseline_ft = [r for r in ft if r.pred_len==10 and r.sample_count==1 and r.temperature==1.0 and r.top_p==0.9]
        best_ft_improve = [r for r in ft if r.pred_len==5 and r.sample_count>=8]
        if baseline_ft:
            b = baseline_ft[0]
            if best_ft_improve:
                best = max(best_ft_improve, key=lambda r: r.dir_accuracy)
                print(f"\nBaseline vs Best combo: {b.dir_accuracy}% → {best.dir_accuracy}%  (+{best.dir_accuracy - b.dir_accuracy}pp)")


if __name__ == "__main__":
    main()
