"""Predict 601398 (ICBC) - bypass proxy for eastmoney.com."""
import sys, os, json

# Bypass proxy for eastmoney.com
os.environ["NO_PROXY"] = "push2his.eastmoney.com,*.eastmoney.com"
os.environ["no_proxy"] = "push2his.eastmoney.com,*.eastmoney.com"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)
os.environ.pop("ALL_PROXY", None)
os.environ.pop("all_proxy", None)

project_root = os.path.dirname(os.path.abspath(__file__))
kronos_repo = os.path.join(project_root, "external", "Kronos")
os.environ["KRONOS_REPO_PATH"] = kronos_repo
os.environ["HF_HOME"] = os.path.join(project_root, "external")
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, kronos_repo)

# Monkey-patch requests to not use proxy for eastmoney
import requests
original_get = requests.get
def patched_get(*args, **kwargs):
    kwargs.setdefault("proxies", {"http": None, "https": None})
    return original_get(*args, **kwargs)
requests.get = patched_get

from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv
from kronos_fincept.schemas import ForecastRequest, ForecastRow
from kronos_fincept.service import forecast_from_request

print("Fetching 601398 (ICBC) data...")
rows = fetch_a_stock_ohlcv("601398", "20250101", "20260430")
print(f"Got {len(rows)} rows")
print(f"Last: {rows[-1]['timestamp']} close={rows[-1]['close']}")

forecast_rows = [ForecastRow.from_dict(r) for r in rows[-60:]]
request = ForecastRequest(symbol="601398", timeframe="1d", pred_len=5, rows=forecast_rows, dry_run=False)

print("Running Kronos inference...")
result = forecast_from_request(request)
print(json.dumps(result, ensure_ascii=False, indent=2))
