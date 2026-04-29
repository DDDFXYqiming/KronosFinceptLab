"""Minimal Qlib-style adapter for FinceptTerminal AI Quant Lab.

The adapter intentionally avoids training in v0.1. It converts a list of OHLCV
rows into a forecast signal that later backtest modules can consume.
"""

from __future__ import annotations

from typing import Any

from kronos_fincept.schemas import ForecastRequest
from kronos_fincept.service import forecast_from_request


class KronosModelAdapter:
    """Qlib-like model adapter exposing fit/predict."""

    def __init__(self, model_id: str = "NeoQuasar/Kronos-small", tokenizer_id: str = "NeoQuasar/Kronos-Tokenizer-base") -> None:
        self.model_id = model_id
        self.tokenizer_id = tokenizer_id
        self.is_fitted = False

    def fit(self, *_args: Any, **_kwargs: Any) -> "KronosModelAdapter":
        """Record readiness. Real fine-tuning is planned for a later phase."""
        self.is_fitted = True
        return self

    def predict(self, symbol: str, timeframe: str, rows: list[dict[str, Any]], pred_len: int, dry_run: bool = False) -> dict[str, Any]:
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
