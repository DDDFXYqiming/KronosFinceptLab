"""Run a resumable, production-path Kronos evaluation.

Smoke remains a cheap health check. Confirm is the only model-ranking stage:
it uses fixed market/date cross-sections and the prediction page's sampling
parameters. Final remains a post-freeze diagnostic rather than model selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kronos_fincept.evaluation.rolling import (  # noqa: E402
    deterministic_batch_seed,
    select_cross_sectional_samples,
    select_evaluation_samples,
    summarize_prediction_rows,
    validate_prediction_samples,
)


MODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "smoke": {
        "fold": "validation_2026_q1",
        "sample_count": 1,
        "temperature": 0.3,
        "top_p": 0.9,
        "bootstrap_replicates": 0,
    },
    "screen": {
        "fold": "validation_2026_q1",
        "sample_count": 1,
        "temperature": 0.3,
        "top_p": 0.9,
        "bootstrap_replicates": 0,
        "a_symbols": 20,
        "hk_symbols": 10,
        "windows_per_symbol": 5,
    },
    "confirm": {
        "fold": "validation_2026_q1",
        "sample_count": 8,
        "temperature": 0.5,
        "top_p": 0.9,
        "bootstrap_replicates": 5000,
        "dates_per_market": 5,
        "a_symbols_per_date": 80,
        "hk_symbols_per_date": 40,
    },
    "final": {
        "fold": "diagnostic_2026_04_07",
        "sample_count": 1,
        "temperature": 0.3,
        "top_p": 0.9,
        "bootstrap_replicates": 1000,
    },
}


def _load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    timestamp = "timestamp" if "timestamp" in frame.columns else "timestamps"
    frame[timestamp] = pd.to_datetime(frame[timestamp], errors="raise")
    frame.sort_values(timestamp, inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    try:
        import numpy as np
        import torch

        np.random.seed(seed)
        torch.manual_seed(seed)
    except ImportError:
        pass


def _load_predictor(args: argparse.Namespace):
    os.environ.setdefault("KRONOS_REPO_PATH", str(PROJECT_ROOT / "external" / "Kronos"))
    from kronos_fincept.predictor import _ensure_kronos_on_syspath

    _ensure_kronos_on_syspath()
    import torch
    from model import Kronos, KronosPredictor, KronosTokenizer

    if args.device == "directml":
        import torch_directml

        device = torch_directml.device()
    else:
        device = torch.device(args.device)

    print(f"[load] device={args.device} model={args.model_path}", flush=True)
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer_path).to(device)
    model = Kronos.from_pretrained(args.model_path).to(device)
    model.eval()
    return KronosPredictor(model, tokenizer, max_context=args.max_context, device=device), torch


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


class _EvaluationLock:
    """Prevent accidental DirectML evaluation concurrency across terminals."""

    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                owner = int(self.path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                owner = -1
            if owner > 0 and self._alive(owner):
                raise RuntimeError(f"another evaluation is running (pid={owner}); do not run DirectML evaluations in parallel")
            self.path.unlink(missing_ok=True)
            descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.acquired:
            self.path.unlink(missing_ok=True)


def _sample_key(item: Mapping[str, Any]) -> str:
    return ":".join(
        str(item.get(field, "")) for field in ("file", "input_start_row", "target_start_row", "target_end")
    )


def _evaluation_config(args: argparse.Namespace, samples: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [_sample_key(item) for item in samples]
    sample_hash = hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()
    return {
        "manifest": str(args.manifest.resolve()),
        "fold": args.fold,
        "mode": args.mode,
        "model_path": str(args.model_path.resolve()),
        "tokenizer_path": str(args.tokenizer_path.resolve()),
        "pred_len": args.pred_len,
        "max_context": args.max_context,
        "batch_size": args.batch_size,
        "sample_count": args.sample_count,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "seed": args.seed,
        "sample_count_total": len(samples),
        "sample_hash": sample_hash,
        "samples_file": str(args.samples_file.resolve()) if args.samples_file is not None else None,
    }


def _progress_path(args: argparse.Namespace) -> Path:
    if args.progress_path is not None:
        return args.progress_path
    return args.output.with_name(f"{args.output.stem}.progress.json")


def _load_progress(path: Path, config: Mapping[str, Any], *, resume: bool) -> tuple[int, list[dict[str, Any]]]:
    if not resume or not path.exists():
        return 0, []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("config") != dict(config):
        raise RuntimeError(f"progress file does not match this evaluation configuration: {path}")
    rows = payload.get("rows", [])
    next_index = int(payload.get("next_index", len(rows)))
    if next_index != len(rows):
        raise RuntimeError(f"progress file is inconsistent: next_index={next_index}, rows={len(rows)}")
    print(f"[resume] continuing at {next_index}/{config['sample_count_total']} samples", flush=True)
    return next_index, rows


def _save_progress(path: Path, config: Mapping[str, Any], next_index: int, rows: list[dict[str, Any]]) -> None:
    _atomic_write(
        path,
        {
            "version": 1,
            "updated_at_unix": time.time(),
            "config": dict(config),
            "next_index": next_index,
            "rows": rows,
        },
    )


def _resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    defaults = MODE_DEFAULTS[args.mode]
    for name in ("fold", "sample_count", "temperature", "top_p", "bootstrap_replicates"):
        if getattr(args, name) is None:
            setattr(args, name, defaults[name])
    if args.mode == "smoke" and args.max_samples is None:
        args.max_samples = 16
    if args.mode == "screen":
        for argument, default_key in (
            ("screen_a_symbols", "a_symbols"),
            ("screen_hk_symbols", "hk_symbols"),
            ("windows_per_symbol", "windows_per_symbol"),
        ):
            if getattr(args, argument) is None:
                setattr(args, argument, defaults[default_key])
    if args.mode == "confirm":
        for argument, default_key in (
            ("dates_per_market", "dates_per_market"),
            ("a_symbols_per_date", "a_symbols_per_date"),
            ("hk_symbols_per_date", "hk_symbols_per_date"),
        ):
            if getattr(args, argument) is None:
                setattr(args, argument, defaults[default_key])
    return args


def _load_samples_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["samples"] if isinstance(payload, dict) else payload
    return [dict(item) for item in rows]


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    args = _resolve_args(args)
    _seed_everything(args.seed)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_pred_len = int(manifest.get("protocol", {}).get("pred_len", args.pred_len))
    if manifest_pred_len != args.pred_len:
        raise ValueError(
            f"manifest pred_len={manifest_pred_len} does not match inference pred_len={args.pred_len}"
        )
    folds = {fold["id"]: fold for fold in manifest["rolling_folds"]}
    if args.fold not in folds:
        raise ValueError(f"unknown fold {args.fold}; choose from {sorted(folds)}")
    if (
        args.mode in {"screen", "confirm"}
        and folds[args.fold].get("role") != "model_selection"
    ):
        raise ValueError(
            "screen/confirm must use a model_selection fold, "
            f"not {args.fold} ({folds[args.fold].get('role')})"
        )

    all_samples = manifest["samples"].get(args.fold, [])
    if args.samples_file is not None:
        samples = _load_samples_file(args.samples_file)
    elif args.mode == "confirm":
        samples = select_cross_sectional_samples(
            all_samples,
            dates_per_market=args.dates_per_market,
            a_symbols_per_date=args.a_symbols_per_date,
            hk_symbols_per_date=args.hk_symbols_per_date,
            seed=args.seed,
        )
    else:
        samples = select_evaluation_samples(
            all_samples,
            mode=args.mode,
            seed=args.seed,
            a_symbols=args.screen_a_symbols,
            hk_symbols=args.screen_hk_symbols,
            windows_per_symbol=args.windows_per_symbol,
            max_samples=args.max_samples,
        )
    if not samples:
        raise ValueError(f"fold {args.fold} has no selected samples")
    validate_prediction_samples(samples, pred_len=args.pred_len)

    config = _evaluation_config(args, samples)
    progress_path = _progress_path(args)
    lock_path = PROJECT_ROOT / "output" / ".evaluation.lock"
    with _EvaluationLock(lock_path):
        start_index, rows = _load_progress(progress_path, config, resume=not args.no_resume)
        data_dir = Path(manifest["data_dir"])
        frames = {item["file"]: _load_frame(data_dir / item["file"]) for item in manifest["universe"]}
        predictor, torch = _load_predictor(args)
        started = time.perf_counter()
        for start in range(start_index, len(samples), args.batch_size):
            batch = samples[start : start + args.batch_size]
            x_frames = []
            x_timestamps = []
            y_timestamps = []
            for item in batch:
                frame = frames[item["file"]]
                timestamp = "timestamp" if "timestamp" in frame.columns else "timestamps"
                x_frame = frame.iloc[item["input_start_row"] : item["input_end_row"]].copy()
                x_frames.append(x_frame)
                x_timestamps.append(pd.Series(pd.to_datetime(x_frame[timestamp], utc=True)))
                y_timestamps.append(
                    pd.Series(
                        pd.to_datetime(
                            frame.iloc[item["target_start_row"] : item["target_end_row"]][timestamp], utc=True
                        )
                    )
                )

            try:
                _seed_everything(deterministic_batch_seed(batch, seed=args.seed))
                with torch.no_grad():
                    predictions = predictor.predict_batch(
                        x_frames,
                        x_timestamps,
                        y_timestamps,
                        args.pred_len,
                        T=args.temperature,
                        top_k=0,
                        top_p=args.top_p,
                        sample_count=args.sample_count,
                        verbose=False,
                    )
            except Exception as exc:
                _save_progress(progress_path, config, start, rows)
                raise RuntimeError(f"prediction failed at sample {start}/{len(samples)}; progress saved to {progress_path}") from exc

            for item, prediction in zip(batch, predictions):
                frame = frames[item["file"]]
                close = frame["close"].astype(float)
                rows.append(
                    {
                        "fold": item["fold"],
                        "symbol": item["symbol"],
                        "market": item["market"],
                        "target_start": item["target_start"],
                        "target_end": item["target_end"],
                        "last_close": float(close.iloc[item["input_end_row"] - 1]),
                        "true_close": float(close.iloc[item["target_end_row"] - 1]),
                        "pred_close": float(prediction.iloc[-1]["close"]),
                    }
                )

            completed = start + len(batch)
            elapsed = time.perf_counter() - started
            rate = completed / elapsed if elapsed > 0 else 0.0
            eta = (len(samples) - completed) / rate if rate > 0 else 0.0
            print(
                f"[progress] mode={args.mode} {completed}/{len(samples)} "
                f"{rate:.2f} samples/s eta={eta:.0f}s",
                flush=True,
            )
            if completed % args.checkpoint_every < len(batch) or completed == len(samples):
                _save_progress(progress_path, config, completed, rows)

        result = {
            "manifest": str(args.manifest),
            "mode": args.mode,
            "fold": args.fold,
            "sealed": bool(folds[args.fold]["sealed"]),
            "oos_status": args.oos_status,
            "model_path": str(args.model_path),
            "selection": {
                "n_all_fold_samples": len(all_samples),
                "n_selected_samples": len(samples),
                "a_symbols": len({item["symbol"] for item in samples if item["market"] == "A"}),
                "hk_symbols": len({item["symbol"] for item in samples if item["market"] == "HK"}),
                "seed": args.seed,
                "sample_hash": config["sample_hash"],
                "strategy": "fixed_fixture" if args.samples_file is not None else (
                    "market_date_cross_section" if args.mode == "confirm" else "symbol_window"
                ),
                "samples_file": str(args.samples_file) if args.samples_file is not None else None,
            },
            "inference": {
                "pred_len": args.pred_len,
                "sample_count": args.sample_count,
                "temperature": args.temperature,
                "top_p": args.top_p,
                "batch_size": args.batch_size,
                "device": args.device,
                "rng_strategy": "ordered_batch_key_v1",
            },
            "summary": summarize_prediction_rows(
                rows,
                bootstrap_replicates=args.bootstrap_replicates,
                bootstrap_seed=args.bootstrap_seed,
            ),
            "rows": rows,
        }
        _atomic_write(args.output, result)
        progress_path.unlink(missing_ok=True)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=tuple(MODE_DEFAULTS), default="final")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--fold", default=None)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--tokenizer-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "output" / "eval_rolling.json")
    parser.add_argument("--pred-len", type=int, default=5)
    parser.add_argument("--max-context", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--sample-count", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--bootstrap-replicates", type=int, default=None)
    parser.add_argument("--bootstrap-seed", type=int, default=42)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--screen-a-symbols", type=int, default=None)
    parser.add_argument("--screen-hk-symbols", type=int, default=None)
    parser.add_argument("--windows-per-symbol", type=int, default=None)
    parser.add_argument("--dates-per-market", type=int, default=None)
    parser.add_argument("--a-symbols-per-date", type=int, default=None)
    parser.add_argument("--hk-symbols-per-date", type=int, default=None)
    parser.add_argument("--samples-file", type=Path, default=None)
    parser.add_argument("--checkpoint-every", type=int, default=64)
    parser.add_argument("--progress-path", type=Path, default=None)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--oos-status", choices=("diagnostic", "strict"), default="diagnostic")
    parser.add_argument("--device", default="directml", choices=("directml", "cpu", "cuda"))
    args = parser.parse_args()
    if args.checkpoint_every <= 0 or args.batch_size <= 0:
        parser.error("--checkpoint-every and --batch-size must be positive")

    result = evaluate(args)
    overall = result["summary"]["overall"]
    print(
        f"fold={result['fold']} mode={result['mode']} sealed={result['sealed']} "
        f"oos={result['oos_status']} n={overall['n_samples']} "
        f"dir_acc={overall.get('direction_accuracy')} "
        f"mean_daily_rankic={overall.get('mean_daily_rankic')} "
        f"score={overall.get('composite_score')}"
    )
    print(f"saved={args.output}")


if __name__ == "__main__":
    main()
