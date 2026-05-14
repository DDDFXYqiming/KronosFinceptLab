pub(crate) fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

pub(crate) fn population_std(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }

    let avg = mean(values);
    let variance = values
        .iter()
        .map(|value| {
            let diff = value - avg;
            diff * diff
        })
        .sum::<f64>()
        / values.len() as f64;
    variance.sqrt()
}

pub(crate) fn round_to(value: f64, digits: i32) -> f64 {
    if !value.is_finite() {
        return value;
    }
    let factor = 10_f64.powi(digits);
    (value * factor).round() / factor
}
