#!/usr/bin/env python3
"""Kronos Forecast Bridge for FinceptTerminal PythonRunner.

Compatible with FinceptTerminal's daemon protocol:
  - Length-prefixed binary frames (4-byte big-endian header + JSON payload)
  - Actions: forecast, batch_forecast, fetch_a_stock, shutdown
  - Supports both --daemon mode (for PythonRunner) and direct CLI mode

Usage:
  # Daemon mode (called by FinceptTerminal PythonRunner)
  python kronos_forecast.py --daemon

  # CLI mode (direct invocation)
  python kronos_forecast.py --input request.json
  python kronos_forecast.py --input request.json --output result.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure kronos_fincept is importable
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent.parent  # integrations/fincept_terminal/scripts -> project root
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


# ---------------------------------------------------------------------------
# Core forecast logic (imported from kronos_fincept)
# ---------------------------------------------------------------------------

def _do_forecast(payload: dict) -> dict:
    """Run single-asset forecast."""
    from kronos_fincept.schemas import ForecastRequest
    from kronos_fincept.service import forecast_from_request

    req = ForecastRequest.from_dict(payload)
    return forecast_from_request(req)


def _do_batch_forecast(payload: dict) -> dict:
    """Run multi-asset batch forecast with ranking."""
    from kronos_fincept.schemas import ForecastRequest, BatchForecastRequest
    from kronos_fincept.service import batch_forecast_from_requests

    batch = BatchForecastRequest.from_dicts(
        payload.get("assets", []),
        shared=payload.get("shared"),
    )
    signals = batch_forecast_from_requests(batch.requests)
    return {
        "ok": True,
        "count": len(signals),
        "rankings": [
            {
                "rank": s.rank,
                "symbol": s.symbol,
                "last_close": s.last_close,
                "predicted_close": s.predicted_close,
                "predicted_return_pct": round(s.predicted_return * 100, 3),
                "signal": "BUY" if s.predicted_return > 0.001 else ("SELL" if s.predicted_return < -0.001 else "HOLD"),
                "elapsed_ms": s.elapsed_ms,
            }
            for s in signals
        ],
        "metadata": {"warning": "Research forecast only; not trading advice."},
    }


def _do_fetch_a_stock(payload: dict) -> dict:
    """Fetch real A-share OHLCV data."""
    from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv

    rows = fetch_a_stock_ohlcv(
        symbol=payload["symbol"],
        start_date=payload.get("start_date", ""),
        end_date=payload.get("end_date", ""),
    )
    return {"ok": True, "symbol": payload["symbol"], "count": len(rows), "rows": rows}


# ---------------------------------------------------------------------------
# Daemon protocol (FinceptTerminal PythonRunner compatible)
# ---------------------------------------------------------------------------

def _daemon_read_frame(stream):
    """Read one length-prefixed frame. Returns bytes payload, or None on EOF."""
    header = b""
    while len(header) < 4:
        chunk = stream.read(4 - len(header))
        if not chunk:
            return None
        header += chunk
    n = int.from_bytes(header, byteorder="big", signed=False)
    if n == 0 or n > 64 * 1024 * 1024:  # sanity: cap frames at 64 MB
        return None
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _daemon_write_frame(stream, data_bytes):
    """Write one length-prefixed frame. `data_bytes` must be bytes."""
    n = len(data_bytes)
    stream.write(n.to_bytes(4, byteorder="big", signed=False))
    stream.write(data_bytes)
    stream.flush()


def _daemon_dispatch(action: str, payload: dict) -> dict:
    """Run one action and return the raw result object."""
    if action == "forecast":
        return _do_forecast(payload)
    if action == "batch_forecast":
        return _do_batch_forecast(payload)
    if action == "fetch_a_stock":
        return _do_fetch_a_stock(payload)
    return {"error": f"Unknown action: {action}"}


def run_daemon():
    """Main daemon loop — read frame, dispatch, write frame, repeat."""
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    # Ready marker
    try:
        ready = json.dumps({"ready": True, "pid": os.getpid()}).encode("utf-8")
        _daemon_write_frame(stdout, ready)
    except Exception:
        pass

    while True:
        frame = _daemon_read_frame(stdin)
        if frame is None:
            break  # EOF — exit
        try:
            req = json.loads(frame.decode("utf-8"))
        except Exception as e:
            err = {"id": 0, "ok": False, "error": f"bad request JSON: {e}"}
            _daemon_write_frame(stdout, json.dumps(err).encode("utf-8"))
            continue

        req_id = req.get("id", 0)
        action = req.get("action", "")
        if action == "shutdown":
            resp = {"id": req_id, "ok": True, "result": {"shutdown": True}}
            _daemon_write_frame(stdout, json.dumps(resp).encode("utf-8"))
            break

        try:
            result = _daemon_dispatch(action, req.get("payload"))
            resp = {"id": req_id, "ok": True, "result": result}
        except Exception as e:
            resp = {"id": req_id, "ok": False, "error": str(e)}
        try:
            _daemon_write_frame(stdout, json.dumps(resp).encode("utf-8"))
        except Exception:
            break


# ---------------------------------------------------------------------------
# CLI mode (direct invocation)
# ---------------------------------------------------------------------------

def main():
    """CLI entry point: read JSON from stdin or --input, write to stdout or --output."""
    import argparse

    parser = argparse.ArgumentParser(description="Kronos Forecast Bridge")
    parser.add_argument("--input", "-i", help="Input JSON file path")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode (PythonRunner)")
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
        return

    # CLI mode: read input
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = json.load(sys.stdin)

    # Determine action from payload
    action = payload.pop("_action", "forecast")

    try:
        result = _daemon_dispatch(action, payload)
    except Exception as e:
        result = {"ok": False, "error": str(e)}

    # Write output
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
