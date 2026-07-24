"""Kronos Finetune Adapter — bridge KFL task system ↔ upstream Kronos finetune pipelines.

Two upstream pipelines available:
  1. finetune/     — QLib-based (requires QLib data preprocessing)
  2. finetune_csv/ — CSV-based (simpler, direct from OHLCV CSV files)

Design: thin wrapper — delegates to upstream scripts via subprocess, KFL provides
config management, logging, and task lifecycle.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
_KRONOS_ROOT = Path(__file__).resolve().parents[2] / "external" / "Kronos"
_FINETUNE_DIR = _KRONOS_ROOT / "finetune"
_FINETUNE_CSV_DIR = _KRONOS_ROOT / "finetune_csv"

# ── Config ───────────────────────────────────────────────────────────────────


@dataclass
class FinetuneConfig:
    """Configuration for a Kronos finetune run."""

    # Upstream pipeline selection
    pipeline: Literal["qlib", "csv"] = "csv"
    """Which upstream pipeline to use: 'qlib' (finetune/) or 'csv' (finetune_csv/)."""

    # Model selection
    base_model: str = "NeoQuasar/Kronos-base"
    """Base model ID to finetune (HuggingFace or local path)."""

    # Data
    csv_path: str | None = None
    """Path to CSV data file (required for 'csv' pipeline)."""

    data_dir: str | None = None
    """Path to QLib data directory (required for 'qlib' pipeline)."""

    # Training
    output_dir: str = "./finetune_output"
    """Directory for finetuned model checkpoints."""

    epochs: int = 3
    """Number of training epochs."""

    batch_size: int = 4
    """Training batch size."""

    learning_rate: float = 5e-5
    """Learning rate."""

    # Tokenizer
    train_tokenizer: bool = True
    """Whether to train tokenizer first (csv pipeline) or use pre-trained."""

    # Hardware
    device: str = "cuda"
    """Device: 'cuda', 'cpu', or 'dml'."""

    # KFL integration
    task_priority: int = 50
    """Task priority in KFL task system (lower = higher priority)."""

    timeout_seconds: int = 3600
    """Maximum runtime before task is considered failed."""


# ── Task wrapper ──────────────────────────────────────────────────────────────


@dataclass
class FinetuneTask:
    """Represents a finetune job in the KFL task system."""

    config: FinetuneConfig
    task_id: str = ""
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    progress: float = 0.0
    log_lines: list[str] = field(default_factory=list)

    def run(self) -> bool:
        """Execute the finetune job. Returns True on success."""
        self.status = "running"
        try:
            if self.config.pipeline == "csv":
                success = _run_csv_pipeline(self)
            else:
                success = _run_qlib_pipeline(self)
            self.status = "completed" if success else "failed"
            return success
        except Exception:
            _logger.exception("Finetune task %s failed", self.task_id)
            self.status = "failed"
            return False


# ── Pipeline runners ─────────────────────────────────────────────────────────


def _run_csv_pipeline(task: FinetuneTask) -> bool:
    """Run the CSV-based finetune pipeline (finetune_csv/)."""
    cfg = task.config

    if not cfg.csv_path:
        _logger.error("csv_path is required for CSV pipeline")
        return False

    csv_path = Path(cfg.csv_path)
    if not csv_path.exists():
        _logger.error("CSV file not found: %s", csv_path)
        return False

    venv_python = _find_venv_python()

    scripts: list[list[str]] = []

    # Step 1: Train tokenizer (optional)
    if cfg.train_tokenizer:
        scripts.append([
            str(venv_python),
            str(_FINETUNE_CSV_DIR / "finetune_tokenizer.py"),
            "--base_model", cfg.base_model,
            "--csv_path", str(csv_path),
            "--output_dir", str(Path(cfg.output_dir) / "tokenizer"),
            "--epochs", str(cfg.epochs),
            "--batch_size", str(cfg.batch_size),
            "--lr", str(cfg.learning_rate),
        ])

    # Step 2: Train predictor
    scripts.append([
        str(venv_python),
        str(_FINETUNE_CSV_DIR / "finetune_base_model.py"),
        "--base_model", cfg.base_model,
        "--csv_path", str(csv_path),
        "--output_dir", str(Path(cfg.output_dir) / "predictor"),
        "--epochs", str(cfg.epochs),
        "--batch_size", str(cfg.batch_size),
        "--lr", str(cfg.learning_rate),
    ])

    total = len(scripts)
    for i, cmd in enumerate(scripts):
        _logger.info("Finetune [%d/%d]: %s", i + 1, total, " ".join(cmd))
        task.progress = (i / total) * 100
        try:
            result = subprocess.run(
                cmd,
                cwd=str(_FINETUNE_CSV_DIR),
                capture_output=True,
                text=True,
                timeout=cfg.timeout_seconds,
            )
            task.log_lines.extend(result.stdout.splitlines()[-20:])
            if result.returncode != 0:
                _logger.error("Step %d failed:\n%s", i + 1, result.stderr[-500:])
                task.log_lines.extend(result.stderr.splitlines())
                return False
        except subprocess.TimeoutExpired:
            _logger.error("Step %d timed out after %ds", i + 1, cfg.timeout_seconds)
            return False

    task.progress = 100.0
    return True


def _run_qlib_pipeline(task: FinetuneTask) -> bool:
    """Run the QLib-based finetune pipeline (finetune/)."""
    cfg = task.config

    if not cfg.data_dir:
        _logger.error("data_dir is required for QLib pipeline")
        return False

    venv_python = _find_venv_python()

    # QLib pipeline: train_tokenizer → train_predictor → qlib_test
    scripts = [
        [str(venv_python), str(_FINETUNE_DIR / "train_tokenizer.py"),
         "--model_name", cfg.base_model, "--data_dir", cfg.data_dir,
         "--output_dir", str(Path(cfg.output_dir) / "tokenizer")],
        [str(venv_python), str(_FINETUNE_DIR / "train_predictor.py"),
         "--model_name", cfg.base_model, "--data_dir", cfg.data_dir,
         "--output_dir", str(Path(cfg.output_dir) / "predictor"),
         "--epochs", str(cfg.epochs), "--batch_size", str(cfg.batch_size)],
    ]

    total = len(scripts)
    for i, cmd in enumerate(scripts):
        _logger.info("QLib finetune [%d/%d]: %s", i + 1, total, " ".join(cmd))
        task.progress = (i / total) * 100
        try:
            result = subprocess.run(
                cmd, cwd=str(_FINETUNE_DIR),
                capture_output=True, text=True,
                timeout=cfg.timeout_seconds,
            )
            task.log_lines.extend(result.stdout.splitlines()[-20:])
            if result.returncode != 0:
                _logger.error("QLib step %d failed:\n%s", i + 1, result.stderr[-500:])
                return False
        except subprocess.TimeoutExpired:
            _logger.error("QLib step %d timed out", i + 1)
            return False

    task.progress = 100.0
    return True


def _find_venv_python() -> str:
    """Find a suitable Python interpreter (prefer KFL venv)."""
    venv_path = Path(__file__).resolve().parents[2] / ".venv311" / "Scripts" / "python.exe"
    if venv_path.exists():
        return str(venv_path)
    return sys.executable


# ── Public API ────────────────────────────────────────────────────────────────


def create_finetune_task(
    csv_path: str | None = None,
    data_dir: str | None = None,
    base_model: str = "NeoQuasar/Kronos-base",
    output_dir: str = "./finetune_output",
    epochs: int = 3,
    **kwargs,
) -> FinetuneTask:
    """Factory: create a FinetuneTask with sensible defaults.

    Args:
        csv_path: Path to CSV data (uses 'csv' pipeline).
        data_dir: Path to QLib data (uses 'qlib' pipeline).
        base_model: HuggingFace model ID.
        output_dir: Directory for finetuned model.
        epochs: Number of training epochs.
        **kwargs: Override any FinetuneConfig field.

    Returns:
        Configured FinetuneTask ready to run.
    """
    pipeline: Literal["csv", "qlib"] = "csv" if csv_path else "qlib"

    config = FinetuneConfig(
        pipeline=pipeline,
        base_model=base_model,
        csv_path=csv_path,
        data_dir=data_dir,
        output_dir=output_dir,
        epochs=epochs,
        **kwargs,
    )
    return FinetuneTask(config=config)


def run_finetune(
    csv_path: str | None = None,
    data_dir: str | None = None,
    base_model: str = "NeoQuasar/Kronos-base",
    **kwargs,
) -> bool:
    """Convenience: create and run a finetune task in one call.

    Returns True on success.
    """
    task = create_finetune_task(
        csv_path=csv_path, data_dir=data_dir, base_model=base_model, **kwargs
    )
    return task.run()
