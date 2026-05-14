use statrs::distribution::{Continuous, ContinuousCDF, Normal};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OptionType {
    Call,
    Put,
}

impl OptionType {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "call" => Ok(Self::Call),
            "put" => Ok(Self::Put),
            _ => Err("option_type must be 'call' or 'put'".to_string()),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Call => "call",
            Self::Put => "put",
        }
    }
}

pub struct OptionPricingResult {
    pub option_type: String,
    pub underlying_price: f64,
    pub strike_price: f64,
    pub time_to_expiration: f64,
    pub risk_free_rate: f64,
    pub volatility: f64,
    pub option_price: f64,
    pub delta: f64,
    pub gamma: f64,
    pub theta: f64,
    pub vega: f64,
    pub rho: f64,
}

pub fn price_black_scholes(
    underlying_price: f64,
    strike_price: f64,
    time_to_expiration: f64,
    volatility: f64,
    risk_free_rate: f64,
    option_type: &str,
) -> Result<OptionPricingResult, String> {
    let option_type = OptionType::parse(option_type)?;

    if time_to_expiration <= 0.0 {
        let price = match option_type {
            OptionType::Call => (underlying_price - strike_price).max(0.0),
            OptionType::Put => (strike_price - underlying_price).max(0.0),
        };
        let delta = match option_type {
            OptionType::Call if underlying_price > strike_price => 1.0,
            OptionType::Put if underlying_price < strike_price => -1.0,
            _ => 0.0,
        };
        return Ok(OptionPricingResult {
            option_type: option_type.as_str().to_string(),
            underlying_price,
            strike_price,
            time_to_expiration: 0.0,
            risk_free_rate,
            volatility,
            option_price: price,
            delta,
            gamma: 0.0,
            theta: 0.0,
            vega: 0.0,
            rho: 0.0,
        });
    }

    if volatility <= 0.0 {
        return Err("Volatility must be positive".to_string());
    }
    if underlying_price <= 0.0 || strike_price <= 0.0 {
        return Err("Prices must be positive".to_string());
    }

    let normal = Normal::new(0.0, 1.0).map_err(|err| err.to_string())?;
    let sqrt_t = time_to_expiration.sqrt();
    let d1 = ((underlying_price / strike_price).ln()
        + (risk_free_rate + 0.5 * volatility.powi(2)) * time_to_expiration)
        / (volatility * sqrt_t);
    let d2 = d1 - volatility * sqrt_t;
    let discount = (-risk_free_rate * time_to_expiration).exp();

    let option_price = match option_type {
        OptionType::Call => {
            underlying_price * normal.cdf(d1) - strike_price * discount * normal.cdf(d2)
        }
        OptionType::Put => {
            strike_price * discount * normal.cdf(-d2) - underlying_price * normal.cdf(-d1)
        }
    };

    let delta = match option_type {
        OptionType::Call => normal.cdf(d1),
        OptionType::Put => normal.cdf(d1) - 1.0,
    };
    let gamma = normal.pdf(d1) / (underlying_price * volatility * sqrt_t);
    let common_theta = (underlying_price * normal.pdf(d1) * volatility) / (2.0 * sqrt_t);
    let theta = match option_type {
        OptionType::Call => {
            -common_theta - risk_free_rate * strike_price * discount * normal.cdf(d2)
        }
        OptionType::Put => {
            -common_theta + risk_free_rate * strike_price * discount * normal.cdf(-d2)
        }
    } / 365.0;
    let vega = underlying_price * sqrt_t * normal.pdf(d1) / 100.0;
    let rho = match option_type {
        OptionType::Call => strike_price * time_to_expiration * discount * normal.cdf(d2) / 100.0,
        OptionType::Put => -strike_price * time_to_expiration * discount * normal.cdf(-d2) / 100.0,
    };

    Ok(OptionPricingResult {
        option_type: option_type.as_str().to_string(),
        underlying_price,
        strike_price,
        time_to_expiration,
        risk_free_rate,
        volatility,
        option_price,
        delta,
        gamma,
        theta,
        vega,
        rho,
    })
}

pub fn calculate_put_call_parity(
    call_price: f64,
    underlying_price: f64,
    strike_price: f64,
    time_to_expiration: f64,
    risk_free_rate: f64,
) -> f64 {
    call_price - underlying_price + strike_price * (-risk_free_rate * time_to_expiration).exp()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn black_scholes_call_matches_known_shape() {
        let result = price_black_scholes(100.0, 100.0, 1.0, 0.2, 0.05, "call").unwrap();
        assert!(result.option_price > 0.0);
        assert!(result.delta > 0.0);
        assert!(result.gamma > 0.0);
        assert!(result.vega > 0.0);
    }

    #[test]
    fn put_call_parity_matches_direct_put() {
        let call = price_black_scholes(100.0, 100.0, 1.0, 0.2, 0.05, "call").unwrap();
        let put = price_black_scholes(100.0, 100.0, 1.0, 0.2, 0.05, "put").unwrap();
        let parity = calculate_put_call_parity(call.option_price, 100.0, 100.0, 1.0, 0.05);
        assert!((parity - put.option_price).abs() < 1e-10);
    }
}
