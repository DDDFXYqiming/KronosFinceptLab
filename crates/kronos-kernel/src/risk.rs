use crate::math::{mean, population_std};

pub fn calculate_var_historical(
    returns: &[f64],
    confidence_level: f64,
    holding_period: usize,
) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }

    let mut sorted = returns.to_vec();
    sorted.sort_by(|a, b| a.total_cmp(b));

    let mut index = ((1.0 - confidence_level) * sorted.len() as f64) as usize;
    if index >= sorted.len() {
        index = sorted.len() - 1;
    }

    -sorted[index] * (holding_period as f64).sqrt()
}

pub fn calculate_sharpe_ratio(
    returns: &[f64],
    risk_free_rate: f64,
    trading_days_per_year: usize,
) -> f64 {
    if returns.is_empty() || trading_days_per_year == 0 {
        return 0.0;
    }

    let rf_daily = (1.0 + risk_free_rate).powf(1.0 / trading_days_per_year as f64) - 1.0;
    let excess_returns: Vec<f64> = returns.iter().map(|value| value - rf_daily).collect();
    let std = population_std(&excess_returns);
    if std == 0.0 {
        return 0.0;
    }

    mean(&excess_returns) / std * (trading_days_per_year as f64).sqrt()
}

pub fn calculate_sortino_ratio(
    returns: &[f64],
    risk_free_rate: f64,
    target_return: f64,
    trading_days_per_year: usize,
) -> f64 {
    if returns.is_empty() || trading_days_per_year == 0 {
        return 0.0;
    }

    let rf_daily = (1.0 + risk_free_rate).powf(1.0 / trading_days_per_year as f64) - 1.0;
    let excess_returns: Vec<f64> = returns.iter().map(|value| value - rf_daily).collect();
    let downside_returns: Vec<f64> = returns
        .iter()
        .copied()
        .filter(|value| *value < target_return)
        .collect();

    if downside_returns.is_empty() {
        return if mean(&excess_returns) > 0.0 {
            f64::INFINITY
        } else {
            0.0
        };
    }

    let downside_deviation = (downside_returns
        .iter()
        .map(|value| value * value)
        .sum::<f64>()
        / downside_returns.len() as f64)
        .sqrt();

    if downside_deviation == 0.0 {
        return 0.0;
    }

    mean(&excess_returns) / downside_deviation * (trading_days_per_year as f64).sqrt()
}

pub fn calculate_max_drawdown(prices: &[f64]) -> f64 {
    if prices.len() < 2 {
        return 0.0;
    }

    let mut peak = prices[0];
    let mut max_drawdown = 0.0;

    for price in prices {
        if *price > peak {
            peak = *price;
        }
        if peak != 0.0 {
            let drawdown = (peak - price) / peak;
            if drawdown > max_drawdown {
                max_drawdown = drawdown;
            }
        }
    }

    max_drawdown
}

pub fn calculate_volatility(returns: &[f64], annualize: bool, trading_days_per_year: usize) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }

    let volatility = population_std(returns);
    if annualize {
        volatility * (trading_days_per_year as f64).sqrt()
    } else {
        volatility
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn historical_var_uses_sorted_left_tail() {
        let returns = vec![0.01, -0.03, 0.02, -0.01, -0.02];
        let var = calculate_var_historical(&returns, 0.8, 1);
        assert_eq!(var, 0.03);
    }

    #[test]
    fn max_drawdown_tracks_peak_to_trough_loss() {
        let max_drawdown = calculate_max_drawdown(&[100.0, 120.0, 90.0, 130.0]);
        assert_eq!(max_drawdown, 0.25);
    }
}
