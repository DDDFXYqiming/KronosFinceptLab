"""Qlib-style adapter for FinceptTerminal AI Quant Lab.

Supports single-asset and batch predictions with ranked return signals.
"""

from __future__ import annotations

from typing import Any

from kronos_fincept.schemas import ForecastRequest
from kronos_fincept.service import (
    batch_forecast_from_requests,
    forecast_from_request,
    RankedSignal,
)


class KronosModelAdapter:
    """Qlib-like model adapter exposing fit/predict/batch_predict."""

    def __init__(
        self,
        model_id: str = "NeoQuasar/Kronos-base",
        tokenizer_id: str = "NeoQuasar/Kronos-Tokenizer-base",
    ) -> None:
        self.model_id = model_id
        self.tokenizer_id = tokenizer_id
        self.is_fitted = False

    def fit(self, *_args: Any, **_kwargs: Any) -> "KronosModelAdapter":
        """Record readiness. Real fine-tuning is planned for a later phase."""
        self.is_fitted = True
        return self

    def predict(
        self,
        symbol: str,
        timeframe: str,
        rows: list[dict[str, Any]],
        pred_len: int,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Return forecast plus a simple predicted-return signal."""
        request = ForecastRequest.from_dict(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "pred_len": pred_len,
                "model_id": self.model_id,
                "tokenizer_id": self.tokenizer_id,
                "dry_run": dry_run,
                "rows": rows,
            }
        )
        response = forecast_from_request(request)
        if not response.get("ok") or not response.get("forecast"):
            return response
        last_close = float(rows[-1]["close"])
        forecast_close = float(response["forecast"][-1]["close"])
        response["signal"] = {
            "predicted_return": forecast_close / last_close - 1.0,
            "signal_type": "research_forecast",
        }
        return response

    def batch_predict(
        self,
        assets: list[dict[str, Any]],
        pred_len: int,
        timeframe: str = "daily",
        dry_run: bool = False,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """Run batch prediction on multiple assets and return ranked signals.

        Args:
            assets: List of dicts with 'symbol' and 'rows' keys.
                Example: [{"symbol": "000001", "rows": [...]}]
            pred_len: Number of future candles to predict.
            timeframe: Candle interval label.
            dry_run: Use deterministic predictor instead of real Kronos.
            top_k: If set, return only top K ranked results.

        Returns:
            {
                "ok": true,
                "count": 5,
                "signals": [
                    {
                        "rank": 1,
                        "symbol": "600036",
                        "last_close": 1500.0,
                        "predicted_close": 1550.0,
                        "predicted_return": 0.033,
                        "signal": "BUY",
                        "elapsed_ms": 123,
                        "forecast": [...]
                    },
                    ...
                ],
                "metadata": { "model_id": ..., "backend": ..., "warning": ... }
            }
        """
        requests: list[ForecastRequest] = []
        for asset in assets:
            req = ForecastRequest.from_dict({
                "symbol": asset["symbol"],
                "timeframe": timeframe,
                "pred_len": pred_len,
                "model_id": self.model_id,
                "tokenizer_id": self.tokenizer_id,
                "dry_run": dry_run,
                "rows": asset["rows"],
            })
            requests.append(req)

        ranked = batch_forecast_from_requests(requests)

        if top_k is not None and top_k > 0:
            ranked = ranked[:top_k]

        signals = []
        for sig in ranked:
            signals.append({
                "rank": sig.rank,
                "symbol": sig.symbol,
                "last_close": sig.last_close,
                "predicted_close": sig.predicted_close,
                "predicted_return": round(sig.predicted_return, 6),
                "signal": "BUY" if sig.rank <= 3 else "HOLD",
                "elapsed_ms": sig.elapsed_ms,
                "forecast": sig.forecast,
            })

        backend = signals[0]["elapsed_ms"] if signals else "dry_run"
        return {
            "ok": True,
            "count": len(signals),
            "signals": signals,
            "metadata": {
                "model_id": self.model_id,
                "tokenizer_id": self.tokenizer_id,
                "pred_len": pred_len,
                "dry_run": dry_run,
                "warning": "Research forecast only; not trading advice.",
            },
        }
