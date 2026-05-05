from __future__ import annotations

import json

from click.testing import CliRunner
from fastapi.testclient import TestClient

from kronos_fincept.api.app import create_app
from kronos_fincept.cli.main import cli
from kronos_fincept.macro import MacroGatherResult, MacroProviderResult, MacroSignal


def _signal(source: str, signal_type: str, *, observed_at: str = "2026-05-05") -> MacroSignal:
    return MacroSignal(
        source=source,
        signal_type=signal_type,
        value=0.5,
        interpretation=f"{source} returned {signal_type}",
        time_horizon="mixed",
        confidence=0.7,
        observed_at=observed_at,
        source_url=f"https://example.test/{source}",
        metadata={"data_quality": f"{source}_quality", "source_time": observed_at},
    )


class FakeMacroManager:
    def gather(self, query, *, provider_ids=None):
        providers = list(provider_ids or [])
        signals = [
            _signal("polymarket", "prediction_market_probability"),
            _signal("us_treasury", "yield_curve"),
            _signal("cftc_cot", "cot_positioning"),
        ]
        provider_results = {
            provider: MacroProviderResult(
                provider_id=provider,
                status="completed",
                signals=[signal for signal in signals if signal.source == provider],
                elapsed_ms=10,
            )
            for provider in providers
            if provider in {"polymarket", "us_treasury", "cftc_cot"}
        }
        provider_results["cme_fedwatch"] = MacroProviderResult(
            provider_id="cme_fedwatch",
            status="unavailable",
            signals=[],
            elapsed_ms=2,
            error="missing endpoint",
            metadata={"reason": "unavailable"},
        )
        return MacroGatherResult(signals=signals, provider_results=provider_results)


def _patch_macro(monkeypatch):
    from kronos_fincept import agent

    monkeypatch.setattr(agent, "_create_macro_data_manager", lambda **kwargs: FakeMacroManager())
    monkeypatch.setattr(
        agent,
        "_generate_report",
        lambda question, context: (
            {
                "conclusion": "三类宏观信号支持谨慎观察。",
                "short_term_prediction": "宏观入口不直接输出 K 线预测。",
                "technical": "不适用。",
                "fundamentals": "不适用。",
                "risk": "仍需监控尾部风险。",
                "uncertainties": "provider 可用性会影响结论。",
                "recommendation": "观察",
                "confidence": 0.66,
                "risk_level": "中",
                "disclaimer": "仅供研究。",
                "macro_analysis": "预测市场、利率和持仓维度均有信号。",
                "macro_signals": context["macro"]["signals"],
                "cross_validation": "三类信号可相互校验。",
                "contradictions": "暂无明显矛盾。",
            },
            agent.AgentToolCall(
                name="deepseek_report",
                status="completed",
                summary="mock report",
                elapsed_ms=1,
                metadata={"provider": "test"},
            ),
        ),
    )


def test_v1085_macro_api_exposes_provider_and_dimension_coverage(monkeypatch) -> None:
    _patch_macro(monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/analyze/macro",
        json={
            "question": "现在适合买黄金吗",
            "provider_ids": ["polymarket", "us_treasury", "cftc_cot", "cme_fedwatch"],
            "context": {"entry": "web-macro"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["macro_data_quality"]["provider_total"] == 4
    assert payload["macro_data_quality"]["signal_count"] == 3
    assert payload["macro_provider_coverage"]["cme_fedwatch"]["status"] == "unavailable"
    assert payload["macro_dimension_coverage"]["sufficient_evidence"] is True
    assert payload["macro_evidence_insufficiency"]["insufficient"] is False


def test_v1085_macro_cli_json_and_text_include_coverage(monkeypatch) -> None:
    _patch_macro(monkeypatch)
    runner = CliRunner()

    json_result = runner.invoke(
        cli,
        [
            "analyze",
            "macro",
            "--question",
            "现在适合买黄金吗",
            "--providers",
            "polymarket,us_treasury,cftc_cot,cme_fedwatch",
            "--output",
            "json",
        ],
    )
    assert json_result.exit_code == 0
    payload = json.loads(json_result.output)
    assert payload["macro_provider_coverage"]["polymarket"]["signal_count"] == 1
    assert payload["macro_data_quality"]["unavailable_count"] == 1

    text_result = runner.invoke(
        cli,
        [
            "analyze",
            "macro",
            "--question",
            "现在适合买黄金吗",
            "--providers",
            "polymarket,us_treasury,cftc_cot,cme_fedwatch",
            "--output",
            "text",
        ],
    )
    assert text_result.exit_code == 0
    assert "Macro Coverage:" in text_result.output
    assert "cme_fedwatch: unavailable" in text_result.output
