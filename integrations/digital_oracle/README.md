# Digital Oracle Integration

> Document status: Current
> Project version: 10.9.0
> Last reviewed: 2026-07-29

Digital Oracle providers are adapted to the KronosFinceptLab `MacroProvider` interface and included by `create_all_providers()`.

## Current status

| Layer | Status | Notes |
|---|---|---|
| Thin provider wrappers | Implemented | 14 wrappers are registered in `WRAPPED_PROVIDERS` |
| Advanced market wrappers | Implemented | Polymarket/Kalshi order books and Deribit/YFinance Greeks |
| KFL provider factory | Integrated | Native and wrapped providers are combined by `create_all_providers()` |
| No-key smoke coverage | Verified | BIS, US Treasury and World Bank returned signals; rate-limited providers degraded cleanly |
| Key-dependent providers | Environment-dependent | Availability depends on API credentials and upstream services |
| Web end-to-end behavior | Runtime-dependent | Exposed through the macro analysis provider path; provider status should be checked at runtime |

## Wrapped providers

- Polymarket
- Kalshi
- CME FedWatch
- Fear & Greed
- BIS
- CFTC COT
- CoinGecko
- Yahoo price
- Stooq price
- US Treasury
- EDGAR
- World Bank
- Web search
- YFinance options

Advanced wrappers add Polymarket and Kalshi order-book signals plus Deribit and YFinance option Greeks.

Provider construction is intentionally tolerant: unavailable credentials, rate limits, missing optional dependencies and upstream failures must degrade to provider-level errors rather than block application startup.

The original implementation checkpoint is archived at [`../../docs/archive/audits/DIGITAL_ORACLE_CHECKPOINT_2026-07-23.md`](../../docs/archive/audits/DIGITAL_ORACLE_CHECKPOINT_2026-07-23.md).
