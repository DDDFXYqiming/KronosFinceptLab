use pyo3::exceptions::PyValueError;
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

#[pyfunction]
fn price_black_scholes(
    py: Python<'_>,
    underlying_price: f64,
    strike_price: f64,
    time_to_expiration: f64,
    volatility: f64,
    risk_free_rate: f64,
    option_type: String,
) -> PyResult<Py<PyDict>> {
    let result = kronos_kernel::price_black_scholes(
        underlying_price,
        strike_price,
        time_to_expiration,
        volatility,
        risk_free_rate,
        &option_type,
    )
    .map_err(PyValueError::new_err)?;
    let dict = PyDict::new(py);
    dict.set_item("option_type", result.option_type)?;
    dict.set_item("underlying_price", result.underlying_price)?;
    dict.set_item("strike_price", result.strike_price)?;
    dict.set_item("time_to_expiration", result.time_to_expiration)?;
    dict.set_item("risk_free_rate", result.risk_free_rate)?;
    dict.set_item("volatility", result.volatility)?;
    dict.set_item("option_price", result.option_price)?;
    dict.set_item("delta", result.delta)?;
    dict.set_item("gamma", result.gamma)?;
    dict.set_item("theta", result.theta)?;
    dict.set_item("vega", result.vega)?;
    dict.set_item("rho", result.rho)?;
    Ok(dict.into())
}

#[pyfunction]
fn calculate_put_call_parity(
    call_price: f64,
    underlying_price: f64,
    strike_price: f64,
    time_to_expiration: f64,
    risk_free_rate: f64,
) -> f64 {
    kronos_kernel::calculate_put_call_parity(
        call_price,
        underlying_price,
        strike_price,
        time_to_expiration,
        risk_free_rate,
    )
}

#[pyfunction]
fn calculate_portfolio_returns(prices: Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    kronos_kernel::calculate_portfolio_returns(&prices)
}

#[pyfunction]
fn calculate_expected_returns(returns: Vec<Vec<f64>>) -> Vec<f64> {
    kronos_kernel::calculate_expected_returns(&returns)
}

#[pyfunction]
fn calculate_covariance_matrix(returns: Vec<Vec<f64>>) -> Vec<Vec<f64>> {
    kronos_kernel::calculate_covariance_matrix(&returns)
}

#[pyfunction]
fn calculate_portfolio_performance(
    py: Python<'_>,
    weights: Vec<f64>,
    expected_returns: Vec<f64>,
    covariance_matrix: Vec<Vec<f64>>,
) -> PyResult<Py<PyDict>> {
    let result = kronos_kernel::calculate_portfolio_performance(
        &weights,
        &expected_returns,
        &covariance_matrix,
    );
    let dict = PyDict::new(py);
    dict.set_item("expected_return", result.expected_return)?;
    dict.set_item("volatility", result.volatility)?;
    Ok(dict.into())
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn calculate_strategy_snapshot(
    py: Python<'_>,
    closes: Vec<f64>,
    fast_period: usize,
    slow_period: usize,
    rsi_period: usize,
    overbought: f64,
    oversold: f64,
    macd_fast_period: usize,
    macd_slow_period: usize,
    macd_signal_period: usize,
    bollinger_period: usize,
    bollinger_std_dev: f64,
) -> PyResult<Py<PyDict>> {
    let snapshot = kronos_kernel::calculate_strategy_snapshot(
        &closes,
        kronos_kernel::StrategyConfig {
            fast_period,
            slow_period,
            rsi_period,
            overbought,
            oversold,
            macd_fast_period,
            macd_slow_period,
            macd_signal_period,
            bollinger_period,
            bollinger_std_dev,
        },
    );
    let dict = PyDict::new(py);
    dict.set_item("ma_crossover", signal_to_dict(py, &snapshot.ma_crossover)?)?;
    dict.set_item("rsi", signal_to_dict(py, &snapshot.rsi)?)?;
    dict.set_item("macd", signal_to_dict(py, &snapshot.macd)?)?;
    dict.set_item("bollinger", signal_to_dict(py, &snapshot.bollinger)?)?;
    Ok(dict.into())
}

fn signal_to_dict<'py>(
    py: Python<'py>,
    signal: &kronos_kernel::StrategySignal,
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new(py);
    dict.set_item("signal", &signal.signal)?;
    dict.set_item("strength", signal.strength)?;
    dict.set_item("reason", &signal.reason)?;
    Ok(dict)
}

#[pyfunction]
fn calculate_backtest_metrics(
    py: Python<'_>,
    equities: Vec<f64>,
    total_trades: usize,
    winning_trades: usize,
) -> PyResult<Py<PyDict>> {
    let result = kronos_kernel::calculate_backtest_metrics(&equities, total_trades, winning_trades);
    let dict = PyDict::new(py);
    dict.set_item("total_return", result.total_return)?;
    dict.set_item("annualized_return", result.annualized_return)?;
    dict.set_item("sharpe_ratio", result.sharpe_ratio)?;
    dict.set_item("max_drawdown", result.max_drawdown)?;
    dict.set_item("total_trades", result.total_trades)?;
    dict.set_item("win_rate", result.win_rate)?;
    dict.set_item("avg_holding_days", result.avg_holding_days)?;
    Ok(dict.into())
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
    module.add_function(wrap_pyfunction!(price_black_scholes, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_put_call_parity, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_portfolio_returns, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_expected_returns, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_covariance_matrix, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_portfolio_performance, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_strategy_snapshot, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_backtest_metrics, module)?)?;
    Ok(())
}
