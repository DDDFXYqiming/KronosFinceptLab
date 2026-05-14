"""Benchmark Python fallback vs optional Rust native kernels.

Run after building and installing the native wheel:
    python scripts/benchmark_rust_native.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from statistics import mean

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from kronos_fincept import native
from kronos_fincept.api.routes.backtest import _calculate_metrics
from kronos_fincept.financial.derivatives import DerivativesPricer
from kronos_fincept.financial.indicators import TechnicalIndicators
from kronos_fincept.financial.portfolio import PortfolioOptimizer
from kronos_fincept.financial.risk import RiskCalculator
from kronos_fincept.financial.strategies import QuantitativeStrategies


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
    pricer = DerivativesPricer(risk_free_rate=0.05)
    portfolio = PortfolioOptimizer()
    strategies = QuantitativeStrategies()
    highs = [price * 1.012 for price in prices]
    lows = [price * 0.991 for price in prices]
    volumes = [1_000_000.0 + (i % 17) * 25_000.0 for i in range(len(prices))]
    portfolio_frame = pd.DataFrame(
        {
            "Asset1": prices,
            "Asset2": [price * (1.0 + ((i % 11) - 5) * 0.0005) for i, price in enumerate(prices)],
            "Asset3": [price * (1.0 + ((i % 13) - 6) * 0.0004) for i, price in enumerate(prices)],
        }
    )
    equity_curve = [
        {"equity": 100_000.0 * (1 + ((i % 9) - 4) * 0.0007)}
        for i in range(1, 250)
    ]

    # Warm up imports, caches, and extension dispatch.
    indicators.calculate_sma(prices, 20)
    indicators.calculate_ema(prices, 20)
    indicators.calculate_rsi(prices, 14)
    indicators.calculate_macd(prices)
    indicators.calculate_bollinger_bands(prices, 20, 2.0)
    indicators.calculate_kdj(highs, lows, prices, 9)
    indicators.calculate_atr(highs, lows, prices, 14)
    indicators.calculate_obv(prices, volumes)
    risk.calculate_var_historical(returns, 0.95)
    risk.calculate_sharpe_ratio(returns)
    risk.calculate_sortino_ratio(returns)
    risk.calculate_max_drawdown(prices)
    risk.calculate_volatility(returns)
    pricer.price_european_call(100.0, 100.0, 1.0, 0.2)
    pricer.put_call_parity(10.0, 100.0, 100.0, 1.0)
    portfolio_returns = portfolio.calculate_returns(portfolio_frame)
    expected_returns = portfolio.calculate_expected_returns(portfolio_returns)
    cov_matrix = portfolio.calculate_covariance_matrix(portfolio_returns)
    portfolio.portfolio_performance(
        np.array([1 / 3, 1 / 3, 1 / 3]),
        expected_returns,
        cov_matrix,
    )
    strategies.run_all_strategies(prices)
    _calculate_metrics(equity_curve, 120, 64)

    return {
        "sma_ms": _time_call(lambda: indicators.calculate_sma(prices, 20), 200),
        "ema_ms": _time_call(lambda: indicators.calculate_ema(prices, 20), 200),
        "rsi_ms": _time_call(lambda: indicators.calculate_rsi(prices, 14), 200),
        "macd_ms": _time_call(lambda: indicators.calculate_macd(prices), 100),
        "bollinger_ms": _time_call(
            lambda: indicators.calculate_bollinger_bands(prices, 20, 2.0), 100
        ),
        "kdj_ms": _time_call(lambda: indicators.calculate_kdj(highs, lows, prices, 9), 100),
        "atr_ms": _time_call(lambda: indicators.calculate_atr(highs, lows, prices, 14), 100),
        "obv_ms": _time_call(lambda: indicators.calculate_obv(prices, volumes), 200),
        "historical_var_ms": _time_call(
            lambda: risk.calculate_var_historical(returns, 0.95), 500
        ),
        "sharpe_ms": _time_call(lambda: risk.calculate_sharpe_ratio(returns), 500),
        "sortino_ms": _time_call(lambda: risk.calculate_sortino_ratio(returns), 500),
        "max_drawdown_ms": _time_call(lambda: risk.calculate_max_drawdown(prices), 500),
        "volatility_ms": _time_call(lambda: risk.calculate_volatility(returns), 500),
        "black_scholes_ms": _time_call(
            lambda: pricer.price_european_call(100.0, 100.0, 1.0, 0.2), 500
        ),
        "put_call_parity_ms": _time_call(
            lambda: pricer.put_call_parity(10.0, 100.0, 100.0, 1.0), 500
        ),
        "portfolio_returns_ms": _time_call(
            lambda: portfolio.calculate_returns(portfolio_frame), 100
        ),
        "portfolio_covariance_ms": _time_call(
            lambda: portfolio.calculate_covariance_matrix(
                portfolio.calculate_returns(portfolio_frame)
            ),
            100,
        ),
        "portfolio_performance_ms": _time_call(
            lambda: portfolio.portfolio_performance(
                np.array([1 / 3, 1 / 3, 1 / 3]),
                expected_returns,
                cov_matrix,
            ),
            500,
        ),
        "strategy_snapshot_ms": _time_call(lambda: strategies.run_all_strategies(prices), 100),
        "backtest_metrics_ms": _time_call(
            lambda: _calculate_metrics(equity_curve, 120, 64), 500
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
