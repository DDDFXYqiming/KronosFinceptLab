"""Unit tests for Phase B — Click CLI layer.

Tests cover:
- CLI group structure and help text
- Forecast command (dry-run, JSON/table output)
- Batch command (dry-run)
- Data fetch/search (mocked AkShare)
- Backtest ranking (dry-run, mocked data)
- Serve command (just invocation check)
- Error handling (missing args, bad input)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kronos_fincept.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


# ── CLI structure tests ───────────────────────────────────

class TestCLIStructure:
    def test_cli_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "KronosFinceptLab" in result.output
        assert "forecast" in result.output
        assert "batch" in result.output
        assert "data" in result.output
        assert "backtest" in result.output
        assert "serve" in result.output

    def test_forecast_help(self, runner):
        result = runner.invoke(cli, ["forecast", "--help"])
        assert result.exit_code == 0
        assert "--symbol" in result.output
        assert "--pred-len" in result.output
        assert "--dry-run" in result.output

    def test_batch_help(self, runner):
        result = runner.invoke(cli, ["batch", "--help"])
        assert result.exit_code == 0
        assert "--symbols" in result.output

    def test_data_help(self, runner):
        result = runner.invoke(cli, ["data", "--help"])
        assert result.exit_code == 0
        assert "fetch" in result.output
        assert "search" in result.output

    def test_backtest_help(self, runner):
        result = runner.invoke(cli, ["backtest", "--help"])
        assert result.exit_code == 0
        assert "ranking" in result.output

    def test_serve_help(self, runner):
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output


# ── Forecast command tests ────────────────────────────────

class TestForecastCommand:
    def test_forecast_missing_symbol(self, runner):
        result = runner.invoke(cli, ["forecast"])
        assert result.exit_code != 0
        assert "Error" in result.stderr or "Error" in result.output or "required" in result.stderr.lower()

    def test_forecast_dry_run_json(self, runner):
        """Test forecast with --input (pre-built JSON) and --dry-run."""
        import json
        import tempfile
        import os

        # Build a minimal request file
        rows = []
        for i in range(60):
            rows.append({
                "timestamp": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
                "open": 100.0 + i * 0.1,
                "high": 100.5 + i * 0.1,
                "low": 99.5 + i * 0.1,
                "close": 100.2 + i * 0.1,
                "volume": 1000000,
                "amount": 100000000,
            })
        payload = {
            "symbol": "600519",
            "timeframe": "1d",
            "pred_len": 5,
            "rows": rows,
            "dry_run": True,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            f.flush()
            tmp_path = f.name

        try:
            result = runner.invoke(cli, ["forecast", "--input", tmp_path])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["ok"] is True
            assert len(data["forecast"]) == 5
        finally:
            os.unlink(tmp_path)

    def test_forecast_dry_run_table(self, runner):
        """Test forecast with table output."""
        import json
        import tempfile
        import os

        rows = []
        for i in range(60):
            rows.append({
                "timestamp": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
                "open": 100.0 + i * 0.1,
                "high": 100.5 + i * 0.1,
                "low": 99.5 + i * 0.1,
                "close": 100.2 + i * 0.1,
                "volume": 1000000,
                "amount": 100000000,
            })
        payload = {
            "symbol": "600519",
            "timeframe": "1d",
            "pred_len": 3,
            "rows": rows,
            "dry_run": True,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            f.flush()
            tmp_path = f.name

        try:
            result = runner.invoke(cli, ["--output", "table", "forecast", "--input", tmp_path])
            assert result.exit_code == 0
            assert "600519" in result.output
        finally:
            os.unlink(tmp_path)


# ── Batch command tests ───────────────────────────────────

class TestBatchCommand:
    def test_batch_dry_run(self, runner):
        """Test batch with mocked AkShare data."""
        from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv

        mock_rows = []
        for i in range(60):
            mock_rows.append({
                "timestamp": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
                "open": 100.0 + i * 0.1,
                "high": 100.5 + i * 0.1,
                "low": 99.5 + i * 0.1,
                "close": 100.2 + i * 0.1,
                "volume": 1000000,
                "amount": 100000000,
            })

        with patch("kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv", return_value=mock_rows):
            result = runner.invoke(cli, ["batch", "--symbols", "600519,000858",
                                          "--pred-len", "5", "--dry-run"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["rankings"]) == 2


# ── Data command tests ────────────────────────────────────

class TestDataCommand:
    def test_data_fetch_json(self, runner):
        """Test data fetch with mocked AkShare."""
        mock_rows = [
            {"timestamp": "2026-01-02T00:00:00Z", "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.5, "volume": 1000000, "amount": 100000000},
        ]
        with patch("kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv", return_value=mock_rows):
            result = runner.invoke(cli, ["data", "fetch", "--symbol", "600519",
                                          "--start", "20260101", "--end", "20260430"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["symbol"] == "600519"

    def test_data_search(self, runner):
        """Test data search with mocked AkShare."""
        import pandas as pd
        mock_df = pd.DataFrame({
            "代码": ["600519", "000858"],
            "名称": ["贵州茅台", "五粮液"],
        })
        with patch("akshare.stock_zh_a_spot_em", return_value=mock_df):
            result = runner.invoke(cli, ["data", "search", "--q", "茅台"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["ok"] is True


# ── Backtest command tests ────────────────────────────────

class TestBacktestCommand:
    def test_backtest_ranking_json(self, runner):
        """Test backtest ranking with mocked data."""
        mock_rows = []
        for i in range(200):
            mock_rows.append({
                "timestamp": f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}T00:00:00Z",
                "open": 100.0 + i * 0.05,
                "high": 100.5 + i * 0.05,
                "low": 99.5 + i * 0.05,
                "close": 100.2 + i * 0.05,
                "volume": 1000000,
                "amount": 100000000,
            })

        with patch("kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv", return_value=mock_rows):
            result = runner.invoke(cli, [
                "backtest", "ranking",
                "--symbols", "600519,000858",
                "--start", "20250101", "--end", "20260430",
                "--top-k", "1", "--dry-run",
            ])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "metrics" in data
        assert "equity_curve" in data


# ── Output format tests ───────────────────────────────────

class TestOutputFormat:
    def test_json_output_is_valid(self, runner):
        """All JSON outputs should be parseable."""
        import json
        import tempfile
        import os

        rows = []
        for i in range(60):
            rows.append({
                "timestamp": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
                "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.2,
                "volume": 1000000, "amount": 100000000,
            })
        payload = {"symbol": "600519", "timeframe": "1d", "pred_len": 3, "rows": rows, "dry_run": True}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(payload, f)
            tmp_path = f.name

        try:
            result = runner.invoke(cli, ["forecast", "--input", tmp_path])
            # Should not raise JSONDecodeError
            data = json.loads(result.output)
            assert isinstance(data, dict)
        finally:
            os.unlink(tmp_path)
