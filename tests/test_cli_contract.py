import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cli_returns_valid_json_with_dry_run_predictor():
    request = {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "pred_len": 2,
        "dry_run": True,
        "rows": [
            {"timestamp": "2026-04-29T00:00:00Z", "open": 100, "high": 110, "low": 90, "close": 105},
            {"timestamp": "2026-04-29T01:00:00Z", "open": 105, "high": 112, "low": 100, "close": 108},
            {"timestamp": "2026-04-29T02:00:00Z", "open": 108, "high": 115, "low": 103, "close": 111},
        ],
    }

    proc = subprocess.run(
        [sys.executable, "-m", "kronos_fincept.cli"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["symbol"] == "BTC/USDT"
    assert len(payload["forecast"]) == 2
    assert payload["metadata"]["warning"] == "Research forecast only; not trading advice."
