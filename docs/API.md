# KronosFinceptLab API Documentation

Base URL: `http://localhost:8000`

## Endpoints

### Health Check
```
GET /api/health
```
Returns: `{ status, version, model_loaded, model_id, device, uptime_seconds }`

### Forecast
```
POST /api/forecast
Content-Type: application/json

{
  "symbol": "600519",
  "timeframe": "1d",
  "pred_len": 5,
  "rows": [
    { "timestamp": "2026-01-02T00:00:00Z", "open": 100, "high": 101, "low": 99, "close": 100.5 }
  ],
  "dry_run": false
}
```

### Batch Forecast
```
POST /api/batch
Content-Type: application/json

{
  "assets": [
    { "symbol": "600519", "rows": [...] },
    { "symbol": "000858", "rows": [...] }
  ],
  "pred_len": 5,
  "dry_run": false
}
```

### Data
```
GET /api/data/a-stock/{symbol}?start_date=20250101&end_date=20260430
GET /api/data/search?q=茅台
```

### Backtest
```
POST /api/backtest/ranking
Content-Type: application/json

{
  "symbols": ["600519", "000858"],
  "start_date": "20250101",
  "end_date": "20260430",
  "top_k": 1,
  "pred_len": 5,
  "dry_run": true
}
```

## Error Format
```json
{ "ok": false, "error": "Error message" }
```

## Interactive Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
