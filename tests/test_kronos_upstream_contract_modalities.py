"""Kronos upstream contract tests across API, CLI, and MCP.

These tests intentionally mock the heavy upstream Kronos predictor. The mock
matches the documented upstream shape: historical OHLCV(+amount) DataFrame in,
future-indexed OHLCV(+amount) DataFrame out.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from types import SimpleNamespace
from typing import Any

import pandas as pd
from click.testing import CliRunner
from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app
from kronos_fincept.predictor import ForecastResult, KronosPredictorWrapper


def _rows(n: int = 12) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": f"2026-04-{(i % 28) + 1:02d}T00:00:00Z",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
        }
        for i in range(n)
    ]


class _FakeServiceWrapper:
    instances: list["_FakeServiceWrapper"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.__class__.instances.append(self)

    def predict(self, df: pd.DataFrame, x_timestamp: pd.Series, pred_len: int) -> ForecastResult:
        assert list(df.columns) == ["open", "high", "low", "close", "volume", "amount"]
        assert len(x_timestamp) == len(df)
        assert self.kwargs["temperature"] == 0.7
        assert self.kwargs["top_k"] == 3
        assert self.kwargs["top_p"] == 0.8
        assert self.kwargs["sample_count"] == 1
        future = pd.date_range(pd.Timestamp("2026-05-01", tz="UTC"), periods=pred_len, freq="D")
        frame = pd.DataFrame(
            {
                "timestamp": future,
                "open": [120.0 + i for i in range(pred_len)],
                "high": [121.0 + i for i in range(pred_len)],
                "low": [119.0 + i for i in range(pred_len)],
                "close": [120.5 + i for i in range(pred_len)],
                "volume": [0.0] * pred_len,
                "amount": [0.0] * pred_len,
            }
        )
        return ForecastResult(frame=frame, device="cpu", elapsed_ms=1, backend="kronos")


def _patch_real_model_with_fake(monkeypatch) -> None:
    from kronos_fincept import service

    _FakeServiceWrapper.instances.clear()
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(
            kronos=SimpleNamespace(
                enable_real_model=True,
                allow_dry_run=True,
                model_id="NeoQuasar/Kronos-base",
            )
        ),
    )
    monkeypatch.setattr(service, "KronosPredictorWrapper", _FakeServiceWrapper)


def _request_payload() -> dict[str, Any]:
    return {
        "symbol": "BTC/USDT",
        "timeframe": "1d",
        "pred_len": 2,
        "rows": _rows(),
        "dry_run": False,
        "model_id": "NeoQuasar/Kronos-base",
        "temperature": 0.7,
        "top_k": 3,
        "top_p": 0.8,
        "sample_count": 1,
    }


def test_kronos_wrapper_sends_documented_predict_arguments_without_loading_model(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeUpstreamPredictor:
        def predict(self, **kwargs: Any) -> pd.DataFrame:
            captured.update(kwargs)
            y_timestamp = kwargs["y_timestamp"]
            pred_len = kwargs["pred_len"]
            return pd.DataFrame(
                {
                    "open": [10.0] * pred_len,
                    "high": [11.0] * pred_len,
                    "low": [9.0] * pred_len,
                    "close": [10.5] * pred_len,
                    "volume": [1000.0] * pred_len,
                    "amount": [10000.0] * pred_len,
                },
                index=y_timestamp,
            )

    fake = FakeUpstreamPredictor()
    wrapper = KronosPredictorWrapper(
        temperature=0.7,
        top_k=3,
        top_p=0.8,
        sample_count=2,
    )
    wrapper._resolved_device = "cpu"
    monkeypatch.setattr(wrapper, "_load", lambda: fake)

    timestamps = pd.Series(pd.date_range("2026-04-01", periods=4, freq="D", tz="UTC"))
    df = pd.DataFrame(
        {
            "open": [1.0, 2.0, 3.0, 4.0],
            "high": [2.0, 3.0, 4.0, 5.0],
            "low": [0.5, 1.5, 2.5, 3.5],
            "close": [1.5, 2.5, 3.5, 4.5],
            "volume": [10.0, 11.0, 12.0, 13.0],
            "amount": [100.0, 110.0, 120.0, 130.0],
        }
    )

    result = wrapper.predict(df=df, x_timestamp=timestamps, pred_len=2)

    assert captured["df"].equals(df)
    assert captured["x_timestamp"].equals(timestamps)
    assert len(captured["y_timestamp"]) == 2
    assert captured["pred_len"] == 2
    assert captured["T"] == 0.7
    assert captured["top_k"] == 3
    assert captured["top_p"] == 0.8
    assert captured["sample_count"] == 2
    assert captured["verbose"] is False
    assert result.backend == "kronos"
    assert list(result.frame.columns) == ["timestamp", "index", "open", "high", "low", "close", "volume", "amount"]


def test_api_forecast_uses_mocked_real_kronos_contract(monkeypatch):
    _patch_real_model_with_fake(monkeypatch)
    client = TestClient(create_app())

    response = client.post("/api/forecast", json=_request_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["metadata"]["backend"] == "kronos"
    assert len(payload["forecast"]) == 2
    assert _FakeServiceWrapper.instances[0].kwargs["max_context"] == 512


def test_click_cli_forecast_uses_mocked_real_kronos_contract(monkeypatch, tmp_path):
    from kronos_fincept.cli.main import cli

    _patch_real_model_with_fake(monkeypatch)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request_payload()), encoding="utf-8")

    result = CliRunner().invoke(cli, ["forecast", "--input", str(request_path)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["metadata"]["backend"] == "kronos"
    assert payload["forecast"][0]["timestamp"] == "D1"


def _install_fake_mcp(monkeypatch) -> None:
    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    stdio_module = types.ModuleType("mcp.server.stdio")
    types_module = types.ModuleType("mcp.types")

    class FakeServer:
        def __init__(self, name: str) -> None:
            self.name = name

        def list_tools(self):
            def decorator(fn):
                return fn
            return decorator

        def call_tool(self):
            def decorator(fn):
                return fn
            return decorator

    class FakeTool:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class FakeTextContent:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    server_module.Server = FakeServer
    stdio_module.stdio_server = lambda: None
    types_module.Tool = FakeTool
    types_module.TextContent = FakeTextContent

    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.stdio", stdio_module)
    monkeypatch.setitem(sys.modules, "mcp.types", types_module)


def test_mcp_forecast_uses_mocked_real_kronos_contract(monkeypatch):
    _install_fake_mcp(monkeypatch)
    _patch_real_model_with_fake(monkeypatch)

    module = importlib.import_module("kronos_mcp.kronos_mcp_server")
    module = importlib.reload(module)
    content = module._handle_forecast(_request_payload())[0]
    payload = json.loads(content.text)

    assert payload["ok"] is True
    assert payload["metadata"]["backend"] == "kronos"
    assert payload["forecast"][1]["close"] == 121.5
