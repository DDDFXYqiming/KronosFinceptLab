"""Run pretrained model grid via subprocess to avoid DML deadlock."""
import json, os, sys, time, subprocess
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
script = str(PROJ / "examples" / "eval_one_group_pretrained.py")
out_path = PROJ / "output" / "eval_pretrained_results.json"
out_path.parent.mkdir(exist_ok=True)

grid = [
    (10, 1, 1.0, 0.9, "baseline"),
    (10, 8, 1.0, 0.9, "sample_count=8"),
    (10, 1, 0.5, 0.9, "pl10+T0.5"),
    (10, 8, 0.5, 0.9, "pl10+sc8+T0.5"),
    (5,  1, 1.0, 0.9, "pred_len=5"),
    (5,  8, 1.0, 0.9, "pl5+sc8"),
    (5,  8, 0.5, 0.9, "+T0.5"),
    (5,  8, 0.3, 0.9, "+T0.3"),
]

existing = {}
if out_path.exists():
    for r in json.load(open(out_path)):
        existing[r["note"]] = r

for pred_len, sc, T, p, note in grid:
    note_full = "pre_" + note
    if note_full in existing:
        print(f"[skip] {note_full} already done")
        continue

    print(f"\n{'='*50}")
    print(f"[run] pretrained {note}: pl={pred_len} sc={sc} T={T} P={p}")
    print(f"{'='*50}")

    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, script,
         str(pred_len), str(sc), str(T), str(p), note],
        capture_output=True, text=True, timeout=600, cwd=str(PROJ),
    )
    elapsed = time.perf_counter() - t0
    print(f"[exit] code={result.returncode} time={elapsed:.0f}s")
    out_lines = result.stdout.strip().split("\n")
    for line in out_lines[-3:]:
        if line.strip():
            print(f"  {line}")

    if result.returncode != 0:
        for line in result.stderr.strip().split("\n")[-3:]:
            if line.strip():
                print(f"  [err] {line}")

    if out_path.exists():
        new_results = json.load(open(out_path))
        for r in new_results:
            if r["note"] == note_full:
                print(f"[ok] {r['note']}: acc={r['dir_accuracy']}% n={r['n_samples']}")
                break

print(f"\nAll done. Results in {out_path}")
