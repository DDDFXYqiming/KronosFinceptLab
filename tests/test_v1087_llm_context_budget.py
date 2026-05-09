from __future__ import annotations

import json
from types import SimpleNamespace


def test_v1087_llm_context_compacts_indicator_arrays_and_research_payloads():
    from kronos_fincept import agent

    rows = [float(i) for i in range(300)]
    context = {
        "assets": [
            {
                "symbol": "600036",
                "market": "cn",
                "technical_indicators": {
                    "sma_20": {"values": rows, "period": 20},
                    "macd": {
                        "macd_line": rows,
                        "signal_line": rows,
                        "histogram": rows,
                    },
                },
                "online_research": {
                    "enabled": True,
                    "provider": "serper",
                    "queries": ["招商银行 600036"],
                    "results": [
                        {
                            "title": f"result-{index}",
                            "snippet": "x" * 1000,
                            "url": f"https://example.com/{index}",
                            "body": "y" * 2000,
                        }
                        for index in range(20)
                    ],
                    "responses": [{"raw": "duplicate payload"}],
                },
            }
        ]
    }

    compact = agent._compact_llm_report_context(context)
    asset = compact["assets"][0]
    technical = asset["technical_indicators"]
    research = asset["online_research"]
    encoded_technical = json.dumps(technical, ensure_ascii=False)

    assert "values" not in encoded_technical
    assert technical["sma_20"]["current"] == 299.0
    assert technical["sma_20"]["previous"] == 298.0
    assert technical["sma_20"]["points"] == 300
    assert technical["macd"]["macd_line_current"] == 299.0
    assert len(encoded_technical) < 1200
    assert len(research["results"]) == 12
    assert research["result_count"] == 20
    assert research["results_truncated"] is True
    assert research["results"][0]["snippet"].endswith("[truncated]")
    assert "responses" not in research
    assert "body" not in research["results"][0]
    assert len(context["assets"][0]["technical_indicators"]["sma_20"]["values"]) == 300


def test_v1087_llm_context_compacts_market_rows_for_web_analysis_budget():
    from kronos_fincept import agent

    rows = [
        {
            "timestamp": f"2025-01-{(index % 28) + 1:02d}T00:00:00Z",
            "open": 30 + index * 0.01,
            "high": 31 + index * 0.01,
            "low": 29 + index * 0.01,
            "close": 30.5 + index * 0.01,
            "volume": 100000 + index,
            "amount": 3000000 + index,
        }
        for index in range(356)
    ]
    context = {
        "assets": [
            {
                "symbol": "600036",
                "market": "cn",
                "market_data": {
                    "current_price": 37.94,
                    "latest_timestamp": "2026-05-08T00:00:00Z",
                    "data_points": len(rows),
                    "rows": rows,
                    "price_change_1d": 0.21,
                    "price_change_1w": -1.23,
                    "volume": 123456,
                    "high_52w": 42.0,
                    "low_52w": 30.0,
                },
            }
        ]
    }

    compact = agent._compact_llm_report_context(context)
    market_data = compact["assets"][0]["market_data"]
    encoded = json.dumps(compact, ensure_ascii=False)

    assert "rows" not in market_data
    assert market_data["row_count"] == 356
    assert market_data["rows_truncated"] is True
    assert len(market_data["recent_rows"]) == 5
    assert market_data["recent_rows"][-1]["close"] == rows[-1]["close"]
    assert len(encoded) < 3500
    assert len(context["assets"][0]["market_data"]["rows"]) == 356


def test_v1087_report_prompt_sends_compact_context_to_llm(monkeypatch):
    import requests

    from kronos_fincept import agent

    captured: dict[str, object] = {}
    deepseek = SimpleNamespace(
        is_configured=True,
        api_key="sk-deepseek-test",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
    )
    monkeypatch.setattr(agent, "settings", SimpleNamespace(llm=SimpleNamespace(deepseek=deepseek)))

    def fake_post(url, *, headers, json, timeout):
        captured["payload"] = json
        return SimpleNamespace(
            status_code=200,
            text="ok",
            json=lambda: {
                "choices": [
                    {
                        "message": {
                            "content": '{"conclusion":"ok","recommendation":"持有","confidence":0.6,"risk_level":"中"}'
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    monkeypatch.setattr(requests, "post", fake_post)

    report = agent._call_deepseek_report(
        "帮我看看招商银行现在能不能买",
        {
            "assets": [
                {
                    "symbol": "600036",
                    "market": "cn",
                    "technical_indicators": {"sma_20": {"values": list(range(300)), "period": 20}},
                }
            ],
            "page_context": {"entry": "web-analysis"},
        },
    )

    assert report is not None
    payload = captured["payload"]
    user_content = payload["messages"][1]["content"]
    prompt = json.loads(user_content)
    technical = prompt["trusted_project_context"]["assets"][0]["technical_indicators"]
    assert "values" not in json.dumps(technical, ensure_ascii=False)
    assert technical["sma_20"]["current"] == 299.0
    assert len(user_content) < 3000


def test_v1087_web_report_uses_short_openrouter_probe_before_deepseek(monkeypatch):
    from types import SimpleNamespace

    from kronos_fincept import agent

    monkeypatch.setattr(
        agent,
        "settings",
        SimpleNamespace(
            llm=SimpleNamespace(
                openrouter=SimpleNamespace(
                    is_configured=True,
                    api_key="sk-or-test",
                    base_url="https://openrouter.ai/api/v1",
                    model="openrouter/free",
                ),
                deepseek=SimpleNamespace(
                    is_configured=True,
                    api_key="***",
                    base_url="https://api.deepseek.com/v1",
                    model="deepseek-chat",
                ),
            )
        ),
    )

    timeouts = agent._report_provider_timeouts({"entry": "web-analysis"})

    assert timeouts["openrouter"] <= 10
    assert timeouts["deepseek"] >= 25
