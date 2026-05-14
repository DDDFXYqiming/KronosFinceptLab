use crate::indicators::{calculate_bollinger_bands, calculate_macd, calculate_rsi, calculate_sma};

pub struct StrategySignal {
    pub signal: String,
    pub strength: f64,
    pub reason: String,
}

pub struct StrategySnapshot {
    pub ma_crossover: StrategySignal,
    pub rsi: StrategySignal,
    pub macd: StrategySignal,
    pub bollinger: StrategySignal,
}

#[derive(Clone, Copy)]
pub struct StrategyConfig {
    pub fast_period: usize,
    pub slow_period: usize,
    pub rsi_period: usize,
    pub overbought: f64,
    pub oversold: f64,
    pub macd_fast_period: usize,
    pub macd_slow_period: usize,
    pub macd_signal_period: usize,
    pub bollinger_period: usize,
    pub bollinger_std_dev: f64,
}

impl Default for StrategyConfig {
    fn default() -> Self {
        Self {
            fast_period: 20,
            slow_period: 50,
            rsi_period: 14,
            overbought: 70.0,
            oversold: 30.0,
            macd_fast_period: 12,
            macd_slow_period: 26,
            macd_signal_period: 9,
            bollinger_period: 20,
            bollinger_std_dev: 2.0,
        }
    }
}

pub fn calculate_strategy_snapshot(closes: &[f64], config: StrategyConfig) -> StrategySnapshot {
    StrategySnapshot {
        ma_crossover: ma_crossover_signal(closes, config.fast_period, config.slow_period),
        rsi: rsi_signal(
            closes,
            config.rsi_period,
            config.overbought,
            config.oversold,
        ),
        macd: macd_signal(
            closes,
            config.macd_fast_period,
            config.macd_slow_period,
            config.macd_signal_period,
        ),
        bollinger: bollinger_signal(closes, config.bollinger_period, config.bollinger_std_dev),
    }
}

fn ma_crossover_signal(closes: &[f64], fast_period: usize, slow_period: usize) -> StrategySignal {
    if closes.len() < slow_period + 2 {
        return hold("Insufficient data", 0.0);
    }

    let fast_ma = calculate_sma(closes, fast_period);
    let slow_ma = calculate_sma(closes, slow_period);
    if fast_ma.is_empty() || slow_ma.is_empty() {
        return hold("MA calculation failed", 0.0);
    }

    let offset = slow_period.saturating_sub(fast_period);
    if offset > fast_ma.len() {
        return hold("Insufficient MA data", 0.0);
    }
    let fast_values = &fast_ma[offset..];
    if fast_values.len() < 2 || slow_ma.len() < 2 {
        return hold("Insufficient MA data", 0.0);
    }

    let fast_prev = fast_values[fast_values.len() - 2];
    let fast_curr = fast_values[fast_values.len() - 1];
    let slow_prev = slow_ma[slow_ma.len() - 2];
    let slow_curr = slow_ma[slow_ma.len() - 1];
    let strength = if slow_curr != 0.0 {
        ((fast_curr - slow_curr).abs() / slow_curr * 10.0).min(1.0)
    } else {
        0.0
    };

    if fast_prev <= slow_prev && fast_curr > slow_curr {
        StrategySignal {
            signal: "buy".to_string(),
            strength,
            reason: format!("Fast MA ({fast_period}) crossed above Slow MA ({slow_period})"),
        }
    } else if fast_prev >= slow_prev && fast_curr < slow_curr {
        StrategySignal {
            signal: "sell".to_string(),
            strength,
            reason: format!("Fast MA ({fast_period}) crossed below Slow MA ({slow_period})"),
        }
    } else {
        hold("No crossover detected", 0.0)
    }
}

