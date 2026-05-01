pub fn calculate_ema(prices: &[f64], period: usize) -> Vec<f64> {
    if period == 0 || prices.len() < period {
        return Vec::new();
    }

    let multiplier = 2.0 / (period as f64 + 1.0);
    let first = prices[..period].iter().sum::<f64>() / period as f64;
    let mut values = Vec::with_capacity(prices.len() - period + 1);
    values.push(first);

    for price in prices.iter().skip(period) {
        let previous = *values.last().unwrap_or(&first);
        values.push((price - previous) * multiplier + previous);
    }

    values
}

pub fn calculate_rsi(prices: &[f64], period: usize) -> Vec<f64> {
    if period == 0 || prices.len() < period + 1 {
        return Vec::new();
    }

    let mut gains = Vec::with_capacity(prices.len() - 1);
    let mut losses = Vec::with_capacity(prices.len() - 1);

    for pair in prices.windows(2) {
        let delta = pair[1] - pair[0];
        gains.push(if delta > 0.0 { delta } else { 0.0 });
        losses.push(if delta < 0.0 { -delta } else { 0.0 });
    }

    let mut avg_gain = gains[..period].iter().sum::<f64>() / period as f64;
    let mut avg_loss = losses[..period].iter().sum::<f64>() / period as f64;
    let mut values = Vec::with_capacity(gains.len().saturating_sub(period));

    for i in period..gains.len() {
        let rsi = if avg_loss == 0.0 {
            100.0
        } else {
            let rs = avg_gain / avg_loss;
            100.0 - (100.0 / (1.0 + rs))
        };
        values.push(rsi);

        avg_gain = (avg_gain * (period as f64 - 1.0) + gains[i]) / period as f64;
        avg_loss = (avg_loss * (period as f64 - 1.0) + losses[i]) / period as f64;
    }

    values
}

pub struct MacdResult {
    pub macd_line: Vec<f64>,
    pub signal_line: Vec<f64>,
    pub histogram: Vec<f64>,
}

pub fn calculate_macd(
    prices: &[f64],
    fast_period: usize,
    slow_period: usize,
    signal_period: usize,
) -> MacdResult {
    if fast_period == 0
        || slow_period == 0
        || signal_period == 0
        || fast_period > slow_period
        || prices.len() < slow_period + signal_period
    {
        return MacdResult {
            macd_line: Vec::new(),
            signal_line: Vec::new(),
            histogram: Vec::new(),
        };
    }

    let fast_ema = calculate_ema(prices, fast_period);
    let slow_ema = calculate_ema(prices, slow_period);
    let offset = slow_period - fast_period;
    let fast_values = &fast_ema[offset..];

    let macd_line: Vec<f64> = fast_values
        .iter()
        .zip(slow_ema.iter())
        .map(|(fast, slow)| fast - slow)
        .collect();
    let signal_line = calculate_ema(&macd_line, signal_period);
    let min_len = macd_line.len().min(signal_line.len());
    let histogram = (signal_period - 1..min_len)
        .map(|i| macd_line[i] - signal_line[i])
        .collect();

    MacdResult {
        macd_line: macd_line[signal_period - 1..].to_vec(),
        signal_line,
        histogram,
    }
}

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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rsi_matches_python_contract_shape() {
        let prices = vec![
            100.0, 101.0, 102.0, 101.0, 103.0, 104.0, 103.5, 105.0, 106.0, 104.0, 103.0, 104.5,
            105.5, 106.0, 107.0, 108.0,
        ];
        let rsi = calculate_rsi(&prices, 14);
        assert_eq!(rsi.len(), 1);
        assert!((0.0..=100.0).contains(&rsi[0]));
    }

    #[test]
    fn macd_empty_when_history_is_too_short() {
        let prices = vec![100.0; 20];
        let macd = calculate_macd(&prices, 12, 26, 9);
        assert!(macd.macd_line.is_empty());
        assert!(macd.signal_line.is_empty());
        assert!(macd.histogram.is_empty());
    }

    #[test]
    fn historical_var_uses_sorted_left_tail() {
        let returns = vec![0.01, -0.03, 0.02, -0.01, -0.02];
        let var = calculate_var_historical(&returns, 0.8, 1);
        assert_eq!(var, 0.03);
    }
}
