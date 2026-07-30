from kronos_fincept.macro.providers.digital_oracle import KalshiFedProvider
from kronos_fincept.macro.schemas import MacroQuery


def test_kalshi_fed_aggregates_meeting_probabilities(monkeypatch):
    event_payload = {
        "events": [
            {
                "event_ticker": "KXFEDDECISION-26SEP",
                "strike_date": "2026-09-16T18:00:00Z",
                "last_updated_ts": "2026-07-30T12:00:00Z",
            }
        ]
    }
    market_payload = {
        "markets": [
            {"ticker": "KXFEDDECISION-26SEP-H25", "subtitle": "Hike 25bps", "yes_bid_dollars": "0.5200", "yes_ask_dollars": "0.5400"},
            {"ticker": "KXFEDDECISION-26SEP-H0", "subtitle": "Hike 0bps", "yes_bid_dollars": "0.4200", "yes_ask_dollars": "0.4400"},
            {"ticker": "KXFEDDECISION-26SEP-C25", "subtitle": "Cut 25bps", "yes_bid_dollars": "0.0200", "yes_ask_dollars": "0.0400"},
        ]
    }

    def fake_get_json(url, *, params=None, timeout=8):
        if url.endswith("/events"):
            return event_payload
        assert url.endswith("/markets")
        assert params["event_ticker"] == "KXFEDDECISION-26SEP"
        return market_payload

    monkeypatch.setattr("kronos_fincept.macro.providers.digital_oracle._get_json", fake_get_json)

    signals = KalshiFedProvider().fetch_signals(MacroQuery(question="美联储降息概率", limit=3))

    assert len(signals) == 1
    signal = signals[0]
    assert signal.source == "kalshi_fed"
    assert signal.signal_type == "fed_decision_probability"
    assert signal.value == 0.53
    assert signal.metadata["meeting_date"] == "2026-09-16"
    assert signal.metadata["probabilities"] == {"hike": 0.53, "hold": 0.43, "cut": 0.03}
    assert signal.metadata["source_kind"] == "prediction_market_alternative_not_cme_fedwatch"
    assert "Kalshi Fed" in signal.interpretation


def test_kalshi_fed_is_registered_and_selected_for_rate_questions():
    from kronos_fincept.agent import select_macro_provider_ids
    from kronos_fincept.macro import create_default_providers

    provider_ids = {provider.provider_id for provider in create_default_providers()}
    assert "kalshi_fed" in provider_ids
    assert "kalshi_fed" in select_macro_provider_ids("CPI rate decision probability")


def test_manager_preserves_unavailable_status_for_unconfigured_provider():
    from kronos_fincept.macro import MacroDataManager
    from kronos_fincept.macro.providers.base import MacroProvider, MacroProviderUnavailable

    class UnconfiguredProvider(MacroProvider):
        provider_id = "unconfigured_test"
        display_name = "Unconfigured test"

        def fetch_signals(self, query):
            raise MacroProviderUnavailable("endpoint is not configured")

    result = MacroDataManager(providers=[UnconfiguredProvider()]).gather("Fed rate")

    assert result.provider_results["unconfigured_test"].status == "unavailable"
    assert result.provider_results["unconfigured_test"].error == "endpoint is not configured"
