"""Real-time alert and monitoring engine for KronosFinceptLab.

Supports price, indicator, volume, and prediction-deviation alerts
with Feishu webhook and email notification channels.
"""

from __future__ import annotations

import json
import logging
import smtplib
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from kronos_fincept.config import settings
from kronos_fincept.security_utils import env_int, validate_webhook_url

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AlertType(Enum):
    """Types of alert conditions."""
    PRICE_CHANGE = "price_change"                # Price moved beyond threshold (%)
    PRICE_ABOVE = "price_above"                  # Price crossed above a level
    PRICE_BELOW = "price_below"                  # Price crossed below a level
    RSI_OVERBOUGHT = "rsi_overbought"            # RSI > 70
    RSI_OVERSOLD = "rsi_oversold"                # RSI < 30
    MACD_CROSSOVER = "macd_crossover"            # MACD line crosses signal line
    PREDICTION_DEVIATION = "prediction_deviation"  # Actual price vs prediction deviates
    VOLUME_SPIKE = "volume_spike"                # Volume > N * avg volume


class NotificationChannel(Enum):
    """Supported notification delivery channels."""
    FEISHU = "feishu"
    EMAIL = "email"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AlertRule:
    """Definition of a single alert rule."""
    id: str
    name: str
    alert_type: AlertType
    symbol: str
    market: str = "cn"
    params: dict = field(default_factory=dict)
    enabled: bool = True
    channel: NotificationChannel = NotificationChannel.FEISHU
    webhook_url: Optional[str] = None
    email_to: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        d = asdict(self)
        d["alert_type"] = self.alert_type.value
        d["channel"] = self.channel.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> AlertRule:
        """Deserialize from dict (from JSON storage)."""
        data = dict(data)
        data["alert_type"] = AlertType(data["alert_type"])
        data["channel"] = NotificationChannel(data.get("channel", "feishu"))
        return cls(**data)


@dataclass
class AlertEvent:
    """A triggered alert event ready for notification."""
    rule_id: str
    rule_name: str
    alert_type: AlertType
    symbol: str
    message: str
    current_value: float
    threshold_value: float
    timestamp: str
    severity: str  # "info", "warning", "critical"

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        d = asdict(self)
        d["alert_type"] = self.alert_type.value
        return d


# ---------------------------------------------------------------------------
# Alert Engine
# ---------------------------------------------------------------------------

