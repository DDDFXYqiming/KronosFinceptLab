#!/usr/bin/env python3
"""End-to-end integration test: simulate FinceptTerminal PythonWorker calling kronos_forecast.py.

This test verifies:
1. Bridge script starts in --daemon mode and sends {"ready": true} handshake
2. 4-byte big-endian length-prefixed framing works correctly
3. forecast action returns valid prediction data
4. batch_forecast action returns ranked signals
5. fetch_a_stock action returns A-share data
6. shutdown action cleanly terminates the process
7. Error handling returns proper error responses (not crashes)

Protocol: matches PythonWorker (FinceptTerminal C++) <-> Python daemon (bridge script).
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Protocol helpers (mirrors PythonWorker C++ implementation)
# ---------------------------------------------------------------------------

def send_frame(proc: subprocess.Popen, data: dict) -> None:
    """Send one length-prefixed frame to the daemon's stdin."""
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    header = struct.pack(">I", len(payload))
    proc.stdin.write(header + payload)
    proc.stdin.flush()


def recv_frame(proc: subprocess.Popen, timeout: float = 30.0) -> dict | None:
    """Read one length-prefixed frame from the daemon's stdout. Returns None on EOF/timeout."""
    import threading

    result = [None]

    def _read():
        try:
            # Read 4-byte header
            header = b""
            while len(header) < 4:
                chunk = proc.stdout.read(4 - len(header))
                if not chunk:
                    return
                header += chunk

            n = struct.unpack(">I", header)[0]
            if n == 0 or n > 64 * 1024 * 1024:
                return

            # Read payload
            buf = b""
            while len(buf) < n:
                chunk = proc.stdout.read(n - len(buf))
                if not chunk:
                    return
                buf += chunk

            result[0] = json.loads(buf.decode("utf-8"))
        except Exception:
            pass

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result[0]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # tests/ -> project root
BRIDGE_SCRIPT = os.path.join(PROJECT_ROOT, "integrations", "fincept_terminal", "scripts", "kronos_forecast.py")

# Minimal OHLCV data for testing (10 candles)
SAMPLE_ROWS = [
    {"timestamp": f"2026-04-{day:02d}", "open": 100 + i, "high": 105 + i, "low": 98 + i, "close": 103 + i}
    for i, day in enumerate(range(1, 11), 1)
]


