"""Quick API test: check forecast accuracy with 90-row data."""
import json, urllib.request, urllib.error
from pathlib import Path

API = "http://127.0.0.1:8000"
KEY = "local-dev-key"

PROJ = Path(__file__).resolve().parents[1]

num_ok = 0
num_fail = 0
results = []

csv_files = sorted((PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2").glob("cn_*.csv"))[:10]

for f in csv_files:
    lines = open(f).read().strip().split("\n")
    data = lines[1:]
    n = len(data)
    if n < 150:
        continue
    symbol = f.stem.replace("cn_", "")

    ctx = data[n-150:n-60]
    last_close = float(ctx[-1].split(",")[4])
    actual_close = float(data[n-60+4].split(",")[4])  # 5th day after context

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
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")[:200]
        print(f"  FAIL {symbol}: {err}", flush=True)
        num_fail += 1
        continue
    except Exception as e:
        print(f"  ERROR {symbol}: {e}", flush=True)
        num_fail += 1
        continue

    if not r.get("ok"):
        print(f"  FAIL {symbol}: {r.get('error','')}", flush=True)
        num_fail += 1
        continue

    forecast = r.get("forecast", [])
    if len(forecast) < 5:
        continue

    pred_close = float(forecast[-1]["close"])
    pred_dir = pred_close > last_close
    actual_dir = actual_close > last_close
    correct = pred_dir == actual_dir
    results.append((symbol, last_close, pred_close, actual_close, correct, r["metadata"]["device"]))
    num_ok += 1

print(f"\n{'='*70}")
print(f"Results: {num_ok} ok, {num_fail} failed")
print(f"{'='*70}")
correct = sum(1 for r in results if r[4])
total = len(results)
acc = correct / total * 100 if total else 0
for symbol, last, pred, actual, ok, device in results:
    mark = "OK" if ok else "NO"
    print(f"  {symbol:>6}  last={last:>8.2f}  pred5={pred:>8.2f}  actual5={actual:>8.2f}  {mark:>2}  ({device})")
print(f"\nDirection accuracy: {acc:.1f}% ({correct}/{total})")
print(f"Eval benchmark:     54.1%")
if abs(acc - 54.1) <= 5:
    print(f"✅ MATCHES eval benchmark (within 5pp)")
else:
    print(f"⚠️ DEVIATES from eval benchmark (delta={acc-54.1:+.1f}pp)")
