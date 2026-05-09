"""Input and output contracts for KronosFinceptLab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_MODEL_ID = "NeoQuasar/Kronos-base"
DEFAULT_TOKENIZER_ID = "NeoQuasar/Kronos-Tokenizer-base"

# ── Kronos model family ──
# Model Zoo (from upstream Kronos README):
#   Kronos-mini  4.1M  ctx=2048  Tokenizer-2k
#   Kronos-small 24.7M ctx=512   Tokenizer-base
#   Kronos-base  102.3M ctx=512  Tokenizer-base
#   Kronos-large 499.2M ctx=512  Tokenizer-base (closed)

_KRONOS_MODEL_VARIANTS: dict[str, dict[str, str | int]] = {
    "NeoQuasar/Kronos-mini": {"tokenizer": "NeoQuasar/Kronos-Tokenizer-2k", "max_context": 2048},
    "NeoQuasar/Kronos-small": {"tokenizer": "NeoQuasar/Kronos-Tokenizer-base", "max_context": 512},
    "NeoQuasar/Kronos-base": {"tokenizer": "NeoQuasar/Kronos-Tokenizer-base", "max_context": 512},
}

RESEARCH_WARNING = "Research forecast only; not trading advice."


def resolve_tokenizer_id(model_id: str) -> str:
    """Return the appropriate tokenizer ID for a given Kronos model ID."""
    variant = _KRONOS_MODEL_VARIANTS.get(model_id)
    if variant is not None:
        return str(variant["tokenizer"])
    # Fallback: if model_id contains "mini", use Tokenizer-2k
    if "mini" in model_id.lower():
        return "NeoQuasar/Kronos-Tokenizer-2k"
    return DEFAULT_TOKENIZER_ID


def resolve_max_context(model_id: str) -> int:
    """Return the appropriate max_context for a given Kronos model ID."""
    variant = _KRONOS_MODEL_VARIANTS.get(model_id)
    if variant is not None:
        return int(variant["max_context"])
    if "mini" in model_id.lower():
        return 2048
    return 512


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

    @classmethod
    def from_pydantic(cls, pydantic_row: Any) -> "ForecastRow":
        """Convert a Pydantic ForecastRowIn to a dataclass ForecastRow."""
        return cls(
            timestamp=pydantic_row.timestamp,
            open=pydantic_row.open,
            high=pydantic_row.high,
            low=pydantic_row.low,
            close=pydantic_row.close,
            volume=pydantic_row.volume,
            amount=pydantic_row.amount,
        )

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

    @classmethod
    def from_pydantic(cls, pydantic_req: Any) -> "ForecastRequest":
        """Convert a Pydantic ForecastRequestIn to a dataclass ForecastRequest."""
        return cls(
            symbol=pydantic_req.symbol,
            timeframe=pydantic_req.timeframe,
            pred_len=pydantic_req.pred_len,
            rows=[ForecastRow.from_pydantic(r) for r in pydantic_req.rows],
            model_id=pydantic_req.model_id,
            tokenizer_id=pydantic_req.tokenizer_id,
            dry_run=pydantic_req.dry_run,
            max_context=pydantic_req.max_context,
            temperature=pydantic_req.temperature,
            top_k=pydantic_req.top_k,
            top_p=pydantic_req.top_p,
            sample_count=pydantic_req.sample_count,
        )

    @classmethod
    def from_batch_item(
        cls,
        symbol: str,
        timeframe: str,
        pred_len: int,
        rows: list[Any],
        model_id: str | None = None,
        tokenizer_id: str | None = None,
        dry_run: bool = False,
        max_context: int | None = None,
        temperature: float | None = None,
        top_k: int | None = None,
        top_p: float | None = None,
        sample_count: int | None = None,
    ) -> "ForecastRequest":
        """Build a ForecastRequest from a batch item with optional field fallbacks."""
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            pred_len=pred_len,
            rows=[ForecastRow.from_pydantic(r) for r in rows],
            model_id=model_id or DEFAULT_MODEL_ID,
            tokenizer_id=tokenizer_id or DEFAULT_TOKENIZER_ID,
            dry_run=dry_run,
            max_context=max_context if max_context is not None else 512,
            temperature=temperature if temperature is not None else 1.0,
            top_k=top_k if top_k is not None else 0,
            top_p=top_p if top_p is not None else 0.9,
            sample_count=sample_count if sample_count is not None else 1,
        )

    def rows_as_dicts(self) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self.rows]


def build_error_response(message: str, symbol: str | None = None) -> dict[str, Any]:
    response: dict[str, Any] = {"ok": False}
    if symbol is not None:
        response["symbol"] = symbol
    response["error"] = message
    return response


@dataclass(frozen=True)
class BatchForecastRequest:
    """Batch forecast request wrapping multiple single-asset requests.

    Each entry in *requests* must be a fully-formed ForecastRequest.
    Alternatively, callers may provide *symbols_data* with shared defaults
    to build ForecastRequest objects automatically.
    """

    requests: list[ForecastRequest]

    @classmethod
    def from_dicts(cls, payloads: list[dict[str, Any]], shared: dict[str, Any] | None = None) -> "BatchForecastRequest":
        """Build a BatchForecastRequest from a list of per-symbol dicts.

        Parameters
        ----------
        payloads:
            One dict per symbol.  Each dict must contain at least *symbol* and
            *rows*.  All other ForecastRequest fields are optional and may be
            overridden per-symbol or via *shared* defaults.
        shared:
            Optional dict of defaults (e.g. ``timeframe``, ``pred_len``,
            ``model_id``, ...) applied to every symbol unless the per-symbol
            dict already defines that key.
        """
        if not payloads:
            raise ValueError("requests list must not be empty")
        merged = dict(shared or {})
        requests: list[ForecastRequest] = []
        for entry in payloads:
            combined: dict[str, Any] = {**merged, **entry}  # per-symbol wins
            requests.append(ForecastRequest.from_dict(combined))
        return cls(requests=requests)