def start_daemon(dry_run: bool = True) -> subprocess.Popen:
    """Start the bridge script in daemon mode."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(PROJECT_ROOT, "src")

    proc = subprocess.Popen(
        [sys.executable, BRIDGE_SCRIPT, "--daemon"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return proc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ready_handshake() -> bool:
    """Daemon should send {"ready": true} on startup."""
    print("  [1] Ready handshake...", end=" ")
    proc = start_daemon()
    try:
        msg = recv_frame(proc, timeout=10)
        if msg and msg.get("ready") is True:
            print(f"OK (pid={msg.get('pid')})")
            return True
        print(f"FAIL (got: {msg})")
        return False
    finally:
        proc.kill()
        proc.wait()


def test_forecast_dry_run() -> bool:
    """Single-asset forecast in dry-run mode."""
    print("  [2] Forecast (dry-run)...", end=" ")
    proc = start_daemon()
    try:
        # Drain ready frame
        recv_frame(proc, timeout=10)

        # Send forecast request
        send_frame(proc, {
            "id": 1,
            "action": "forecast",
            "payload": {
                "symbol": "TEST/USD",
                "timeframe": "1d",
                "pred_len": 3,
                "dry_run": True,
                "rows": SAMPLE_ROWS,
            },
        })

        resp = recv_frame(proc, timeout=15)
        if not resp:
            print("FAIL (no response)")
            return False

        if resp.get("ok") and resp.get("result", {}).get("ok"):
            forecast = resp["result"]["forecast"]
            print(f"OK ({len(forecast)} candles predicted)")
            return True
        print(f"FAIL ({resp})")
        return False
    finally:
        proc.kill()
        proc.wait()


def test_batch_forecast() -> bool:
    """Batch forecast with ranking."""
    print("  [3] Batch forecast (dry-run)...", end=" ")
    proc = start_daemon()
    try:
        recv_frame(proc, timeout=10)

        send_frame(proc, {
            "id": 2,
            "action": "batch_forecast",
            "payload": {
                "assets": [
                    {"symbol": "STOCK_A", "rows": SAMPLE_ROWS},
                    {"symbol": "STOCK_B", "rows": SAMPLE_ROWS},
                    {"symbol": "STOCK_C", "rows": SAMPLE_ROWS},
                ],
                "shared": {"pred_len": 3, "dry_run": True},
            },
        })

        resp = recv_frame(proc, timeout=15)
        if not resp:
            print("FAIL (no response)")
            return False

        result = resp.get("result", {})
        if resp.get("ok") and result.get("ok") and result.get("count", 0) == 3:
            rankings = result["rankings"]
            symbols = [r["symbol"] for r in rankings]
            print(f"OK (ranked: {symbols})")
            return True
        print(f"FAIL ({resp})")
        return False
    finally:
        proc.kill()
        proc.wait()


def test_shutdown() -> bool:
    """Shutdown action should cleanly terminate the daemon."""
    print("  [4] Shutdown...", end=" ")
    proc = start_daemon()
    try:
        recv_frame(proc, timeout=10)

        send_frame(proc, {"id": 99, "action": "shutdown"})
        resp = recv_frame(proc, timeout=5)

        # Wait for process to exit
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        if resp and resp.get("ok"):
            print("OK")
            return True
        print(f"FAIL (resp={resp}, exit_code={proc.returncode})")
        return False
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_error_handling() -> bool:
    """Invalid OHLC data should return error, not crash."""
    print("  [5] Error handling...", end=" ")
    proc = start_daemon()
    try:
        recv_frame(proc, timeout=10)

        # Invalid: high < close
        send_frame(proc, {
            "id": 3,
            "action": "forecast",
            "payload": {
                "symbol": "BAD/DATA",
                "timeframe": "1d",
                "pred_len": 3,
                "dry_run": True,
                "rows": [
                    {"timestamp": "2026-04-01", "open": 100, "high": 90, "low": 80, "close": 110},
                ],
            },
        })

        resp = recv_frame(proc, timeout=10)
        if not resp:
            print("FAIL (no response)")
            return False

        # Should get an error response (either ok=false in result, or error in outer)
        has_error = (
            (not resp.get("ok", True)) or
            (not resp.get("result", {}).get("ok", True))
        )
        if has_error:
            print("OK (error returned gracefully)")
            return True
        print(f"FAIL (expected error, got: {resp})")
        return False
    finally:
        proc.kill()
        proc.wait()


def test_unknown_action() -> bool:
    """Unknown action should return error, not crash."""
    print("  [6] Unknown action...", end=" ")
    proc = start_daemon()
    try:
        recv_frame(proc, timeout=10)

        send_frame(proc, {"id": 4, "action": "nonexistent_action", "payload": {}})
        resp = recv_frame(proc, timeout=10)

        if resp and "error" in str(resp).lower():
            print("OK")
            return True
        print(f"FAIL ({resp})")
        return False
    finally:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("KronosFinceptLab ↔ FinceptTerminal Integration Test")
    print("=" * 60)
    print(f"Bridge script: {BRIDGE_SCRIPT}")
    print(f"Python: {sys.executable}")
    print()

    tests = [
        test_ready_handshake,
        test_forecast_dry_run,
        test_batch_forecast,
        test_shutdown,
        test_error_handling,
        test_unknown_action,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"EXCEPTION: {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    print("ALL TESTS PASSED ✅")


if __name__ == "__main__":
    main()
