"""Final production-path evaluation: multi-window, multi-model, with baselines.

Data source: CSV (same as training, noted for comparison).
Windows: 2024H1, 2024H2, 2025H1 (last 5% of data in each window).
Models: finetuned_small, pretrained_small, pretrained_base.
Params: default (T=0.5, sc=8) vs baseline (T=1.0, sc=1).
Baselines: random (50%), simple momentum.
"""

import json, os, sys, time, subprocess
from pathlib import Path
import numpy as np

PROJ = Path(__file__).resolve().parents[1]
OUT = PROJ / "output"
OUT.mkdir(exist_ok=True)

SCRIPT = str(PROJ / "examples" / "eval_one_run.py")

grid = [
    # (model_key, model_path_note, pred_len, sc, T, P, label)
    ("finetuned_small",   "ft_default",  5, 8,  0.5, 0.9, "FT best"),
    ("finetuned_small",   "ft_baseline", 5, 1,  1.0, 0.9, "FT baseline"),
    ("pretrained_small",  "pre_default", 5, 8,  0.5, 0.9, "Pre best"),
    ("pretrained_small",  "pre_baseline",5, 1,  1.0, 0.9, "Pre baseline"),
    ("pretrained_base",   "base_default",5, 8,  0.5, 0.9, "Base best"),
    ("pretrained_base",   "base_baseline",5,1,  1.0, 0.9, "Base baseline"),
]

all_results = []
out_path = OUT / "eval_final_results.json"
run_log = OUT / "eval_final_log.txt"

for model_key, path_note, pl, sc, T, P, label in grid:
    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, SCRIPT, model_key, str(pl), str(sc), str(T), str(P), label],
        capture_output=True, text=True, timeout=600, cwd=str(PROJ),
    )
    elapsed = time.perf_counter() - t0

    # Parse last stdout line for result JSON
    result_line = ""
    for line in reversed(result.stdout.strip().split("\n")):
        line = line.strip()
        if line.startswith("[RESULT]"):
            result_line = line[len("[RESULT]"):].strip()
            break

    entry = {
        "model": model_key,
        "label": label,
        "pred_len": pl,
        "sample_count": sc,
        "temperature": T,
        "top_p": P,
        "elapsed_s": round(elapsed, 1),
    }

    if result.returncode == 0 and result_line:
        try:
            data = json.loads(result_line)
            entry.update(data)
        except json.JSONDecodeError:
            entry["error"] = f"bad result: {result_line[:100]}"
    else:
        entry["error"] = f"exit={result.returncode}"

    all_results.append(entry)
    json.dump(all_results, open(out_path, "w", encoding="utf-8"), indent=2)

    with open(run_log, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {label}: acc={entry.get('dir_accuracy','?')}% "
                f"samples={entry.get('n_samples','?')} time={entry['elapsed_s']}s\n")

    print(f"[{elapsed:5.0f}s] {label:20s}  acc={entry.get('dir_accuracy','?'):>5}  n={entry.get('n_samples','?'):>4}  "
          f"{entry.get('error','')}", flush=True)

# Print summary
print(f"\n{'='*70}")
print("FINAL RESULTS")
print(f"{'='*70}")
print(f"{'Label':<20} {'Acc%':>6} {'Loss':>8} {'PPL':>8} {'Samples':>7} {'Time':>6}")
print("-" * 70)
for r in all_results:
    acc = r.get("dir_accuracy", "?")
    loss = r.get("loss", "?")
    ppl = r.get("perplexity", "?")
    ns = r.get("n_samples", "?")
    ts = r.get("elapsed_s", "?")
    print(f"{r['label']:<20} {str(acc):>6} {str(loss):>8} {str(ppl):>8} {str(ns):>7} {str(ts):>6}")

# Compare FT best vs Pre best
ft = [r for r in all_results if r.get("label") == "FT best"]
pre = [r for r in all_results if r.get("label") == "Pre best"]
if ft and pre:
    ft_a = ft[0].get("dir_accuracy", 0)
    pre_a = pre[0].get("dir_accuracy", 0)
    if isinstance(ft_a, (int, float)) and isinstance(pre_a, (int, float)):
        print(f"\nFT best vs Pre best: {ft_a}% vs {pre_a}%  Δ={ft_a-pre_a:+.1f}pp")
        print(f"FT best vs Random (50%): {ft_a}% vs 50%  Δ={ft_a-50:+.1f}pp")

print(f"\nSaved to {out_path}")
