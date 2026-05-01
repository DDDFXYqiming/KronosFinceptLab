"""kronos alert — Alert rule management and monitoring.

Examples:
    kronos alert add --type price_change --symbol 600036 --threshold 3.0
    kronos alert add --type rsi_oversold --symbol 600036 --period 14
    kronos alert add --type price_above --symbol AAPL --market us --level 200
    kronos alert add --type prediction_deviation --symbol 600036 --deviation 8.0 --channel email --email-to user@example.com
    kronos alert list
    kronos alert remove abc123def456
    kronos alert check
    kronos alert monitor --interval 5
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

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
from kronos_fincept.cli.output import output_json


# Mapping from CLI type string to factory function and required params
_RULE_FACTORIES: dict[str, tuple[Any, dict[str, tuple[str, ...]]]] = {
    "price_change": (
        price_change_rule,
        {
            "threshold": ("threshold_pct", float),
        },
    ),
    "price_above": (
        price_above_rule,
        {
            "level": ("level", float),
        },
    ),
    "price_below": (
        price_below_rule,
        {
            "level": ("level", float),
        },
    ),
    "rsi_overbought": (
        rsi_overbought_rule,
        {
            "period": ("period", int),
        },
    ),
    "rsi_oversold": (
        rsi_oversold_rule,
        {
            "period": ("period", int),
        },
    ),
    "macd_crossover": (macd_crossover_rule, {}),
    "prediction_deviation": (
        prediction_deviation_rule,
        {
            "deviation": ("deviation_pct", float),
        },
    ),
    "volume_spike": (
        volume_spike_rule,
        {
            "multiplier": ("multiplier", float),
        },
    ),
}


def _get_engine() -> AlertEngine:
    """Get alert engine with project-root persistence."""
    project_root = Path(__file__).resolve().parents[4]  # src/kronos_fincept/cli/commands/ -> project root
    storage_path = project_root / ".hermes" / "alerts.json"
    return get_engine(storage_path=str(storage_path))


@click.group("alert")
@click.pass_context
def alert_group(ctx: click.Context) -> None:
    """Manage and monitor alert rules."""


@alert_group.command("add")
@click.option("--type", "alert_type", type=click.Choice(list(_RULE_FACTORIES.keys())),
              required=True, help="Alert type")
@click.option("--symbol", "-s", type=str, required=True, help="Ticker symbol")
@click.option("--market", "-m", type=str, default="cn",
              help="Market: cn (A-stock), us, hk, crypto (default: cn)")
@click.option("--threshold", type=float, default=None,
              help="Price change threshold %% (for price_change)")
@click.option("--level", type=float, default=None,
              help="Price level (for price_above / price_below)")
@click.option("--period", type=int, default=None,
              help="RSI period (for rsi_overbought / rsi_oversold)")
@click.option("--deviation", type=float, default=None,
              help="Prediction deviation %% threshold (for prediction_deviation)")
@click.option("--multiplier", type=float, default=None,
              help="Volume multiplier (for volume_spike)")
@click.option("--channel", type=click.Choice(["feishu", "email"]), default="feishu",
              help="Notification channel (default: feishu)")
@click.option("--webhook-url", type=str, default=None,
              help="Feishu webhook URL override")
@click.option("--email-to", type=str, default=None,
              help="Email recipient override")
@click.option("--name", type=str, default=None, help="Human-readable rule name")
@click.pass_context
def add_rule(
    ctx: click.Context,
    alert_type: str,
    symbol: str,
    market: str,
    threshold: float | None,
    level: float | None,
    period: int | None,
    deviation: float | None,
    multiplier: float | None,
    channel: str,
    webhook_url: str | None,
    email_to: str | None,
    name: str | None,
) -> None:
    """Add a new alert rule."""
    if alert_type not in _RULE_FACTORIES:
        click.echo(f"Error: Unknown alert type '{alert_type}'", err=True)
        raise SystemExit(1)

    factory, param_map = _RULE_FACTORIES[alert_type]
    kwargs: dict[str, Any] = {
        "symbol": symbol,
        "market": market,
        "channel": NotificationChannel(channel),
    }

    if webhook_url:
        kwargs["webhook_url"] = webhook_url
    if email_to:
        kwargs["email_to"] = email_to

    # Apply type-specific params
    if alert_type == "price_change" and threshold is not None:
        kwargs["threshold_pct"] = threshold
    elif alert_type in ("price_above", "price_below") and level is not None:
        kwargs["level"] = level
    elif alert_type in ("rsi_overbought", "rsi_oversold") and period is not None:
        kwargs["period"] = period
    elif alert_type == "prediction_deviation" and deviation is not None:
        kwargs["deviation_pct"] = deviation
    elif alert_type == "volume_spike" and multiplier is not None:
        kwargs["multiplier"] = multiplier

    # Set a custom name if provided
    if name:
        kwargs["name"] = name

    try:
        rule = factory(**kwargs)
        engine = _get_engine()
        engine.register_rule(rule)
        click.echo(f"Rule added: {rule.id} — {rule.name}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@alert_group.command("list")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output as JSON")
@click.option("--type", "filter_type", type=str, default=None,
              help="Filter by alert type")
@click.pass_context
def list_rules(ctx: click.Context, as_json: bool, filter_type: str | None) -> None:
    """List all registered alert rules."""
    engine = _get_engine()
    rules = engine.list_rules()

    if filter_type:
        try:
            at = AlertType(filter_type)
            rules = [r for r in rules if r.alert_type == at]
        except ValueError:
            click.echo(f"Error: Unknown alert type '{filter_type}'", err=True)
            raise SystemExit(1)

    if not rules:
        click.echo("No alert rules registered.")
        return

    if as_json:
        data = {"rules": [r.to_dict() for r in rules]}
        output_json(data)
        return

    # Plain text output
    click.echo(f"Alert Rules ({len(rules)}):")
    click.echo("")
    for r in rules:
        status = "enabled" if r.enabled else "disabled"
        click.echo(
            f"  ID:      {r.id}\n"
            f"  Name:    {r.name}\n"
            f"  Type:    {r.alert_type.value}\n"
            f"  Symbol:  {r.symbol} ({r.market})\n"
            f"  Channel: {r.channel.value}\n"
            f"  Status:  {status}\n"
        )


@alert_group.command("remove")
@click.argument("rule_id", type=str, required=True)
@click.pass_context
def remove_rule(ctx: click.Context, rule_id: str) -> None:
    """Remove an alert rule by ID."""
    engine = _get_engine()
    if engine.unregister_rule(rule_id):
        click.echo(f"Rule removed: {rule_id}")
    else:
        click.echo(f"Error: Rule '{rule_id}' not found", err=True)
        raise SystemExit(1)


@alert_group.command("check")
@click.option("--rule-id", type=str, default=None,
              help="Check only this specific rule")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output as JSON")
@click.pass_context
def check_rules(ctx: click.Context, rule_id: str | None, as_json: bool) -> None:
    """Run a one-time check of all (or a specific) alert rules."""
    engine = _get_engine()

    if rule_id:
        rule = engine.get_rule(rule_id)
        if rule is None:
            click.echo(f"Error: Rule '{rule_id}' not found", err=True)
            raise SystemExit(1)
        events = [engine.check_rule(rule)]
    else:
        events = engine.check_all()

    events = [e for e in events if e is not None]

    if as_json:
        data = {
            "ok": True,
            "checked": len(events) if rule_id else len(engine.list_rules()),
            "triggered": len(events),
            "events": [e.to_dict() for e in events],
        }
        output_json(data)
        return

    if not events:
        click.echo("No alerts triggered.")
        return

    click.echo(f"Triggered Alerts ({len(events)}):")
    click.echo("")
    for e in events:
        click.echo(
            f"  [{e.severity.upper()}] {e.rule_name}\n"
            f"  Symbol: {e.symbol}\n"
            f"  Message: {e.message}\n"
            f"  Current: {e.current_value:.4f}, Threshold: {e.threshold_value:.4f}\n"
            f"  Time: {e.timestamp}\n"
        )


@alert_group.command("monitor")
@click.option("--interval", "-i", type=int, default=5,
              help="Polling interval in minutes (default: 5)")
@click.option("--once", is_flag=True, default=False,
              help="Run one check cycle and exit (useful for cron)")
@click.pass_context
def monitor(ctx: click.Context, interval: int, once: bool) -> None:
    """Start continuous alert monitoring.

    Polls all rules at the specified interval and sends notifications
    for triggered alerts.
    """
    engine = _get_engine()
    rules = engine.list_rules()

    if not rules:
        click.echo("No alert rules registered. Add some rules first.")
        raise SystemExit(1)

    click.echo(f"Monitoring {len(rules)} alert rule(s) every {interval} minute(s)...")
    click.echo("")

    if once:
        _run_monitor_cycle(engine)
        return

    # Continuous loop
    try:
        while True:
            _run_monitor_cycle(engine)
            click.echo(f"Sleeping for {interval} minute(s)...")
            time.sleep(interval * 60)
    except KeyboardInterrupt:
        click.echo("\nMonitoring stopped.")
        raise SystemExit(0)


def _run_monitor_cycle(engine: AlertEngine) -> None:
    """Run one monitoring cycle: check rules and send notifications."""
    click.echo(f"[{datetime.now(timezone.utc).isoformat()}] Checking rules...")
    events = engine.check_all()

    if not events:
        click.echo("No alerts triggered.")
        return

    click.echo(f"  {len(events)} alert(s) triggered:")
    for e in events:
        click.echo(f"    [{e.severity.upper()}] {e.rule_name}: {e.message}")
        ok = engine.notify(e)
        if ok:
            click.echo(f"      -> Notification sent ({e.alert_type.value})")
        else:
            click.echo(f"      -> Notification FAILED", err=True)
