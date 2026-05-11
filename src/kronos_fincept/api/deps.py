"""Dependency injection for FastAPI endpoints."""

from __future__ import annotations

import os
import importlib.util
from functools import lru_cache
from typing import Any

from kronos_fincept.config import settings
from kronos_fincept.predictor import DryRunPredictor, KronosPredictorWrapper
from kronos_fincept.predictor import _ensure_kronos_on_syspath, _resolve_kronos_repo
from kronos_fincept.schemas import DEFAULT_MODEL_ID, DEFAULT_TOKENIZER_ID
from kronos_fincept.security_utils import safe_configured_model_id


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


MODEL_CAPABILITY_NAMES = [
    "torch",
    "huggingface_hub",
    "einops",
    "safetensors",
    "kronos_repo",
    "kronos_code",
]


@lru_cache(maxsize=4)
def get_model_info(deep: bool = False) -> dict[str, Any]:
    """Return info about the currently configured model.

    The default path is intentionally lightweight for cloud health probes: it
    does not import torch or upstream Kronos code. Use deep=True for an explicit
    operator diagnostic that validates heavyweight imports.
    """
    device = "cpu"
    model_enabled = settings.kronos.enable_real_model
    capabilities: dict[str, bool] = {
        "akshare": _has_module("akshare"),
        "baostock": _has_module("baostock"),
        "yfinance": _has_module("yfinance"),
        "torch": _has_module("torch"),
        "huggingface_hub": _has_module("huggingface_hub"),
        "einops": _has_module("einops"),
        "safetensors": _has_module("safetensors"),
        "kronos_repo": False,
        "kronos_code": False,
    }
    model_error: str | None = None

    # Check for AMD ROCm
    rocm = os.environ.get("ROCR_VISIBLE_DEVICES")
    if rocm:
        device = "rocm"

    repo = _resolve_kronos_repo()
    capabilities["kronos_repo"] = repo is not None
    if repo is not None:
        capabilities["kronos_code"] = (repo / "model" / "__init__.py").is_file()

    if not model_enabled:
        model_error = "Real Kronos inference is disabled by KRONOS_ENABLE_REAL_MODEL=0."
    elif deep:
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda:0"
        except Exception as exc:
            model_error = f"torch unavailable: {exc}"

        if repo is not None:
            try:
                _ensure_kronos_on_syspath()
                from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: F401
                capabilities["kronos_code"] = True
            except Exception as exc:
                capabilities["kronos_code"] = False
                model_error = f"kronos code unavailable: {exc}"
        elif model_error is None:
            model_error = (
                "KRONOS_REPO_PATH is unset or does not point to a Kronos repo, "
                "and external/Kronos was not found."
            )
    elif repo is None:
        model_error = (
            "KRONOS_REPO_PATH is unset or does not point to a Kronos repo, "
            "and external/Kronos was not found."
        )

    model_ready = all(capabilities[name] for name in MODEL_CAPABILITY_NAMES)
    if model_enabled and model_error is None and not model_ready:
        missing = ", ".join(name for name in MODEL_CAPABILITY_NAMES if not capabilities[name])
        model_error = f"missing model prerequisites: {missing}"
    model_loaded = model_enabled and deep and model_ready and model_error is None
    data_sources_ready = all(
        capabilities[name]
        for name in [
            "akshare",
            "baostock",
            "yfinance",
        ]
    )
    model_runtime_ready = True
    if model_enabled:
        model_runtime_ready = model_ready and (model_error is None or not deep)

    status = "ok" if data_sources_ready and model_runtime_ready else "degraded"

    return {
        "status": status,
        "model_loaded": model_loaded,
        "model_id": safe_configured_model_id(settings.kronos.model_id, DEFAULT_MODEL_ID),
        "tokenizer_id": settings.kronos.tokenizer_id or DEFAULT_TOKENIZER_ID,
        "device": device,
        "runtime_mode": "standard" if model_enabled else "lowmem",
        "model_enabled": model_enabled,
        "deep_check": deep,
        "capabilities": capabilities,
        "model_error": None if model_loaded else model_error,
    }


def _has_module(name: str) -> bool:
    """Return whether a Python module can be imported without importing it."""
    return importlib.util.find_spec(name) is not None
