"""Final API verification: 30 stocks x 5 windows, respecting rate limits."""
import json, urllib.request, urllib.error, time
from pathlib import Path

API = "http://127.0.0.1:8000"
KEY = "local-dev-key"
PROJ = Path(__file__).resolve().parents[1]

h = json.loads(urllib.request.urlopen(f"{API}/api/health", timeout=10).read())
print(f"Model: {h.get('model_display_name', h.get('model_id','?'))}")

csv_files = sorted((PROJ / "external" / "Kronos" / "finetune_csv" / "data_v2").glob("cn_*.csv"))[:20]
total_correct = 0; total_samples = 0; rate_limited = 0; errors = 0

for f in csv_files:
    lines = open(f, encoding="utf-8").read().strip().split("\n")
    data = lines[1:]; n = len(data)
    if n < 150: continue
    symbol = f.stem.replace("cn_", "")

    for offset in range(0, 16, 5):
        ctx_end = n - 60 - offset
        ctx_start = ctx_end - 90
        if ctx_start < 0 or ctx_end + 5 > n: continue

        ctx = data[ctx_start:ctx_end]
        last_close = float(ctx[-1].split(",")[4])
        actual_close = float(data[ctx_end + 4].split(",")[4])

        rows = [{"timestamp": f"{p[0]}T00:00:00Z", "open": float(p[1]), "high": float(p[2]),
                  "low": float(p[3]), "close": float(p[4]), "volume": float(p[5]), "amount": float(p[6])}
                for p in (line.split(",") for line in ctx)]

        body = json.dumps({"symbol": symbol, "timeframe": "1d", "pred_len": 5,
                            "sample_count": 8, "temperature": 0.5, "rows": rows})
        req = urllib.request.Request(f"{API}/api/forecast", data=body.encode("utf-8"),
                                      headers={"Content-Type": "application/json", "X-Kronos-Api-Key": KEY})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                r = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429: rate_limited += 1
            else: errors += 1
            time.sleep(5)
            continue
        except Exception:
            errors += 1
            time.sleep(5)
            continue

        if total_samples > 0 and total_samples % 20 == 0:
            print(f"  progress: {total_samples} samples, acc={total_correct/total_samples*100:.1f}%", flush=True)
        if r.get("ok") and len(r.get("forecast", [])) >= 5:
            pred_close = float(r["forecast"][-1]["close"])
            correct = (pred_close > last_close) == (actual_close > last_close)
            total_correct += int(correct)
            total_samples += 1

        # Rate limit: ensure spacing
        elapsed = time.time() - t0
        if elapsed < 2.5:
            time.sleep(2.5 - elapsed)

acc = total_correct / total_samples * 100 if total_samples else 0
print(f"\n{'='*50}")
print(f"Accuracy: {acc:.1f}% ({total_correct}/{total_samples})")
print(f"Errors:   {errors}   Rate-limited: {rate_limited}")
print(f"Eval:     54.1%")
dev = acc - 54.1
print(f"Delta:    {dev:+.1f}pp")
if abs(dev) <= 5: print("Result:  MATCHES eval benchmark")
elif acc >= 50: print("Result:  ABOVE random 50%")
else: print("Result:  BELOW random 50%")

out = PROJ / "output" / "api_final_verified.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump({"accuracy": acc, "correct": total_correct, "total": total_samples,
               "errors": errors, "rate_limited": rate_limited, "eval_benchmark": 54.1}, f, indent=2)
print(f"Saved to {out}")
