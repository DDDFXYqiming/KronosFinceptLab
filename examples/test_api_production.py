"""Test production API prediction quality vs evaluation benchmark.

Calls the running API (port 8000) exactly as the frontend would.
Uses historical CSV data to verify prediction direction against known outcomes.
"""

import json, os, sys, time
from pathlib import Path
import urllib.request
import urllib.error

PROJ = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"
KEY = "local-dev-key"
HEADERS = {
    "Content-Type": "application/json",
    "X-Kronos-Api-Key": KEY,
}

DATA_DIR = PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2"
N_STOCKS = 30

def api_post(path: str, body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{API}{path}", data=data, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def api_get(path: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(f"{API}{path}", headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ── 1. Health check ──
print("=== 1. Health check ===", flush=True)
h = api_get("/api/health", 10)
print(f"  model_id: {h.get('model_id')}")
print(f"  model_display_name: {h.get('model_display_name')}")
print(f"  device: {h.get('device')}")
print(f"  model_enabled: {h.get('model_enabled')}")

# ── 2. Forecast API test ──
print("\n=== 2. Forecast API direction accuracy ===", flush=True)

csv_files = sorted(DATA_DIR.glob("cn_*.csv"))[:N_STOCKS]
results = []

for f in csv_files:
    lines = open(f, encoding="utf-8").read().strip().split("\n")
    headers_line = lines[0]
    data_lines = lines[1:]
    n = len(data_lines)
    if n < 150:
        continue

    symbol = f.stem.replace("cn_", "")

    # Take a sliding window: use rows [n-150, n-100) as context (90 days)
    # and compare pred direction with actual direction from [n-100, n-95)
    ctx_lines = data_lines[n-150:n-60]  # 90 days context
    actual_start = n - 60  # first actual day after context
    actual_end = n - 55    # 5 days later

    if actual_end > n:
        continue

    # Parse actual data for comparison
    def parse_close(line):
        return float(line.split(",")[4])

    last_close = parse_close(ctx_lines[-1])
    actual_close_5 = parse_close(data_lines[actual_end - 1])

    # Build forecast request
    rows = []
    for line in ctx_lines:
        parts = line.split(",")
        rows.append({
            "timestamp": f"{parts[0]}T00:00:00Z",
            "open": float(parts[1]),
            "high": float(parts[2]),
            "low": float(parts[3]),
            "close": float(parts[4]),
            "volume": float(parts[5]),
            "amount": float(parts[6]),
        })

    body = {
        "symbol": symbol,
        "timeframe": "1d",
        "pred_len": 5,
        "sample_count": 8,
        "temperature": 0.5,
        "rows": rows,
    }

    try:
        resp = api_post("/api/forecast", body, 120)
    except Exception as e:
        print(f"  [api error] {symbol}: {e}", flush=True)
        continue

    if not resp.get("ok"):
        print(f"  [api fail] {symbol}: {resp.get('error','')}", flush=True)
        continue

    forecast = resp.get("forecast", [])
    if len(forecast) < 5:
        continue

    pred_close_5 = float(forecast[-1]["close"])
    pred_dir = pred_close_5 > last_close
    actual_dir = actual_close_5 > last_close
    correct = pred_dir == actual_dir

    results.append({
        "symbol": symbol,
        "last_close": last_close,
        "pred_close_5": round(pred_close_5, 2),
        "actual_close_5": actual_close_5,
        "pred_dir": "UP" if pred_dir else "DOWN",
        "actual_dir": "UP" if actual_dir else "DOWN",
        "correct": correct,
    })

# ── Print results ──
correct_count = sum(1 for r in results if r["correct"])
total = len(results)
accuracy = correct_count / total * 100 if total > 0 else 0

print(f"\n{'Symbol':<8} {'Last':>8} {'Pred5':>8} {'Actual5':>8} {'PredDir':>6} {'ActDir':>6} {'Correct':>8}")
print("-" * 60)
for r in results:
    print(f"{r['symbol']:<8} {r['last_close']:>8.2f} {r['pred_close_5']:>8.2f} {r['actual_close_5']:>8.2f} {r['pred_dir']:>6} {r['actual_dir']:>6} {'✅' if r['correct'] else '❌':>8}")

print(f"\n{'='*60}")
print(f"Forecast API Direction Accuracy: {accuracy:.1f}% ({correct_count}/{total})")
print(f"Eval benchmark:                 54.1%")
print(f"{'='*60}")

if accuracy >= 50:
    print(f"✅ API accuracy ({accuracy:.1f}%) is above random (50%)")
else:
    print(f"❌ API accuracy ({accuracy:.1f}%) is at or below random (50%)")

# ── 3. Analysis API test ──
print("\n=== 3. Analysis API test ===", flush=True)

try:
    # Test analyze agent endpoint with a simple question
    from_date = "20260101"
    to_date = "20260724"
    test_stocks = ["000001", "000333", "000858"]
    
    for sym in test_stocks[:1]:  # Just 1 to avoid long wait
        print(f"  Analyzing {sym}...", flush=True)
        body = {
            "question": f"分析{sym}的短期走势和技术指标",
            "symbol": sym,
            "market": "cn",
            "defer_kronos_predictions": False,
        }
        try:
            resp = api_post("/api/v1/analyze/agent", body, 180)
            ok = resp.get("ok", False)
            print(f"    ok={ok}")
            if ok:
                analysis = resp.get("analysis", "") or resp.get("data", {}).get("analysis", "")
                # Check if prediction part was included
                has_prediction = "预测" in analysis or "K线预测" in analysis or "forecast" in analysis.lower()
                print(f"    has_prediction_section: {has_prediction}")
                print(f"    analysis_length: {len(str(analysis))} chars")
                # Print first 300 chars of analysis
                print(f"    preview: {str(analysis)[:300]}...")
        except Exception as e:
            print(f"    error: {e}", flush=True)

except Exception as e:
    print(f"  Analysis test error: {e}", flush=True)

# ── Summary ──
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"Model:          {h.get('model_display_name', h.get('model_id','?'))}")
print(f"Device:         {h.get('device','?')}")
print(f"Prediction acc: {accuracy:.1f}% ({correct_count}/{total})")
print(f"Eval baseline:  54.1%")
print(f"Result:         {'✅ MATCHES' if abs(accuracy - 54.1) <= 5 else '⚠️ DEVIATES'} eval benchmark")

# Save
out = PROJ / "output" / "api_production_test.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({
        "health": h,
        "forecast_accuracy": round(accuracy, 1),
        "correct": correct_count,
        "total": total,
        "results": results,
    }, f, indent=2, ensure_ascii=False)
print(f"Saved to {out}")
