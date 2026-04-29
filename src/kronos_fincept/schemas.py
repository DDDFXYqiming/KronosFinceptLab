"""Input and output contracts for KronosFinceptLab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_MODEL_ID = "NeoQuasar/Kronos-small"
DEFAULT_TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"
RESEARCH_WARNING = "Research forecast only; not trading advice."


def _required(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ValueError(f"missing required field: {key}")
    return mapping[key]


def _to_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc


@dataclass(frozen=True)
class ForecastRow:
    """One OHLCV row accepted by Kronos."""

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    amount: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ForecastRow":
        row = cls(
            timestamp=str(_required(payload, "timestamp")),
            open=_to_float(_required(payload, "open"), "open"),
            high=_to_float(_required(payload, "high"), "high"),
            low=_to_float(_required(payload, "low"), "low"),
            close=_to_float(_required(payload, "close"), "close"),
            volume=_to_float(payload.get("volume", 0.0), "volume"),
            amount=_to_float(payload.get("amount", 0.0), "amount"),
        )
        row.validate_ohlc()
        return row

    def validate_ohlc(self) -> None:
        """Validate basic OHLC constraints."""
        if self.high < max(self.open, self.close):
            raise ValueError("high must be greater than or equal to open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be less than or equal to open and close")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.amount < 0:
            raise ValueError("amount must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
        }


@dataclass(frozen=True)
class ForecastRequest:
    """Validated forecast request."""

    symbol: str
    timeframe: str
    pred_len: int
    rows: list[ForecastRow]
    model_id: str = DEFAULT_MODEL_ID
    tokenizer_id: str = DEFAULT_TOKENIZER_ID
    dry_run: bool = False
    max_context: int = 512
    temperature: float = 1.0
    top_k: int = 0
    top_p: float = 0.9
    sample_count: int = 1

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ForecastRequest":
        rows_payload = _required(payload, "rows")
        if not isinstance(rows_payload, list) or not rows_payload:
            raise ValueError("rows must be a non-empty list")

        pred_len = int(_required(payload, "pred_len"))
        if pred_len <= 0:
            raise ValueError("pred_len must be positive")

        return cls(
            symbol=str(_required(payload, "symbol")),
            timeframe=str(payload.get("timeframe", "unknown")),
            pred_len=pred_len,
            rows=[ForecastRow.from_dict(row) for row in rows_payload],
            model_id=str(payload.get("model_id", DEFAULT_MODEL_ID)),
            tokenizer_id=str(payload.get("tokenizer_id", DEFAULT_TOKENIZER_ID)),
            dry_run=bool(payload.get("dry_run", False)),
            max_context=int(payload.get("max_context", 512)),
            temperature=float(payload.get("temperature", 1.0)),
            top_k=int(payload.get("top_k", 0)),
            top_p=float(payload.get("top_p", 0.9)),
            sample_count=int(payload.get("sample_count", 1)),
        )

    def rows_as_dicts(self) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self.rows]


def build_error_response(message: str, symbol: str | None = None) -> dict[str, Any]:
    response: dict[str, Any] = {"ok": False}
    if symbol is not None:
        response["symbol"] = symbol
    response["error"] = message
    return response
