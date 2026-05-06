from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from kronos_fincept.macro import MacroQuery
from kronos_fincept.macro.providers import digital_oracle


def _option_frame(rows: list[dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_v1082_yfinance_options_returns_structured_volatility_signals() -> None:
    class FakeTicker:
        options = ("2026-06-19", "2026-07-17")

        def history(self, period: str):
            return pd.DataFrame({"Close": [99.5, 100.0]})

        def option_chain(self, expiration: str):
            if expiration == "2026-06-19":
                return SimpleNamespace(
                    calls=_option_frame(
                        [
                            {"strike": 95.0, "impliedVolatility": 0.25, "openInterest": 80, "volume": 20},
                            {"strike": 100.0, "impliedVolatility": 0.20, "openInterest": 140, "volume": 30},
                            {"strike": 105.0, "impliedVolatility": 0.22, "openInterest": 60, "volume": 10},
                        ]
                    ),
                    puts=_option_frame(
                        [
                            {"strike": 95.0, "impliedVolatility": 0.28, "openInterest": 70, "volume": 25},
                            {"strike": 100.0, "impliedVolatility": 0.24, "openInterest": 110, "volume": 35},
                            {"strike": 105.0, "impliedVolatility": 0.26, "openInterest": 90, "volume": 20},
                        ]
                    ),
                )
            return SimpleNamespace(
                calls=_option_frame([{"strike": 100.0, "impliedVolatility": 0.31, "openInterest": 10, "volume": 1}]),
                puts=_option_frame([{"strike": 100.0, "impliedVolatility": 0.33, "openInterest": 10, "volume": 1}]),
            )

    class FakeYFinance:
        @staticmethod
        def Ticker(symbol: str):
            assert symbol == "AAPL"
            return FakeTicker()

    signals = digital_oracle.YFinanceProvider(lambda: FakeYFinance()).fetch_signals(
        MacroQuery("AAPL options", symbols=("AAPL",), limit=10)
    )

    by_type = {signal.signal_type: signal for signal in signals}

    assert {
        "options_atm_iv",
        "options_skew_proxy",
        "options_iv_term_structure",
        "options_put_call_open_interest",
        "options_put_call_volume",
        "options_max_pain",
    } <= set(by_type)
    assert by_type["options_atm_iv"].value == pytest.approx(0.22)
    assert by_type["options_skew_proxy"].value == pytest.approx(0.06)
    assert by_type["options_iv_term_structure"].metadata["next_expiration"] == "2026-07-17"
    assert by_type["options_put_call_open_interest"].metadata["data_quality"] == "yfinance_options_chain"


def test_v1082_fear_greed_falls_back_to_vix_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_json(url: str, **kwargs):
        if "fearandgreed" in url:
            raise RuntimeError("cnn unavailable")
        assert "%5EVIX" in url
        return {
            "chart": {
                "result": [
                    {
                        "timestamp": [1777600000, 1778040000],
                        "indicators": {"quote": [{"close": [12.0, 15.0]}]},
                    }
                ]
            }
        }

    monkeypatch.setattr(digital_oracle, "_get_json", fake_get_json)

    signals = digital_oracle.FearGreedProvider().fetch_signals(MacroQuery("黄金风险偏好"))

    assert len(signals) == 1
    assert signals[0].signal_type == "vix_fear_proxy"
    assert signals[0].value == pytest.approx(0.25)
    assert signals[0].metadata["data_quality"] == "fallback_yahoo_chart_vix"


def test_v1082_deribit_returns_crypto_options_and_futures_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_json(url: str, **kwargs):
        params = kwargs.get("params") or {}
        if params.get("kind") == "option":
            return {
                "result": [
                    {
                        "instrument_name": "BTC-26JUN26-90000-C",
                        "mark_iv": 50.0,
                        "underlying_price": 100000.0,
                    },
                    {
                        "instrument_name": "BTC-26JUN26-90000-P",
                        "mark_iv": 62.0,
                        "underlying_price": 100000.0,
                    },
                    {
                        "instrument_name": "BTC-26SEP26-100000-C",
                        "mark_iv": 55.0,
                        "underlying_price": 100000.0,
                    },
                    {
                        "instrument_name": "BTC-26SEP26-105000-C",
                        "mark_iv": 50.0,
                        "underlying_price": 100000.0,
                    },
                    {
                        "instrument_name": "BTC-26SEP26-100000-P",
                        "mark_iv": 57.0,
                        "underlying_price": 100000.0,
                    },
                ]
            }
        if params.get("kind") == "future":
            return {
                "result": [
                    {"instrument_name": "BTC-PERPETUAL", "mark_price": 100000.0, "index_price": 100000.0},
                    {"instrument_name": "BTC-26JUN26", "mark_price": 102000.0, "index_price": 100000.0},
                ]
            }
        raise AssertionError("unexpected request")

    monkeypatch.setattr(digital_oracle, "_get_json", fake_get_json)

    signals = digital_oracle.DeribitProvider().fetch_signals(MacroQuery("BTC options and futures", limit=10))
    by_type = {signal.signal_type: signal for signal in signals}

    assert {"deribit_atm_iv", "deribit_skew_proxy", "deribit_iv_term_structure", "crypto_futures_basis"} <= set(
        by_type
    )
    assert by_type["deribit_atm_iv"].metadata["currency"] == "BTC"
    assert by_type["deribit_skew_proxy"].value == pytest.approx(0.12)
    assert by_type["crypto_futures_basis"].value == pytest.approx(0.02)
