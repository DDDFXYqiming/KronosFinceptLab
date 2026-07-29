"""Run the staged Kronos evaluation pipeline sequentially.

Examples::

    python examples/eval_pipeline.py --phase screen --manifest output/evaluation_manifest.json --tokenizer-path <path>
    python examples/eval_pipeline.py --phase confirm --manifest output/evaluation_manifest.json --tokenizer-path <path>
    python examples/eval_pipeline.py --phase final --model-key v3_cont_epoch_2 --manifest output/evaluation_manifest.json --tokenizer-path <path>

The runner deliberately starts one evaluator at a time.  DirectML is not
safe to stress with concurrent checkpoint processes on this machine.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = PROJECT_ROOT / "examples" / "eval_rolling.py"


def _hub_cache() -> Path:
    configured = os.environ.get("KRONOS_HUB_CACHE")
    if configured:
        return Path(configured)
    preferred = Path(r"E:\AI_Projects\ModelCache\huggingface\hub")
    return preferred if preferred.exists() else Path.home() / ".cache" / "huggingface" / "hub"


def _model_paths() -> dict[str, Path]:
    base = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
    hub = _hub_cache()
    return {
        "pretrained_small": hub / "models--NeoQuasar--Kronos-small" / "snapshots" / "901c26c1332695a2a8f243eb2f37243a37bea320",
        "full_small": base / "finetuned_full_small" / "basemodel" / "best_model",
        "full_small_v3": base / "finetuned_full_small_v3" / "basemodel" / "best_model",
        "v2_small_v2": base / "finetuned_v2_small_v2" / "basemodel" / "best_model",
        "v3_best": base / "finetuned_v3_fromFTv1" / "basemodel" / "best_model",
        "v3_cont_best": base / "finetuned_v3_fromFTv1_cont" / "basemodel" / "best_model",
        "v3_cont_epoch_1": base / "finetuned_v3_fromFTv1_cont" / "basemodel" / "epoch_1",
        "v3_cont_epoch_2": base / "finetuned_v3_fromFTv1_cont" / "basemodel" / "epoch_2",
        "cont2_best": base / "finetuned_v3_small_cont2" / "basemodel" / "best_model",
    }


SCREEN_KEYS = [
    "pretrained_small",
    "full_small",
    "full_small_v3",
    "v2_small_v2",
    "v3_best",
    "v3_cont_best",
    "v3_cont_epoch_1",
    "v3_cont_epoch_2",
    "cont2_best",
]


def _read_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_one(args: argparse.Namespace, key: str, model_path: Path, *, output: Path, mode: str, extra: list[str] | None = None) -> dict[str, Any]:
    if not model_path.exists():
        return {"model_key": key, "model_path": str(model_path), "error": "model path not found"}

    command = [
        sys.executable,
        str(EVALUATOR),
        "--mode",
        mode,
        "--manifest",
        str(args.manifest),
        "--model-path",
        str(model_path),
        "--tokenizer-path",
        str(args.tokenizer_path),
        "--output",
        str(output),
        "--device",
        args.device,
        "--batch-size",
        str(args.batch_size),
        "--seed",
        str(args.seed),
        "--oos-status",
        args.oos_status,
    ]
    if args.fold:
        command.extend(["--fold", args.fold])
    if args.no_resume:
        command.append("--no-resume")
    if extra:
        command.extend(extra)

    print(f"\n[pipeline] {mode} {key}", flush=True)
    completed = subprocess.run(command, cwd=str(PROJECT_ROOT), check=False)
    entry: dict[str, Any] = {
        "model_key": key,
        "model_path": str(model_path),
        "returncode": completed.returncode,
        "output": str(output),
    }
    if completed.returncode == 0 and output.exists():
        result = _read_result(output)
        entry.update({"summary": result.get("summary"), "selection": result.get("selection"), "inference": result.get("inference")})
    else:
        entry["error"] = f"evaluator exited with code {completed.returncode}"
    return entry


def _write_summary(path: Path, phase: str, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"phase": phase, "results": entries}
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class _PipelineLock:
    """Guard the whole phase so two terminals cannot duplicate a run."""

    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

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
                descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            else:
                raise RuntimeError(f"another evaluation pipeline is running (pid={owner})")
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.acquired:
            self.path.unlink(missing_ok=True)


def _confirm_keys(screen_report: Path) -> list[str]:
    report = json.loads(screen_report.read_text(encoding="utf-8"))
    completed = {
        entry.get("model_key")
        for entry in report.get("results", [])
        if entry.get("returncode") == 0
    }
    missing = [key for key in SCREEN_KEYS if key not in completed]
    if missing:
        raise RuntimeError(
            "screen report is incomplete; run the full screen phase before confirm: " + ", ".join(missing)
        )
    candidates = []
    for entry in report.get("results", []):
        overall = (entry.get("summary") or {}).get("overall") or {}
        accuracy = overall.get("direction_accuracy")
        if accuracy is not None:
            candidates.append((float(accuracy), entry["model_key"]))
    candidates.sort(reverse=True)
    selected = [key for _, key in candidates[:2]]
    if "pretrained_small" not in selected:
        selected.append("pretrained_small")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("smoke", "screen", "confirm", "final"), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tokenizer-path", type=Path, required=True)
    parser.add_argument("--model-key", choices=tuple(_model_paths()), default=None)
    parser.add_argument("--model-path", type=Path, default=None)
    parser.add_argument("--screen-report", type=Path, default=PROJECT_ROOT / "output" / "evaluation" / "screen" / "summary.json")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "output" / "evaluation")
    parser.add_argument("--fold", default=None)
    parser.add_argument("--device", choices=("directml", "cpu", "cuda"), default="directml")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--oos-status", choices=("diagnostic", "strict"), default="diagnostic")
    parser.add_argument("--production-audit", action="store_true")
    parser.add_argument(
        "--all-models",
        action="store_true",
        help="For confirm, run all nine screened models instead of only the top two plus baseline.",
    )
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    paths = _model_paths()
    if args.phase == "screen":
        keys = SCREEN_KEYS
        mode = "screen"
    elif args.phase == "confirm":
        keys = SCREEN_KEYS if args.all_models else _confirm_keys(args.screen_report)
        mode = "confirm"
    elif args.phase == "smoke":
        keys = [args.model_key or "v3_cont_epoch_2"]
        mode = "smoke"
    else:
        if not args.model_key and not args.model_path:
            parser.error("--phase final requires --model-key or --model-path")
        keys = [args.model_key] if args.model_key else []
        if args.model_key != "pretrained_small":
            keys.append("pretrained_small")
        mode = "final"

    if args.model_path is not None:
        if args.model_key is None:
            keys = ["custom"]
            if args.phase == "final":
                keys.append("pretrained_small")
        paths["custom"] = args.model_path

    phase_dir = args.output_dir / args.phase
    entries: list[dict[str, Any]] = []
    with _PipelineLock(PROJECT_ROOT / "output" / ".evaluation_pipeline.lock"):
        for key in keys:
            model_path = paths[key]
            output = phase_dir / f"{key}.json"
            entry = _run_one(args, key, model_path, output=output, mode=mode)
            entries.append(entry)
            _write_summary(phase_dir / "summary.json", args.phase, entries)

            if args.phase == "final" and args.production_audit and key != "pretrained_small" and entry.get("returncode") == 0:
                audit_output = phase_dir / f"{key}_production_audit.json"
                audit = _run_one(
                    args,
                    key,
                    model_path,
                    output=audit_output,
                    mode="final",
                    extra=["--max-samples", "256", "--sample-count", "8", "--bootstrap-replicates", "200"],
                )
                entries.append(audit)
                _write_summary(phase_dir / "summary.json", args.phase, entries)

    print(f"\n[pipeline] completed phase={args.phase} results={phase_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
