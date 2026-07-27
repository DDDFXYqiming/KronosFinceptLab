"""Test data + forecast pipeline for 600036."""
import json, urllib.request, urllib.error

API = "http://127.0.0.1:8000"
KEY = "local-dev-key"

# 1. Fetch data
print("=== Data fetch ===")
try:
    url = f"{API}/api/data/a-stock/600036?start_date=20250101&end_date=20260430"
    req = urllib.request.Request(url, headers={"X-Kronos-Api-Key": KEY})
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    print(f"ok={d.get('ok')} count={d.get('count')}")
    if d.get("rows"):
        print(f"First: {d['rows'][0]['timestamp']} -> Last: {d['rows'][-1]['timestamp']}")
        print(f"Last close: {d['rows'][-1]['close']}")
except Exception as e:
    print(f"Data fetch error: {e}")

# 2. Forecast with last 90 rows
print("\n=== Forecast ===")
if d.get("rows") and len(d["rows"]) >= 90:
    rows = d["rows"][-90:]
    body = json.dumps({"symbol": "600036", "timeframe": "1d", "pred_len": 5, "rows": rows})
    try:
        req = urllib.request.Request(f"{API}/api/forecast", data=body.encode("utf-8"),
                                      headers={"Content-Type": "application/json", "X-Kronos-Api-Key": KEY})
        with urllib.request.urlopen(req, timeout=120) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        print(f"ok={r.get('ok')} device={r['metadata']['device']}")
        if r.get("forecast"):
            f5 = r["forecast"]
            print(f"D1={f5[0]['close']:.4f} -> D5={f5[-1]['close']:.4f}")
            ret = (f5[-1]["close"] / rows[-1]["close"] - 1) * 100
            print(f"Pred 5d return: {ret:.2f}%")
        if r.get("probabilistic"):
            p = r["probabilistic"]
            print(f"Probabilistic: sc={p['sample_count']} upside={p['upside_probability']}")
    except Exception as e:
        print(f"Forecast error: {e}")
