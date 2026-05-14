# Rust-First Incremental Migration Spec

## Summary

KronosFinceptLab should move performance-sensitive, deterministic computation
into Rust while keeping Python as the orchestration layer for FastAPI, CLI,
PyTorch/Kronos inference, LLM workflows, and third-party finance SDKs. This
phase expands the existing PyO3 native extension instead of adding a Rust HTTP
service or rewriting the backend.

Current baseline:

- Python is the primary backend implementation.
- Rust is already present as a Cargo workspace with `kronos-kernel` and
  `kronos-fincept-native`.
- Existing Rust coverage includes technical indicators and several risk
  metrics.
- The native extension remains optional and must keep Python fallbacks.

## Scope

This phase migrates pure computation only:

- Black-Scholes option pricing, Greeks, and put-call parity.
- Portfolio return, expected return, covariance, and performance helper
  calculations.
- Strategy snapshot signal calculation for the default strategy bundle.
- Backtest performance metric calculation from an equity curve.

This phase does not migrate:

- FastAPI route definitions or Pydantic request/response models.
- PyTorch/Kronos model inference and model caching.
- LLM agent routing, prompts, and provider calls.
- akshare, baostock, yfinance, requests-based data adapters.
- SciPy constrained portfolio optimization.

## Implementation

- Split `crates/kronos-kernel/src/lib.rs` into domain modules:
  `indicators`, `risk`, `derivatives`, `portfolio`, `strategies`, and
  `backtest`.
- Expose new PyO3 functions from `kronos_fincept_native`:
  `price_black_scholes`, `calculate_put_call_parity`,
  `calculate_portfolio_returns`, `calculate_expected_returns`,
  `calculate_covariance_matrix`, `calculate_portfolio_performance`,
  `calculate_strategy_snapshot`, and `calculate_backtest_metrics`.
- Extend `src/kronos_fincept/native.py` with safe wrappers. Wrappers return
  `None` when Rust is disabled, unavailable, missing a function, or raises an
  unexpected bridge error.
- Wire Rust-first calls into the Python financial modules and backtest metrics,
  preserving existing public dataclasses and API response shapes.
- Default packaged runtime to `USE_RUST_ENGINE=auto`. In `auto`, missing native
  wheels fall back without warning; forced mode (`1`, `true`, `yes`, `on`)
  logs missing native extension warnings.

## Toolchain And Packaging

- Development requires a working Rust linker for the active target and
  `maturin>=1.8,<2`.
- Windows MSVC target requires Visual Studio C++ Build Tools (`link.exe`).
- Docker builds should install Rust and build/install the native wheel before
  the app starts.
- If the local linker cannot be installed, Python-level code and fallback tests
  may still be updated, but Rust compile and native parity verification remain
  blocked until the linker is available.

## Verification

Run these checks after the toolchain is available:

- `cargo test -p kronos-kernel`
- `cargo test --workspace`
- `python -m maturin build --manifest-path crates/kronos-python/Cargo.toml --release --out dist/native`
- Install the newest wheel from `dist/native`.
- `python -m pytest tests/test_rust_native_bridge.py -q`
- `python -m pytest tests/test_derivatives.py tests/test_portfolio.py tests/test_indicators_strategies.py tests/test_risk.py tests/test_api.py tests/test_cli.py -q`
- `python scripts/benchmark_rust_native.py`
