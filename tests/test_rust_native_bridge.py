"""Tests for the optional Rust acceleration bridge."""

from __future__ import annotations

import importlib

import numpy as np
import pytest

from kronos_fincept import native
from kronos_fincept.financial.indicators import TechnicalIndicators
from kronos_fincept.financial.risk import RiskCalculator


def _reset_native_cache() -> None:
    native._load_native.cache_clear()


def test_rust_engine_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("USE_RUST_ENGINE", raising=False)
    _reset_native_cache()

    assert native.calculate_rsi([100.0, 101.0, 102.0], 14) is None
    assert native.calculate_macd([100.0] * 40, 12, 26, 9) is None
    assert native.calculate_var_historical([0.01, -0.02], 0.95, 1) is None


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
def test_native_historical_var_matches_python(monkeypatch):
    returns = np.array([0.01, -0.02, 0.005, -0.03, 0.02, -0.01])
    calculator = RiskCalculator()

    monkeypatch.setenv("USE_RUST_ENGINE", "0")
    python_var = calculator.calculate_var_historical(returns, 0.95, 2)

    monkeypatch.setenv("USE_RUST_ENGINE", "1")
    _reset_native_cache()
    rust_var = calculator.calculate_var_historical(returns, 0.95, 2)

    assert rust_var == pytest.approx(python_var, rel=1e-12, abs=1e-12)
