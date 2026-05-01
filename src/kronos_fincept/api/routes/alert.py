"""REST API endpoints for alert rule management and one-time checks.

Endpoints:
    POST /api/alert/rules      — Register a new alert rule
    GET  /api/alert/rules      — List all registered rules
    DELETE /api/alert/rules/{rule_id} — Remove a rule
    POST /api/alert/check      — Run a one-time check of all (or specific) rules
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kronos_fincept.alert_engine import (
    AlertEngine,
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

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AlertRuleIn(BaseModel):
    """Input schema for creating an alert rule."""
    name: str = Field(..., description="Human-readable rule name")
    alert_type: str = Field(..., description="Alert type", examples=["price_change"])
    symbol: str = Field(..., description="Ticker symbol")
    market: str = Field(default="cn", description="Market: cn, us, hk, crypto")
    params: dict = Field(default_factory=dict, description="Type-specific parameters")
    enabled: bool = Field(default=True)
    channel: str = Field(default="feishu", description="Notification channel: feishu, email")
    webhook_url: str | None = Field(default=None, description="Feishu webhook URL override")
    email_to: str | None = Field(default=None, description="Email recipient override")


class AlertRuleOut(BaseModel):
    """Output schema for an alert rule."""
    id: str
    name: str
    alert_type: str
    symbol: str
    market: str
    params: dict
    enabled: bool
    channel: str
    webhook_url: str | None = None
    email_to: str | None = None


class AlertRulesListOut(BaseModel):
    """List of alert rules."""
    ok: bool
    rules: list[AlertRuleOut]


class AlertEventOut(BaseModel):
    """A triggered alert event."""
    rule_id: str
    rule_name: str
    alert_type: str
    symbol: str
    message: str
    current_value: float
    threshold_value: float
    timestamp: str
    severity: str


class AlertCheckOut(BaseModel):
    """Response from a one-time check."""
    ok: bool
    checked: int
    triggered: int
    events: list[AlertEventOut]


class AlertCheckIn(BaseModel):
    """Optional input for checking a specific rule."""
    rule_id: str | None = Field(default=None, description="Check only this rule ID")


class AlertDeleteOut(BaseModel):
    """Response from deleting a rule."""
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_RULE_FACTORIES = {
    "price_change": price_change_rule,
    "price_above": price_above_rule,
    "price_below": price_below_rule,
    "rsi_overbought": rsi_overbought_rule,
    "rsi_oversold": rsi_oversold_rule,
    "macd_crossover": macd_crossover_rule,
    "prediction_deviation": prediction_deviation_rule,
    "volume_spike": volume_spike_rule,
}


def _get_engine() -> AlertEngine:
    """Get the alert engine singleton."""
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[3]
    storage_path = project_root / ".hermes" / "alerts.json"
    return get_engine(storage_path=str(storage_path))


def _rule_to_out(rule: AlertRule) -> AlertRuleOut:
    """Convert internal AlertRule to Pydantic output model."""
    return AlertRuleOut(
        id=rule.id,
        name=rule.name,
        alert_type=rule.alert_type.value,
        symbol=rule.symbol,
        market=rule.market,
        params=rule.params,
        enabled=rule.enabled,
        channel=rule.channel.value,
        webhook_url=rule.webhook_url,
        email_to=rule.email_to,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/alert/rules", response_model=AlertRuleOut)
async def create_alert_rule(req: AlertRuleIn) -> AlertRuleOut:
    """Register a new alert rule."""
    engine = _get_engine()

    # Validate alert type
    if req.alert_type not in _RULE_FACTORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown alert type: '{req.alert_type}'. "
                   f"Supported types: {list(_RULE_FACTORIES.keys())}",
        )

    # Validate channel
    try:
        channel = NotificationChannel(req.channel)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown notification channel: '{req.channel}'. "
                   f"Supported: feishu, email",
        )

    # Build kwargs
    kwargs: dict[str, Any] = {
        "symbol": req.symbol,
        "market": req.market,
        "channel": channel,
    }

    if req.webhook_url:
        kwargs["webhook_url"] = req.webhook_url
    if req.email_to:
        kwargs["email_to"] = req.email_to

    # Merge type-specific params into kwargs
    factory = _RULE_FACTORIES[req.alert_type]
    kwargs.update(req.params)

    try:
        rule: AlertRule = factory(**kwargs)
        engine.register_rule(rule)
        logger.info(
            "Alert rule registered via API: %s (%s)", rule.id, rule.name,
        )
        return _rule_to_out(rule)
    except Exception as exc:
        logger.error("Failed to create alert rule: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/alert/rules", response_model=AlertRulesListOut)
async def list_alert_rules() -> AlertRulesListOut:
    """List all registered alert rules."""
    engine = _get_engine()
    rules = engine.list_rules()
    return AlertRulesListOut(
        ok=True,
        rules=[_rule_to_out(r) for r in rules],
    )


@router.delete("/alert/rules/{rule_id}", response_model=AlertDeleteOut)
async def delete_alert_rule(rule_id: str) -> AlertDeleteOut:
    """Remove an alert rule by ID."""
    engine = _get_engine()
    if engine.unregister_rule(rule_id):
        logger.info("Alert rule deleted via API: %s", rule_id)
        return AlertDeleteOut(ok=True, message=f"Rule '{rule_id}' deleted")
    raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")


@router.post("/alert/check", response_model=AlertCheckOut)
async def check_alert_rules(req: AlertCheckIn | None = None) -> AlertCheckOut:
    """Run a one-time check of all rules or a specific rule."""
    engine = _get_engine()

    if req and req.rule_id:
        rule = engine.get_rule(req.rule_id)
        if rule is None:
            raise HTTPException(
                status_code=404,
                detail=f"Rule '{req.rule_id}' not found",
            )
        events_raw = [engine.check_rule(rule)]
        checked = 1
    else:
        events_raw = engine.check_all()
        checked = len(engine.list_rules())

    events = [e for e in events_raw if e is not None]
    events_out = [
        AlertEventOut(
            rule_id=e.rule_id,
            rule_name=e.rule_name,
            alert_type=e.alert_type.value,
            symbol=e.symbol,
            message=e.message,
            current_value=e.current_value,
            threshold_value=e.threshold_value,
            timestamp=e.timestamp,
            severity=e.severity,
        )
        for e in events
    ]

    return AlertCheckOut(
        ok=True,
        checked=checked,
        triggered=len(events),
        events=events_out,
    )
