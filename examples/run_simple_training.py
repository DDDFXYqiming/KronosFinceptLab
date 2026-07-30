"""Run the three frozen clean_v5_compact experiments sequentially."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FINETUNE_ROOT = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
TRAINER = FINETUNE_ROOT / "train_sequential.py"
CONFIGS = (
    FINETUNE_ROOT / "configs" / "config_simple_m1.yaml",
    FINETUNE_ROOT / "configs" / "config_simple_m2.yaml",
    FINETUNE_ROOT / "configs" / "config_simple_m3.yaml",
)


class _TrainingLock:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                owner = int(self.path.read_text(encoding="utf-8").strip())
                os.kill(owner, 0)
            except (OSError, ValueError):
                self.path.unlink(missing_ok=True)
                descriptor = os.open(
                    str(self.path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            else:
                raise RuntimeError(
                    f"the fixed three-model training cycle is already running "
                    f"(pid={owner})"
                )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not (FINETUNE_ROOT / "clean_v5_compact" / "manifest.json").exists():
        parser.error(
            "clean_v5_compact is missing; "
            "run examples/prepare_clean_v5_compact.py first"
        )

    with _TrainingLock(PROJECT_ROOT / "output" / ".simple_training.lock"):
        for config in CONFIGS:
            command = [sys.executable, str(TRAINER), "--config", str(config)]
            print(f"[training] {' '.join(command)}", flush=True)
            if args.dry_run:
                continue
            completed = subprocess.run(command, cwd=str(FINETUNE_ROOT), check=False)
            if completed.returncode != 0:
                raise SystemExit(
                    f"training stopped after {config.name} returned {completed.returncode}; "
                    "remaining experiments were not started"
                )
    print("[training] fixed three-model cycle complete", flush=True)


if __name__ == "__main__":
    main()
