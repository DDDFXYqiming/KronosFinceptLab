# Logging System 4-Blind-Spot Fix Report
**Date**: 2026-07-23 | **Tests**: 151 passed / 152 (1 pre-existing failure)

---

## Blind Spot #1: TextFormatter drops unknown extra fields
**Status**: ✅ Already fixed (pre-existing)
`logging_config.py` `TextFormatter.format()` already has generic `extra` field traversal:
```python
for key, val in record.__dict__.items():
    if key not in skip_fields and not key.startswith('_'):
        json_record[key] = val
```

## Blind Spot #2: LLM success path not logged
**Status**: ✅ Already fixed (pre-existing)
`agent.py` `_call_llm_json()` already emits `logger.debug("LLM call succeeded", extra={"event": "agent.llm.io", ...})` on success.

## Blind Spot #3: Data source IO methods unlogged
**Status**: ✅ Fixed (this session)

**`financial/baostock_financial.py`** (+2 methods):
- `get_financial_data()` → `@log_perf(event="baostock.financial", log_args=True, log_result=True, max_result_len=500)`
- `get_income_statements()` → `@log_perf(event="baostock.income", log_args=True, log_result=True, max_result_len=500)`

**`financial/yahoo_financial.py`** (+4 methods):
- `get_financial_data()` → `@log_perf(event="yahoo.financial", ...)`
- `get_income_statements()` → `@log_perf(event="yahoo.income", ...)`
- `get_balance_sheets()` → `@log_perf(event="yahoo.balance", ...)`
- `get_cash_flow_statements()` → `@log_perf(event="yahoo.cashflow", ...)`

_Note: `data_sources/` (13 raw source files) not instrumented; `financial/` layer is their primary caller._

## Blind Spot #4: `@log_perf` decorators missing event-specific params
**Status**: ✅ Fixed (this session)

**`logging_config.py`** — added `max_result_len` parameter to `log_perf()`:
- Signature: `def log_perf(event=None, log_args=False, log_result=False, max_result_len=None)`
- Truncation in both `wrapper` (sync) and `awrapper` (async):
```python
if max_result_len and len(repr_result) > max_result_len:
    repr_result = repr_result[:max_result_len] + "...[truncated]"
```

**`agent.py`** — 12 decorators all now include `log_args=True, log_result=True, max_result_len=N`:

| Event | max_result_len |
|-------|----------------|
| agent.llm_structured | 500 |
| agent.analyze | 2000 |
| agent.macro | 2000 |
| agent.macro_proof | 1500 |
| agent.classify_macro | 500 |
| agent.resolve_symbols | 500 |
| agent.asset_ctx | 1000 |
| agent.research | 1000 |
| agent.batch_pred | 2000 |
| agent.generate_report | 3000 |
| agent.llm_report | 2000 |

## Files Modified
1. `src/logging_config.py` — `log_perf` decorator enhanced with `max_result_len`
2. `src/agent/agent.py` — 12 `@log_perf` decorators standardized
3. `src/financial/baostock_financial.py` — 2 IO methods decorated
4. `src/financial/yahoo_financial.py` — 4 IO methods decorated
