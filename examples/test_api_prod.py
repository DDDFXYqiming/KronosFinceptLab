"""Test API production prediction quality against eval benchmark."""
import json, urllib.request, urllib.error
from pathlib import Path

API = "http://127.0.0.1:8000"
KEY = "local-dev-key"
PROJ = Path(__file__).resolve().parents[1]

# Health check
h = json.loads(urllib.request.urlopen(f"{API}/api/health", timeout=10).read())
print(f"Model: {h.get('model_display_name', h.get('model_id','?'))}")
print(f"Device: {h.get('device','?')}")
print(f"Enabled: {h.get('model_enabled')}")

# Forecast accuracy test
csv_files = sorted((PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2").glob("cn_*.csv"))[:30]
results = []
fails = 0

for f in csv_files:
    lines = open(f, encoding="utf-8").read().strip().split("\n")
    data = lines[1:]
    n = len(data)
    if n < 150:
        continue
    symbol = f.stem.replace("cn_", "")

    ctx = data[n-150:n-60]
    last_close = float(ctx[-1].split(",")[4])
    actual_close = float(data[n-60+4].split(",")[4])

    rows = []
    for line in ctx:
        p = line.split(",")
        rows.append({"timestamp": f"{p[0]}T00:00:00Z", "open": float(p[1]), "high": float(p[2]),
                      "low": float(p[3]), "close": float(p[4]), "volume": float(p[5]), "amount": float(p[6])})

    body = json.dumps({"symbol": symbol, "timeframe": "1d", "pred_len": 5,
                        "sample_count": 8, "temperature": 0.5, "rows": rows})
    req = urllib.request.Request(f"{API}/api/forecast", data=body.encode("utf-8"),
                                  headers={"Content-Type": "application/json", "X-Kronos-Api-Key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            r = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"ERR {symbol}: {e}", flush=True)
        fails += 1
        continue

    if not r.get("ok"):
        print(f"FAIL {symbol}: {r.get('error','')[:100]}", flush=True)
        fails += 1
        continue

    forecast = r.get("forecast", [])
    if len(forecast) < 5:
        continue

    pred_close = float(forecast[-1]["close"])
    results.append((symbol, last_close, pred_close, actual_close, pred_close > last_close, actual_close > last_close))

# Results
correct = sum(1 for r in results if r[4] == r[5])
total = len(results)
acc = correct / total * 100 if total else 0

print(f"\n{'='*60}")
print(f"Forecast API: {total} stocks, {fails} failures")
print(f"{'='*60}")
for sym, last, pred, actual, pd_, ad_ in results:
    match = "OK" if pd_ == ad_ else "NO"
    print(f"  {sym:>6}  last={last:>8.2f}  pred5={pred:>8.2f}  actual5={actual:>8.2f}  {match}")

print(f"\nDirection accuracy: {acc:.1f}% ({correct}/{total})")
print(f"Eval benchmark:     54.1%")
dev = "within" if abs(acc - 54.1) <= 5 else f"delta={acc-54.1:+.1f}pp"
print(f"Compare:            {dev}")

# Analyze API test
print(f"\n{'='*60}")
print("Analyze API (agent) quick test")
print(f"{'='*60}")
try:
    body = json.dumps({"question": "分析000001短期走势", "symbol": "000001", "market": "cn", "defer_kronos_predictions": False})
    req = urllib.request.Request(f"{API}/api/v1/analyze/agent", data=body.encode("utf-8"),
                                  headers={"Content-Type": "application/json", "X-Kronos-Api-Key": KEY})
    with urllib.request.urlopen(req, timeout=180) as resp:
        r = json.loads(resp.read().decode("utf-8"))
    ok = r.get("ok", False)
    analysis = r.get("analysis", "") or str(r.get("data", {}))
    has_pred = "预测" in analysis or "forecast" in analysis.lower() or "K线" in analysis
    print(f"ok={ok}  analysis_len={len(analysis)}  has_prediction={has_pred}")
    print(f"Preview: {analysis[:200]}...")
except Exception as e:
    print(f"Analyze API error: {e}")

# Save
out = PROJ / "output" / "api_production_test.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({"accuracy": acc, "correct": correct, "total": total, "fails": fails, "results": results}, f, indent=2)
print(f"\nSaved to {out}")
