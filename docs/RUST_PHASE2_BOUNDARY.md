# Rust Phase 2 Boundary

This note defines the current Rust migration boundary for the CFA analysis
modules. The goal is to keep the optional Rust engine useful without replacing
Python libraries that already carry complex numerical behavior.

## Completed in v8.5

- Technical indicators now have optional Rust kernels for SMA, EMA, RSI, MACD,
  Bollinger Bands, KDJ, ATR, and OBV.
- Risk calculations now have optional Rust kernels for Historical VaR, Sharpe,
  Sortino, maximum drawdown, and volatility.
- Python remains the compatibility source. Rust is only used when
  `USE_RUST_ENGINE=1` or `USE_RUST_ENGINE=auto` and `kronos_fincept_native` is
  installed.
- Missing or older native wheels fall back to Python instead of failing the
  caller.

## Keep in Python for now

### DCF

The current DCF implementation is scalar financial modeling logic. It is not a
hot loop compared with data fetching, inference, and rolling indicator
calculation. Moving it to Rust would increase maintenance cost without a clear
runtime gain. Keep DCF in Python until profiling shows repeated batch valuation
as a real bottleneck.

### Derivatives

The Black-Scholes closed-form path can be moved later if needed, but implied
volatility solving and distribution behavior must remain numerically compatible
with SciPy. Keep the current Python implementation as the fallback and consider
Rust only for pure closed-form pricing and Greeks after adding parity fixtures.

### Portfolio

Portfolio optimization depends on constrained numerical optimization. The
existing SciPy path should remain authoritative because reproducing optimizer
behavior in Rust would require a separate optimization stack and materially
raise validation burden. A future Rust scope can cover matrix/statistical helper
kernels such as covariance, returns, and drawdown transforms, while leaving
optimization decisions in Python.

## Future Rust Candidates

- Rolling covariance and correlation matrices for large multi-asset batches.
- Batch risk metric evaluation over many symbols.
- Closed-form Black-Scholes price and Greeks with explicit SciPy parity tests.
- Data-frame independent transforms that operate on contiguous numeric slices.

## Fallback Policy

Every native entry point must keep a Python fallback and parity test. Public
CLI, API, JSON fields, dataclasses, and frontend response shapes must not change
when Rust is enabled.
