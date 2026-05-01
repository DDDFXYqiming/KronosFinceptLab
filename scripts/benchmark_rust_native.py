"""Benchmark Python fallback vs optional Rust native kernels.

Run after building and installing the native wheel:
    python scripts/benchmark_rust_native.py
"""

from __future__ import annotations

import json
import os
import time
from statistics import mean

import numpy as np

from kronos_fincept import native
from kronos_fincept.financial.indicators import TechnicalIndicators
from kronos_fincept.financial.risk import RiskCalculator


def _sample_prices(size: int = 2000) -> list[float]:
    prices = [100.0]
    for i in range(1, size):
        prices.append(prices[-1] * (1 + ((i % 17) - 8) * 0.0008))
    return prices


def _time_call(fn, iterations: int) -> float:
    durations = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        durations.append(time.perf_counter() - start)
    return mean(durations) * 1000


def _bench_mode(mode: str, prices: list[float], returns: np.ndarray) -> dict[str, float]:
    os.environ["USE_RUST_ENGINE"] = mode
    native._load_native.cache_clear()
    indicators = TechnicalIndicators()
    risk = RiskCalculator()

    # Warm up imports, caches, and extension dispatch.
    indicators.calculate_rsi(prices, 14)
    indicators.calculate_macd(prices)
    risk.calculate_var_historical(returns, 0.95)

    return {
        "rsi_ms": _time_call(lambda: indicators.calculate_rsi(prices, 14), 200),
        "macd_ms": _time_call(lambda: indicators.calculate_macd(prices), 100),
        "historical_var_ms": _time_call(
            lambda: risk.calculate_var_historical(returns, 0.95), 500
        ),
    }


def main() -> int:
    prices = _sample_prices()
    returns = RiskCalculator().calculate_returns(prices)
    native_status = native.native_available()

    result = {
        "native_available": native_status,
        "sample_size": len(prices),
        "python": _bench_mode("0", prices, returns),
    }
    if native_status:
        result["rust"] = _bench_mode("1", prices, returns)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if native_status else 2


if __name__ == "__main__":
    raise SystemExit(main())
