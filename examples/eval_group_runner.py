"""Run a single eval group in a subprocess to avoid DML deadlock cascading."""
import json, os, sys, time, subprocess
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
script = str(PROJ / "examples" / "eval_one_group.py")
out_path = PROJ / "output" / "eval_grid_results.json"
out_path.parent.mkdir(exist_ok=True)

grid = [
    (10, 1, 1.0, 0.9, "A: baseline"),
    (10, 8, 1.0, 0.9, "D: sample_count=8"),
    (10, 1, 0.5, 0.9, "J: pl10+T0.5"),
    (10, 8, 0.5, 0.9, "K: pl10+sc8+T0.5"),
    (5,  1, 1.0, 0.9, "B: pred_len=5"),
    (5,  8, 1.0, 0.9, "F: pl5+sc8"),
    (5,  8, 0.5, 0.9, "G: +T0.5"),
    (5,  8, 0.3, 0.9, "I: +T0.3"),
]

# Load existing results
existing = {}
if out_path.exists():
    for r in json.load(open(out_path)):
        existing[r["note"]] = r

for pred_len, sc, T, p, note in grid:
    if note in existing:
        print(f"[skip] {note} already done")
        continue

    print(f"\n{'='*50}")
    print(f"[run] {note}: pl={pred_len} sc={sc} T={T} P={p}")
    print(f"{'='*50}")

    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, script,
         str(pred_len), str(sc), str(T), str(p), note],
        capture_output=True, text=True, timeout=600, cwd=str(PROJ),
    )

    elapsed = time.perf_counter() - t0
    print(f"[exit] code={result.returncode} time={elapsed:.0f}s")

    # Print last few lines of stdout
    out_lines = result.stdout.strip().split("\n")
    for line in out_lines[-5:]:
        if line.strip():
            print(f"  {line}")

    if result.returncode != 0:
        stderr_last = result.stderr.strip().split("\n")[-3:]
        for line in stderr_last:
            if line.strip():
                print(f"  [err] {line}")

    # Check if results were saved
    if out_path.exists():
        new_results = json.load(open(out_path))
        for r in new_results:
            if r["note"] == note:
                print(f"[ok] {note}: acc={r['dir_accuracy']}% n={r['n_samples']}")
                break

print(f"\nAll done. Results in {out_path}")
