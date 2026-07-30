from __future__ import annotations

from kronos_fincept.agent import _ensure_macro_report, _fallback_macro_report, _macro_context_from_gather
from kronos_fincept.macro import MacroGatherResult, MacroProviderResult, MacroSignal


def _signal(source: str, signal_type: str, value: float = 1.0) -> MacroSignal:
    return MacroSignal(
        source=source,
        signal_type=signal_type,
        value=value,
        interpretation=f"{source} {signal_type} signal",
        time_horizon="mixed",
        confidence=0.7,
    )


def _gather(signals: list[MacroSignal]) -> MacroGatherResult:
    provider_results: dict[str, MacroProviderResult] = {}
    for signal in signals:
        provider_results[signal.source] = MacroProviderResult(
            provider_id=signal.source,
            status="completed",
            signals=[signal],
            elapsed_ms=1,
        )
    return MacroGatherResult(signals=signals, provider_results=provider_results)


def test_v1083_macro_context_records_independent_signal_dimensions() -> None:
    result = _gather(
        [
            _signal("polymarket", "prediction_market_probability"),
            _signal("us_treasury", "yield_curve"),
            _signal("cftc_cot", "cot_positioning"),
        ]
    )

    context = _macro_context_from_gather("黄金宏观风险", ["polymarket", "us_treasury", "cftc_cot"], result)

    assert context["dimension_coverage"]["sufficient_evidence"] is True
    assert context["dimension_coverage"]["dimension_count"] == 3
    assert {"prediction_market", "rates", "positioning"} <= set(context["dimension_coverage"]["dimensions"])


def test_v1083_fallback_report_caps_confidence_when_dimensions_are_insufficient() -> None:
    result = _gather(
        [
            _signal("polymarket", "prediction_market_probability"),
            _signal("kalshi", "prediction_market_probability"),
        ]
    )
    context = _macro_context_from_gather("WW3 概率", ["polymarket", "kalshi"], result)

    report = _fallback_macro_report(context)

    assert report["confidence"] <= 0.45
    assert report["recommendation"] == "观察"
    assert report["macro_evidence"]["sufficient_evidence"] is False
    assert "证据不足" in report["conclusion"] or "证据不足" in report["cross_validation"]


def test_v1083_fallback_macro_conclusion_answers_buy_timing_directly() -> None:
    result = _gather(
        [
            _signal("web_search", "news_sentiment"),
            _signal("us_treasury", "yield_curve"),
            _signal("cftc_cot", "cot_positioning"),
        ]
    )
    context = _macro_context_from_gather("全球AI硬件相关股票现在还能买入吗", ["web_search", "us_treasury", "cftc_cot"], result)

    report = _fallback_macro_report(context)

    assert report["conclusion"].startswith("结论：")
    assert "不支持无条件追买" in report["conclusion"]
    assert report["macro_analysis"] == report["conclusion"]


def test_v1083_fallback_macro_conclusion_answers_growth_asset_question() -> None:
    result = _gather(
        [
            _signal("web_search", "news_sentiment"),
            _signal("us_treasury", "yield_curve"),
            _signal("cftc_cot", "cot_positioning"),
        ]
    )
    context = _macro_context_from_gather("现在还能买科技股吗", ["web_search", "us_treasury", "cftc_cot"], result)

    report = _fallback_macro_report(context)

    assert "科技成长资产" in report["conclusion"]
    assert "无条件追买" in report["conclusion"]


def test_v1083_generic_llm_macro_conclusion_is_replaced_with_direct_answer() -> None:
    result = _gather(
        [
            _signal("web_search", "news_sentiment"),
            _signal("us_treasury", "yield_curve"),
            _signal("cftc_cot", "cot_positioning"),
        ]
    )
    context = _macro_context_from_gather("现在还能买科技股吗", ["web_search", "us_treasury", "cftc_cot"], result)

    report = _ensure_macro_report(
        {
            "conclusion": "宏观证据已满足交叉验证，但仍需结合下方信号确认。",
            "macro_analysis": "科技股相关信号已返回。",
            "recommendation": "观察",
            "confidence": 0.6,
            "risk_level": "中",
        },
        context,
    )

    assert "科技成长资产" in report["conclusion"]


def test_v1083_llm_macro_report_is_guarded_when_evidence_is_insufficient() -> None:
    result = _gather([_signal("yahoo_price", "price_trend_1m")])
    context = _macro_context_from_gather("A股现在位置怎么样", ["yahoo_price"], result)

    report = _ensure_macro_report(
        {
            "conclusion": "强烈看多，可以积极买入。",
            "short_term_prediction": "上涨。",
            "technical": "不适用。",
            "fundamentals": "不适用。",
            "risk": "低。",
            "uncertainties": "少。",
            "recommendation": "买入",
            "confidence": 0.92,
            "risk_level": "低",
            "macro_analysis": "单一价格信号支持看多。",
        },
        context,
    )

    assert report["confidence"] <= 0.45
    assert report["recommendation"] == "观察"


def test_gold_report_rejects_web_snippet_prices_without_direct_price_signal() -> None:
    result = _gather(
        [
            _signal("us_treasury", "real_yield_10y", 2.44),
            _signal("cftc_cot", "managed_money_net_position", 124831),
            MacroSignal(
                source="anysearch",
                signal_type="public_web_result",
                value="黄金失守4600",
                interpretation="旧网页摘要提到黄金失守4600。",
                time_horizon="mixed",
                confidence=0.5,
                metadata={"price_eligible": False, "evidence_role": "news_context_only"},
            ),
        ]
    )
    context = _macro_context_from_gather(
        "现在适合买黄金吗",
        ["us_treasury", "cftc_cot", "anysearch"],
        result,
    )

    report = _ensure_macro_report(
        {
            "conclusion": "结论：等待黄金回调至4500以下买入。",
            "macro_analysis": "黄金当前价格约4600，短期偏空。",
            "recommendation": "分批买入",
            "confidence": 0.7,
            "risk_level": "中",
            "probability_scenarios": [
                {"scenario": "黄金回调至4400-4500", "probability": 0.6, "basis": "网页价格"},
            ],
            "monitoring_signals": [
                {"signal": "黄金价格", "current_value": 4600, "threshold": 4500, "meaning": "跌破买入"},
            ],
        },
        context,
    )

    serialized = str(report)
    assert "4600" not in serialized
    assert "4500" not in serialized
    assert "4400" not in serialized
    assert report["recommendation"] == "观察"
    assert report["confidence"] <= 0.45
    assert "宏观证据不足" in report["uncertainties"]
