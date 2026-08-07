"""Evaluate the pred_len=10 training arms plus required baselines on one fixture.

Runs the protocol Confirm (pred_len=10 / sc8 / T=0.5, fixed 600 samples
`evaluation_samples_pred10.json`) for: official Kronos-small, production
v3-cont epoch_2, fast_recipe_best (parent reference) and the two
predict_window=10 arms (best + last epoch, when present). Missing checkpoints
are skipped. Then call compare_evaluations_v2.py with the official baseline.

Usage:
    python examples/eval_pred10_models.py \
      --output-dir output/eval_pred10_training \
      --compare-output output/eval_pred10_training/comparison_report.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = PROJECT_ROOT / "examples" / "eval_rolling.py"
COMPARE = PROJECT_ROOT / "examples" / "compare_evaluations_v2.py"


def hub_cache() -> Path:
    configured = os.environ.get("KRONOS_HUB_CACHE")
    if configured:
        return Path(configured)
    preferred = Path(r"E:\AI_Projects\ModelCache\huggingface\hub")
    return preferred if preferred.exists() else Path.home() / ".cache" / "huggingface" / "hub"


def model_paths() -> dict[str, Path]:
    base = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
    return {
        "pretrained_small": hub_cache()
        / "models--NeoQuasar--Kronos-small"
        / "snapshots"
        / "901c26c1332695a2a8f243eb2f37243a37bea320",
        "production_v3cont_epoch2": base / "finetuned_v3_fromFTv1_cont" / "basemodel" / "epoch_2",
        "fast_recipe_best": base / "finetuned_largecap_v8_fast_recipe" / "basemodel" / "best_model",
        "pred10_prod_best": base / "finetuned_largecap_v8_pred10_prod" / "basemodel" / "best_model",
        "pred10_prod_epoch3": base / "finetuned_largecap_v8_pred10_prod" / "basemodel" / "epoch_3",
        "pred10_fr_best": base / "finetuned_largecap_v8_pred10_fr" / "basemodel" / "best_model",
        "pred10_fr_epoch3": base / "finetuned_largecap_v8_pred10_fr" / "basemodel" / "epoch_3",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "output" / "evaluation_manifest_largecap_v8_recent_pred10.json")
    parser.add_argument("--samples-file", type=Path, default=PROJECT_ROOT / "configs" / "evaluation" / "evaluation_samples_pred10.json")
    parser.add_argument("--fold", default="validation_2026_05_07")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--compare-output", type=Path, default=None)
    parser.add_argument("--device", choices=("directml", "cpu", "cuda"), default="directml")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    tokenizer_path = (
        hub_cache()
        / "models--NeoQuasar--Kronos-Tokenizer-base"
        / "snapshots"
        / "0e0117387f39004a9016484a186a908917e22426"
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, object]] = []
    for key, path in model_paths().items():
        output = args.output_dir / f"{key}.json"
        if not path.exists():
            summary.append({"model_key": key, "model_path": str(path), "error": "model path not found"})
            print(f"[pred10-eval] skip {key}: path not found", flush=True)
            continue
        command = [
            sys.executable,
            str(EVALUATOR),
            "--mode", "confirm",
            "--manifest", str(args.manifest),
            "--fold", args.fold,
            "--samples-file", str(args.samples_file),
            "--model-path", str(path),
            "--tokenizer-path", str(tokenizer_path),
            "--output", str(output),
            "--device", args.device,
            "--batch-size", str(args.batch_size),
            "--pred-len", "10",
            "--sample-count", "8",
            "--temperature", "0.5",
            "--top-p", "0.9",
            "--bootstrap-replicates", "0",
            "--seed", "42",
            "--no-resume",
        ]
        print(f"[pred10-eval] starting {key}", flush=True)
        completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        entry: dict[str, object] = {
            "model_key": key,
            "model_path": str(path),
            "returncode": completed.returncode,
            "output": str(output),
        }
        if completed.returncode == 0 and output.exists():
            result = json.loads(output.read_text(encoding="utf-8"))
            entry["summary"] = result.get("summary")
        else:
            entry["error"] = "evaluator failed"
        summary.append(entry)
        (args.output_dir / "summary.json").write_text(
            json.dumps({"phase": "confirm_pred10", "results": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    compare_output = args.compare_output or args.output_dir / "comparison_report.json"
    compare_command = [
        sys.executable,
        str(COMPARE),
        "--input-dir", str(args.output_dir),
        "--baseline", "pretrained_small",
        "--output", str(compare_output),
        "--bootstrap-replicates", "5000",
        "--seed", "42",
    ]
    print("[pred10-eval] running comparison", flush=True)
    subprocess.run(compare_command, cwd=PROJECT_ROOT, check=False)
    print(f"[pred10-eval] done; comparison saved to {compare_output}", flush=True)


if __name__ == "__main__":
    main()
