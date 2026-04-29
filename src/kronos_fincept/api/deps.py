"""Dependency injection for FastAPI endpoints."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from kronos_fincept.predictor import DryRunPredictor, KronosPredictorWrapper
from kronos_fincept.schemas import DEFAULT_MODEL_ID, DEFAULT_TOKENIZER_ID


def get_predictor(
    dry_run: bool = False,
    model_id: str = DEFAULT_MODEL_ID,
    tokenizer_id: str = DEFAULT_TOKENIZER_ID,
    max_context: int = 512,
    temperature: float = 1.0,
    top_k: int = 0,
    top_p: float = 0.9,
    sample_count: int = 1,
) -> Any:
    """Get a predictor instance — dry-run or real Kronos."""
    if dry_run:
        return DryRunPredictor()
    return KronosPredictorWrapper(
        model_id=model_id,
        tokenizer_id=tokenizer_id,
        max_context=max_context,
        temperature=temperature,
        top_k=top_k,
        top_p=top_p,
        sample_count=sample_count,
    )


@lru_cache(maxsize=1)
def get_model_info() -> dict[str, Any]:
    """Return info about the currently configured model."""
    device = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda:0"
    except ImportError:
        pass

    # Check for AMD ROCm
    rocm = os.environ.get("ROCR_VISIBLE_DEVICES")
    if rocm:
        device = "rocm"

    return {
        "model_id": DEFAULT_MODEL_ID,
        "tokenizer_id": DEFAULT_TOKENIZER_ID,
        "device": device,
    }
