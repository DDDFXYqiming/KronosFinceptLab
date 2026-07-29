from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace


def test_baostock_sessions_are_serialized_across_source_instances(monkeypatch):
    from kronos_fincept.data_sources.baostock_source import BaoStockSource

    state = {"active": 0, "max_active": 0, "logins": 0, "logouts": 0}
    state_lock = threading.Lock()

    class FakeResult:
        error_code = "0"
        error_msg = ""
        fields = []

        def __init__(self):
            self._read = False

        def next(self):
            if self._read:
                return False
            self._read = True
            return True

        def get_row_data(self):
            return [
                "2026-07-29",
                "sz.300308",
                "10",
                "11",
                "9",
                "10.5",
                "10",
                "1000",
                "10000",
                "2",
                "1",
                "1",
                "5",
                "0",
            ]

    def login():
        with state_lock:
            state["logins"] += 1
        return SimpleNamespace(error_code="0", error_msg="")

    def logout():
        with state_lock:
            state["logouts"] += 1
        return SimpleNamespace(error_code="0", error_msg="")

    def query_history_k_data_plus(**kwargs):
        with state_lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.04)
        with state_lock:
            state["active"] -= 1
        return FakeResult()

    fake_baostock = SimpleNamespace(
        login=login,
        logout=logout,
        query_history_k_data_plus=query_history_k_data_plus,
    )
    monkeypatch.setitem(sys.modules, "baostock", fake_baostock)

    sources = [BaoStockSource(), BaoStockSource()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda source: source.fetch(
                    "stock_zh_a_hist",
                    symbol="300308",
                    start_date="20260701",
                    end_date="20260729",
                    adjust="qfq",
                ),
                sources,
            )
        )

    assert all(result["success"] for result in results)
    assert state["max_active"] == 1
    assert state["logins"] == 2
    assert state["logouts"] == 2


def test_missing_market_data_overrides_hallucinated_directional_report():
    from kronos_fincept import agent

    report = agent._normalize_report(
        {
            "conclusion": "三只股票年内将延续强势。",
            "short_term_prediction": "继续上涨。",
            "technical": "均线多头排列，MACD 金叉，突破前高后回踩确认。",
            "fundamentals": "基本面较好。",
            "risk": "风险可控。",
            "recommendation": "逢低加仓",
            "confidence": 0.75,
            "risk_level": "中",
            "asset_reports": [
                {
                    "symbol": "300308",
                    "market": "cn",
                    "conclusion": "中际旭创延续强势。",
                    "technical": "均线多头排列，MACD 金叉。",
                    "recommendation": "加仓",
                    "confidence": 0.8,
                }
            ],
        }
    )
    contexts = [
        {
            "symbol": "300308",
            "market": "cn",
            "name": "中际旭创",
            "online_research": {"enabled": True, "results": [{"title": "一季报增长"}]},
        }
    ]

    guarded = agent._enforce_report_data_quality(report, contexts)

    assert guarded["recommendation"] == "数据不足，暂不判断"
    assert guarded["confidence"] <= 0.25
    assert "行情数据缺失" in guarded["conclusion"]
    asset_report = guarded["asset_reports"][0]["report"]
    assert "无有效K线" in asset_report["technical"]
    assert "MACD 金叉" not in asset_report["technical"]
    assert asset_report["recommendation"] == "数据不足，暂不判断"


def test_deterministic_technical_summary_reflects_actual_indicator_direction():
    from kronos_fincept import agent

    asset = {
        "market_data": {
            "current_price": 100.0,
            "price_change_1d": -4.0,
            "price_change_1w": -10.0,
        },
        "technical_indicators": {
            "sma_20": {"values": [110.0]},
            "sma_50": {"values": [120.0]},
            "rsi_14": {"values": [35.0]},
            "macd": {"macd_line": [-2.0], "signal_line": [-1.0]},
        },
    }

    summary = agent._deterministic_technical_summary(asset)

    assert "低于20日均线" in summary
    assert "低于50日均线" in summary
    assert "MACD线低于信号线" in summary
    assert "近一周-10.00%" in summary
    assert "多头排列" not in summary


def test_quality_guard_rejects_bullish_recommendation_when_tools_are_bearish():
    from kronos_fincept import agent

    report = agent._normalize_report(
        {
            "conclusion": "中际旭创年内走势最强。",
            "technical": "均线多头排列。",
            "recommendation": "增持",
            "confidence": 0.8,
            "asset_reports": [
                {
                    "symbol": "300308",
                    "market": "cn",
                    "conclusion": "延续强势。",
                    "technical": "MACD金叉。",
                    "recommendation": "增持",
                    "confidence": 0.8,
                }
            ],
        }
    )
    contexts = [
        {
            "symbol": "300308",
            "market": "cn",
            "name": "中际旭创",
            "market_data": {
                "current_price": 951.0,
                "latest_timestamp": "2026-07-29T00:00:00Z",
                "price_change_1d": 4.74,
                "price_change_1w": -11.33,
                "data_points": 362,
            },
            "technical_indicators": {
                "sma_20": {"values": [1085.36]},
                "sma_50": {"values": [1153.72]},
                "rsi_14": {"values": [36.69]},
                "macd": {"macd_line": -48.14, "signal_line": -30.58},
            },
            "risk_metrics": {"volatility": 0.71, "max_drawdown": 0.39, "var_95": 0.05},
            "kronos_prediction": {"forecast": [{"close": 925.42}]},
        }
    ]

    guarded = agent._enforce_report_data_quality(
        report,
        contexts,
        question="预测中际旭创今年年内未来走势",
    )

    assert "增持" not in guarded["recommendation"]
    assert "短期不支持看多" in guarded["conclusion"]
    assert guarded["confidence"] <= 0.55
    asset_report = guarded["asset_reports"][0]["report"]
    assert "增持" not in asset_report["recommendation"]
    assert "Kronos 5 日" in asset_report["conclusion"]


def test_evidence_graph_excludes_failed_tools_and_uses_valid_asset_coverage():
    from kronos_fincept import agent

    result = agent.AgentAnalysisResult(
        ok=True,
        question="测试",
        symbol="300308",
        symbols=["300308"],
        market="cn",
        report={"conclusion": "数据不足。", "recommendation": "观察"},
        final_report="数据不足。",
        recommendation="观察",
        confidence=0.2,
        risk_level="未知",
        current_price=None,
        risk_metrics=None,
        kronos_prediction=None,
        tool_calls=[
            agent.AgentToolCall(name="market_data", status="failed", summary="行情获取失败。"),
            agent.AgentToolCall(name="online_research", status="completed", summary="网页结果 3 条。"),
        ],
        steps=[],
        timestamp="2026-07-30T00:00:00Z",
        asset_results=[
            {
                "symbol": "300308",
                "tool_status": {
                    "market_data": "failed",
                    "financial_data": "skipped",
                    "technical_indicators": "skipped",
                    "risk_metrics": "failed",
                    "kronos_prediction": "failed",
                    "online_research": "completed",
                },
            }
        ],
    )

    evidence, _, breakdown = agent._build_evidence_graph_payload(result)

    assert all(item["title"] != "market_data" for item in evidence["items"])
    assert any(item["title"] == "online_research" for item in evidence["items"])
    assert breakdown["data_coverage"] == round(1 / 6, 4)
    assert breakdown["forecast_support"] == 0.0
    assert breakdown["risk_support"] == 0.0
