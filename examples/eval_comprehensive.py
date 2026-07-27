"""Comprehensive evaluation runner: 3 models, 100A+30H stocks, DML, all metrics."""
import json, os, sys, time, subprocess
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
OUT = PROJ / "output"
OUT.mkdir(exist_ok=True)
SCRIPT = str(PROJ / "examples" / "eval_comprehensive_run.py")
out_path = OUT / "eval_comprehensive.json"

# Grid: model_key, label, pl, sc, T, P
grid = [
    ("finetuned_small",  "FT best",   5, 8,  0.5, 0.9),
    ("pretrained_small", "Pre best",  5, 8,  0.5, 0.9),
]

all_results = []
for model_key, label, pl, sc, T, P in grid:
    print(f"\n{'='*50}", flush=True)
    print(f"[run] {label} ({model_key})", flush=True)
    t0 = time.perf_counter()

    result = subprocess.run(
        [sys.executable, SCRIPT, model_key, label, str(pl), str(sc), str(T), str(P)],
        capture_output=True, text=True, timeout=6000, cwd=str(PROJ),
    )
    elapsed = time.perf_counter() - t0

    # Parse result from stdout
    result_json = {}
    for line in reversed(result.stdout.strip().split("\n")):
        line = line.strip()
        if line.startswith("[RESULT]"):
            try:
                result_json = json.loads(line[len("[RESULT]"):])
            except json.JSONDecodeError:
                pass
            break

    if result.returncode != 0 or not result_json:
        print(f"[FAIL] exit={result.returncode}", flush=True)
        if result.stderr:
            for e in result.stderr.strip().split("\n")[-3:]:
                if e.strip():
                    print(f"  err: {e}", flush=True)
        all_results.append({"label": label, "model": model_key, "error": f"exit={result.returncode}"})
    else:
        print(f"[done] {elapsed:.0f}s  acc={result_json.get('dir_accuracy','?')}%  "
              f"IC={result_json.get('ic','?')}  RankIC={result_json.get('rankic','?')}  "
              f"AER={result_json.get('aer','?')}%  IR={result_json.get('ir','?')}", flush=True)
        all_results.append(result_json)

    json.dump(all_results, open(out_path, "w", encoding="utf-8"), indent=2)

# ── Print comparison table ──
print(f"\n{'='*70}")
print("COMPREHENSIVE EVALUATION RESULTS")
print(f"{'='*70}")
print(f"{'Label':<20} {'Acc%':>6} {'IC':>8} {'RankIC':>8} {'AER%':>7} {'IR':>5} {'Samples':>7} {'Time':>6}")
print("-" * 70)
for r in all_results:
    if "error" in r:
        print(f"{r['label']:<20} {'ERR':>6} {r['error']}")
    else:
        print(f"{r['label']:<20} {r.get('dir_accuracy','?'):>5}% {r.get('ic',0):>8.4f} {r.get('rankic',0):>8.4f} "
              f"{r.get('aer',0):>6.1f}% {r.get('ir',0):>5.2f} {r.get('n_samples','?'):>7} {r.get('elapsed_s',0):>5.0f}")

# Comparison
ft = next((r for r in all_results if r.get("label") == "FT best"), None)
pre = next((r for r in all_results if r.get("label") == "Pre best"), None)
if ft and pre and "error" not in ft and "error" not in pre:
    print(f"\n{'='*40}")
    print(f"FT best vs Pre best:")
    print(f"  Direction Acc: {ft.get('dir_accuracy',0)}% vs {pre.get('dir_accuracy',0)}%  (Δ={ft.get('dir_accuracy',0)-pre.get('dir_accuracy',0):+.1f}pp)")
    print(f"  IC:            {ft.get('ic',0):.4f} vs {pre.get('ic',0):.4f}  (Δ={ft.get('ic',0)-pre.get('ic',0):+.4f})")
    print(f"  RankIC:        {ft.get('rankic',0):.4f} vs {pre.get('rankic',0):.4f}  (Δ={ft.get('rankic',0)-pre.get('rankic',0):+.4f})")
    print(f"  AER (top-{ft.get('top_k',10)}):    {ft.get('aer',0):.2f}% vs {pre.get('aer',0):.2f}%  (Δ={ft.get('aer',0)-pre.get('aer',0):+.2f}pp)")
    print(f"  IR:            {ft.get('ir',0):.2f} vs {pre.get('ir',0):.2f}  (Δ={ft.get('ir',0)-pre.get('ir',0):+.2f})")
    print(f"  Samples:       {ft.get('n_samples',0)} vs {pre.get('n_samples',0)}")
print(f"\nSaved to {out_path}")
