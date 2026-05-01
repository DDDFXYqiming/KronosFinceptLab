use pyo3::prelude::*;
use pyo3::types::PyDict;

#[pyfunction]
fn calculate_sma(prices: Vec<f64>, period: usize) -> Vec<f64> {
    kronos_kernel::calculate_sma(&prices, period)
}

#[pyfunction]
fn calculate_ema(prices: Vec<f64>, period: usize) -> Vec<f64> {
    kronos_kernel::calculate_ema(&prices, period)
}

#[pyfunction]
fn calculate_rsi(prices: Vec<f64>, period: usize) -> Vec<f64> {
    kronos_kernel::calculate_rsi(&prices, period)
}

#[pyfunction]
fn calculate_macd(
    py: Python<'_>,
    prices: Vec<f64>,
    fast_period: usize,
    slow_period: usize,
    signal_period: usize,
) -> PyResult<Py<PyDict>> {
    let result = kronos_kernel::calculate_macd(&prices, fast_period, slow_period, signal_period);
    let dict = PyDict::new(py);
    dict.set_item("macd_line", result.macd_line)?;
    dict.set_item("signal_line", result.signal_line)?;
    dict.set_item("histogram", result.histogram)?;
    Ok(dict.into())
}

#[pyfunction]
fn calculate_bollinger_bands(
    py: Python<'_>,
    prices: Vec<f64>,
    period: usize,
    std_dev: f64,
) -> PyResult<Py<PyDict>> {
    let result = kronos_kernel::calculate_bollinger_bands(&prices, period, std_dev);
    let dict = PyDict::new(py);
    dict.set_item("upper", result.upper)?;
    dict.set_item("middle", result.middle)?;
    dict.set_item("lower", result.lower)?;
    Ok(dict.into())
}

#[pyfunction]
fn calculate_kdj(
    py: Python<'_>,
    highs: Vec<f64>,
    lows: Vec<f64>,
    closes: Vec<f64>,
    period: usize,
) -> PyResult<Py<PyDict>> {
    let result = kronos_kernel::calculate_kdj(&highs, &lows, &closes, period);
    let dict = PyDict::new(py);
    dict.set_item("k", result.k)?;
    dict.set_item("d", result.d)?;
    dict.set_item("j", result.j)?;
    Ok(dict.into())
}

#[pyfunction]
fn calculate_atr(highs: Vec<f64>, lows: Vec<f64>, closes: Vec<f64>, period: usize) -> Vec<f64> {
    kronos_kernel::calculate_atr(&highs, &lows, &closes, period)
}

#[pyfunction]
fn calculate_obv(closes: Vec<f64>, volumes: Vec<f64>) -> Vec<f64> {
    kronos_kernel::calculate_obv(&closes, &volumes)
}

#[pyfunction]
fn calculate_var_historical(
    returns: Vec<f64>,
    confidence_level: f64,
    holding_period: usize,
) -> f64 {
    kronos_kernel::calculate_var_historical(&returns, confidence_level, holding_period)
}

#[pyfunction]
fn calculate_sharpe_ratio(
    returns: Vec<f64>,
    risk_free_rate: f64,
    trading_days_per_year: usize,
) -> f64 {
    kronos_kernel::calculate_sharpe_ratio(&returns, risk_free_rate, trading_days_per_year)
}

#[pyfunction]
fn calculate_sortino_ratio(
    returns: Vec<f64>,
    risk_free_rate: f64,
    target_return: f64,
    trading_days_per_year: usize,
) -> f64 {
    kronos_kernel::calculate_sortino_ratio(
        &returns,
        risk_free_rate,
        target_return,
        trading_days_per_year,
    )
}

#[pyfunction]
fn calculate_max_drawdown(prices: Vec<f64>) -> f64 {
    kronos_kernel::calculate_max_drawdown(&prices)
}

#[pyfunction]
fn calculate_volatility(returns: Vec<f64>, annualize: bool, trading_days_per_year: usize) -> f64 {
    kronos_kernel::calculate_volatility(&returns, annualize, trading_days_per_year)
}

#[pymodule]
fn kronos_fincept_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(calculate_sma, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_ema, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_rsi, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_macd, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_bollinger_bands, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_kdj, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_atr, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_obv, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_var_historical, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_sharpe_ratio, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_sortino_ratio, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_max_drawdown, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_volatility, module)?)?;
    Ok(())
}
