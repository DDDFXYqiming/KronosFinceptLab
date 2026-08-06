"""Sequentially evaluate the clean_v8 continuation candidates on one fixture."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = PROJECT_ROOT / "examples" / "eval_rolling.py"


def hub_cache() -> Path:
    configured = os.environ.get("KRONOS_HUB_CACHE")
    if configured:
        return Path(configured)
    preferred = Path(r"E:\AI_Projects\ModelCache\huggingface\hub")
    return preferred if preferred.exists() else Path.home() / ".cache" / "huggingface" / "hub"


def model_paths() -> dict[str, Path]:
    base = PROJECT_ROOT / "external" / "Kronos" / "finetune_csv"
    hub = hub_cache()
    return {
        "pretrained_small": hub / "models--NeoQuasar--Kronos-small" / "snapshots" / "901c26c1332695a2a8f243eb2f37243a37bea320",
        "full_small_v3_parent": base / "finetuned_full_small_v3" / "basemodel" / "best_model",
        "fullv3_epoch1": base / "finetuned_largecap_v8_fullv3_cont" / "basemodel" / "epoch_1",
        "fullv3_epoch2": base / "finetuned_largecap_v8_fullv3_cont" / "basemodel" / "epoch_2",
        "v3cont_parent": base / "finetuned_v3_fromFTv1_cont" / "basemodel" / "epoch_2",
        "v3cont_epoch1": base / "finetuned_largecap_v8_v3cont" / "basemodel" / "epoch_1",
        "v3cont_epoch2": base / "finetuned_largecap_v8_v3cont" / "basemodel" / "epoch_2",
        "v3cont_epoch3": base / "finetuned_largecap_v8_v3cont" / "basemodel" / "epoch_3",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--samples-file", type=Path, required=True)
    parser.add_argument("--tokenizer-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fold", default="validation_2026_05_07")
    parser.add_argument("--device", choices=("directml", "cpu", "cuda"), default="directml")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    paths = model_paths()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, object]] = []
    for key, path in paths.items():
        output = args.output_dir / f"{key}.json"
        if not path.exists():
            summary.append({"model_key": key, "model_path": str(path), "error": "model path not found"})
            continue
        command = [
            sys.executable,
            str(EVALUATOR),
            "--mode", "confirm",
            "--manifest", str(args.manifest),
            "--fold", args.fold,
            "--samples-file", str(args.samples_file),
            "--model-path", str(path),
            "--tokenizer-path", str(args.tokenizer_path),
            "--output", str(output),
            "--device", args.device,
            "--batch-size", str(args.batch_size),
            "--sample-count", "8",
            "--temperature", "0.5",
            "--top-p", "0.9",
            "--bootstrap-replicates", "0",
            "--seed", "42",
            "--no-resume",
        ]
        print(f"[v8-eval] starting {key}", flush=True)
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
            json.dumps({"phase": "confirm", "results": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
