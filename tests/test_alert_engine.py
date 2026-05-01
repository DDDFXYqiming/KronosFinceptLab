"""Unit tests for the alert and monitoring engine.

Tests cover:
- AlertRule creation and serialization
- AlertRule factories
- AlertEngine rule management (register, unregister, list)
- AlertEngine rule checking (price change, RSI, MACD, volume spike)
- Notification (Feishu, Email)
- CLI commands
- API endpoints
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from kronos_fincept.alert_engine import (
    AlertEngine,
    AlertEvent,
    AlertRule,
    AlertType,
    NotificationChannel,
    get_engine,
    price_change_rule,
    price_above_rule,
    price_below_rule,
    rsi_overbought_rule,
    rsi_oversold_rule,
    macd_crossover_rule,
    prediction_deviation_rule,
    volume_spike_rule,
)


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def sample_mock_rows() -> list[dict]:
    """Sample OHLCV data rows (60 days) for A-stock testing."""
    rows = []
    base_price = 100.0
    for i in range(60):
        price = base_price + i * 0.5 + (i % 10) * 0.3
        rows.append({
            "timestamp": f"2026-{i//30+3:02d}-{(i%30)+1:02d}T00:00:00Z",
            "open": price - 0.2,
            "high": price + 0.8,
            "low": price - 0.5,
            "close": price + 0.1,
            "volume": 1000000 + i * 10000,
            "amount": price * (1000000 + i * 10000),
        })
    return rows


@pytest.fixture
def rule_price_change() -> AlertRule:
    return AlertRule(
        id="test_rule_001",
        name="Test Price Change",
        alert_type=AlertType.PRICE_CHANGE,
        symbol="600519",
        market="cn",
        params={"threshold_pct": 5.0},
        enabled=True,
        channel=NotificationChannel.FEISHU,
    )


@pytest.fixture
def rule_rsi_overbought() -> AlertRule:
    return AlertRule(
        id="test_rule_002",
        name="Test RSI Overbought",
        alert_type=AlertType.RSI_OVERBOUGHT,
        symbol="600519",
        market="cn",
        params={"rsi_period": 14, "overbought": 70},
        enabled=True,
        channel=NotificationChannel.FEISHU,
    )


@pytest.fixture
def rule_volume_spike() -> AlertRule:
    return AlertRule(
        id="test_rule_003",
        name="Test Volume Spike",
        alert_type=AlertType.VOLUME_SPIKE,
        symbol="600519",
        market="cn",
        params={"multiplier": 3.0},
        enabled=True,
        channel=NotificationChannel.EMAIL,
    )


@pytest.fixture
def engine(tmp_path: Path) -> AlertEngine:
    """AlertEngine with temp storage."""
    storage = tmp_path / "alerts.json"
    return AlertEngine(storage_path=str(storage))


# ===================================================================
# AlertRule dataclass tests
# ===================================================================

class TestAlertRule:
    def test_create_price_change(self, rule_price_change):
        assert rule_price_change.id == "test_rule_001"
        assert rule_price_change.alert_type == AlertType.PRICE_CHANGE
        assert rule_price_change.params["threshold_pct"] == 5.0

    def test_serialize_deserialize(self):
        rule = price_change_rule("000001", threshold_pct=3.0)
        data = rule.to_dict()
        restored = AlertRule.from_dict(data)
        assert restored.id == rule.id
        assert restored.name == rule.name
        assert restored.alert_type == rule.alert_type
        assert restored.symbol == rule.symbol
        assert restored.params == rule.params

    def test_alert_type_values(self):
        assert AlertType.PRICE_CHANGE.value == "price_change"
        assert AlertType.RSI_OVERBOUGHT.value == "rsi_overbought"
        assert AlertType.MACD_CROSSOVER.value == "macd_crossover"
        assert AlertType.PREDICTION_DEVIATION.value == "prediction_deviation"
        assert AlertType.VOLUME_SPIKE.value == "volume_spike"

    def test_notification_channel_values(self):
        assert NotificationChannel.FEISHU.value == "feishu"
        assert NotificationChannel.EMAIL.value == "email"


# ===================================================================
# Rule factory tests
# ===================================================================

class TestRuleFactories:
    def test_price_change_rule(self):
        rule = price_change_rule("600519", threshold_pct=5.0)
        assert rule.alert_type == AlertType.PRICE_CHANGE
        assert rule.params["threshold_pct"] == 5.0
        assert rule.symbol == "600519"

    def test_price_above_rule(self):
        rule = price_above_rule("AAPL", level=200.0, market="us")
        assert rule.alert_type == AlertType.PRICE_ABOVE
        assert rule.params["level"] == 200.0
        assert rule.market == "us"

    def test_price_below_rule(self):
        rule = price_below_rule("AAPL", level=100.0)
        assert rule.alert_type == AlertType.PRICE_BELOW
        assert rule.params["level"] == 100.0

    def test_rsi_overbought_rule(self):
        rule = rsi_overbought_rule("600519", period=14)
        assert rule.alert_type == AlertType.RSI_OVERBOUGHT
        assert rule.params["rsi_period"] == 14
        assert rule.params["overbought"] == 70

    def test_rsi_oversold_rule(self):
        rule = rsi_oversold_rule("600519", period=14)
        assert rule.alert_type == AlertType.RSI_OVERSOLD
        assert rule.params["oversold"] == 30

    def test_macd_crossover_rule(self):
        rule = macd_crossover_rule("600519")
        assert rule.alert_type == AlertType.MACD_CROSSOVER

    def test_prediction_deviation_rule(self):
        rule = prediction_deviation_rule("600519", deviation_pct=8.0)
        assert rule.alert_type == AlertType.PREDICTION_DEVIATION
        assert rule.params["deviation_pct"] == 8.0

    def test_volume_spike_rule(self):
        rule = volume_spike_rule("600519", multiplier=5.0)
        assert rule.alert_type == AlertType.VOLUME_SPIKE
        assert rule.params["multiplier"] == 5.0

    def test_unique_ids(self):
        r1 = price_change_rule("000001")
        r2 = price_change_rule("000001")
        assert r1.id != r2.id


# ===================================================================
# AlertEngine rule management tests
# ===================================================================

class TestAlertEngineManagement:
    def test_register_rule(self, engine, rule_price_change):
        engine.register_rule(rule_price_change)
        rules = engine.list_rules()
        assert len(rules) == 1
        assert rules[0].id == rule_price_change.id

    def test_register_multiple_rules(self, engine):
        rules = [
            price_change_rule("600519"),
            rsi_overbought_rule("000001"),
            volume_spike_rule("600519"),
        ]
        for r in rules:
            engine.register_rule(r)
        assert len(engine.list_rules()) == 3

    def test_unregister_rule(self, engine, rule_price_change):
        engine.register_rule(rule_price_change)
        assert engine.unregister_rule(rule_price_change.id) is True
        assert len(engine.list_rules()) == 0

    def test_unregister_nonexistent(self, engine):
        assert engine.unregister_rule("nonexistent") is False

    def test_get_rule(self, engine, rule_price_change):
        engine.register_rule(rule_price_change)
        assert engine.get_rule(rule_price_change.id) is rule_price_change
        assert engine.get_rule("nonexistent") is None

    def test_disable_rule_skips_check(self, engine, rule_price_change):
        rule_price_change.enabled = False
        engine.register_rule(rule_price_change)
        events = engine.check_all()
        assert len(events) == 0

    def test_persistence(self, tmp_path):
        storage = tmp_path / "alerts.json"
        eng1 = AlertEngine(storage_path=str(storage))
        eng1.register_rule(price_change_rule("600519"))

        # Re-create engine (loads from file)
        eng2 = AlertEngine(storage_path=str(storage))
        rules = eng2.list_rules()
        assert len(rules) == 1
        assert rules[0].symbol == "600519"


# ===================================================================
# AlertEngine check tests (mocked data)
# ===================================================================

class TestAlertEngineChecks:
    def test_check_price_change_no_trigger(self, engine):
        """Should not trigger if change is below threshold."""
        rule = AlertRule(
            id="pc_test",
            name="PC Test",
            alert_type=AlertType.PRICE_CHANGE,
            symbol="600519",
            params={"threshold_pct": 50.0},
        )
        engine.register_rule(rule)

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            return_value=[
                {"timestamp": "2026-01-01T00:00:00Z", "open": 100.0, "high": 102.0,
                 "low": 99.0, "close": 101.0, "volume": 1000000, "amount": 1.0e8},
                {"timestamp": "2026-01-02T00:00:00Z", "open": 101.0, "high": 103.0,
                 "low": 100.0, "close": 102.0, "volume": 1000000, "amount": 1.0e8},
            ],
        ):
            events = engine.check_all()
        assert len(events) == 0

    def test_check_price_change_trigger(self, engine):
        """Should trigger if change exceeds threshold."""
        rule = AlertRule(
            id="pc_test2",
            name="PC Test Trigger",
            alert_type=AlertType.PRICE_CHANGE,
            symbol="600519",
            params={"threshold_pct": 1.0},
        )
        engine.register_rule(rule)

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            return_value=[
                {"timestamp": "2026-01-01T00:00:00Z", "open": 100.0, "high": 100.0,
                 "low": 100.0, "close": 100.0, "volume": 1000000, "amount": 1.0e8},
                {"timestamp": "2026-01-02T00:00:00Z", "open": 105.0, "high": 105.0,
                 "low": 105.0, "close": 105.0, "volume": 1000000, "amount": 1.0e8},
            ],
        ):
            events = engine.check_all()
        assert len(events) == 1
        assert events[0].alert_type == AlertType.PRICE_CHANGE
        assert events[0].current_value == 105.0

    def test_check_price_above_trigger(self, engine):
        """Should trigger when price is above level."""
        rule = price_above_rule("600519", level=103.0)
        engine.register_rule(rule)

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            return_value=[
                {"timestamp": "2026-01-01T00:00:00Z", "open": 100.0, "high": 100.0,
                 "low": 100.0, "close": 100.0, "volume": 1000000, "amount": 1.0e8},
                {"timestamp": "2026-01-02T00:00:00Z", "open": 104.0, "high": 104.0,
                 "low": 104.0, "close": 104.0, "volume": 1000000, "amount": 1.0e8},
            ],
        ):
            events = engine.check_all()
        assert len(events) == 1
        assert events[0].alert_type == AlertType.PRICE_ABOVE

    def test_check_price_below_no_trigger(self, engine):
        """Should not trigger when price is above level."""
        rule = price_below_rule("600519", level=100.0)
        engine.register_rule(rule)

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            return_value=[
                {"timestamp": "2026-01-01T00:00:00Z", "open": 100.0, "high": 100.0,
                 "low": 100.0, "close": 100.0, "volume": 1000000, "amount": 1.0e8},
                {"timestamp": "2026-01-02T00:00:00Z", "open": 110.0, "high": 110.0,
                 "low": 110.0, "close": 110.0, "volume": 1000000, "amount": 1.0e8},
            ],
        ):
            events = engine.check_all()
        assert len(events) == 0

    def test_check_volume_spike_trigger(self, engine):
        """Should trigger on volume spike."""
        rule = volume_spike_rule("600519", multiplier=2.0)
        engine.register_rule(rule)

        rows = []
        for i in range(30):
            rows.append({
                "timestamp": f"2026-01-{i+1:02d}T00:00:00Z",
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                "volume": 1000000,
                "amount": 1.0e8,
            })
        # Double the last volume
        rows[-1]["volume"] = 3000000
        rows[-1]["close"] = 100.5

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            return_value=rows,
        ):
            events = engine.check_all()
        assert len(events) == 1
        assert events[0].alert_type == AlertType.VOLUME_SPIKE

    def test_check_rsi_overbought_trigger(self, engine):
        """Should trigger on RSI overbought."""
        rule = rsi_overbought_rule("600519", period=14)
        engine.register_rule(rule)

        # Create data with strong uptrend to make RSI > 70
        rows = []
        price = 100.0
        for i in range(60):
            price += 1.0 + (i % 3) * 0.5  # Strong uptrend
            rows.append({
                "timestamp": f"2026-01-{i+1:02d}T00:00:00Z",
                "open": price - 0.5,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 1000000,
                "amount": 1.0e8,
            })

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            return_value=rows,
        ):
            events = engine.check_all()
        assert len(events) == 1
        assert events[0].alert_type == AlertType.RSI_OVERBOUGHT

    def test_check_rsi_oversold_trigger(self, engine):
        """Should trigger on RSI oversold."""
        rule = rsi_oversold_rule("600519", period=14)
        engine.register_rule(rule)

        # Create data with strong downtrend to make RSI < 30
        rows = []
        price = 200.0
        for i in range(60):
            price -= 1.0 + (i % 3) * 0.5  # Strong downtrend
            if price < 1:
                price = 1
            rows.append({
                "timestamp": f"2026-01-{i+1:02d}T00:00:00Z",
                "open": price + 0.5,
                "high": price + 1.0,
                "low": price - 0.5,
                "close": price,
                "volume": 1000000,
                "amount": 1.0e8,
            })

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            return_value=rows,
        ):
            events = engine.check_all()
        assert len(events) == 1
        assert events[0].alert_type == AlertType.RSI_OVERSOLD

    def test_data_fetch_failure_graceful(self, engine, rule_price_change):
        """Should handle data fetch errors gracefully."""
        engine.register_rule(rule_price_change)

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            side_effect=ValueError("API error"),
        ):
            events = engine.check_all()
        assert len(events) == 0  # Graceful degradation

    def test_check_prediction_deviation_no_prediction(self, engine):
        """Should not crash when prediction is unavailable."""
        rule = prediction_deviation_rule("600519", deviation_pct=5.0)
        engine.register_rule(rule)

        with patch(
            "kronos_fincept.akshare_adapter.fetch_a_stock_ohlcv",
            return_value=[
                {"timestamp": "2026-01-01T00:00:00Z", "open": 100.0, "high": 100.0,
                 "low": 100.0, "close": 100.0, "volume": 1000000, "amount": 1.0e8},
                {"timestamp": "2026-01-02T00:00:00Z", "open": 105.0, "high": 105.0,
                 "low": 105.0, "close": 105.0, "volume": 1000000, "amount": 1.0e8},
            ],
        ):
            events = engine.check_all()
        # Should not crash; returns no events if prediction can't be fetched
        assert len(events) == 0


# ===================================================================
# AlertEvent tests
# ===================================================================

class TestAlertEvent:
    def test_event_creation(self):
        event = AlertEvent(
            rule_id="r1",
            rule_name="Test Event",
            alert_type=AlertType.PRICE_CHANGE,
            symbol="600519",
            message="Price changed",
            current_value=105.0,
            threshold_value=5.0,
            timestamp="2026-05-01T12:00:00Z",
            severity="warning",
        )
        assert event.rule_id == "r1"
        assert event.severity == "warning"

    def test_event_serialization(self):
        event = AlertEvent(
            rule_id="r1",
            rule_name="Test Event",
            alert_type=AlertType.PRICE_CHANGE,
            symbol="600519",
            message="Price changed",
            current_value=105.0,
            threshold_value=5.0,
            timestamp="2026-05-01T12:00:00Z",
            severity="warning",
        )
        data = event.to_dict()
        assert data["alert_type"] == "price_change"
        assert data["current_value"] == 105.0


# ===================================================================
# Notification tests
# ===================================================================

class TestNotifications:
    def test_notify_no_webhook(self, engine, rule_price_change):
        """Should return False when no webhook URL configured."""
        engine.register_rule(rule_price_change)
        event = AlertEvent(
            rule_id=rule_price_change.id,
            rule_name=rule_price_change.name,
            alert_type=AlertType.PRICE_CHANGE,
            symbol="600519",
            message="Test",
            current_value=100.0,
            threshold_value=5.0,
            timestamp="2026-05-01T12:00:00Z",
            severity="info",
        )
        result = engine.notify(event)
        assert result is False

    def test_notify_feishu_success(self):
        """Mock a successful Feishu webhook call."""
        engine = AlertEngine(storage_path="/tmp/test_alerts.json")
        rule = AlertRule(
            id="test_feishu",
            name="Feishu Test",
            alert_type=AlertType.PRICE_CHANGE,
            symbol="600519",
            channel=NotificationChannel.FEISHU,
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx",
        )
        engine._rules[rule.id] = rule

        event = AlertEvent(
            rule_id="test_feishu",
            rule_name="Feishu Test",
            alert_type=AlertType.PRICE_CHANGE,
            symbol="600519",
            message="Test message",
            current_value=100.0,
            threshold_value=5.0,
            timestamp="2026-05-01T12:00:00Z",
            severity="info",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"code": 0, "msg": "success"}'
            mock_urlopen.return_value = mock_response
            mock_urlopen.return_value.__enter__.return_value = mock_response

            result = engine.notify(event)
            assert result is True

    def test_notify_email_no_credentials(self, engine, rule_volume_spike):
        """Should return False when SMTP credentials missing."""
        engine.register_rule(rule_volume_spike)
        event = AlertEvent(
            rule_id=rule_volume_spike.id,
            rule_name=rule_volume_spike.name,
            alert_type=AlertType.VOLUME_SPIKE,
            symbol="600519",
            message="Test",
            current_value=100.0,
            threshold_value=3.0,
            timestamp="2026-05-01T12:00:00Z",
            severity="info",
        )
        result = engine.notify(event)
        assert result is False


# ===================================================================
# Global engine singleton tests
# ===================================================================

class TestEngineSingleton:
    def test_get_engine_singleton(self):
        eng1 = get_engine()
        eng2 = get_engine()
        assert eng1 is eng2


# ===================================================================
# CLI tests
# ===================================================================

class TestCLIAlertCommands:
    @pytest.fixture
    def runner(self):
        from click.testing import CliRunner
        return CliRunner()

    @pytest.fixture
    def cli(self):
        from kronos_fincept.cli.main import cli
        return cli

    def test_alert_help(self, runner, cli):
        result = runner.invoke(cli, ["alert", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "remove" in result.output
        assert "check" in result.output
        assert "monitor" in result.output

    def test_list_empty(self, runner, cli):
        result = runner.invoke(cli, ["alert", "list"])
        # Should not crash with no rules
        assert result.exit_code == 0


# ===================================================================
# API tests
# ===================================================================

class TestAlertAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from kronos_fincept.api.app import create_app
        app = create_app()
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def reset_engine(self):
        """Clear engine rules between tests to avoid cross-test pollution."""
        from kronos_fincept.alert_engine import _engine
        if _engine is not None:
            _engine._rules.clear()
        yield

    def test_list_rules_empty(self, client):
        resp = client.get("/api/alert/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["rules"] == []

    def test_create_rule(self, client):
        resp = client.post("/api/alert/rules", json={
            "name": "Test API Rule",
            "alert_type": "price_change",
            "symbol": "600519",
            "market": "cn",
            "params": {"threshold_pct": 3.0},
            "channel": "feishu",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_type"] == "price_change"
        assert data["symbol"] == "600519"
        assert "id" in data

    def test_create_rule_invalid_type(self, client):
        resp = client.post("/api/alert/rules", json={
            "name": "Bad Type",
            "alert_type": "nonexistent",
            "symbol": "600519",
        })
        assert resp.status_code == 400

    def test_delete_rule(self, client):
        # Create first
        create_resp = client.post("/api/alert/rules", json={
            "name": "To Delete",
            "alert_type": "price_change",
            "symbol": "600519",
            "params": {"threshold_pct": 5.0},
        })
        rule_id = create_resp.json()["id"]

        # Delete
        resp = client.delete(f"/api/alert/rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_nonexistent(self, client):
        resp = client.delete("/api/alert/rules/nonexistent_id")
        assert resp.status_code == 404

    def test_check_rules(self, client):
        resp = client.post("/api/alert/check")
        assert resp.status_code == 200
        data = resp.json()
        assert "checked" in data
        assert "triggered" in data
        assert "events" in data
