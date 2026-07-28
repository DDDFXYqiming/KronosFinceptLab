"""Economic calendar provider — ForexFactory calendar via requests-html.

Optional dependency: requests-html (pip install requests-html).
Falls back gracefully when not available or when scraping fails.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

CALENDAR_URL = "https://www.forexfactory.com/calendar?day={date_str}"

IMPACT_MAP = {
    3: "HIGH",
    2: "MEDIUM",
    1: "LOW",
}

try:
    from requests_html import HTMLSession
    _HTML_SESSION_AVAILABLE = True
except ImportError:
    _HTML_SESSION_AVAILABLE = False


def _scrape_forexfactory(date_str: str) -> list[dict[str, Any]]:
    if not _HTML_SESSION_AVAILABLE:
        return []

    try:
        session = HTMLSession()
        resp = session.get(CALENDAR_URL.format(date_str=date_str), timeout=20)
        resp.html.render(timeout=15, sleep=1)
    except Exception:
        return []

    events = []
    rows = resp.html.find("tr.calendar__row")
    for row in rows:
        try:
            currency_el = row.find("td.calendar__cell.calendar__currency", first=True)
            event_el = row.find("td.calendar__cell.calendar__event", first=True)
            impact_el = row.find("td.calendar__cell.calendar__impact", first=True)
            actual_el = row.find("td.calendar__cell.calendar__actual", first=True)
            forecast_el = row.find("td.calendar__cell.calendar__forecast", first=True)
            previous_el = row.find("td.calendar__cell.calendar__previous", first=True)
        except Exception:
            continue

        currency = currency_el.text.strip() if currency_el else ""
        event = event_el.text.strip() if event_el else ""
        actual = actual_el.text.strip() if actual_el else ""
        forecast = forecast_el.text.strip() if forecast_el else ""
        previous = previous_el.text.strip() if previous_el else ""

        # Count impact icons (red/orange/yellow)
        impact_count = 0
        if impact_el:
            impact_count = len(impact_el.find("span.icon--impact"))

        if not currency or not event:
            continue

        events.append({
            "currency": currency,
            "event": event,
            "impact": IMPACT_MAP.get(impact_count, "LOW"),
            "actual": actual,
            "forecast": forecast,
            "previous": previous,
        })

    try:
        session.close()
    except Exception:
        pass

    return events


class EconomicCalendarProvider(MacroProvider):
    provider_id = "economic_calendar"
    display_name = "Economic Calendar"
    capabilities = ("calendar", "events", "macro")
    requires_api_key = False

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        signals: list[MacroSignal] = []
        today_str = date.today().isoformat()

        events = _scrape_forexfactory(today_str)
        for event in events[:15]:
            impact = event.get("impact", "LOW")
            interpretation = (
                f"{event['event']} ({event['currency']}, impact={impact}, "
                f"actual={event['actual']}, forecast={event['forecast']}, previous={event['previous']})"
            )
            signal = MacroSignal(
                source=self.provider_id,
                signal_type="calendar",
                value=impact,
                interpretation=interpretation,
                time_horizon="1d",
                confidence=0.8 if impact == "HIGH" else 0.6,
                observed_at=today_str,
                metadata=event,
            )
            signals.append(signal)

        return signals
