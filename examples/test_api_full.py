"""Full API production verification: multi-window, 30 stocks, compare to eval."""
import json, urllib.request, urllib.error, time
from pathlib import Path

API = "http://127.0.0.1:8000"
KEY = "local-dev-key"
PROJ = Path(__file__).resolve().parents[1]

# Health check
h = json.loads(urllib.request.urlopen(f"{API}/api/health", timeout=10).read())
print(f"Model: {h.get('model_display_name', h.get('model_id','?'))}")
print(f"Device: {h.get('device','?')}")

# Full accuracy test: multiple windows per stock
csv_files = sorted((PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2").glob("cn_*.csv"))[:30]
total_correct = 0
total_samples = 0
failures = 0
details = []

for f in csv_files:
    lines = open(f, encoding="utf-8").read().strip().split("\n")
    data = lines[1:]
    n = len(data)
    if n < 150:
        continue
    symbol = f.stem.replace("cn_", "")

    # Multiple sliding windows in last 150 days
    for offset in range(0, 50, 5):  # 10 windows per stock
        ctx_end = n - 60 - offset
        ctx_start = ctx_end - 90
        if ctx_start < 0 or ctx_end + 5 > n:
            continue

        ctx = data[ctx_start:ctx_end]
        last_close = float(ctx[-1].split(",")[4])
        actual_close = float(data[ctx_end + 4].split(",")[4])

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
            failures += 1
            continue

        if not r.get("ok"):
            failures += 1
            continue

        forecast = r.get("forecast", [])
        if len(forecast) < 5:
            continue

        pred_close = float(forecast[-1]["close"])
        correct = (pred_close > last_close) == (actual_close > last_close)
        total_correct += int(correct)
        total_samples += 1

        if total_samples <= 60:
            details.append((symbol, last_close, pred_close, actual_close, correct))

acc = total_correct / total_samples * 100 if total_samples else 0
print(f"\n{'='*60}")
print(f"Full API Verification: {total_samples} samples, {failures} failures")
print(f"{'='*60}")
for sym, last, pred, actual, ok in details[:50]:
    m = "OK" if ok else "NO"
    print(f"  {sym:>6}  last={last:>8.2f}  pred5={pred:>8.2f}  actual5={actual:>8.2f}  {m}")

print(f"\n{'='*60}")
print(f"Direction accuracy:  {acc:.1f}% ({total_correct}/{total_samples})")
print(f"Eval benchmark:      54.1%")
print(f"Eval sample count:   510")
print(f"API sample count:    {total_samples}")
dev = acc - 54.1
if abs(dev) <= 3:
    print(f"Result: MATCHES eval benchmark (within 3pp)")
elif acc < 50:
    print(f"Result: BELOW random 50%")
else:
    print(f"Result: ABOVE random 50% but below eval (delta={dev:+.1f}pp)")

# Save
out = PROJ / "output" / "api_full_verification.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({
        "accuracy": acc, "correct": total_correct, "total": total_samples,
        "fails": failures, "eval_benchmark": 54.1,
    }, f, indent=2)
print(f"Saved to {out}")
