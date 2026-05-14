"""Tests for the optional Rust acceleration bridge."""

from __future__ import annotations

import importlib

import numpy as np
import pytest

from kronos_fincept import native
from kronos_fincept.api.routes.backtest import _calculate_metrics
from kronos_fincept.financial.derivatives import DerivativesPricer
from kronos_fincept.financial.indicators import TechnicalIndicators
from kronos_fincept.financial.portfolio import PortfolioOptimizer
from kronos_fincept.financial.risk import RiskCalculator
from kronos_fincept.financial.strategies import QuantitativeStrategies


def _reset_native_cache() -> None:
    native._load_native.cache_clear()


def test_rust_engine_can_be_disabled(monkeypatch):
    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    _reset_native_cache()

    assert native.calculate_sma([100.0, 101.0, 102.0], 2) is None
    assert native.calculate_ema([100.0, 101.0, 102.0], 2) is None
    assert native.calculate_rsi([100.0, 101.0, 102.0], 14) is None
    assert native.calculate_macd([100.0] * 40, 12, 26, 9) is None
    assert native.calculate_bollinger_bands([100.0] * 30, 20, 2.0) is None
    assert native.calculate_kdj([102.0] * 20, [98.0] * 20, [100.0] * 20, 9) is None
    assert native.calculate_atr([102.0] * 20, [98.0] * 20, [100.0] * 20, 14) is None
    assert native.calculate_obv([100.0, 101.0], [1000.0, 1200.0]) is None
    assert native.calculate_var_historical([0.01, -0.02], 0.95, 1) is None
    assert native.calculate_sharpe_ratio([0.01, -0.02], 0.03, 252) is None
    assert native.calculate_sortino_ratio([0.01, -0.02], 0.03, 0.0, 252) is None
    assert native.calculate_max_drawdown([100.0, 90.0]) is None
    assert native.calculate_volatility([0.01, -0.02], True, 252) is None
    assert native.price_black_scholes(100.0, 100.0, 1.0, 0.2, 0.05, "call") is None
    assert native.calculate_put_call_parity(10.0, 100.0, 100.0, 1.0, 0.05) is None
    assert native.calculate_portfolio_returns([[100.0], [101.0]]) is None
    assert native.calculate_expected_returns([[0.01], [0.02]]) is None
    assert native.calculate_covariance_matrix([[0.01], [0.02]]) is None
    assert native.calculate_portfolio_performance([1.0], [0.01], [[0.1]]) is None
    assert native.calculate_strategy_snapshot([100.0] * 80) is None
    assert native.calculate_backtest_metrics([100.0, 101.0], 1, 1) is None


def test_auto_mode_is_default_and_falls_back_when_extension_is_missing(monkeypatch):
    monkeypatch.delenv("USE_RUST_ENGINE", raising=False)
    _reset_native_cache()
    if native.native_available():
        pytest.skip("native extension is installed in this environment")

    assert native.rust_engine_mode() == "auto"
    assert native.calculate_sma([100.0, 101.0, 102.0], 2) is None
    assert native.price_black_scholes(100.0, 100.0, 1.0, 0.2, 0.05, "call") is None


