"""Kronos predictor wrappers.

The module provides a deterministic dry-run predictor for integration tests and a
lazy real Kronos predictor hook for environments where the upstream Kronos code
and model dependencies are installed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pandas as pd

from kronos_fincept.data_adapter import make_future_timestamps
from kronos_fincept.schemas import DEFAULT_MODEL_ID, DEFAULT_TOKENIZER_ID


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
    """Lazy wrapper around upstream Kronos classes."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        tokenizer_id: str = DEFAULT_TOKENIZER_ID,
        max_context: int = 512,
        device: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.tokenizer_id = tokenizer_id
        self.max_context = max_context
        self.device = device
        self._predictor: Any | None = None

    def _load(self) -> Any:
        if self._predictor is not None:
            return self._predictor

        try:
            import torch
            from model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Real Kronos inference requires upstream Kronos on PYTHONPATH plus torch/HuggingFace dependencies. "
                "Use dry_run=true for contract tests or install Kronos before real inference."
            ) from exc

        device = self.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_id)
        model = Kronos.from_pretrained(self.model_id)
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
            T=1.0,
            top_p=0.9,
            sample_count=1,
        )
        frame = frame.reset_index(drop=False)
        if "timestamp" not in frame.columns:
            frame.insert(0, "timestamp", y_timestamp.reset_index(drop=True))
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        device = self.device or "auto"
        return ForecastResult(frame=frame, device=device, elapsed_ms=elapsed_ms, backend="kronos")
