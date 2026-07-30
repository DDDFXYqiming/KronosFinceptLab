from __future__ import annotations

from kronos_fincept import agent
from kronos_fincept.web_search import WebSearchResponse, WebSearchResult


def test_probability_scenarios_are_normalized_to_one():
    rows = agent._normalize_probability_scenarios(
        [
            {"scenario": "基准", "probability": 55, "basis": "信号中性"},
            {"scenario": "下行", "probability": 25, "basis": "风险上升"},
        ]
    )

    assert [row["probability"] for row in rows] == [0.6875, 0.3125]
    assert sum(row["probability"] for row in rows) == 1.0


def test_structured_monitoring_signal_is_the_source_of_truth():
    rows = agent._enrich_macro_monitoring_signals(
        [
            {
                "signal": "美国10Y实际收益率",
                "current_value": "模型猜测值",
                "threshold": "突破2.5%",
                "meaning": "实际利率变化影响商品估值。",
            }
        ],
        [
            {
                "source": "us_treasury",
                "signal_type": "real_yield_10y",
                "value": 2.41,
                "interpretation": "实际利率数据",
                "observed_at": "2026-07-30T00:00:00+00:00",
                "source_url": "https://example.com/treasury",
                "metadata": {"evidence_role": "structured_current"},
            }
        ],
        question="黄金现在适合买入吗",
    )

    assert rows[0]["current_value"] == 2.41
    assert rows[0]["status"] == "verified"
    assert rows[0]["provider"] == "us_treasury"
    assert rows[0]["source_url"] == "https://example.com/treasury"


def test_numeric_monitoring_signal_never_uses_anysearch(monkeypatch):
    calls: list[str] = []

    class FakeClient:
        is_configured = True

        def search(self, query: str):
            calls.append(query)
            raise AssertionError("numeric monitoring must not call AnySearch")

    monkeypatch.setattr(agent, "AnySearchClient", FakeClient)
    rows = agent._enrich_macro_monitoring_signals(
        [
            {
                "signal": "碳酸锂现货价格",
                "current_value": None,
                "threshold": "跌破某数值",
                "meaning": "价格变化影响板块趋势。",
            }
        ],
        [],
        question="A股港股锂矿上下游的所有股票最近几个月一直跌跌不休，还有救吗？",
    )

    assert rows[0]["current_value"] == "未获取"
    assert rows[0]["status"] == "unavailable"
    assert calls == []


def test_dated_anysearch_event_can_fill_qualitative_monitoring(monkeypatch):
    class FakeClient:
        is_configured = True

        def search(self, query: str):
            return WebSearchResponse(
                enabled=True,
                status="completed",
                provider="anysearch",
                query=query,
                results=[
                    WebSearchResult(
                        title="锂矿企业宣布减产",
                        url="https://example.com/lithium-cut",
                        snippet="企业公告显示将下调部分产能。",
                        source="example",
                        published_at="2026-07-30T00:00:00+00:00",
                    )
                ],
                elapsed_ms=10,
            )

    monkeypatch.setattr(agent, "AnySearchClient", FakeClient)
    rows = agent._enrich_macro_monitoring_signals(
        [
            {
                "signal": "锂矿企业减产公告",
                "current_value": None,
                "threshold": "头部企业宣布减产",
                "meaning": "供给端收缩可能改善预期。",
            }
        ],
        [],
        question="A股港股锂矿上下游的所有股票最近几个月一直跌跌不休，还有救吗？",
    )

    assert rows[0]["status"] == "news_context"
    assert rows[0]["provider"] == "anysearch"
    assert rows[0]["observed_at"] == "2026-07-30T00:00:00+00:00"
    assert rows[0]["source_url"] == "https://example.com/lithium-cut"


def test_undated_anysearch_result_is_not_current(monkeypatch):
    class FakeClient:
        is_configured = True

        def search(self, query: str):
            return WebSearchResponse(
                enabled=True,
                status="completed",
                provider="anysearch",
                query=query,
                results=[
                    WebSearchResult(
                        title="锂矿企业宣布减产",
                        url="https://example.com/undated",
                        snippet="未提供发布日期。",
                        source="example",
                        published_at=None,
                    )
                ],
                elapsed_ms=10,
            )

    monkeypatch.setattr(agent, "AnySearchClient", FakeClient)
    rows = agent._enrich_macro_monitoring_signals(
        [
            {
                "signal": "锂矿企业减产公告",
                "current_value": None,
                "threshold": "头部企业宣布减产",
                "meaning": "供给端收缩可能改善预期。",
            }
        ],
        [],
        question="A股港股锂矿上下游的所有股票最近几个月一直跌跌不休，还有救吗？",
    )

    assert rows[0]["status"] == "unavailable"
    assert rows[0]["current_value"] == "未获取"


def test_unrelated_spy_price_does_not_validate_lithium_price_claim():
    context = {
        "question": "A股港股锂矿上下游的所有股票最近几个月一直跌跌不休，还有救吗？",
        "selected_provider_ids": ["yahoo_price"],
        "signals": [
            {
                "source": "yahoo_price",
                "signal_type": "price_trend_1m",
                "value": -0.01,
                "interpretation": "SPY 最新价变化",
                "confidence": 0.6,
                "metadata": {"symbol": "SPY", "latest": 500, "price_eligible": True},
            }
        ],
        "dimension_coverage": {"sufficient_evidence": False, "dimension_count": 1, "required_dimension_count": 3},
    }
    report = agent._ensure_macro_report(
        {
            "conclusion": "结论：碳酸锂价格约15万元/吨，板块可以抄底。",
            "short_term_prediction": "碳酸锂价格可能回到15万元/吨。",
            "macro_analysis": "碳酸锂价格约15万元/吨。",
            "recommendation": "买入",
            "confidence": 0.8,
            "risk_level": "高",
            "probability_scenarios": [
                {"scenario": "碳酸锂价格回到15万元/吨", "probability": 0.7, "basis": "网页摘要"},
                {"scenario": "继续下跌", "probability": 0.3, "basis": "供给压力"},
            ],
            "monitoring_signals": [],
        },
        context,
    )

    assert "15万元" not in str(report)
    assert report["recommendation"] == "观察"


def test_lithium_guard_removes_cross_asset_and_nested_unverified_price_claims():
    context = {
        "question": "A股港股锂矿上下游的所有股票最近几个月一直跌跌不休，还有救吗？",
        "signals": [],
        "dimension_coverage": {"sufficient_evidence": False, "dimension_count": 0, "required_dimension_count": 3},
    }
    report = agent._ensure_macro_report(
        {
            "conclusion": "锂矿板块短期承压。",
            "fundamentals": "供给压力仍在。碳酸锂价格约15万元/吨。",
            "uncertainties": "当前缺少可验证的黄金直接报价。",
            "probability_scenarios": [
                {"scenario": "锂价继续下行至15万元/吨", "probability": 0.3, "basis": "供给压力"},
                {"scenario": "板块震荡", "probability": 0.2, "basis": "等待催化"},
            ],
            "time_layered_conclusions": [
                {"tier": "S", "label": "短期", "time_range": "1-2周", "judgment": "碳酸锂价格跌破15万元/吨", "confidence": 0.3},
                {"tier": "M", "label": "中期", "time_range": "1-3个月", "judgment": "等待供需再平衡", "confidence": 0.5},
            ],
            "monitoring_signals": [],
        },
        context,
    )

    assert sum(row["probability"] for row in report["probability_scenarios"]) == 1.0
    assert "黄金" not in str(report)
    assert "15万元" not in str(report)
    assert report["monitoring_signals"][-1]["signal"] == "碳酸锂相关价格"
