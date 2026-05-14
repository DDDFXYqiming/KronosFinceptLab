use crate::math::{population_std, round_to};

pub struct BacktestMetrics {
    pub total_return: f64,
    pub annualized_return: f64,
    pub sharpe_ratio: f64,
    pub max_drawdown: f64,
    pub total_trades: usize,
    pub win_rate: f64,
    pub avg_holding_days: usize,
}

pub fn calculate_backtest_metrics(
    equities: &[f64],
    total_trades: usize,
    winning_trades: usize,
) -> BacktestMetrics {
    if equities.len() < 2 {
        return BacktestMetrics {
            total_return: 0.0,
            annualized_return: 0.0,
            sharpe_ratio: 0.0,
            max_drawdown: 0.0,
            total_trades,
            win_rate: 0.0,
            avg_holding_days: 0,
        };
    }

    let initial = equities[0];
    let final_equity = equities[equities.len() - 1];
    let total_return = if initial > 0.0 {
        final_equity / initial - 1.0
    } else {
        0.0
    };

    let n_days = equities.len();
    let years = n_days as f64 / 252.0;
    let annualized_return = if years > 0.0 && total_return > -1.0 {
        (1.0 + total_return).powf(1.0 / years) - 1.0
    } else {
        -1.0
    };

    let daily_returns: Vec<f64> = equities
        .windows(2)
        .map(|pair| {
            if pair[0] > 0.0 {
                pair[1] / pair[0] - 1.0
            } else {
                0.0
            }
        })
        .collect();
    let sharpe_ratio = if daily_returns.is_empty() {
        0.0
    } else {
        let mean_ret = daily_returns.iter().sum::<f64>() / daily_returns.len() as f64;
        let std_ret = population_std(&daily_returns);
        if std_ret > 0.0 {
            mean_ret / std_ret * (252.0_f64).sqrt()
        } else {
            0.0
        }
    };

    let mut peak = equities[0];
    let mut max_drawdown = 0.0;
    for equity in equities {
        if *equity > peak {
            peak = *equity;
        }
        let drawdown = if peak > 0.0 {
            (peak - equity) / peak
        } else {
            0.0
        };
        if drawdown > max_drawdown {
            max_drawdown = drawdown;
        }
    }

    let win_rate = if total_trades > 0 {
        winning_trades as f64 / total_trades as f64
    } else {
        0.0
    };
    let avg_holding_days = 1_usize.max(n_days / total_trades.max(1));

    BacktestMetrics {
        total_return: round_to(total_return, 6),
        annualized_return: round_to(annualized_return, 6),
        sharpe_ratio: round_to(sharpe_ratio, 4),
        max_drawdown: round_to(max_drawdown, 6),
        total_trades,
        win_rate: round_to(win_rate, 4),
        avg_holding_days,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn metrics_match_python_contract_shape() {
        let metrics = calculate_backtest_metrics(&[100_000.0, 101_000.0, 99_000.0], 2, 1);
        assert_eq!(metrics.total_trades, 2);
        assert_eq!(metrics.win_rate, 0.5);
        assert!(metrics.max_drawdown > 0.0);
        assert!(metrics.avg_holding_days >= 1);
    }
}
