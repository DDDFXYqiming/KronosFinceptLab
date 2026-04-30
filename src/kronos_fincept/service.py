"""High-level forecast service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from kronos_fincept.data_adapter import rows_to_dataframe
from kronos_fincept.predictor import DryRunPredictor, KronosPredictorWrapper
from kronos_fincept.schemas import ForecastRequest, RESEARCH_WARNING


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        normalized: dict[str, Any] = {}
        for key, value in record.items():
            if key == "timestamp":
                normalized[key] = str(value)
            else:
                try:
                    normalized[key] = float(value) if value is not None else 0.0
                except (TypeError, ValueError):
                    normalized[key] = str(value)
        records.append(normalized)
    return records


def forecast_from_request(request: ForecastRequest) -> dict[str, Any]:
    """Run a forecast request and return the stable JSON contract."""
    df, timestamps = rows_to_dataframe(request.rows_as_dicts())
    predictor = DryRunPredictor() if request.dry_run else KronosPredictorWrapper(
        model_id=request.model_id,
        tokenizer_id=request.tokenizer_id,
        max_context=request.max_context,
        temperature=request.temperature,
        top_k=request.top_k,
        top_p=request.top_p,
        sample_count=request.sample_count,
    )
    result = predictor.predict(df=df, x_timestamp=timestamps, pred_len=request.pred_len)
    return {
        "ok": True,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "model_id": request.model_id,
        "tokenizer_id": request.tokenizer_id,
        "pred_len": request.pred_len,
        "forecast": _frame_to_records(result.frame),
        "metadata": {
            "device": result.device,
            "elapsed_ms": result.elapsed_ms,
            "backend": result.backend,
            "warning": RESEARCH_WARNING,
        },
    }


@dataclass
class RankedSignal:
    """One ranked signal from batch forecast."""
    rank: int
    symbol: str
    last_close: float
    predicted_close: float
    predicted_return: float
    elapsed_ms: int
    forecast: list[dict[str, Any]]


def batch_forecast_from_requests(
    requests: list[ForecastRequest],
) -> list[RankedSignal]:
    """Run forecast on multiple assets and return ranked by predicted_return.

    Args:
        requests: List of ForecastRequest, one per asset.

    Returns:
        List of RankedSignal sorted by predicted_return descending (best first).
    """
    signals: list[RankedSignal] = []

    for req in requests:
        response = forecast_from_request(req)
        if not response.get("ok") or not response.get("forecast"):
            continue

        last_close = float(req.rows[-1].close)
        forecast_close = float(response["forecast"][-1]["close"])
        predicted_return = forecast_close / last_close - 1.0
        elapsed_ms = response.get("metadata", {}).get("elapsed_ms", 0)

        signals.append(RankedSignal(
            rank=0,
            symbol=req.symbol,
            last_close=last_close,
            predicted_close=forecast_close,
            predicted_return=predicted_return,
            elapsed_ms=elapsed_ms,
            forecast=response["forecast"],
        ))

    # Sort by predicted_return descending
    signals.sort(key=lambda s: s.predicted_return, reverse=True)

    # Assign ranks
    for i, sig in enumerate(signals):
        sig.rank = i + 1

    return signals
