"""High-level forecast service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from kronos_fincept.data_adapter import rows_to_dataframe
from kronos_fincept.predictor import DryRunPredictor, KronosPredictorWrapper, ProbabilisticForecastResult
from kronos_fincept.schemas import ForecastRequest, RESEARCH_WARNING


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx, record in enumerate(frame.to_dict(orient="records"), start=1):
        normalized: dict[str, Any] = {}
        for key, value in record.items():
            if key == "timestamp":
                # 预测结果使用 D1~D5 格式，不输出具体日期
                normalized[key] = f"D{idx}"
            elif key == "index":
                # 跳过原始日期索引，不输出
                continue
            else:
                try:
                    normalized[key] = float(value) if value is not None else 0.0
                except (TypeError, ValueError):
                    normalized[key] = str(value)
        records.append(normalized)
    return records


def forecast_from_request(request: ForecastRequest) -> dict[str, Any]:
    """Run a forecast request and return the stable JSON contract.

    When sample_count > 1, runs probabilistic forecasting and includes
    Upside Probability, Volatility Amplification, Forecast Range, and Mean Forecast.
    """
    df, timestamps = rows_to_dataframe(request.rows_as_dicts())

    if request.dry_run:
        # Dry-run: simple deterministic prediction
        predictor = DryRunPredictor()
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

    # Real inference
    predictor = KronosPredictorWrapper(
        model_id=request.model_id,
        tokenizer_id=request.tokenizer_id,
        max_context=request.max_context,
        temperature=request.temperature,
        top_k=request.top_k,
        top_p=request.top_p,
        sample_count=request.sample_count,
    )

    if request.sample_count > 1:
        # Probabilistic forecasting
        prob_result = predictor.predict_probabilistic(
            df=df,
            x_timestamp=timestamps,
            pred_len=request.pred_len,
        )
        return {
            "ok": True,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "model_id": request.model_id,
            "tokenizer_id": request.tokenizer_id,
            "pred_len": request.pred_len,
            "forecast": _frame_to_records(prob_result.mean_frame),
            "probabilistic": {
                "sample_count": prob_result.sample_count,
                "upside_probability": round(prob_result.upside_probability, 4),
                "volatility_amplification": round(prob_result.volatility_amplification, 4),
                "forecast_range": {
                    "min": round(prob_result.forecast_range[0], 2),
                    "max": round(prob_result.forecast_range[1], 2),
                },
                "mean_final_close": round(prob_result.mean_final_close, 2),
            },
            "metadata": {
                "device": prob_result.device,
                "elapsed_ms": prob_result.elapsed_ms,
                "backend": prob_result.backend,
                "warning": RESEARCH_WARNING,
            },
        }
    else:
        # Single sample (original behavior)
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

    Uses predict_batch() when available for better performance.

    Args:
        requests: List of ForecastRequest, one per asset.

    Returns:
        List of RankedSignal sorted by predicted_return descending (best first).
    """
    if not requests:
        return []

    # Check if we should use batch prediction
    # Use batch when all requests are single-sample (not probabilistic)
    use_batch = (
        not requests[0].dry_run
        and all(req.sample_count == 1 for req in requests)
        and len(requests) > 1
    )

    if use_batch:
        # Prepare batch inputs
        from kronos_fincept.predictor import KronosPredictorWrapper
        from kronos_fincept.data_adapter import rows_to_dataframe

        predictor = KronosPredictorWrapper(
            model_id=requests[0].model_id,
            tokenizer_id=requests[0].tokenizer_id,
            max_context=requests[0].max_context,
            temperature=requests[0].temperature,
            top_k=requests[0].top_k,
            top_p=requests[0].top_p,
            sample_count=requests[0].sample_count,
        )

        dfs = []
        timestamps = []
        for req in requests:
            df, ts = rows_to_dataframe(req.rows_as_dicts())
            dfs.append(df)
            timestamps.append(ts)

        try:
            results = predictor.predict_batch(dfs, timestamps, requests[0].pred_len)

            signals: list[RankedSignal] = []
            for i, (req, result) in enumerate(zip(requests, results)):
                forecast_records = _frame_to_records(result.frame)
                last_close = float(req.rows[-1].close)
                forecast_close = float(forecast_records[-1]["close"])
                predicted_return = forecast_close / last_close - 1.0

                signals.append(RankedSignal(
                    rank=0,
                    symbol=req.symbol,
                    last_close=last_close,
                    predicted_close=forecast_close,
                    predicted_return=predicted_return,
                    elapsed_ms=result.elapsed_ms,
                    forecast=forecast_records,
                ))

            # Sort by predicted_return descending
            signals.sort(key=lambda s: s.predicted_return, reverse=True)

            # Assign ranks
            for i, sig in enumerate(signals):
                sig.rank = i + 1

            return signals

        except Exception:
            # Fallback to sequential if batch fails
            pass

    # Fallback: sequential prediction
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
