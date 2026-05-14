pub struct MacdResult {
    pub macd_line: Vec<f64>,
    pub signal_line: Vec<f64>,
    pub histogram: Vec<f64>,
}

pub struct BollingerBandsResult {
    pub upper: Vec<f64>,
    pub middle: Vec<f64>,
    pub lower: Vec<f64>,
}

pub struct KdjResult {
    pub k: Vec<f64>,
    pub d: Vec<f64>,
    pub j: Vec<f64>,
}

pub fn calculate_sma(prices: &[f64], period: usize) -> Vec<f64> {
    if period == 0 || prices.len() < period {
        return Vec::new();
    }

    let mut values = Vec::with_capacity(prices.len() - period + 1);
    let mut sum = prices[..period].iter().sum::<f64>();
    values.push(sum / period as f64);

    for i in period..prices.len() {
        sum += prices[i] - prices[i - period];
        values.push(sum / period as f64);
    }

    values
}

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

pub fn calculate_bollinger_bands(
    prices: &[f64],
    period: usize,
    std_dev: f64,
) -> BollingerBandsResult {
    if period == 0 || prices.len() < period {
        return BollingerBandsResult {
            upper: Vec::new(),
            middle: Vec::new(),
            lower: Vec::new(),
        };
    }

    let mut upper = Vec::with_capacity(prices.len() - period + 1);
    let mut middle = Vec::with_capacity(prices.len() - period + 1);
    let mut lower = Vec::with_capacity(prices.len() - period + 1);

    for window in prices.windows(period) {
        let sma = window.iter().sum::<f64>() / period as f64;
        let variance = window
            .iter()
            .map(|price| {
                let diff = price - sma;
                diff * diff
            })
            .sum::<f64>()
            / period as f64;
        let band_width = std_dev * variance.sqrt();

        middle.push(sma);
        upper.push(sma + band_width);
        lower.push(sma - band_width);
    }

    BollingerBandsResult {
        upper,
        middle,
        lower,
    }
}

pub fn calculate_kdj(highs: &[f64], lows: &[f64], closes: &[f64], period: usize) -> KdjResult {
    if period == 0
        || closes.len() < period
        || highs.len() != closes.len()
        || lows.len() != closes.len()
    {
        return KdjResult {
            k: Vec::new(),
            d: Vec::new(),
            j: Vec::new(),
        };
    }

    let mut k_values = Vec::with_capacity(closes.len() - period + 1);
    let mut d_values = Vec::with_capacity(closes.len() - period + 1);
    let mut j_values = Vec::with_capacity(closes.len() - period + 1);
    let mut previous_k = 50.0;
    let mut previous_d = 50.0;

    for i in period - 1..closes.len() {
        let start = i + 1 - period;
        let period_high = highs[start..=i]
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        let period_low = lows[start..=i]
            .iter()
            .copied()
            .fold(f64::INFINITY, f64::min);
        let rsv = if period_high == period_low {
            50.0
        } else {
            (closes[i] - period_low) / (period_high - period_low) * 100.0
        };

        let k = (2.0 / 3.0) * previous_k + (1.0 / 3.0) * rsv;
        let d = (2.0 / 3.0) * previous_d + (1.0 / 3.0) * k;
        let j = 3.0 * k - 2.0 * d;

        k_values.push(k);
        d_values.push(d);
        j_values.push(j);

        previous_k = k;
        previous_d = d;
    }

    KdjResult {
        k: k_values,
        d: d_values,
        j: j_values,
    }
}

pub fn calculate_atr(highs: &[f64], lows: &[f64], closes: &[f64], period: usize) -> Vec<f64> {
    if period == 0
        || closes.len() < period + 1
        || highs.len() != closes.len()
        || lows.len() != closes.len()
    {
        return Vec::new();
    }

    let mut true_ranges = Vec::with_capacity(closes.len() - 1);
    for i in 1..closes.len() {
        let high_low = highs[i] - lows[i];
        let high_close = (highs[i] - closes[i - 1]).abs();
        let low_close = (lows[i] - closes[i - 1]).abs();
        true_ranges.push(high_low.max(high_close).max(low_close));
    }

    let mut values = Vec::with_capacity(true_ranges.len() - period + 1);
    values.push(true_ranges[..period].iter().sum::<f64>() / period as f64);

    for tr in true_ranges.iter().skip(period) {
        let previous = *values.last().unwrap();
        values.push((previous * (period as f64 - 1.0) + tr) / period as f64);
    }

    values
}

pub fn calculate_obv(closes: &[f64], volumes: &[f64]) -> Vec<f64> {
    if closes.len() < 2 || volumes.len() < 2 || closes.len() != volumes.len() {
        return Vec::new();
    }

    let mut values = Vec::with_capacity(closes.len());
    values.push(0.0);

    for i in 1..closes.len() {
        let previous = *values.last().unwrap();
        if closes[i] > closes[i - 1] {
            values.push(previous + volumes[i]);
        } else if closes[i] < closes[i - 1] {
            values.push(previous - volumes[i]);
        } else {
            values.push(previous);
        }
    }

    values
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sma_uses_rolling_windows() {
        let sma = calculate_sma(&[1.0, 2.0, 3.0, 4.0], 3);
        assert_eq!(sma, vec![2.0, 3.0]);
    }

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
}