def test_rust_engine_falls_back_when_extension_is_missing(monkeypatch):
    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    if native.native_available():
        pytest.skip("native extension is installed in this environment")

    assert native.calculate_rsi([100.0, 101.0, 102.0], 14) is None


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_rsi_matches_python(monkeypatch):
    prices = [100.0]
    for i in range(1, 80):
        prices.append(prices[-1] * (1 + ((i % 7) - 3) * 0.001))

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_rsi = TechnicalIndicators().calculate_rsi(prices, 14).values

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_rsi = TechnicalIndicators().calculate_rsi(prices, 14).values

    assert rust_rsi == pytest.approx(python_rsi, rel=1e-12, abs=1e-12)


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_moving_averages_match_python(monkeypatch):
    prices = [100.0]
    for i in range(1, 80):
        prices.append(prices[-1] * (1 + ((i % 9) - 4) * 0.0012))

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    indicators = TechnicalIndicators()
    python_sma = indicators.calculate_sma(prices, 20).values
    python_ema = indicators.calculate_ema(prices, 20).values

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_indicators = TechnicalIndicators()
    rust_sma = rust_indicators.calculate_sma(prices, 20).values
    rust_ema = rust_indicators.calculate_ema(prices, 20).values

    assert rust_sma == pytest.approx(python_sma, rel=1e-12, abs=1e-12)
    assert rust_ema == pytest.approx(python_ema, rel=1e-12, abs=1e-12)


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_macd_matches_python(monkeypatch):
    prices = [100.0]
    for i in range(1, 90):
        prices.append(prices[-1] * (1 + ((i % 11) - 5) * 0.0015))

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_macd = TechnicalIndicators().calculate_macd(prices)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_macd = TechnicalIndicators().calculate_macd(prices)

    assert rust_macd.macd_line == pytest.approx(python_macd.macd_line, rel=1e-12, abs=1e-12)
    assert rust_macd.signal_line == pytest.approx(python_macd.signal_line, rel=1e-12, abs=1e-12)
    assert rust_macd.histogram == pytest.approx(python_macd.histogram, rel=1e-12, abs=1e-12)


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_volatility_indicators_match_python(monkeypatch):
    closes = [100.0]
    for i in range(1, 90):
        closes.append(closes[-1] * (1 + ((i % 13) - 6) * 0.001))
    highs = [price * 1.012 for price in closes]
    lows = [price * 0.991 for price in closes]
    volumes = [1_000_000.0 + (i % 7) * 10_000.0 for i in range(len(closes))]

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    indicators = TechnicalIndicators()
    python_bollinger = indicators.calculate_bollinger_bands(closes, 20, 2.0)
    python_kdj = indicators.calculate_kdj(highs, lows, closes, 9)
    python_atr = indicators.calculate_atr(highs, lows, closes, 14)
    python_obv = indicators.calculate_obv(closes, volumes)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_indicators = TechnicalIndicators()
    rust_bollinger = rust_indicators.calculate_bollinger_bands(closes, 20, 2.0)
    rust_kdj = rust_indicators.calculate_kdj(highs, lows, closes, 9)
    rust_atr = rust_indicators.calculate_atr(highs, lows, closes, 14)
    rust_obv = rust_indicators.calculate_obv(closes, volumes)

    assert rust_bollinger.upper == pytest.approx(python_bollinger.upper, rel=1e-12, abs=1e-12)
    assert rust_bollinger.middle == pytest.approx(python_bollinger.middle, rel=1e-12, abs=1e-12)
    assert rust_bollinger.lower == pytest.approx(python_bollinger.lower, rel=1e-12, abs=1e-12)
    assert rust_kdj.k == pytest.approx(python_kdj.k, rel=1e-12, abs=1e-12)
    assert rust_kdj.d == pytest.approx(python_kdj.d, rel=1e-12, abs=1e-12)
    assert rust_kdj.j == pytest.approx(python_kdj.j, rel=1e-12, abs=1e-12)
    assert rust_atr.values == pytest.approx(python_atr.values, rel=1e-12, abs=1e-12)
    assert rust_obv.values == pytest.approx(python_obv.values, rel=1e-12, abs=1e-12)


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_historical_var_matches_python(monkeypatch):
    returns = np.array([0.01, -0.02, 0.005, -0.03, 0.02, -0.01])
    calculator = RiskCalculator()

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_var = calculator.calculate_var_historical(returns, 0.95, 2)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_var = calculator.calculate_var_historical(returns, 0.95, 2)

    assert rust_var == pytest.approx(python_var, rel=1e-12, abs=1e-12)


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_risk_ratios_match_python(monkeypatch):
    prices = [100.0]
    for i in range(1, 100):
        prices.append(prices[-1] * (1 + ((i % 15) - 7) * 0.0013))
    calculator = RiskCalculator()
    returns = calculator.calculate_returns(prices)

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_sharpe = calculator.calculate_sharpe_ratio(returns)
    python_sortino = calculator.calculate_sortino_ratio(returns)
    python_max_drawdown = calculator.calculate_max_drawdown(prices)
    python_volatility = calculator.calculate_volatility(returns)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_calculator = RiskCalculator()
    rust_sharpe = rust_calculator.calculate_sharpe_ratio(returns)
    rust_sortino = rust_calculator.calculate_sortino_ratio(returns)
    rust_max_drawdown = rust_calculator.calculate_max_drawdown(prices)
    rust_volatility = rust_calculator.calculate_volatility(returns)

    assert rust_sharpe == pytest.approx(python_sharpe, rel=1e-12, abs=1e-12)
    assert rust_sortino == pytest.approx(python_sortino, rel=1e-12, abs=1e-12)
    assert rust_max_drawdown == pytest.approx(python_max_drawdown, rel=1e-12, abs=1e-12)
    assert rust_volatility == pytest.approx(python_volatility, rel=1e-12, abs=1e-12)


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_derivatives_match_python(monkeypatch):
    pricer = DerivativesPricer(risk_free_rate=0.05)

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_call = pricer.price_european_call(100.0, 100.0, 1.0, 0.2)
    python_parity = pricer.put_call_parity(python_call.option_price, 100.0, 100.0, 1.0)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_call = pricer.price_european_call(100.0, 100.0, 1.0, 0.2)
    rust_parity = pricer.put_call_parity(rust_call.option_price, 100.0, 100.0, 1.0)

    assert rust_call.option_price == pytest.approx(python_call.option_price, rel=1e-12, abs=1e-12)
    assert rust_call.delta == pytest.approx(python_call.delta, rel=1e-12, abs=1e-12)
    assert rust_call.gamma == pytest.approx(python_call.gamma, rel=1e-12, abs=1e-12)
    assert rust_call.theta == pytest.approx(python_call.theta, rel=1e-12, abs=1e-12)
    assert rust_call.vega == pytest.approx(python_call.vega, rel=1e-12, abs=1e-12)
    assert rust_call.rho == pytest.approx(python_call.rho, rel=1e-12, abs=1e-12)
    assert rust_parity == pytest.approx(python_parity, rel=1e-12, abs=1e-12)


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_portfolio_helpers_match_python(monkeypatch):
    import pandas as pd

    prices = pd.DataFrame(
        {
            "Asset1": [100.0, 101.0, 103.0, 102.0],
            "Asset2": [50.0, 51.0, 50.5, 52.0],
        }
    )
    optimizer = PortfolioOptimizer()
    weights = np.array([0.6, 0.4])

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_returns = optimizer.calculate_returns(prices)
    python_expected = optimizer.calculate_expected_returns(python_returns)
    python_cov = optimizer.calculate_covariance_matrix(python_returns)
    python_perf = optimizer.portfolio_performance(weights, python_expected, python_cov)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_returns = optimizer.calculate_returns(prices)
    rust_expected = optimizer.calculate_expected_returns(rust_returns)
    rust_cov = optimizer.calculate_covariance_matrix(rust_returns)
    rust_perf = optimizer.portfolio_performance(weights, rust_expected, rust_cov)

    assert rust_returns.values == pytest.approx(python_returns.values, rel=1e-12, abs=1e-12)
    assert rust_expected == pytest.approx(python_expected, rel=1e-12, abs=1e-12)
    assert rust_cov == pytest.approx(python_cov, rel=1e-12, abs=1e-12)
    assert rust_perf == pytest.approx(python_perf, rel=1e-12, abs=1e-12)


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_strategy_snapshot_matches_python(monkeypatch):
    prices = [100.0]
    for i in range(1, 90):
        prices.append(prices[-1] * (1 + ((i % 9) - 4) * 0.001))
    strategies = QuantitativeStrategies()

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_result = strategies.run_all_strategies(prices)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_result = strategies.run_all_strategies(prices)

    assert rust_result.keys() == python_result.keys()
    for name in python_result:
        assert rust_result[name].signal == python_result[name].signal
        assert rust_result[name].strength == pytest.approx(
            python_result[name].strength, rel=1e-12, abs=1e-12
        )
        assert rust_result[name].reason == python_result[name].reason


@pytest.mark.skipif(
    importlib.util.find_spec("kronos_fincept_native") is None,
    reason="native Rust extension is not built",
)
def test_native_backtest_metrics_match_python(monkeypatch):
    equity_curve = [
        {"equity": 100000.0},
        {"equity": 101000.0},
        {"equity": 99000.0},
        {"equity": 103000.0},
    ]

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_metrics = _calculate_metrics(equity_curve, 3, 2)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_metrics = _calculate_metrics(equity_curve, 3, 2)

    assert rust_metrics == python_metrics
