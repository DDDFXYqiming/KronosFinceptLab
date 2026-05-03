import sys
import types

import pandas as pd
from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app


def test_v1021_global_market_fetch_data_normalizes_hk_symbol_and_dates(monkeypatch):
    from kronos_fincept.financial.global_market import GlobalMarketSource

    calls = []

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            calls.append({"symbol": self.symbol, **kwargs})
            return pd.DataFrame(
                {
                    "Open": [10.0],
                    "High": [10.8],
                    "Low": [9.8],
                    "Close": [10.5],
                    "Volume": [123456],
                },
                index=pd.to_datetime(["2026-04-30"]),
            )

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=FakeTicker))

    source = GlobalMarketSource()
    rows = source.fetch_data("HK1810", "20250101", "20260430", market="hk")

    assert calls == [
        {
            "symbol": "1810.HK",
            "start": "2025-01-01",
            "end": "2026-05-01",
            "interval": "1d",
        }
    ]
    assert rows == [
        {
            "timestamp": "2026-04-30T00:00:00",
            "open": 10.0,
            "high": 10.8,
            "low": 9.8,
            "close": 10.5,
            "volume": 123456.0,
            "amount": 0.0,
        }
    ]


def test_v1021_global_data_route_uses_current_global_market_source(monkeypatch):
    from kronos_fincept.financial.global_market import GlobalMarketSource

    captured = {}

    def fake_fetch_data(self, symbol, start_date=None, end_date=None, *, market="auto", interval="1d", period="1y"):
        captured.update(
            {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "market": market,
                "interval": interval,
                "period": period,
            }
        )
        return [
            {
                "timestamp": "2026-04-30",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000.0,
                "amount": 0.0,
            }
        ]

    monkeypatch.setattr(GlobalMarketSource, "fetch_data", fake_fetch_data)

    client = TestClient(create_app())
    response = client.get("/api/data/global/HK1810?market=hk&start_date=20250101&end_date=20260430")

    assert response.status_code == 200
    assert captured == {
        "symbol": "HK1810",
        "start_date": "20250101",
        "end_date": "20260430",
        "market": "hk",
        "interval": "1d",
        "period": "1y",
    }
    payload = response.json()
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["rows"][0]["close"] == 10.5


def test_v1021_deepseek_report_prompt_serializes_non_plain_context():
    from kronos_fincept.agent import _serialize_deepseek_user_prompt

    payload = _serialize_deepseek_user_prompt(
        {
            "question": "测试",
            "trusted_project_context": {
                "timestamp": pd.Timestamp("2026-05-03 17:03:16"),
                "nan_value": float("nan"),
                "numpy_like": pd.Series([1]).iloc[0],
            },
        }
    )

    assert payload is not None
    assert "2026-05-03T17:03:16" in payload
    assert '"nan_value": null' in payload
    assert '"numpy_like": 1' in payload
