"""Optional Rust acceleration bridge.

The Python implementation remains the source of compatibility. Rust kernels are
used only when explicitly enabled and the native extension is installed.
"""

from __future__ import annotations

import importlib
import logging
import os
from functools import lru_cache
from typing import Any, Iterable

from kronos_fincept.logging_config import log_event

logger = logging.getLogger(__name__)

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
        module = importlib.import_module("kronos_fincept_native")
        log_event(
            logger,
            logging.INFO,
            "rust_native.available",
            "Rust native extension loaded",
            mode=rust_engine_mode(),
        )
        return module
    except ImportError as exc:
        if is_rust_engine_requested():
            log_event(
                logger,
                logging.WARNING,
                "rust_native.unavailable",
                "Rust native extension unavailable; using Python fallback",
                mode=rust_engine_mode(),
                error_type=type(exc).__name__,
            )
        return None


def native_available() -> bool:
    """Return whether the optional Rust extension can be imported."""
    return _load_native() is not None


def _native_function(name: str) -> Any | None:
    native = _load_native()
    if native is None:
        return None
    func = getattr(native, name, None)
    if func is None:
        log_event(
            logger,
            logging.WARNING,
            "rust_native.missing_function",
            "Rust native function missing; using Python fallback",
            mode=rust_engine_mode(),
            function=name,
        )
    return func


def calculate_sma(prices: Iterable[float], period: int) -> list[float] | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_sma")
    if calculate is None:
        return None
    return list(calculate([float(p) for p in prices], int(period)))


def calculate_ema(prices: Iterable[float], period: int) -> list[float] | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_ema")
    if calculate is None:
        return None
    return list(calculate([float(p) for p in prices], int(period)))


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


def calculate_bollinger_bands(
    prices: Iterable[float],
    period: int,
    std_dev: float,
) -> dict[str, list[float]] | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_bollinger_bands")
    if calculate is None:
        return None
    result = calculate(
        [float(p) for p in prices],
        int(period),
        float(std_dev),
    )
    return {
        "upper": list(result["upper"]),
        "middle": list(result["middle"]),
        "lower": list(result["lower"]),
    }


def calculate_kdj(
    highs: Iterable[float],
    lows: Iterable[float],
    closes: Iterable[float],
    period: int,
) -> dict[str, list[float]] | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_kdj")
    if calculate is None:
        return None
    result = calculate(
        [float(p) for p in highs],
        [float(p) for p in lows],
        [float(p) for p in closes],
        int(period),
    )
    return {
        "k": list(result["k"]),
        "d": list(result["d"]),
        "j": list(result["j"]),
    }


def calculate_atr(
    highs: Iterable[float],
    lows: Iterable[float],
    closes: Iterable[float],
    period: int,
) -> list[float] | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_atr")
    if calculate is None:
        return None
    return list(
        calculate(
            [float(p) for p in highs],
            [float(p) for p in lows],
            [float(p) for p in closes],
            int(period),
        )
    )


def calculate_obv(
    closes: Iterable[float],
    volumes: Iterable[float],
) -> list[float] | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_obv")
    if calculate is None:
        return None
    return list(
        calculate(
            [float(p) for p in closes],
            [float(v) for v in volumes],
        )
    )


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


def calculate_sharpe_ratio(
    returns: Iterable[float],
    risk_free_rate: float,
    trading_days_per_year: int,
) -> float | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_sharpe_ratio")
    if calculate is None:
        return None
    return float(
        calculate(
            [float(r) for r in returns],
            float(risk_free_rate),
            int(trading_days_per_year),
        )
    )


def calculate_sortino_ratio(
    returns: Iterable[float],
    risk_free_rate: float,
    target_return: float,
    trading_days_per_year: int,
) -> float | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_sortino_ratio")
    if calculate is None:
        return None
    return float(
        calculate(
            [float(r) for r in returns],
            float(risk_free_rate),
            float(target_return),
            int(trading_days_per_year),
        )
    )


def calculate_max_drawdown(prices: Iterable[float]) -> float | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_max_drawdown")
    if calculate is None:
        return None
    return float(calculate([float(p) for p in prices]))


def calculate_volatility(
    returns: Iterable[float],
    annualize: bool,
    trading_days_per_year: int,
) -> float | None:
    if not is_rust_engine_requested():
        return None
    calculate = _native_function("calculate_volatility")
    if calculate is None:
        return None
    return float(
        calculate(
            [float(r) for r in returns],
            bool(annualize),
            int(trading_days_per_year),
        )
    )
