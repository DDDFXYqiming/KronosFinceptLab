"""Kronos predictor wrappers.

The module provides a deterministic dry-run predictor for integration tests and a
lazy real Kronos predictor hook for environments where the upstream Kronos code
and model dependencies are installed.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from kronos_fincept.data_adapter import make_future_timestamps
from kronos_fincept.schemas import DEFAULT_MODEL_ID, DEFAULT_TOKENIZER_ID

_KRONOS_REPO_ENV = "KRONOS_REPO_PATH"


def _resolve_kronos_repo() -> Path | None:
    """Resolve the upstream Kronos repo path from env or well-known locations."""
    env = os.environ.get(_KRONOS_REPO_ENV)
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    # Check well-known project-local location
    here = Path(__file__).resolve().parents[3]  # project root
    local = here / "external" / "Kronos"
    if local.is_dir():
        return local
    return None


def _ensure_kronos_on_syspath() -> None:
    """Insert the upstream Kronos repo root into sys.path so `from model import ...` works."""
    repo = _resolve_kronos_repo()
    if repo is None:
        return
    repo_str = str(repo)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def _hf_cache_hint(model_id: str) -> str:
    """Return a hint about HuggingFace cache location."""
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    return (
        f"HuggingFace model '{model_id}' not found or download failed. "
        f"Cache location: {hf_home}. "
        f"To use a local model directory, pass its path as model_id. "
        f"For offline usage, set HF_HUB_OFFLINE=1 and ensure models are pre-downloaded."
    )


@dataclass(frozen=True)
class ForecastResult:
    """Structured forecast output."""

    frame: pd.DataFrame
    device: str
    elapsed_ms: int
    backend: str


class DryRunPredictor:
    """Deterministic predictor used before real Kronos dependencies are available."""

    def predict(self, df: pd.DataFrame, x_timestamp: pd.Series, pred_len: int) -> ForecastResult:
        started = time.perf_counter()
        y_timestamp = make_future_timestamps(x_timestamp, pred_len)
        last = df.iloc[-1]
        rows: list[dict[str, Any]] = []
        for index, timestamp in enumerate(y_timestamp, start=1):
            drift = 1.0 + index * 0.001
            close = float(last["close"]) * drift
            open_price = float(last["close"]) * (1.0 + (index - 1) * 0.001)
            high = max(open_price, close) * 1.002
            low = min(open_price, close) * 0.998
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": float(last.get("volume", 0.0)),
                    "amount": float(last.get("amount", 0.0)),
                }
            )
        frame = pd.DataFrame(rows)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ForecastResult(frame=frame, device="cpu", elapsed_ms=elapsed_ms, backend="dry_run")


class KronosPredictorWrapper:
    """Lazy wrapper around upstream Kronos classes.

    Resolution order for the upstream `model` package:
      1. ``KRONOS_REPO_PATH`` env var (absolute path to the Kronos repo root)
      2. ``external/Kronos`` in the project tree
      3. ``PYTHONPATH`` must already contain the Kronos root
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        tokenizer_id: str = DEFAULT_TOKENIZER_ID,
        max_context: int = 512,
        device: str | None = None,
        temperature: float = 1.0,
        top_k: int = 0,
        top_p: float = 0.9,
        sample_count: int = 1,
    ) -> None:
        self.model_id = model_id
        self.tokenizer_id = tokenizer_id
        self.max_context = max_context
        self.device = device
        self.temperature = temperature
        self.top_k = top_k
        self.top_p = top_p
        self.sample_count = sample_count
        self._predictor: Any | None = None

    def _load(self) -> Any:
        if self._predictor is not None:
            return self._predictor

        _ensure_kronos_on_syspath()

        try:
            import torch  # noqa: F401
            from model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:
            repo = _resolve_kronos_repo()
            hint_parts = [
                "Real Kronos inference requires the upstream Kronos package and torch/huggingface-hub.",
                "Resolution order:",
                f"  1. Set env KRONOS_REPO_PATH=<path-to-Kronos-repo>  (current: {os.environ.get(_KRONOS_REPO_ENV, 'unset')})",
                f"  2. Place Kronos at external/Kronos in the project root  (found: {repo is not None})",
                "  3. Add the Kronos root to PYTHONPATH manually",
                "Use dry_run=true for contract tests without Kronos installed.",
            ]
            raise RuntimeError("\n".join(hint_parts)) from exc

        try:
            from huggingface_hub import hf_hub_download  # noqa: F401
        except ImportError:
            pass  # will fail at from_pretrained time with a clear error

        device = self.device or ("cuda:0" if torch.cuda.is_available() else "cpu")

        try:
            tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_id)
        except Exception as exc:
            raise RuntimeError(_hf_cache_hint(self.tokenizer_id)) from exc

        try:
            model = Kronos.from_pretrained(self.model_id)
        except Exception as exc:
            raise RuntimeError(_hf_cache_hint(self.model_id)) from exc

        model.to(device)
        model.eval()
        self._predictor = KronosPredictor(model, tokenizer, max_context=self.max_context, device=device)
        return self._predictor

    def predict(self, df: pd.DataFrame, x_timestamp: pd.Series, pred_len: int) -> ForecastResult:
        started = time.perf_counter()
        predictor = self._load()
        y_timestamp = make_future_timestamps(x_timestamp, pred_len)
        frame = predictor.predict(
            df=df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=self.temperature,
            top_k=self.top_k,
            top_p=self.top_p,
            sample_count=self.sample_count,
            verbose=False,
        )
        frame = frame.reset_index(drop=False)
        if "timestamp" not in frame.columns:
            frame.insert(0, "timestamp", y_timestamp.reset_index(drop=True))
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        device = self.device or "auto"
        return ForecastResult(frame=frame, device=device, elapsed_ms=elapsed_ms, backend="kronos")
