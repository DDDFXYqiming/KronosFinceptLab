pub mod backtest;
pub mod derivatives;
pub mod indicators;
mod math;
pub mod portfolio;
pub mod risk;
pub mod strategies;

pub use backtest::{calculate_backtest_metrics, BacktestMetrics};
pub use derivatives::{
    calculate_put_call_parity, price_black_scholes, OptionPricingResult, OptionType,
};
pub use indicators::{
    calculate_atr, calculate_bollinger_bands, calculate_ema, calculate_kdj, calculate_macd,
    calculate_obv, calculate_rsi, calculate_sma, BollingerBandsResult, KdjResult, MacdResult,
};
pub use portfolio::{
    calculate_covariance_matrix, calculate_expected_returns, calculate_portfolio_performance,
    calculate_portfolio_returns, PortfolioPerformance,
};
pub use risk::{
    calculate_max_drawdown, calculate_sharpe_ratio, calculate_sortino_ratio,
    calculate_var_historical, calculate_volatility,
};
pub use strategies::{
    calculate_strategy_snapshot, StrategyConfig, StrategySignal, StrategySnapshot,
};
