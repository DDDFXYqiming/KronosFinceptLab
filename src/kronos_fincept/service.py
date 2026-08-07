"""High-level forecast service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from kronos_fincept.config import settings
from kronos_fincept.data_adapter import rows_to_dataframe
from kronos_fincept.predictor import (
    DryRunPredictor,
    KronosPredictorWrapper,
    ProbabilisticForecastResult,
    prewarm_predictor,
)
from kronos_fincept.logging_config import log_event, log_perf
from kronos_fincept.schemas import (
    DEFAULT_MODEL_ID,
    ForecastRequest,
    RESEARCH_WARNING,
    build_error_response,
    resolve_tokenizer_id,
    resolve_max_context,
)
from kronos_fincept.security_utils import safe_configured_model_id, validate_kronos_model_id


logger = logging.getLogger(__name__)


def _effective_model_id(model_id: str) -> str:
    if model_id == DEFAULT_MODEL_ID and settings.kronos.model_id:
        return safe_configured_model_id(settings.kronos.model_id, DEFAULT_MODEL_ID)
    return validate_kronos_model_id(model_id)


def _configured_device() -> str | None:
    value = str(getattr(settings.kronos, "device", "") or "").strip()
    return value or None


def _predictor_device_kwargs() -> dict[str, str]:
    device = _configured_device()
    return {"device": device} if device else {}


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx, record in enumerate(frame.to_dict(orient="records"), start=1):
        normalized: dict[str, Any] = {}
        for key, value in record.items():
            if key == "timestamp":
                # Prediction results use D1~D5 format, don't output specific dates
                normalized[key] = f"D{idx}"
            elif key == "index":
                # Skip original date index, don't output
                continue
            else:
                try:
                    normalized[key] = float(value) if value is not None else 0.0
                except (TypeError, ValueError):
                    normalized[key] = str(value)
        records.append(normalized)
    return records


def _build_forecast_response(
    request: ForecastRequest,
    frame: pd.DataFrame,
    device: str,
    elapsed_ms: int,
    backend: str,
    probabilistic: dict[str, Any] | None = None,
    model_cached: bool = False,
    cache_key: str = "",
    load_wait_ms: int = 0,
    inference_wait_ms: int = 0,
) -> dict[str, Any]:
    """Build the standard forecast API response."""
    effective_model_id = _effective_model_id(request.model_id)
    resp: dict[str, Any] = {
        "ok": True,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "model_id": effective_model_id,
        "tokenizer_id": resolve_tokenizer_id(effective_model_id),
        "pred_len": request.pred_len,
        "forecast": _frame_to_records(frame),
        "metadata": {
            "device": device,
            "elapsed_ms": elapsed_ms,
            "backend": backend,
            "warning": RESEARCH_WARNING,
            "model_cached": model_cached,
            "cache_key": cache_key,
            "load_wait_ms": load_wait_ms,
            "inference_wait_ms": inference_wait_ms,
        },
    }
    if probabilistic is not None:
        resp["probabilistic"] = probabilistic
    return resp


@log_perf(event="svc.forecast", level=20)
def forecast_from_request(request: ForecastRequest) -> dict[str, Any]:
    """Run a forecast request and return the stable JSON contract.

    When sample_count > 1, runs probabilistic forecasting and includes
    Upside Probability, Volatility Amplification, Forecast Range, and Mean Forecast.
    """
    df, timestamps = rows_to_dataframe(request.rows_as_dicts())
    eff_id = _effective_model_id(request.model_id)
    log_event(
        logger,
        logging.INFO,
        "svc.forecast.audit",
        "Kronos forecast request audit",
        symbol=request.symbol,
        model_id=eff_id,
        bar_count=int(len(df)),
        time_range=[
            str(timestamps.iloc[0]),
            str(timestamps.iloc[-1]),
        ],
        pred_len=request.pred_len,
        max_context=request.max_context,
        temperature=request.temperature,
        top_k=request.top_k,
        top_p=request.top_p,
        sample_count=request.sample_count,
        dry_run=request.dry_run,
    )

    if request.dry_run:
        if not settings.kronos.allow_dry_run:
            return build_error_response(
                "Dry-run/mock predictor is disabled in this environment. "
                "Use real Kronos inference or enable KRONOS_ALLOW_DRY_RUN=1 explicitly.",
                request.symbol,
            )
        # Dry-run: simple deterministic prediction
        predictor = DryRunPredictor()
        result = predictor.predict(df=df, x_timestamp=timestamps, pred_len=request.pred_len)
        return _build_forecast_response(
            request, result.frame, result.device, result.elapsed_ms, result.backend,
            model_cached=result.model_cached,
            cache_key=result.cache_key,
            load_wait_ms=result.load_wait_ms,
            inference_wait_ms=result.inference_wait_ms,
        )

    if not settings.kronos.enable_real_model:
        return build_error_response(
            "Real Kronos inference is disabled by KRONOS_ENABLE_REAL_MODEL=0. "
            "Use dry_run=true or enable the model runtime explicitly.",
            request.symbol,
        )

    predictor = KronosPredictorWrapper(
        model_id=eff_id,
        tokenizer_id=resolve_tokenizer_id(eff_id),
        max_context=resolve_max_context(eff_id),
        temperature=request.temperature,
        top_k=request.top_k,
        top_p=request.top_p,
        sample_count=request.sample_count,
        **_predictor_device_kwargs(),
    )

    if request.sample_count > 1:
        # Probabilistic forecasting
        prob_result = predictor.predict_probabilistic(
            df=df,
            x_timestamp=timestamps,
            pred_len=request.pred_len,
        )
        prob_data = {
            "sample_count": prob_result.sample_count,
            "upside_probability": round(prob_result.upside_probability, 4),
            "volatility_amplification": round(prob_result.volatility_amplification, 4),
            "forecast_range": {
                "min": round(prob_result.forecast_range[0], 2),
                "max": round(prob_result.forecast_range[1], 2),
            },
            "mean_final_close": round(prob_result.mean_final_close, 2),
        }
        return _build_forecast_response(
            request, prob_result.mean_frame, prob_result.device,
            prob_result.elapsed_ms, prob_result.backend, probabilistic=prob_data,
            model_cached=prob_result.model_cached,
            cache_key=prob_result.cache_key,
            load_wait_ms=prob_result.load_wait_ms,
            inference_wait_ms=prob_result.inference_wait_ms,
        )
    else:
        # Single sample (original behavior)
        result = predictor.predict(df=df, x_timestamp=timestamps, pred_len=request.pred_len)
        return _build_forecast_response(
            request, result.frame, result.device, result.elapsed_ms, result.backend,
            model_cached=result.model_cached,
            cache_key=result.cache_key,
            load_wait_ms=result.load_wait_ms,
            inference_wait_ms=result.inference_wait_ms,
        )


def prewarm_default_predictor() -> dict[str, Any]:
    """Preload the configured real Kronos predictor into the shared process cache."""
    effective_id = _effective_model_id(DEFAULT_MODEL_ID)
    tokenizer_id = getattr(settings.kronos, "tokenizer_id", "") or resolve_tokenizer_id(effective_id)
    return prewarm_predictor(
        model_id=effective_id,
        tokenizer_id=tokenizer_id,
        max_context=resolve_max_context(effective_id),
        **_predictor_device_kwargs(),
    )


@log_perf(event="svc.batch_forecast_responses", level=20)
def forecast_batch_responses(requests: list[ForecastRequest]) -> list[dict[str, Any]]:
    """Return standard forecast responses while batching compatible real-model requests.

    Kronos' upstream ``predict_batch`` accepts ``sample_count`` and performs the
    stochastic samples inside one batched inference call. This keeps the normal
    response contract while avoiding one model invocation per asset.
    """
    if not requests:
        return []

    first = requests[0]
    compatible = (
        len(requests) > 1
        and all(not req.dry_run for req in requests)
        and settings.kronos.enable_real_model
        and all(req.pred_len == first.pred_len for req in requests)
        and all(_effective_model_id(req.model_id) == _effective_model_id(first.model_id) for req in requests)
        and all(req.temperature == first.temperature for req in requests)
        and all(req.top_k == first.top_k for req in requests)
        and all(req.top_p == first.top_p for req in requests)
        and all(req.sample_count == first.sample_count for req in requests)
    )
    if not compatible:
        return [forecast_from_request(req) for req in requests]

    effective_id = _effective_model_id(first.model_id)
    predictor = KronosPredictorWrapper(
        model_id=effective_id,
        tokenizer_id=resolve_tokenizer_id(effective_id),
        max_context=resolve_max_context(effective_id),
        temperature=first.temperature,
        top_k=first.top_k,
        top_p=first.top_p,
        sample_count=first.sample_count,
        **_predictor_device_kwargs(),
    )
    frames: list[pd.DataFrame] = []
    timestamps: list[pd.Series] = []
    for request in requests:
        frame, series = rows_to_dataframe(request.rows_as_dicts())
        frames.append(frame)
        timestamps.append(series)

    try:
        results = predictor.predict_batch(frames, timestamps, first.pred_len)
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "svc.batch_forecast.fallback",
            "Batch forecast failed; falling back to sequential forecasts",
            error_type=type(exc).__name__,
            batch_size=len(requests),
        )
        return [forecast_from_request(req) for req in requests]

    responses: list[dict[str, Any]] = []
    for request, result in zip(requests, results):
        response = _build_forecast_response(
            request,
            result.frame,
            result.device,
            result.elapsed_ms,
            result.backend,
            model_cached=result.model_cached,
            cache_key=result.cache_key,
            load_wait_ms=result.load_wait_ms,
            inference_wait_ms=result.inference_wait_ms,
        )
        response["metadata"]["batch_size"] = len(requests)
        response["metadata"]["sample_count"] = request.sample_count
        responses.append(response)
    return responses


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


@log_perf(event="svc.batch_forecast", level=20)
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

    if any(not req.dry_run for req in requests) and not settings.kronos.enable_real_model:
        return []

    # Check if we should use batch prediction
    # Use batch when all requests are single-sample (not probabilistic)
    use_batch = (
        all(not req.dry_run for req in requests)
        and all(req.pred_len == requests[0].pred_len for req in requests)
        and all(_effective_model_id(req.model_id) == _effective_model_id(requests[0].model_id) for req in requests)
        and all(req.temperature == requests[0].temperature for req in requests)
        and all(req.top_k == requests[0].top_k for req in requests)
        and all(req.top_p == requests[0].top_p for req in requests)
        and len(requests) > 1
    )

    if use_batch:
        # Prepare batch inputs
        effective_id = _effective_model_id(requests[0].model_id)
        predictor = KronosPredictorWrapper(
            model_id=effective_id,
            tokenizer_id=resolve_tokenizer_id(effective_id),
            max_context=resolve_max_context(effective_id),
            temperature=requests[0].temperature,
            top_k=requests[0].top_k,
            top_p=requests[0].top_p,
            sample_count=requests[0].sample_count,
            **_predictor_device_kwargs(),
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
