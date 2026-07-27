"""Test Analyze API - diagnose empty analysis."""
import json, urllib.request, urllib.error

API = "http://127.0.0.1:8000"
KEY = "local-dev-key"

print("=== Analyze API test ===")
body = json.dumps({
    "question": "分析000001短期走势",
    "symbol": "000001",
    "market": "cn",
    "defer_kronos_predictions": False,
})
req = urllib.request.Request(
    f"{API}/api/v1/analyze/agent",
    data=body.encode("utf-8"),
    headers={"Content-Type": "application/json", "X-Kronos-Api-Key": KEY},
)
try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        r = json.loads(resp.read().decode("utf-8"))
    print(f"ok = {r.get('ok')}")
    print(f"keys: {list(r.keys())}")
    if "error" in r:
        print(f"error: {r['error']}")
    if "analysis" in r:
        val = r["analysis"]
        print(f"analysis type: {type(val).__name__}")
        print(f"analysis repr: {repr(val)[:300]}")
    if "data" in r:
        d = r["data"]
        print(f"data type: {type(d).__name__}")
        print(f"data keys: {list(d.keys()) if isinstance(d, dict) else 'N/A'}")
        if isinstance(d, dict):
            for k, v in d.items():
                print(f"  {k}: {type(v).__name__} = {str(v)[:200]}")
    print(f"\nFull response: {json.dumps(r, indent=2, ensure_ascii=False)[:2000]}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode('utf-8')[:1000]}")
except Exception as e:
    print(f"Error: {e}")
