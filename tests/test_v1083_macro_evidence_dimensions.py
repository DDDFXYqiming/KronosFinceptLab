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
    assert "宏观证据不足" in report["uncertainties"]
