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


def test_single_asset_summary_conclusion_answers_buy_timing_directly():
    from kronos_fincept import agent

    report = agent._normalize_report(
        {
            "conclusion": "结论：招商银行当前处于短期强势上行通道，但估值已不便宜，建议观望或轻仓参与，不宜追高。",
            "recommendation": "观察",
            "confidence": 0.6,
            "risk_level": "中",
        }
    )
    contexts = [
        {
            "symbol": "600036",
            "market": "cn",
            "name": "招商银行",
            "market_data": {
                "current_price": 40.55,
                "price_change_1w": 3.44,
            },
            "technical_indicators": {
                "sma_20": {"values": [37.99]},
                "sma_50": {"values": [37.15]},
            },
            "risk_metrics": {"volatility": 0.1769},
            "kronos_prediction": {"forecast": [{"close": 40.21}]},
        }
    ]

    guarded = agent._enforce_report_data_quality(report, contexts)

    assert "建议观望或轻仓参与" in guarded["conclusion"]
    assert "不宜追高" in guarded["conclusion"]
    assert "当前建议观察" not in guarded["conclusion"]


def test_quality_guard_replaces_multi_asset_llm_technical_text_and_exposes_sources():
    from kronos_fincept import agent

    report = agent._normalize_report(
        {
            "conclusion": "两只股票短期信号不同。",
            "short_term_prediction": "模型预测略有回落。",
            "technical": "宁德时代价格低于50日均线；MACD柱线-6.23。",
            "risk": "风险中等。",
            "recommendation": "观察",
            "confidence": 0.8,
            "asset_reports": [
                {"symbol": "002594", "market": "cn", "conclusion": "比亚迪观察。"},
                {"symbol": "300750", "market": "cn", "conclusion": "宁德时代谨慎。"},
            ],
        }
    )
    contexts = [
        {
            "symbol": "002594",
            "market": "cn",
            "name": "比亚迪",
            "market_data": {"current_price": 96.2, "price_change_1w": 4.69},
            "technical_indicators": {
                "sma_20": {"values": [91.23]},
                "sma_50": {"values": [90.28]},
                "rsi_14": {"values": [60.38]},
                "macd": {"macd_line": [1.58], "signal_line": [0.99]},
            },
            "risk_metrics": {"volatility": 0.3315, "max_drawdown": 0.4138, "var_95": 0.0272},
            "kronos_prediction": {"forecast": [{"close": 94.46}]},
            "online_research": {
                "results": [
                    {"title": "有来源", "url": "https://example.test/byd"},
                    {"title": "无来源"},
                ]
            },
        },
        {
            "symbol": "300750",
            "market": "cn",
            "name": "宁德时代",
            "market_data": {"current_price": 401.88, "price_change_1w": 4.93},
            "technical_indicators": {
                "sma_20": {"values": [376.2]},
                "sma_50": {"values": [391.6]},
                "rsi_14": {"values": [55.49]},
                "macd": {"macd_line": [1.67], "signal_line": [-3.12]},
            },
            "risk_metrics": {"volatility": 0.3755, "max_drawdown": 0.2418, "var_95": 0.0317},
            "kronos_prediction": {"forecast": [{"close": 371.5}]},
            "online_research": {
                "results": [{"title": "宁德时代公告", "url": "https://example.test/catl"}]
            },
        },
    ]

    guarded = agent._enforce_report_data_quality(report, contexts)

    assert "宁德时代(300750)：最新收盘价401.88" in guarded["technical"]
    assert "价格高于50日均线(391.60)" in guarded["technical"]
    assert "低于50日均线" not in guarded["technical"]
    assert "MACD柱线-6.23" not in guarded["technical"]
    assert "。；" not in guarded["technical"]
    assert [source["url"] for source in guarded["sources"]] == [
        "https://example.test/byd",
        "https://example.test/catl",
    ]


def test_report_normalization_omits_empty_contradiction_sources():
    from kronos_fincept.agent import _normalize_report

    report = _normalize_report(
        {
            "conclusion": "结论",
            "contradictions": {
                "contradiction": "技术面偏弱，但基本面稳健",
                "sources": [
                    {"source": "", "observed_at": "2026-07-30T00:00:00Z"},
                    {"provider": "china_macro_nbs", "observed_at": "2026-07-30T00:00:00Z"},
                ],
                "observed_at": "2026-07-30T00:00:00Z",
            },
        }
    )

    assert report["contradictions"] == (
        "矛盾：技术面偏弱，但基本面稳健；"
        "来源：china_macro_nbs；时间：2026-07-30T00:00:00Z"
    )
    assert "来源：；" not in report["contradictions"]


