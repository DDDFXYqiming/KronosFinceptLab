"""Apply the frozen screen or confirmation decision without further tuning."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.rolling import (  # noqa: E402
    compare_candidate_to_baseline,
    select_screen_candidate,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _candidate(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("candidate must use NAME=RESULT.json")
    name, path = value.split("=", 1)
    return name, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    screen = subparsers.add_parser("screen")
    screen.add_argument("--baseline", type=Path, required=True)
    screen.add_argument("--candidate", type=_candidate, action="append", required=True)
    screen.add_argument("--output", type=Path, required=True)

    confirm = subparsers.add_parser("confirm")
    confirm.add_argument("--baseline", type=Path, required=True)
    confirm.add_argument("--candidate", type=Path, required=True)
    confirm.add_argument("--bootstrap", type=int, default=500)
    confirm.add_argument("--seed", type=int, default=42)
    confirm.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "screen":
        baseline = _load(args.baseline)
        candidates = {name: _load(path)["summary"]["overall"] for name, path in args.candidate}
        decision = select_screen_candidate(candidates, baseline["summary"]["overall"])
        decision["inputs"] = {
            "baseline": str(args.baseline),
            "candidates": {name: str(path) for name, path in args.candidate},
        }
    else:
        baseline = _load(args.baseline)
        candidate = _load(args.candidate)
        decision = compare_candidate_to_baseline(
            candidate["rows"],
            baseline["rows"],
            n_bootstrap=args.bootstrap,
            seed=args.seed,
        )
        decision["inputs"] = {
            "baseline": str(args.baseline),
            "candidate": str(args.candidate),
        }
    _write(args.output, decision)
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    print(f"saved={args.output.resolve()}")


if __name__ == "__main__":
    main()
