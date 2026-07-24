"""Kronos Finetune Adapter — bridge to upstream Kronos finetune pipelines.

Provides KFL-compatible wrappers for:
- finetune/ (QLib-based): train_predictor.py, train_tokenizer.py, qlib_test.py
- finetune_csv/ (CSV-based): finetune_base_model.py, finetune_tokenizer.py, train_sequential.py

Usage:
    from integrations.kronos_finetune import FinetuneTask, run_finetune
"""

from __future__ import annotations

from .adapter import FinetuneConfig, FinetuneTask, create_finetune_task, run_finetune

__all__ = [
    "FinetuneConfig",
    "FinetuneTask",
    "create_finetune_task",
    "run_finetune",
]