def test_quality_guard_replaces_single_asset_llm_numbers_with_structured_facts():
    from kronos_fincept import agent

    report = agent._normalize_report(
        {
            "conclusion": "净利润108亿，PE 89倍，建议立即买入。",
            "fundamentals": "未经核验的基本面数字。",
            "recommendation": "立即买入",
            "confidence": 0.9,
        }
    )
    contexts = [
        {
            "symbol": "300308",
            "market": "cn",
            "name": "中际旭创",
            "asset_class": "equity",
            "market_data": {
                "current_price": 864.0,
                "price_change_1w": -17.44,
            },
            "technical_indicators": {
                "sma_20": {"values": [1071.41]},
                "sma_50": {"values": [1150.26]},
            },
            "financial_data": {
                "period": "2025",
                "revenue": 38_240_000_000,
                "net_income": 11_580_000_000,
            },
            "risk_metrics": {
                "volatility": 0.72,
                "max_drawdown": 0.39,
                "var_95": 0.05,
            },
            "kronos_prediction": {"forecast": [{"close": 796.0}]},
        }
    ]

    guarded = agent._enforce_report_data_quality(report, contexts)

    assert "净利润115.80亿" in guarded["fundamentals"]
    assert "108亿" not in guarded["conclusion"]
    assert "PE 89倍" not in guarded["conclusion"]
    assert guarded["recommendation"] == "中际旭创：谨慎/观望"
    assert "短期不支持看多" in guarded["conclusion"]


def test_llm_research_context_excludes_results_without_public_url():
    from kronos_fincept import agent

    compact = agent._compact_online_research_for_llm(
        {
            "enabled": True,
            "results": [
                {"title": "带来源", "url": "https://example.test/source", "snippet": "可引用"},
                {"title": "无来源", "snippet": "不能作为事实"},
                {"title": "本地路径", "url": "file:///tmp/source", "snippet": "不能作为公开来源"},
            ],
        }
    )

    assert compact["result_count"] == 3
    assert compact["cited_result_count"] == 1
    assert [item["title"] for item in compact["results"]] == ["带来源"]


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


def test_evidence_graph_binds_price_forecast_and_risk_for_each_asset():
    from kronos_fincept import agent

    assets = [
        {
            "symbol": "002594",
            "current_price": 96.2,
            "kronos_prediction": {"prediction_days": 5, "forecast": [{"close": 94.46}]},
            "risk_metrics": {"volatility": 0.33},
            "confidence": 0.7,
            "report": {"conclusion": "比亚迪短期信号分化。"},
            "tool_status": {},
        },
        {
            "symbol": "300750",
            "current_price": 401.88,
            "kronos_prediction": {"prediction_days": 5, "forecast": [{"close": 371.5}]},
            "risk_metrics": {"volatility": 0.38},
            "confidence": 0.6,
            "report": {"conclusion": "宁德时代短期不支持看多。"},
            "tool_status": {},
        },
    ]
    result = agent.AgentAnalysisResult(
        ok=True,
        question="比亚迪和宁德时代哪个技术面更看涨",
        symbol="002594",
        symbols=["002594", "300750"],
        market="cn",
        report={"conclusion": "比较完成。", "recommendation": "观察"},
        final_report="比较完成。",
        recommendation="观察",
        confidence=0.65,
        risk_level="中",
        current_price=96.2,
        risk_metrics={"volatility": 0.33},
        kronos_prediction={"forecast": [{"close": 94.46}]},
        tool_calls=[],
        steps=[],
        timestamp="2026-07-30T00:00:00Z",
        asset_results=assets,
    )

    evidence, claims, _ = agent._build_evidence_graph_payload(result)

    titles = {item["title"] for item in evidence["items"]}
    assert {"002594 当前价格", "300750 当前价格"} <= titles
    assert {"002594 Kronos 预测", "300750 Kronos 预测"} <= titles
    catl_claim = next(claim for claim in claims if "宁德时代" in claim["claim"])
    catl_items = {
        item["id"]: item
        for item in evidence["items"]
        if item.get("payload", {}).get("symbol") == "300750"
    }
    assert set(catl_claim["evidence_ids"]) == set(catl_items)
