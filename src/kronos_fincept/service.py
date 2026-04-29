"""High-level forecast service."""

from __future__ import annotations

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
                normalized[key] = float(value) if value is not None else 0.0
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
