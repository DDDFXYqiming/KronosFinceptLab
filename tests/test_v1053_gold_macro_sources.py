from __future__ import annotations

import sys
from types import SimpleNamespace

from kronos_fincept import agent as agent_module
from kronos_fincept.macro import MacroQuery
from kronos_fincept.macro.providers import digital_oracle as providers
from kronos_fincept.macro.schemas import MacroGatherResult, MacroProviderResult, MacroSignal


class _FakeCloseSeries:
    def __init__(self, values: list[float]) -> None:
        self._values = values
        self.iloc = self

    def __getitem__(self, index: int) -> float:
        return self._values[index]


class _FakeHistory:
    empty = False

    def __init__(self, closes: list[float]) -> None:
        self._closes = closes

    def __getitem__(self, column: str) -> _FakeCloseSeries:
        assert column == "Close"
        return _FakeCloseSeries(self._closes)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> bytes:
        return self._text.encode("utf-8")

    def raise_for_status(self) -> None:
        return None

    @property
    def text(self) -> str:
        return self._text

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_v1053_gold_macro_price_maps_to_gold_future_when_no_symbol() -> None:
    calls: list[str] = []

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            calls.append(symbol)

        def history(self, period: str):
            assert period == "1mo"
            return _FakeHistory([100.0, 110.0])

    class FakeYFinance:
        Ticker = FakeTicker

    signals = providers.YahooPriceProvider(yfinance_loader=lambda: FakeYFinance).fetch_signals(
        MacroQuery("现在适合买黄金吗")
    )

    assert calls == ["GC=F"]
    assert len(signals) == 1
    assert signals[0].signal_type == "price_trend_1m"
    assert signals[0].value == 0.1
    assert signals[0].metadata["symbol"] == "GC=F"


def test_v1053_cftc_gold_uses_upstream_soda_where_filter_and_net_position(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get_json(url: str, *, params=None, timeout: int = 8):
        captured["url"] = url
        captured["params"] = params
        assert url == "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
        assert params is not None
        assert "commodity_name" not in params
        assert "GOLD" in str(params.get("$where"))
        return [
            {
                "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
                "report_date_as_yyyy_mm_dd": "2026-03-04T00:00:00.000",
                "commodity_name": "GOLD",
                "open_interest_all": "550000",
                "prod_merc_positions_long_all": "80000",
                "prod_merc_positions_short_all": "195000",
                "m_money_positions_long_all": "180000",
                "m_money_positions_short_all": "45000",
            }
        ]

    monkeypatch.setattr(providers, "_get_json", fake_get_json)

    signals = providers.CftcCotProvider().fetch_signals(MacroQuery("黄金 CFTC 持仓"))

    assert captured["params"]
    assert len(signals) == 1
    assert signals[0].value == 135000
    assert signals[0].observed_at == "2026-03-04"
    assert signals[0].metadata["commodity"] == "GOLD"
    assert signals[0].metadata["open_interest"] == 550000
    assert signals[0].metadata["commercial_net"] == -115000


def test_v1053_treasury_returns_real_10y_and_breakeven_for_gold_macro(monkeypatch) -> None:
    calls: list[str] = []
    nominal_csv = "Date,2 Yr,10 Yr\n03/10/2026,3.57,4.15\n"
    real_csv = "Date,5 Yr,10 Yr,30 Yr\n03/10/2026,1.52,1.82,2.56\n"

    def fake_get(url: str, *, headers=None, timeout: int = 8):
        calls.append(str(url))
        if "type=daily_treasury_real_yield_curve" in str(url):
            return _FakeResponse(real_csv)
        if "type=daily_treasury_yield_curve" in str(url):
            return _FakeResponse(nominal_csv)
        raise AssertionError(f"unexpected Treasury URL: {url}")

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fake_get))

    signals = providers.USTreasuryProvider().fetch_signals(MacroQuery("黄金和美国实际利率"))
    by_type = {signal.signal_type: signal for signal in signals}

    assert any("type=daily_treasury_yield_curve" in url for url in calls)
    assert any("type=daily_treasury_real_yield_curve" in url for url in calls)
    assert by_type["yield_curve_10y_2y_spread"].value == 0.58
    assert by_type["real_yield_10y"].value == 1.82
    assert by_type["breakeven_10y"].value == 2.33


