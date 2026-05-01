use pyo3::prelude::*;
use pyo3::types::PyDict;

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
fn calculate_var_historical(
    returns: Vec<f64>,
    confidence_level: f64,
    holding_period: usize,
) -> f64 {
    kronos_kernel::calculate_var_historical(&returns, confidence_level, holding_period)
}

#[pymodule]
fn kronos_fincept_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(calculate_rsi, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_macd, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_var_historical, module)?)?;
    Ok(())
}