fn rsi_signal(closes: &[f64], period: usize, overbought: f64, oversold: f64) -> StrategySignal {
    if closes.len() < period + 2 {
        return hold("Insufficient data", 0.0);
    }

    let rsi = calculate_rsi(closes, period);
    if rsi.len() < 2 {
        return hold("RSI calculation failed", 0.0);
    }

    let rsi_prev = rsi[rsi.len() - 2];
    let rsi_curr = rsi[rsi.len() - 1];
    let mut strength = if rsi_curr < oversold {
        (oversold - rsi_curr) / oversold
    } else if rsi_curr > overbought {
        (rsi_curr - overbought) / (100.0 - overbought)
    } else {
        0.0
    };
    strength = strength.min(1.0);

    if rsi_prev <= oversold && rsi_curr > oversold {
        StrategySignal {
            signal: "buy".to_string(),
            strength,
            reason: format!("RSI crossed above oversold level ({oversold})"),
        }
    } else if rsi_prev >= overbought && rsi_curr < overbought {
        StrategySignal {
            signal: "sell".to_string(),
            strength,
            reason: format!("RSI crossed below overbought level ({overbought})"),
        }
    } else if rsi_curr < oversold {
        StrategySignal {
            signal: "buy".to_string(),
            strength,
            reason: format!("RSI in oversold territory ({rsi_curr:.1})"),
        }
    } else if rsi_curr > overbought {
        StrategySignal {
            signal: "sell".to_string(),
            strength,
            reason: format!("RSI in overbought territory ({rsi_curr:.1})"),
        }
    } else {
        hold("RSI in neutral zone", 0.0)
    }
}

fn macd_signal(
    closes: &[f64],
    fast_period: usize,
    slow_period: usize,
    signal_period: usize,
) -> StrategySignal {
    if closes.len() < slow_period + signal_period + 2 {
        return hold("Insufficient data", 0.0);
    }

    let macd = calculate_macd(closes, fast_period, slow_period, signal_period);
    if macd.macd_line.len() < 2 || macd.signal_line.len() < 2 {
        return hold("MACD calculation failed", 0.0);
    }

    let macd_prev = macd.macd_line[macd.macd_line.len() - 2];
    let macd_curr = macd.macd_line[macd.macd_line.len() - 1];
    let signal_prev = macd.signal_line[macd.signal_line.len() - 2];
    let signal_curr = macd.signal_line[macd.signal_line.len() - 1];
    let strength = if signal_curr != 0.0 {
        ((macd_curr - signal_curr).abs() / signal_curr.abs()).min(1.0)
    } else {
        0.0
    };

    if macd_prev <= signal_prev && macd_curr > signal_curr {
        StrategySignal {
            signal: "buy".to_string(),
            strength,
            reason: "MACD crossed above signal line".to_string(),
        }
    } else if macd_prev >= signal_prev && macd_curr < signal_curr {
        StrategySignal {
            signal: "sell".to_string(),
            strength,
            reason: "MACD crossed below signal line".to_string(),
        }
    } else {
        hold("No MACD crossover detected", 0.0)
    }
}

fn bollinger_signal(closes: &[f64], period: usize, std_dev: f64) -> StrategySignal {
    if closes.len() < period + 1 {
        return hold("Insufficient data", 0.0);
    }

    let bollinger = calculate_bollinger_bands(closes, period, std_dev);
    if bollinger.upper.is_empty() || bollinger.lower.is_empty() {
        return hold("Bollinger calculation failed", 0.0);
    }

    let current_price = closes[closes.len() - 1];
    let upper = bollinger.upper[bollinger.upper.len() - 1];
    let lower = bollinger.lower[bollinger.lower.len() - 1];
    let middle = bollinger.middle[bollinger.middle.len() - 1];

    if current_price > upper {
        let strength = if upper - middle != 0.0 {
            ((current_price - upper) / (upper - middle)).min(1.0)
        } else {
            0.0
        };
        StrategySignal {
            signal: "buy".to_string(),
            strength,
            reason: format!("Price ({current_price:.2}) broke above upper band ({upper:.2})"),
        }
    } else if current_price < lower {
        let strength = if middle - lower != 0.0 {
            ((lower - current_price) / (middle - lower)).min(1.0)
        } else {
            0.0
        };
        StrategySignal {
            signal: "sell".to_string(),
            strength,
            reason: format!("Price ({current_price:.2}) broke below lower band ({lower:.2})"),
        }
    } else {
        hold("Price within Bollinger Bands", 0.0)
    }
}

fn hold(reason: &str, strength: f64) -> StrategySignal {
    StrategySignal {
        signal: "hold".to_string(),
        strength,
        reason: reason.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snapshot_returns_all_default_strategies() {
        let closes: Vec<f64> = (0..80).map(|i| 100.0 + i as f64 * 0.1).collect();
        let snapshot = calculate_strategy_snapshot(&closes, StrategyConfig::default());
        assert!(!snapshot.ma_crossover.signal.is_empty());
        assert!(!snapshot.rsi.signal.is_empty());
        assert!(!snapshot.macd.signal.is_empty());
        assert!(!snapshot.bollinger.signal.is_empty());
    }
}
