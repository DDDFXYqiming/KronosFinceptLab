"""Optional Rust acceleration bridge.

The Python implementation remains the compatibility source. Rust kernels are
used when requested and the native extension is installed. Missing or failing
native calls fall back to Python.
"""

from __future__ import annotations

import importlib
import logging
import os
from functools import lru_cache
from typing import Any, Iterable

from kronos_fincept.logging_config import log_event

logger = logging.getLogger(__name__)

_AUTO_VALUE = "auto"
_FORCED_TRUE_VALUES = {"1", "true", "yes", "on"}
_TRUE_VALUES = _FORCED_TRUE_VALUES | {_AUTO_VALUE}
_FALSE_VALUES = {"", "0", "false", "no", "off"}


def rust_engine_mode() -> str:
    """Return the normalized Rust engine mode."""
    return os.environ.get("USE_RUST_ENGINE", _AUTO_VALUE).strip().lower()


def is_rust_engine_requested() -> bool:
    """Return whether callers should try the Rust extension."""
    mode = rust_engine_mode()
    if mode in _FALSE_VALUES:
        return False
    return mode in _TRUE_VALUES


def is_rust_engine_forced() -> bool:
    """Return whether missing or failing Rust should be logged loudly."""
    return rust_engine_mode() in _FORCED_TRUE_VALUES


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
        level = logging.WARNING if is_rust_engine_forced() else logging.DEBUG
        if is_rust_engine_requested():
            log_event(
                logger,
                level,
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
        level = logging.WARNING if is_rust_engine_forced() else logging.DEBUG
        log_event(
            logger,
            level,
            "rust_native.missing_function",
            "Rust native function missing; using Python fallback",
            mode=rust_engine_mode(),
            function=name,
        )
    return func


def _call_native(name: str, *args: Any) -> Any | None:
    if not is_rust_engine_requested():
        return None
    func = _native_function(name)
    if func is None:
        return None
    try:
        return func(*args)
    except Exception as exc:
        level = logging.WARNING if is_rust_engine_forced() else logging.DEBUG
        log_event(
            logger,
            level,
            "rust_native.call_failed",
            "Rust native call failed; using Python fallback",
            mode=rust_engine_mode(),
            function=name,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return None


def _float_list(values: Iterable[float]) -> list[float]:
    return [float(value) for value in values]


def _float_matrix(rows: Iterable[Iterable[float]]) -> list[list[float]]:
    return [[float(value) for value in row] for row in rows]


def calculate_sma(prices: Iterable[float], period: int) -> list[float] | None:
    result = _call_native("calculate_sma", _float_list(prices), int(period))
    return list(result) if result is not None else None


def calculate_ema(prices: Iterable[float], period: int) -> list[float] | None:
    result = _call_native("calculate_ema", _float_list(prices), int(period))
    return list(result) if result is not None else None


def calculate_rsi(prices: Iterable[float], period: int) -> list[float] | None:
    result = _call_native("calculate_rsi", _float_list(prices), int(period))
    return list(result) if result is not None else None


def calculate_macd(
    prices: Iterable[float],
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> dict[str, list[float]] | None:
    result = _call_native(
        "calculate_macd",
        _float_list(prices),
        int(fast_period),
        int(slow_period),
        int(signal_period),
    )
    if result is None:
        return None
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
    result = _call_native(
        "calculate_bollinger_bands",
        _float_list(prices),
        int(period),
        float(std_dev),
    )
    if result is None:
        return None
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
    result = _call_native(
        "calculate_kdj",
        _float_list(highs),
        _float_list(lows),
        _float_list(closes),
        int(period),
    )
    if result is None:
        return None
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
    result = _call_native(
        "calculate_atr",
        _float_list(highs),
        _float_list(lows),
        _float_list(closes),
        int(period),
    )
    return list(result) if result is not None else None


def calculate_obv(
    closes: Iterable[float],
    volumes: Iterable[float],
) -> list[float] | None:
    result = _call_native("calculate_obv", _float_list(closes), _float_list(volumes))
    return list(result) if result is not None else None


def calculate_var_historical(
    returns: Iterable[float],
    confidence_level: float,
    holding_period: int,
) -> float | None:
    result = _call_native(
        "calculate_var_historical",
        _float_list(returns),
        float(confidence_level),
        int(holding_period),
    )
    return float(result) if result is not None else None


def calculate_sharpe_ratio(
    returns: Iterable[float],
    risk_free_rate: float,
    trading_days_per_year: int,
) -> float | None:
    result = _call_native(
        "calculate_sharpe_ratio",
        _float_list(returns),
        float(risk_free_rate),
        int(trading_days_per_year),
    )
    return float(result) if result is not None else None


def calculate_sortino_ratio(
    returns: Iterable[float],
    risk_free_rate: float,
    target_return: float,
    trading_days_per_year: int,
) -> float | None:
    result = _call_native(
        "calculate_sortino_ratio",
        _float_list(returns),
        float(risk_free_rate),
        float(target_return),
        int(trading_days_per_year),
    )
    return float(result) if result is not None else None


def calculate_max_drawdown(prices: Iterable[float]) -> float | None:
    result = _call_native("calculate_max_drawdown", _float_list(prices))
    return float(result) if result is not None else None


def calculate_volatility(
    returns: Iterable[float],
    annualize: bool,
    trading_days_per_year: int,
) -> float | None:
    result = _call_native(
        "calculate_volatility",
        _float_list(returns),
        bool(annualize),
        int(trading_days_per_year),
    )
    return float(result) if result is not None else None


def price_black_scholes(
    underlying_price: float,
    strike_price: float,
    time_to_expiration: float,
    volatility: float,
    risk_free_rate: float,
    option_type: str,
) -> dict[str, Any] | None:
    result = _call_native(
        "price_black_scholes",
        float(underlying_price),
        float(strike_price),
        float(time_to_expiration),
        float(volatility),
        float(risk_free_rate),
        str(option_type),
    )
    return dict(result) if result is not None else None

def calculate_put_call_parity(
    call_price: float,
    underlying_price: float,
    strike_price: float,
    time_to_expiration: float,
    risk_free_rate: float,
) -> float | None:
    result = _call_native(
        "calculate_put_call_parity",
        float(call_price),
        float(underlying_price),
        float(strike_price),
        float(time_to_expiration),
        float(risk_free_rate),
    )
    return float(result) if result is not None else None


def calculate_portfolio_returns(prices: Iterable[Iterable[float]]) -> list[list[float]] | None:
    result = _call_native("calculate_portfolio_returns", _float_matrix(prices))
    return _float_matrix(result) if result is not None else None


def calculate_expected_returns(returns: Iterable[Iterable[float]]) -> list[float] | None:
    result = _call_native("calculate_expected_returns", _float_matrix(returns))
    return list(result) if result is not None else None


def calculate_covariance_matrix(returns: Iterable[Iterable[float]]) -> list[list[float]] | None:
    result = _call_native("calculate_covariance_matrix", _float_matrix(returns))
    return _float_matrix(result) if result is not None else None


def calculate_portfolio_performance(
    weights: Iterable[float],
    expected_returns: Iterable[float],
    covariance_matrix: Iterable[Iterable[float]],
) -> dict[str, float] | None:
    result = _call_native(
        "calculate_portfolio_performance",
        _float_list(weights),
        _float_list(expected_returns),
        _float_matrix(covariance_matrix),
    )
    if result is None:
        return None
    return {
        "expected_return": float(result["expected_return"]),
        "volatility": float(result["volatility"]),
    }


def calculate_strategy_snapshot(
    closes: Iterable[float],
    fast_period: int = 20,
    slow_period: int = 50,
    rsi_period: int = 14,
    overbought: float = 70,
    oversold: float = 30,
    macd_fast_period: int = 12,
    macd_slow_period: int = 26,
    macd_signal_period: int = 9,
    bollinger_period: int = 20,
    bollinger_std_dev: float = 2.0,
) -> dict[str, dict[str, Any]] | None:
    result = _call_native(
        "calculate_strategy_snapshot",
        _float_list(closes),
        int(fast_period),
        int(slow_period),
        int(rsi_period),
        float(overbought),
        float(oversold),
        int(macd_fast_period),
        int(macd_slow_period),
        int(macd_signal_period),
        int(bollinger_period),
        float(bollinger_std_dev),
    )
    return {str(key): dict(value) for key, value in dict(result).items()} if result is not None else None


def calculate_backtest_metrics(
    equities: Iterable[float],
    total_trades: int,
    winning_trades: int,
) -> dict[str, Any] | None:
    result = _call_native(
        "calculate_backtest_metrics",
        _float_list(equities),
        int(total_trades),
        int(winning_trades),
    )
    return dict(result) if result is not None else None
