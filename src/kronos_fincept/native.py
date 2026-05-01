"""Optional Rust acceleration bridge.

The Python implementation remains the source of compatibility. Rust kernels are
used only when explicitly enabled and the native extension is installed.
"""

from __future__ import annotations

import importlib
import os
from functools import lru_cache
from typing import Any, Iterable

_TRUE_VALUES = {"1", "true", "yes", "on", "auto"}
_FALSE_VALUES = {"", "0", "false", "no", "off"}


def rust_engine_mode() -> str:
    """Return the normalized Rust engine mode."""
    return os.environ.get("USE_RUST_ENGINE", "0").strip().lower()


def is_rust_engine_requested() -> bool:
    """Return whether callers should try the Rust extension."""
    mode = rust_engine_mode()
    if mode in _FALSE_VALUES:
        return False
    return mode in _TRUE_VALUES


@lru_cache(maxsize=1)
def _load_native() -> Any | None:
    try:
        return importlib.import_module("kronos_fincept_native")
    except ImportError:
        return None


def native_available() -> bool:
    """Return whether the optional Rust extension can be imported."""
    return _load_native() is not None


def calculate_rsi(prices: Iterable[float], period: int) -> list[float] | None:
    if not is_rust_engine_requested():
        return None
    native = _load_native()
    if native is None:
        return None
    return list(native.calculate_rsi([float(p) for p in prices], int(period)))


def calculate_macd(
    prices: Iterable[float],
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> dict[str, list[float]] | None:
    if not is_rust_engine_requested():
        return None
    native = _load_native()
    if native is None:
        return None
    result = native.calculate_macd(
        [float(p) for p in prices],
        int(fast_period),
        int(slow_period),
        int(signal_period),
    )
    return {
        "macd_line": list(result["macd_line"]),
        "signal_line": list(result["signal_line"]),
        "histogram": list(result["histogram"]),
    }


def calculate_var_historical(
    returns: Iterable[float],
    confidence_level: float,
    holding_period: int,
) -> float | None:
    if not is_rust_engine_requested():
        return None
    native = _load_native()
    if native is None:
        return None
    return float(
        native.calculate_var_historical(
            [float(r) for r in returns],
            float(confidence_level),
            int(holding_period),
        )
    )