def test_v1053_treasury_text_fetch_prefers_requests_for_fast_csv(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeResponse:
        text = "Date,10 Yr\n05/01/2026,1.91\n"

        def raise_for_status(self) -> None:
            calls.append({"raised": False})

    def fake_get(url: str, *, headers=None, timeout: int = 8):
        calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fake_get))

    def forbidden_urlopen(*args, **kwargs):
        raise AssertionError("Treasury CSV should use the faster requests client when available")

    monkeypatch.setattr(providers.urllib.request, "urlopen", forbidden_urlopen)

    text = providers._get_text(
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all",
        params={"type": "daily_treasury_real_yield_curve"},
        timeout=4,
    )

    assert "05/01/2026" in text
    request_call = calls[0]
    assert "type=daily_treasury_real_yield_curve" in str(request_call["url"])
    assert request_call["timeout"] == 4
    assert "Mozilla/5.0" in str(request_call["headers"])



def test_v1053_agent_gold_macro_report_keeps_direct_gold_sources(monkeypatch) -> None:
    class FakeMacroManager:
        def gather(self, query, *, provider_ids=None):
            assert query.question == "现在适合买黄金吗"
            assert tuple(provider_ids or ()) == ("yahoo_price", "cftc_cot", "us_treasury")
            signals = [
                MacroSignal(
                    source="yahoo_price",
                    signal_type="price_trend_1m",
                    value=-0.028389,
                    interpretation="黄金期货 1 月价格下跌。",
                    time_horizon="short",
                    confidence=0.64,
                    metadata={"symbol": "GC=F", "label": "黄金期货"},
                ),
                MacroSignal(
                    source="cftc_cot",
                    signal_type="managed_money_net_position",
                    value=89752.0,
                    interpretation="CFTC 黄金管理基金净多头。",
                    time_horizon="medium",
                    confidence=0.66,
                    metadata={"commodity": "GOLD"},
                ),
                MacroSignal(
                    source="us_treasury",
                    signal_type="real_yield_10y",
                    value=1.91,
                    interpretation="美国 10Y 实际收益率。",
                    time_horizon="medium",
                    confidence=0.74,
                ),
            ]
            return MacroGatherResult(
                signals=signals,
                provider_results={
                    signal.source: MacroProviderResult(signal.source, "completed", [signal])
                    for signal in signals
                },
            )

    def fake_generate_report(question, context):
        macro = context["macro"]
        return (
            {
                "conclusion": "黄金宏观链路已获取直接信号。",
                "recommendation": "观察",
                "confidence": 0.6,
                "risk_level": "中",
                "macro_signals": macro["signals"],
            },
            agent_module.AgentToolCall(
                name="deepseek_synthesis",
                status="skipped",
                summary="test synthesis skipped",
                elapsed_ms=0,
            ),
        )

    monkeypatch.setattr(agent_module, "_create_macro_data_manager", lambda: FakeMacroManager())
    monkeypatch.setattr(agent_module, "_call_deepseek_macro_router", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent_module, "_generate_report", fake_generate_report)

    result = agent_module.analyze_macro_question(
        "现在适合买黄金吗",
        provider_ids=["yahoo_price", "cftc_cot", "us_treasury"],
    )

    assert result.ok is True
    assert result.tool_calls[0].status == "completed"
    signal_map = {(item["source"], item["signal_type"]): item for item in result.report["macro_signals"]}
    assert signal_map[("yahoo_price", "price_trend_1m")]["metadata"]["symbol"] == "GC=F"
    assert signal_map[("cftc_cot", "managed_money_net_position")]["metadata"]["commodity"] == "GOLD"
    assert signal_map[("us_treasury", "real_yield_10y")]["value"] == 1.91