class AlertEngine:
    """Core alert engine — manages rules, checks conditions, dispatches notifications.

    Usage::

        engine = AlertEngine()
        rule = price_change_rule("600036", threshold_pct=5.0)
        engine.register_rule(rule)
        events = engine.check_all()
        for event in events:
            engine.notify(event)
    """

    def __init__(
        self,
        data_manager: Any = None,
        storage_path: str | Path | None = None,
    ) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._data_manager = data_manager
        self._indicators: Any = None
        self._storage_path = Path(storage_path) if storage_path else (
            Path.cwd() / ".hermes" / "alerts.json"
        )
        self._load_rules()

    # ---- Rule management ------------------------------------------------

    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._validate_rule(rule)
        max_rules = max(1, env_int("KRONOS_ALERT_MAX_RULES", 100))
        if rule.id not in self._rules and len(self._rules) >= max_rules:
            raise ValueError(f"alert rule limit exceeded ({max_rules})")
        self._rules[rule.id] = rule
        self._save_rules()
        logger.info("Alert rule registered: %s (%s)", rule.id, rule.name)

    def unregister_rule(self, rule_id: str) -> bool:
        """Remove an alert rule. Returns True if removed."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            self._save_rules()
            logger.info("Alert rule removed: %s", rule_id)
            return True
        logger.warning("Alert rule not found: %s", rule_id)
        return False

    def get_rule(self, rule_id: str) -> AlertRule | None:
        """Get a single rule by ID."""
        return self._rules.get(rule_id)

    def list_rules(self) -> list[AlertRule]:
        """Return all registered rules."""
        return list(self._rules.values())

    # ---- Checking -------------------------------------------------------

    def check_rule(self, rule: AlertRule) -> Optional[AlertEvent]:
        """Check a single rule. Returns AlertEvent if triggered, else None."""
        if not rule.enabled:
            return None

        try:
            if rule.market == "cn":
                return self._check_a_stock_rule(rule)
            else:
                return self._check_global_rule(rule)
        except Exception as exc:
            logger.warning(
                "Error checking rule %s (%s): %s", rule.id, rule.name, exc,
            )
            return None

    def check_all(self) -> list[AlertEvent]:
        """Check all registered rules. Returns list of triggered events."""
        events: list[AlertEvent] = []
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            event = self.check_rule(rule)
            if event is not None:
                events.append(event)
        return events

    # ---- Notification ---------------------------------------------------

    def notify(self, event: AlertEvent) -> bool:
        """Send notification for an event. Returns True on success."""
        rule = self._rules.get(event.rule_id)
        if rule is None:
            logger.warning("Cannot notify — rule %s not found", event.rule_id)
            return False

        if rule.channel == NotificationChannel.FEISHU:
            webhook = rule.webhook_url or self._default_feishu_webhook()
            if webhook:
                try:
                    webhook = validate_webhook_url(webhook)
                except ValueError as exc:
                    logger.warning("Blocked unsafe alert webhook for rule %s: %s", rule.id, exc)
                    return False
            return self._notify_feishu(event, webhook)
        elif rule.channel == NotificationChannel.EMAIL:
            email_to = rule.email_to or self._default_email_to()
            return self._notify_email(event, email_to)
        else:
            logger.warning("Unknown notification channel: %s", rule.channel)
            return False

    # ---- Common alert evaluation ----------------------------------------

    def _evaluate_alert_conditions(
        self,
        rule: AlertRule,
        closes: list[float],
        current_price: float,
        prev_price: float,
        volumes: list[float] | None = None,
    ) -> Optional[AlertEvent]:
        """Evaluate alert conditions shared between A-stock and global markets.

        Returns AlertEvent if triggered, else None.
        """
        alert_type = rule.alert_type
        params = rule.params or {}

        if alert_type == AlertType.PRICE_CHANGE:
            threshold_pct = params.get("threshold_pct", 5.0)
            change_pct = abs((current_price - prev_price) / prev_price) * 100
            if change_pct >= threshold_pct:
                direction = "up" if current_price > prev_price else "down"
                return AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    alert_type=alert_type,
                    symbol=rule.symbol,
                    message=(
                        f"{rule.symbol} price moved {direction} {change_pct:.2f}% "
                        f"to {current_price:.2f} (threshold: {threshold_pct}%)"
                    ),
                    current_value=current_price,
                    threshold_value=threshold_pct,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="warning" if change_pct >= threshold_pct * 2 else "info",
                )

        elif alert_type == AlertType.PRICE_ABOVE:
            level = params.get("level", 0.0)
            if current_price > level:
                return AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    alert_type=alert_type,
                    symbol=rule.symbol,
                    message=f"{rule.symbol} price {current_price:.2f} crossed above {level:.2f}",
                    current_value=current_price,
                    threshold_value=level,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="info",
                )

        elif alert_type == AlertType.PRICE_BELOW:
            level = params.get("level", 0.0)
            if current_price < level:
                return AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    alert_type=alert_type,
                    symbol=rule.symbol,
                    message=f"{rule.symbol} price {current_price:.2f} crossed below {level:.2f}",
                    current_value=current_price,
                    threshold_value=level,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="warning",
                )

        elif alert_type in (AlertType.RSI_OVERBOUGHT, AlertType.RSI_OVERSOLD):
            rsi = self._calc_rsi(closes, params.get("rsi_period", 14))
            if rsi is None:
                return None
            if alert_type == AlertType.RSI_OVERBOUGHT and rsi > params.get("overbought", 70):
                return AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    alert_type=alert_type,
                    symbol=rule.symbol,
                    message=(
                        f"{rule.symbol} RSI is {rsi:.1f} -- overbought "
                        f"(threshold: >{params.get('overbought', 70)})"
                    ),
                    current_value=rsi,
                    threshold_value=float(params.get("overbought", 70)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="info",
                )
            if alert_type == AlertType.RSI_OVERSOLD and rsi < params.get("oversold", 30):
                return AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    alert_type=alert_type,
                    symbol=rule.symbol,
                    message=(
                        f"{rule.symbol} RSI is {rsi:.1f} -- oversold "
                        f"(threshold: <{params.get('oversold', 30)})"
                    ),
                    current_value=rsi,
                    threshold_value=float(params.get("oversold", 30)),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="warning",
                )

        elif alert_type == AlertType.VOLUME_SPIKE:
            if volumes is None or len(volumes) < 20:
                return None
            multiplier = params.get("multiplier", 3.0)
            avg_volume = sum(volumes[:-1]) / (len(volumes) - 1)
            current_volume = volumes[-1]
            if avg_volume > 0 and current_volume > avg_volume * multiplier:
                ratio = current_volume / avg_volume
                return AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    alert_type=alert_type,
                    symbol=rule.symbol,
                    message=(
                        f"{rule.symbol} volume spike: {current_volume:.0f} "
                        f"({ratio:.1f}x avg, threshold: {multiplier}x)"
                    ),
                    current_value=float(current_volume),
                    threshold_value=avg_volume * multiplier,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="info",
                )

        return None

    # ---- A-stock rule checking ------------------------------------------

    def _check_a_stock_rule(self, rule: AlertRule) -> Optional[AlertEvent]:
        """Check an A-stock alert rule."""
        try:
            from kronos_fincept.akshare_adapter import fetch_a_stock_ohlcv

            rows = fetch_a_stock_ohlcv(
                symbol=rule.symbol,
                start_date="20260101",
                end_date="20261231",
            )
        except Exception as exc:
            logger.warning("Failed to fetch A-stock data for %s: %s", rule.symbol, exc)
            return None

        if not rows or len(rows) < 2:
            return None

        closes = [r["close"] for r in rows]
        current_price = closes[-1]
        prev_price = closes[-2] if len(closes) >= 2 else current_price
        volumes = [r.get("volume", 0) for r in rows]

        # Check common conditions first
        event = self._evaluate_alert_conditions(rule, closes, current_price, prev_price, volumes)
        if event is not None:
            return event

        # A-stock specific: MACD crossover
        alert_type = rule.alert_type
        if alert_type == AlertType.MACD_CROSSOVER:
            macd_info = self._calc_macd(closes)
            if macd_info is None:
                return None
            macd_line, signal_line = macd_info
            if len(macd_line) < 2 or len(signal_line) < 2:
                return None
            prev_macd, cur_macd = macd_line[-2], macd_line[-1]
            prev_signal, cur_signal = signal_line[-2], signal_line[-1]
            if prev_macd <= prev_signal and cur_macd > cur_signal:
                direction = "bullish"
            elif prev_macd >= prev_signal and cur_macd < cur_signal:
                direction = "bearish"
            else:
                return None
            return AlertEvent(
                rule_id=rule.id,
                rule_name=rule.name,
                alert_type=alert_type,
                symbol=rule.symbol,
                message=(
                    f"{rule.symbol} MACD {direction} crossover: "
                    f"MACD={cur_macd:.4f}, Signal={cur_signal:.4f}"
                ),
                current_value=cur_macd,
                threshold_value=cur_signal,
                timestamp=datetime.now(timezone.utc).isoformat(),
                severity="info",
            )

        # A-stock specific: Prediction deviation
        elif alert_type == AlertType.PREDICTION_DEVIATION:
            params = rule.params or {}
            deviation_pct = params.get("deviation_pct", 10.0)
            pred_price = self._get_latest_prediction(rule.symbol)
            if pred_price is None or pred_price == 0:
                return None
            deviation = abs(current_price - pred_price) / pred_price * 100
            if deviation >= deviation_pct:
                direction = "above" if current_price > pred_price else "below"
                return AlertEvent(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    alert_type=alert_type,
                    symbol=rule.symbol,
                    message=(
                        f"{rule.symbol} actual {current_price:.2f} is {deviation:.1f}% "
                        f"{direction} prediction {pred_price:.2f} "
                        f"(threshold: {deviation_pct}%)"
                    ),
                    current_value=current_price,
                    threshold_value=pred_price,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    severity="critical" if deviation >= deviation_pct * 2 else "warning",
                )

        return None

    def _check_global_rule(self, rule: AlertRule) -> Optional[AlertEvent]:
        """Check a global (non-A-share) alert rule."""
        try:
            from kronos_fincept.financial.global_market import GlobalMarketSource

            gms = GlobalMarketSource()
            df = gms.get_stock_data(
                symbol=rule.symbol,
                market=rule.market,
                period="3mo",
                interval="1d",
            )
        except Exception as exc:
            logger.warning("Failed to fetch global data for %s: %s", rule.symbol, exc)
            return None

        if df is None or df.empty or len(df) < 2:
            return None

        closes = df["Close"].tolist()
        current_price = float(closes[-1])
        prev_price = float(closes[-2]) if len(closes) >= 2 else current_price
        volumes = df["Volume"].tolist() if "Volume" in df.columns else None

        return self._evaluate_alert_conditions(rule, closes, current_price, prev_price, volumes)

    # ---- Indicator helpers ----------------------------------------------

    def _calc_rsi(self, closes: list[float], period: int = 14) -> float | None:
        """Calculate RSI from close prices. Returns current RSI or None."""
        if len(closes) < period + 1:
            return None
        try:
            from kronos_fincept.financial.indicators import TechnicalIndicators
            if self._indicators is None:
                self._indicators = TechnicalIndicators()
            rsi = self._indicators.calculate_rsi(closes, period)
            return rsi.current if rsi.values else None
        except Exception:
            # Fallback: manual RSI calculation
            deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
            gains = [d if d > 0 else 0 for d in deltas]
            losses = [-d if d < 0 else 0 for d in deltas]
            avg_gain = sum(gains[:period]) / period
            avg_loss = sum(losses[:period]) / period
            for i in range(period, len(deltas)):
                if avg_loss == 0:
                    return 100.0
                rs = avg_gain / avg_loss
                rsi_val = 100 - (100 / (1 + rs))
                avg_gain = (avg_gain * (period - 1) + gains[i]) / period
                avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            return rsi_val if avg_loss > 0 else 100.0

    def _calc_macd(
        self, closes: list[float],
    ) -> tuple[list[float], list[float]] | None:
        """Calculate MACD line and signal line. Returns (macd_line, signal_line) or None."""
        if len(closes) < 26 + 9:
            return None
        try:
            from kronos_fincept.financial.indicators import TechnicalIndicators
            if self._indicators is None:
                self._indicators = TechnicalIndicators()
            macd = self._indicators.calculate_macd(closes)
            if macd.macd_line and macd.signal_line:
                return macd.macd_line, macd.signal_line
            return None
        except Exception:
            return None

    def _get_latest_prediction(self, symbol: str) -> float | None:
        """Get the latest predicted close for a symbol from the predictor."""
        try:
            from kronos_fincept.predictor import DryRunPredictor
            predictor = DryRunPredictor()
            # Use a minimal predicted value to check deviation
            result = predictor.predict(symbol=symbol, rows=[], pred_len=1)
            if result and "forecast" in result and result["forecast"]:
                return float(result["forecast"][0].get("close", 0))
            return None
        except Exception as exc:
            logger.debug("Could not get prediction for %s: %s", symbol, exc)
            return None

    # ---- Feishu notification -------------------------------------------

    def _default_feishu_webhook(self) -> str:
        """Get default Feishu webhook URL from config/environment."""
        import os
        return os.environ.get(
            "FEISHU_WEBHOOK_URL",
            getattr(settings, "feishu_webhook_url", ""),
        )

    def _notify_feishu(self, event: AlertEvent, webhook_url: str) -> bool:
        """Send alert to Feishu via incoming webhook."""
        if not webhook_url:
            logger.warning("Feishu webhook URL not configured — cannot send notification")
            return False

        try:
            import urllib.request
            import urllib.error

            severity_icon = {
                "info": "ℹ️",
                "warning": "⚠️",
                "critical": "🚨",
            }

            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": (
                                f"{severity_icon.get(event.severity, '')} "
                                f"[{event.severity.upper()}] Alert: {event.rule_name}"
                            ),
                        },
                        "template": {
                            "info": "blue",
                            "warning": "yellow",
                            "critical": "red",
                        }.get(event.severity, "blue"),
                    },
                    "elements": [
                        {"tag": "markdown", "content": f"**Symbol:** {event.symbol}"},
                        {"tag": "markdown", "content": f"**Type:** {event.alert_type.value}"},
                        {"tag": "markdown", "content": f"**Message:** {event.message}"},
                        {
                            "tag": "markdown",
                            "content": (
                                f"**Current Value:** {event.current_value:.4f}\n"
                                f"**Threshold Value:** {event.threshold_value:.4f}"
                            ),
                        },
                        {
                            "tag": "note",
                            "elements": [
                                {
                                    "tag": "plain_text",
                                    "content": f"Triggered at {event.timestamp}",
                                },
                            ],
                        },
                    ],
                },
            }

            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body)
                if result.get("code") == 0:
                    logger.info("Feishu alert sent for %s", event.rule_id)
                    return True
                else:
                    logger.warning(
                        "Feishu API error: %s", result.get("msg", body),
                    )
                    return False

        except Exception as exc:
            logger.warning("Failed to send Feishu notification: %s", exc)
            return False

    # ---- Email notification ---------------------------------------------

    def _default_email_to(self) -> str:
        """Get default email recipient from config/environment."""
        import os
        return os.environ.get("ALERT_EMAIL_TO", "")

    def _get_smtp_config(self) -> dict:
        """Get SMTP configuration from environment."""
        import os
        return {
            "host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            "port": int(os.environ.get("SMTP_PORT", "587")),
            "user": os.environ.get("SMTP_USER", ""),
            "password": os.environ.get("SMTP_PASSWORD", ""),
            "from_addr": os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "")),
        }

    def _notify_email(self, event: AlertEvent, email_to: str) -> bool:
        """Send alert via email over SMTP."""
        if not email_to:
            logger.warning("Email recipient not configured — cannot send notification")
            return False

        smtp = self._get_smtp_config()
        if not smtp["user"] or not smtp["password"]:
            logger.warning("SMTP credentials not configured — cannot send email")
            return False

        subject = (
            f"[KronosFinceptLab] {event.severity.upper()} Alert: "
            f"{event.rule_name} — {event.symbol}"
        )

        body = (
            f"Alert Rule: {event.rule_name} ({event.rule_id})\n"
            f"Symbol: {event.symbol}\n"
            f"Type: {event.alert_type.value}\n"
            f"Severity: {event.severity}\n"
            f"Message: {event.message}\n"
            f"Current Value: {event.current_value:.4f}\n"
            f"Threshold Value: {event.threshold_value:.4f}\n"
            f"Timestamp: {event.timestamp}\n"
        )

        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = smtp["from_addr"]
            msg["To"] = email_to

            with smtplib.SMTP(smtp["host"], smtp["port"], timeout=10) as server:
                server.starttls()
                server.login(smtp["user"], smtp["password"])
                server.send_message(msg)

            logger.info("Email alert sent to %s for %s", email_to, event.rule_id)
            return True

        except Exception as exc:
            logger.warning("Failed to send email notification: %s", exc)
            return False

    # ---- Persistence ----------------------------------------------------

    def _storage_path(self) -> Path:
        """Get path to JSON rules file."""
        if not hasattr(self, "_storage_path_internal"):
            self._storage_path_internal = Path.cwd() / ".hermes" / "alerts.json"
        return self._storage_path_internal

    def _load_rules(self) -> None:
        """Load rules from JSON file."""
        path = self._storage_path
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                try:
                    rule = AlertRule.from_dict(item)
                    self._validate_rule(rule)
                    self._rules[rule.id] = rule
                except Exception as exc:
                    logger.warning("Skipping invalid rule entry: %s", exc)
            logger.info("Loaded %d alert rules from %s", len(self._rules), path)
        except Exception as exc:
            logger.warning("Failed to load alert rules: %s", exc)

    def _save_rules(self) -> None:
        """Save rules to JSON file."""
        path = self._storage_path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = [rule.to_dict() for rule in self._rules.values()]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to save alert rules: %s", exc)

    @staticmethod
    def _validate_rule(rule: AlertRule) -> None:
        if len(str(rule.id)) > 64:
            raise ValueError("alert rule id is too long")
        if not rule.name or len(str(rule.name)) > 80:
            raise ValueError("alert rule name is invalid")
        if not rule.symbol or len(str(rule.symbol)) > 32:
            raise ValueError("alert rule symbol is invalid")
        if len(str(rule.market)) > 16:
            raise ValueError("alert rule market is invalid")
        params = rule.params or {}
        if len(params) > 10:
            raise ValueError("too many alert params")
        for key, item in params.items():
            if len(str(key)) > 40 or len(str(item)) > 120:
                raise ValueError("alert param is too large")


# ---------------------------------------------------------------------------
# Rule factories
# ---------------------------------------------------------------------------

def _generate_rule_id() -> str:
    """Generate a unique rule ID."""
    import uuid
    return uuid.uuid4().hex[:12]


def price_change_rule(
    symbol: str,
    threshold_pct: float = 5.0,
    market: str = "cn",
    channel: NotificationChannel = NotificationChannel.FEISHU,
    **kwargs: Any,
) -> AlertRule:
    """Alert when daily price change exceeds threshold_pct percent."""
    return AlertRule(
        id=_generate_rule_id(),
        name=f"{symbol} Price Change >{threshold_pct}%",
        alert_type=AlertType.PRICE_CHANGE,
        symbol=symbol,
        market=market,
        params={"threshold_pct": threshold_pct},
        channel=channel,
        **kwargs,
    )


def price_above_rule(
    symbol: str,
    level: float,
    market: str = "cn",
    channel: NotificationChannel = NotificationChannel.FEISHU,
    **kwargs: Any,
) -> AlertRule:
    """Alert when price crosses above a specific level."""
    return AlertRule(
        id=_generate_rule_id(),
        name=f"{symbol} Above {level}",
        alert_type=AlertType.PRICE_ABOVE,
        symbol=symbol,
        market=market,
        params={"level": level},
        channel=channel,
        **kwargs,
    )


def price_below_rule(
    symbol: str,
    level: float,
    market: str = "cn",
    channel: NotificationChannel = NotificationChannel.FEISHU,
    **kwargs: Any,
) -> AlertRule:
    """Alert when price crosses below a specific level."""
    return AlertRule(
        id=_generate_rule_id(),
        name=f"{symbol} Below {level}",
        alert_type=AlertType.PRICE_BELOW,
        symbol=symbol,
        market=market,
        params={"level": level},
        channel=channel,
        **kwargs,
    )


def rsi_overbought_rule(
    symbol: str,
    period: int = 14,
    market: str = "cn",
    channel: NotificationChannel = NotificationChannel.FEISHU,
    **kwargs: Any,
) -> AlertRule:
    """Alert when RSI exceeds overbought threshold (default >70)."""
    return AlertRule(
        id=_generate_rule_id(),
        name=f"{symbol} RSI Overbought",
        alert_type=AlertType.RSI_OVERBOUGHT,
        symbol=symbol,
        market=market,
        params={"rsi_period": period, "overbought": 70},
        channel=channel,
        **kwargs,
    )


def rsi_oversold_rule(
    symbol: str,
    period: int = 14,
    market: str = "cn",
    channel: NotificationChannel = NotificationChannel.FEISHU,
    **kwargs: Any,
) -> AlertRule:
    """Alert when RSI drops below oversold threshold (default <30)."""
    return AlertRule(
        id=_generate_rule_id(),
        name=f"{symbol} RSI Oversold",
        alert_type=AlertType.RSI_OVERSOLD,
        symbol=symbol,
        market=market,
        params={"rsi_period": period, "oversold": 30},
        channel=channel,
        **kwargs,
    )


def macd_crossover_rule(
    symbol: str,
    market: str = "cn",
    channel: NotificationChannel = NotificationChannel.FEISHU,
    **kwargs: Any,
) -> AlertRule:
    """Alert on MACD line crossing the signal line."""
    return AlertRule(
        id=_generate_rule_id(),
        name=f"{symbol} MACD Crossover",
        alert_type=AlertType.MACD_CROSSOVER,
        symbol=symbol,
        market=market,
        params={},
        channel=channel,
        **kwargs,
    )


def prediction_deviation_rule(
    symbol: str,
    deviation_pct: float = 10.0,
    market: str = "cn",
    channel: NotificationChannel = NotificationChannel.FEISHU,
    **kwargs: Any,
) -> AlertRule:
    """Alert when actual price deviates from latest prediction by deviation_pct."""
    return AlertRule(
        id=_generate_rule_id(),
        name=f"{symbol} Prediction Deviation >{deviation_pct}%",
        alert_type=AlertType.PREDICTION_DEVIATION,
        symbol=symbol,
        market=market,
        params={"deviation_pct": deviation_pct},
        channel=channel,
        **kwargs,
    )


def volume_spike_rule(
    symbol: str,
    multiplier: float = 3.0,
    market: str = "cn",
    channel: NotificationChannel = NotificationChannel.FEISHU,
    **kwargs: Any,
) -> AlertRule:
    """Alert when volume exceeds N times the average."""
    return AlertRule(
        id=_generate_rule_id(),
        name=f"{symbol} Volume Spike >{multiplier}x",
        alert_type=AlertType.VOLUME_SPIKE,
        symbol=symbol,
        market=market,
        params={"multiplier": multiplier},
        channel=channel,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Convenience: global engine singleton (lazy)
# ---------------------------------------------------------------------------

_engine: AlertEngine | None = None


def get_engine(storage_path: str | Path | None = None) -> AlertEngine:
    """Get the global AlertEngine singleton."""
    global _engine
    if _engine is None:
        _engine = AlertEngine(storage_path=storage_path)
    return _engine
