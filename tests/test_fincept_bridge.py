"""Integration tests simulating FinceptTerminal PythonRunner calls.

PythonRunner runs scripts as subprocesses via QProcess with:
- PYTHONIOENCODING=utf-8
- PYTHONPATH=<scripts_dir>
- stdout captured as JSON
- stderr captured for error reporting
- exit code checked for success/failure

These tests reproduce that calling convention.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_SCRIPT = ROOT / "integrations" / "fincept_terminal" / "scripts" / "kronos_forecast.py"


def _python_env() -> dict[str, str]:
    """Simulate FinceptTerminal's PythonRunner environment."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")
    return env


def _run_bridge_stdin(request: dict) -> subprocess.CompletedProcess:
    """Run bridge script with stdin JSON (PythonRunner default mode)."""
    return subprocess.run(
        [sys.executable, str(BRIDGE_SCRIPT)],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        env=_python_env(),
        timeout=30,
    )


def _run_bridge_file(request: dict, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run bridge script with --input file (alternative mode)."""
    input_file = tmp_path / "request.json"
    input_file.write_text(json.dumps(request), encoding="utf-8")
    output_file = tmp_path / "forecast.json"
    return subprocess.run(
        [sys.executable, str(BRIDGE_SCRIPT), "--input", str(input_file), "--output", str(output_file)],
        text=True,
        capture_output=True,
        env=_python_env(),
        timeout=30,
    )


class TestPythonRunnerStdinMode:
    """Simulate PythonRunner stdin-based script invocation."""

    def test_dry_run_forecast_returns_json_on_stdout(self):
        request = {
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "pred_len": 2,
            "dry_run": True,
            "rows": [
                {"timestamp": "2026-04-29T00:00:00Z", "open": 100, "high": 110, "low": 90, "close": 105},
                {"timestamp": "2026-04-29T01:00:00Z", "open": 105, "high": 112, "low": 100, "close": 108},
            ],
        }
        proc = _run_bridge_stdin(request)
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert payload["symbol"] == "BTC/USDT"
        assert len(payload["forecast"]) == 2

    def test_error_returns_nonzero_exit_code(self):
        request = {
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "pred_len": 2,
            "dry_run": True,
            "rows": [
                {"timestamp": "2026-04-29T00:00:00Z", "open": 100, "high": 99, "low": 90, "close": 105},
            ],
        }
        proc = _run_bridge_stdin(request)
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False
        assert "error" in payload

    def test_stdout_is_always_valid_json(self):
        """Even on error, stdout must be parseable JSON (PythonRunner requirement)."""
        request = {"invalid": True}
        proc = _run_bridge_stdin(request)
        payload = json.loads(proc.stdout)
        assert "ok" in payload

    def test_stderr_is_clean_on_success(self):
        request = {
            "symbol": "ETH/USDT",
            "timeframe": "5m",
            "pred_len": 1,
            "dry_run": True,
            "rows": [
                {"timestamp": "2026-04-29T00:00:00Z", "open": 100, "high": 110, "low": 90, "close": 105},
            ],
        }
        proc = _run_bridge_stdin(request)
        assert proc.returncode == 0
        # stderr should be empty or contain only non-critical warnings
        assert "Traceback" not in proc.stderr
        assert "Error" not in proc.stderr

    def test_sampling_params_passthrough(self):
        request = {
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "pred_len": 1,
            "dry_run": True,
            "temperature": 0.5,
            "top_p": 0.95,
            "sample_count": 3,
            "max_context": 256,
            "rows": [
                {"timestamp": "2026-04-29T00:00:00Z", "open": 100, "high": 110, "low": 90, "close": 105},
                {"timestamp": "2026-04-29T01:00:00Z", "open": 105, "high": 112, "low": 100, "close": 108},
            ],
        }
        proc = _run_bridge_stdin(request)
        assert proc.returncode == 0
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True


class TestPythonRunnerFileMode:
    """Simulate PythonRunner --input/--output file-based invocation."""

    def test_file_mode_returns_json(self, tmp_path):
        request = {
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "pred_len": 2,
            "dry_run": True,
            "rows": [
                {"timestamp": "2026-04-29T00:00:00Z", "open": 100, "high": 110, "low": 90, "close": 105},
                {"timestamp": "2026-04-29T01:00:00Z", "open": 105, "high": 112, "low": 100, "close": 108},
            ],
        }
        proc = _run_bridge_file(request, tmp_path)
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        output_file = tmp_path / "forecast.json"
        assert output_file.exists()
        payload = json.loads(output_file.read_text(encoding="utf-8"))
        assert payload["ok"] is True
        assert len(payload["forecast"]) == 2


class TestBridgeStandaloneExecution:
    """Test bridge script as a standalone executable (no package install needed)."""

    def test_bridge_script_is_executable(self):
        """Verify the bridge script can be called directly."""
        assert BRIDGE_SCRIPT.exists()
        proc = subprocess.run(
            [sys.executable, str(BRIDGE_SCRIPT), "--help"],
            text=True,
            capture_output=True,
            env=_python_env(),
            timeout=10,
        )
        # --help should exit 0 and show usage
        assert proc.returncode == 0
        assert "forecast" in proc.stdout.lower() or "kronos" in proc.stdout.lower()

    def test_bridge_script_missing_input_exits_nonzero(self):
        """If no input is provided, should exit with error."""
        proc = subprocess.run(
            [sys.executable, str(BRIDGE_SCRIPT)],
            input="",
            text=True,
            capture_output=True,
            env=_python_env(),
            timeout=10,
        )
        assert proc.returncode != 0
