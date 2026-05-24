from __future__ import annotations

from fastapi.testclient import TestClient

from kronos_fincept.agent import _strip_think_blocks
from kronos_fincept.api.app import create_app
from kronos_fincept.api.models import ForecastRequestIn, ForecastRowIn
from kronos_fincept.schemas import ForecastRequest


def _row() -> ForecastRowIn:
    return ForecastRowIn(
        timestamp="2026-05-20",
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=12345,
    )


def test_model_family_defaults_follow_selected_model() -> None:
    pydantic_req = ForecastRequestIn(
        symbol="600036",
        pred_len=3,
        rows=[_row()],
        model_id="NeoQuasar/Kronos-mini",
    )

    request = ForecastRequest.from_pydantic(pydantic_req)

    assert request.model_id == "NeoQuasar/Kronos-mini"
    assert request.tokenizer_id == "NeoQuasar/Kronos-Tokenizer-2k"
    assert request.max_context == 2048


def test_explicit_model_context_overrides_family_default() -> None:
    pydantic_req = ForecastRequestIn(
        symbol="600036",
        pred_len=3,
        rows=[_row()],
        model_id="NeoQuasar/Kronos-mini",
        max_context=256,
    )

    request = ForecastRequest.from_pydantic(pydantic_req)

    assert request.max_context == 256


def test_batch_item_preserves_model_family_fields() -> None:
    request = ForecastRequest.from_batch_item(
        symbol="600036",
        timeframe="1d",
        pred_len=5,
        rows=[_row()],
        model_id="NeoQuasar/Kronos-mini",
    )

    assert request.tokenizer_id == "NeoQuasar/Kronos-Tokenizer-2k"
    assert request.max_context == 2048


def test_health_exposes_supported_model_ids() -> None:
    payload = TestClient(create_app()).get("/api/health").json()

    assert payload["default_model_id"] == "NeoQuasar/Kronos-base"
    assert "NeoQuasar/Kronos-mini" in payload["supported_model_ids"]
    assert "NeoQuasar/Kronos-base" in payload["supported_model_ids"]


def test_deepseek_think_blocks_are_removed_before_json_parse() -> None:
    content = '<think>private reasoning</think>{"recommendation":"BUY"}'

    assert _strip_think_blocks(content) == '{"recommendation":"BUY"}'
    assert _strip_think_blocks("<think>unfinished") == ""


def test_rss_endpoint_fetches_and_normalizes_items(monkeypatch) -> None:
    from kronos_fincept.api.routes import news

    monkeypatch.setenv("KRONOS_RSS_VALIDATE_DNS", "0")
    monkeypatch.setattr(
        news,
        "_fetch_text",
        lambda url: """<?xml version="1.0"?>
<rss><channel><title>Market Feed</title>
<item><title>Macro update</title><link>https://example.com/a</link><pubDate>Wed, 20 May 2026 12:00:00 GMT</pubDate><description><![CDATA[<b>Rates</b> moved]]></description></item>
<item><title>Bad link</title><link>javascript:alert(1)</link></item>
</channel></rss>""",
    )

    response = TestClient(create_app()).post(
        "/api/news/rss",
        json={"feeds": [{"id": "market", "title": "Markets", "url": "https://example.com/feed.xml"}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["items"][0]["feed_id"] == "market"
    assert payload["items"][0]["title"] == "Macro update"
    assert payload["items"][0]["summary"] == "Rates moved"
    assert len(payload["items"]) == 1


def test_rss_endpoint_rejects_private_targets(monkeypatch) -> None:
    monkeypatch.setenv("KRONOS_RSS_VALIDATE_DNS", "0")

    response = TestClient(create_app()).post(
        "/api/news/rss",
        json={"feeds": [{"url": "https://127.0.0.1/feed.xml"}]},
    )

    assert response.status_code == 422
