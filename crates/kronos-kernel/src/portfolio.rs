use crate::math::mean;

pub struct PortfolioPerformance {
    pub expected_return: f64,
    pub volatility: f64,
}

pub fn calculate_portfolio_returns(prices: &[Vec<f64>]) -> Vec<Vec<f64>> {
    if prices.len() < 2 {
        return Vec::new();
    }
    let width = prices[0].len();
    if width == 0 || prices.iter().any(|row| row.len() != width) {
        return Vec::new();
    }

    prices
        .windows(2)
        .map(|pair| {
            pair[0]
                .iter()
                .zip(pair[1].iter())
                .map(|(previous, current)| {
                    if *previous == 0.0 && *current == 0.0 {
                        f64::NAN
                    } else {
                        current / previous - 1.0
                    }
                })
                .collect()
        })
        .collect()
}

pub fn calculate_expected_returns(returns: &[Vec<f64>]) -> Vec<f64> {
    let Some(width) = matrix_width(returns) else {
        return Vec::new();
    };

    (0..width)
        .map(|column| {
            let values: Vec<f64> = returns.iter().map(|row| row[column]).collect();
            mean(&values)
        })
        .collect()
}

pub fn calculate_covariance_matrix(returns: &[Vec<f64>]) -> Vec<Vec<f64>> {
    let Some(width) = matrix_width(returns) else {
        return Vec::new();
    };
    if returns.len() < 2 {
        return vec![vec![0.0; width]; width];
    }

    let means = calculate_expected_returns(returns);
    let mut matrix = vec![vec![0.0; width]; width];

    for i in 0..width {
        for j in i..width {
            let covariance = returns
                .iter()
                .map(|row| (row[i] - means[i]) * (row[j] - means[j]))
                .sum::<f64>()
                / (returns.len() - 1) as f64;
            matrix[i][j] = covariance;
            matrix[j][i] = covariance;
        }
    }

    matrix
}

pub fn calculate_portfolio_performance(
    weights: &[f64],
    expected_returns: &[f64],
    covariance_matrix: &[Vec<f64>],
) -> PortfolioPerformance {
    if weights.len() != expected_returns.len()
        || covariance_matrix.len() != weights.len()
        || covariance_matrix
            .iter()
            .any(|row| row.len() != weights.len())
    {
        return PortfolioPerformance {
            expected_return: 0.0,
            volatility: 0.0,
        };
    }

    let expected_return = weights
        .iter()
        .zip(expected_returns.iter())
        .map(|(weight, expected)| weight * expected)
        .sum::<f64>();
    let variance = (0..weights.len())
        .map(|i| {
            (0..weights.len())
                .map(|j| weights[i] * covariance_matrix[i][j] * weights[j])
                .sum::<f64>()
        })
        .sum::<f64>();

    PortfolioPerformance {
        expected_return,
        volatility: variance.max(0.0).sqrt(),
    }
}

fn matrix_width(matrix: &[Vec<f64>]) -> Option<usize> {
    let first = matrix.first()?;
    let width = first.len();
    if width == 0 || matrix.iter().any(|row| row.len() != width) {
        return None;
    }
    Some(width)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn returns_are_row_major() {
        let prices = vec![vec![100.0, 200.0], vec![110.0, 190.0], vec![121.0, 209.0]];
        let returns = calculate_portfolio_returns(&prices);
        assert_eq!(returns.len(), 2);
        assert!((returns[0][0] - 0.1).abs() < 1e-12);
        assert!((returns[0][1] + 0.05).abs() < 1e-12);
    }

    #[test]
    fn covariance_matrix_is_symmetric() {
        let returns = vec![vec![0.1, -0.05], vec![0.1, 0.1], vec![-0.05, 0.02]];
        let cov = calculate_covariance_matrix(&returns);
        assert_eq!(cov.len(), 2);
        assert!((cov[0][1] - cov[1][0]).abs() < 1e-12);
    }
}
