"""DBnomics macro provider — free economic data from 100+ sources.

DBnomics aggregates official statistics from the IMF, OECD, Eurostat, World Bank,
BIS, ECB, FRED, and many more.  This provider maps query keywords to relevant
datasets and fetches the latest observations for key macro indicators via the
free v22 API (no API key required).

API docs: https://api.db.nomics.world/v22/swagger-ui/dist/
"""

from __future__ import annotations

import re
from typing import Any

import requests

from kronos_fincept.macro.providers.base import MacroProvider
from kronos_fincept.macro.schemas import MacroQuery, MacroSignal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.db.nomics.world/v22"
_USER_AGENT = (
    "Mozilla/5.0 (compatible; KronosFinceptLab/10.9; "
    "+https://github.com/DDDFXYqiming/KronosFinceptLab)"
)
_REQUEST_TIMEOUT = 12  # seconds

# ---------------------------------------------------------------------------
# Series catalog
#
# Each entry is a tuple:
#   (provider_code, dataset_code, series_code, signal_type,
#    label, capability, countries_str)
#
# "countries_str" is a comma-separated list of ISO two-letter country codes
# that the series covers; used for keyword-based filtering.
# ---------------------------------------------------------------------------

SERIES_CATALOG: list[tuple[str, str, str, str, str, str, str]] = [
    # ---- GDP -----------------------------------------------------------------
    ("IMF", "WEO:2025-04", "USA.NGDPRPPPPC.pcent", "gdp_growth",
     "USA GDP growth (IMF WEO)", "gdp", "US"),
    ("IMF", "WEO:2025-04", "CHN.NGDPRPPPPC.pcent", "gdp_growth",
     "CHN GDP growth (IMF WEO)", "gdp", "CN"),
    ("IMF", "WEO:2025-04", "JPN.NGDPRPPPPC.pcent", "gdp_growth",
     "JPN GDP growth (IMF WEO)", "gdp", "JP"),
    ("IMF", "WEO:2025-04", "DEU.NGDPRPPPPC.pcent", "gdp_growth",
     "DEU GDP growth (IMF WEO)", "gdp", "DE"),
    ("IMF", "WEO:2025-04", "GBR.NGDPRPPPPC.pcent", "gdp_growth",
     "GBR GDP growth (IMF WEO)", "gdp", "GB"),
    ("IMF", "WEO:2025-04", "FRA.NGDPRPPPPC.pcent", "gdp_growth",
     "FRA GDP growth (IMF WEO)", "gdp", "FR"),
    ("IMF", "WEO:2025-04", "IND.NGDPRPPPPC.pcent", "gdp_growth",
     "IND GDP growth (IMF WEO)", "gdp", "IN"),
    ("IMF", "WEO:2025-04", "CAN.NGDPRPPPPC.pcent", "gdp_growth",
     "CAN GDP growth (IMF WEO)", "gdp", "CA"),
    ("IMF", "WEO:2025-04", "AUS.NGDPRPPPPC.pcent", "gdp_growth",
     "AUS GDP growth (IMF WEO)", "gdp", "AU"),
    ("IMF", "WEO:2025-04", "KOR.NGDPRPPPPC.pcent", "gdp_growth",
     "KOR GDP growth (IMF WEO)", "gdp", "KR"),
    ("IMF", "WEO:2025-04", "BRA.NGDPRPPPPC.pcent", "gdp_growth",
     "BRA GDP growth (IMF WEO)", "gdp", "BR"),
    ("OECD", "EO/EO147", "USA.GDPV_ANNPCT.pcent", "gdp_growth",
     "USA GDP growth (OECD)", "gdp", "US"),
    ("OECD", "EO/EO147", "DEU.GDPV_ANNPCT.pcent", "gdp_growth",
     "DEU GDP growth (OECD)", "gdp", "DE"),
    ("OECD", "EO/EO147", "JPN.GDPV_ANNPCT.pcent", "gdp_growth",
     "JPN GDP growth (OECD)", "gdp", "JP"),
    ("OECD", "EO/EO147", "GBR.GDPV_ANNPCT.pcent", "gdp_growth",
     "GBR GDP growth (OECD)", "gdp", "GB"),
    ("OECD", "EO/EO147", "FRA.GDPV_ANNPCT.pcent", "gdp_growth",
     "FRA GDP growth (OECD)", "gdp", "FR"),

    # ---- Inflation / CPI ----------------------------------------------------
    ("IMF", "WEO:2025-04", "USA.PCPIPCH.pcent", "inflation",
     "USA CPI inflation (IMF WEO)", "inflation", "US"),
    ("IMF", "WEO:2025-04", "CHN.PCPIPCH.pcent", "inflation",
     "CHN CPI inflation (IMF WEO)", "inflation", "CN"),
    ("IMF", "WEO:2025-04", "DEU.PCPIPCH.pcent", "inflation",
     "DEU CPI inflation (IMF WEO)", "inflation", "DE"),
    ("IMF", "WEO:2025-04", "GBR.PCPIPCH.pcent", "inflation",
     "GBR CPI inflation (IMF WEO)", "inflation", "GB"),
    ("IMF", "WEO:2025-04", "JPN.PCPIPCH.pcent", "inflation",
     "JPN CPI inflation (IMF WEO)", "inflation", "JP"),
    ("IMF", "WEO:2025-04", "FRA.PCPIPCH.pcent", "inflation",
     "FRA CPI inflation (IMF WEO)", "inflation", "FR"),
    ("IMF", "WEO:2025-04", "IND.PCPIPCH.pcent", "inflation",
     "IND CPI inflation (IMF WEO)", "inflation", "IN"),
    ("IMF", "WEO:2025-04", "CAN.PCPIPCH.pcent", "inflation",
     "CAN CPI inflation (IMF WEO)", "inflation", "CA"),
    ("IMF", "WEO:2025-04", "AUS.PCPIPCH.pcent", "inflation",
     "AUS CPI inflation (IMF WEO)", "inflation", "AU"),
    ("IMF", "WEO:2025-04", "KOR.PCPIPCH.pcent", "inflation",
     "KOR CPI inflation (IMF WEO)", "inflation", "KR"),
    ("IMF", "WEO:2025-04", "BRA.PCPIPCH.pcent", "inflation",
     "BRA CPI inflation (IMF WEO)", "inflation", "BR"),
    ("OECD", "EO/EO147", "USA.CPI.pcent", "inflation",
     "USA CPI (OECD)", "inflation", "US"),
    ("OECD", "EO/EO147", "DEU.CPI.pcent", "inflation",
     "DEU CPI (OECD)", "inflation", "DE"),
    ("OECD", "EO/EO147", "GBR.CPI.pcent", "inflation",
     "GBR CPI (OECD)", "inflation", "GB"),
    ("OECD", "EO/EO147", "FRA.CPI.pcent", "inflation",
     "FRA CPI (OECD)", "inflation", "FR"),
    ("OECD", "EO/EO147", "JPN.CPI.pcent", "inflation",
     "JPN CPI (OECD)", "inflation", "JP"),
    ("OECD", "EO/EO147", "CAN.CPI.pcent", "inflation",
     "CAN CPI (OECD)", "inflation", "CA"),

    # ---- Interest rates / policy rates --------------------------------------
    # FRED effective federal funds rate
    ("FRED", "DFF", "DFF", "policy_rate",
     "USA Fed Funds Rate (FRED)", "interest_rates", "US"),
    # ECB main refinancing operations rate
    ("ECB", "FM/M.U2.EUR.4F.KR.MRR_RT.LEV",
     "FM.M.U2.EUR.4F.KR.MRR_RT.LEV", "policy_rate",
     "ECB Main Refinancing Rate", "interest_rates", "EU"),
    # BIS central bank policy rates
    ("BIS", "WS_CBPOL/1.0", "US.PA.010200.A", "policy_rate",
     "USA Central Bank Policy Rate (BIS)", "interest_rates", "US"),
    ("BIS", "WS_CBPOL/1.0", "CN.PA.010200.A", "policy_rate",
     "CHN Central Bank Policy Rate (BIS)", "interest_rates", "CN"),
    ("BIS", "WS_CBPOL/1.0", "JP.PA.010200.A", "policy_rate",
     "JPN Central Bank Policy Rate (BIS)", "interest_rates", "JP"),
    ("BIS", "WS_CBPOL/1.0", "DE.PA.010200.A", "policy_rate",
     "DEU Central Bank Policy Rate (BIS)", "interest_rates", "DE"),
    ("BIS", "WS_CBPOL/1.0", "GB.PA.010200.A", "policy_rate",
     "GBR Central Bank Policy Rate (BIS)", "interest_rates", "GB"),

    # ---- Employment / unemployment ------------------------------------------
    ("IMF", "WEO:2025-04", "USA.LUR.pcent", "unemployment",
     "USA unemployment rate (IMF WEO)", "employment", "US"),
    ("IMF", "WEO:2025-04", "DEU.LUR.pcent", "unemployment",
     "DEU unemployment rate (IMF WEO)", "employment", "DE"),
    ("IMF", "WEO:2025-04", "GBR.LUR.pcent", "unemployment",
     "GBR unemployment rate (IMF WEO)", "employment", "GB"),
    ("IMF", "WEO:2025-04", "FRA.LUR.pcent", "unemployment",
     "FRA unemployment rate (IMF WEO)", "employment", "FR"),
    ("IMF", "WEO:2025-04", "JPN.LUR.pcent", "unemployment",
     "JPN unemployment rate (IMF WEO)", "employment", "JP"),
    ("IMF", "WEO:2025-04", "CHN.LUR.pcent", "unemployment",
     "CHN unemployment rate (IMF WEO)", "employment", "CN"),
    ("IMF", "WEO:2025-04", "CAN.LUR.pcent", "unemployment",
     "CAN unemployment rate (IMF WEO)", "employment", "CA"),
    ("IMF", "WEO:2025-04", "AUS.LUR.pcent", "unemployment",
     "AUS unemployment rate (IMF WEO)", "employment", "AU"),
    ("IMF", "WEO:2025-04", "IND.LUR.pcent", "unemployment",
     "IND unemployment rate (IMF WEO)", "employment", "IN"),

    # ---- Trade balance / current account ------------------------------------
    ("IMF", "WEO:2025-04", "USA.BCA_NGDPD.pcent", "current_account",
     "USA current account balance (%GDP) (IMF WEO)", "trade_balance", "US"),
    ("IMF", "WEO:2025-04", "CHN.BCA_NGDPD.pcent", "current_account",
     "CHN current account balance (%GDP) (IMF WEO)", "trade_balance", "CN"),
    ("IMF", "WEO:2025-04", "DEU.BCA_NGDPD.pcent", "current_account",
     "DEU current account balance (%GDP) (IMF WEO)", "trade_balance", "DE"),
    ("IMF", "WEO:2025-04", "JPN.BCA_NGDPD.pcent", "current_account",
     "JPN current account balance (%GDP) (IMF WEO)", "trade_balance", "JP"),
    ("IMF", "WEO:2025-04", "GBR.BCA_NGDPD.pcent", "current_account",
     "GBR current account balance (%GDP) (IMF WEO)", "trade_balance", "GB"),
    ("IMF", "WEO:2025-04", "FRA.BCA_NGDPD.pcent", "current_account",
     "FRA current account balance (%GDP) (IMF WEO)", "trade_balance", "FR"),
    ("IMF", "WEO:2025-04", "IND.BCA_NGDPD.pcent", "current_account",
     "IND current account balance (%GDP) (IMF WEO)", "trade_balance", "IN"),

    # ---- Government debt ----------------------------------------------------
    ("IMF", "WEO:2025-04", "USA.GGXWDG_NGDP.pcent", "government_debt",
     "USA government debt (%GDP) (IMF WEO)", "debt", "US"),
    ("IMF", "WEO:2025-04", "CHN.GGXWDG_NGDP.pcent", "government_debt",
     "CHN government debt (%GDP) (IMF WEO)", "debt", "CN"),
    ("IMF", "WEO:2025-04", "DEU.GGXWDG_NGDP.pcent", "government_debt",
     "DEU government debt (%GDP) (IMF WEO)", "debt", "DE"),
    ("IMF", "WEO:2025-04", "JPN.GGXWDG_NGDP.pcent", "government_debt",
     "JPN government debt (%GDP) (IMF WEO)", "debt", "JP"),
    ("IMF", "WEO:2025-04", "GBR.GGXWDG_NGDP.pcent", "government_debt",
     "GBR government debt (%GDP) (IMF WEO)", "debt", "GB"),
    ("IMF", "WEO:2025-04", "FRA.GGXWDG_NGDP.pcent", "government_debt",
     "FRA government debt (%GDP) (IMF WEO)", "debt", "FR"),
    ("IMF", "WEO:2025-04", "IND.GGXWDG_NGDP.pcent", "government_debt",
     "IND government debt (%GDP) (IMF WEO)", "debt", "IN"),
    ("IMF", "WEO:2025-04", "CAN.GGXWDG_NGDP.pcent", "government_debt",
     "CAN government debt (%GDP) (IMF WEO)", "debt", "CA"),
    ("IMF", "WEO:2025-04", "BRA.GGXWDG_NGDP.pcent", "government_debt",
     "BRA government debt (%GDP) (IMF WEO)", "debt", "BR"),
]

# ---------------------------------------------------------------------------
# Keyword-to-capability routing
# ---------------------------------------------------------------------------

_CAPABILITY_KEYWORDS: dict[str, str] = {
    "gdp": "gdp",
    "growth": "gdp",
    "economy": "gdp",
    "economic": "gdp",
    "gross domestic": "gdp",
    "inflation": "inflation",
    "cpi": "inflation",
    "consumer price": "inflation",
    "price": "inflation",
    "interest": "interest_rates",
    "rate": "interest_rates",
    "fed": "interest_rates",
    "federal reserve": "interest_rates",
    "central bank": "interest_rates",
    "policy rate": "interest_rates",
    "ecb": "interest_rates",
    "employment": "employment",
    "unemployment": "employment",
    "job": "employment",
    "labor": "employment",
    "labour": "employment",
    "jobless": "employment",
    "trade": "trade_balance",
    "export": "trade_balance",
    "import": "trade_balance",
    "current account": "trade_balance",
    "balance of": "trade_balance",
    "debt": "debt",
    "fiscal": "debt",
    "deficit": "debt",
    "surplus": "debt",
    "government debt": "debt",
    "sovereign": "debt",
    "public debt": "debt",
}

# ---------------------------------------------------------------------------
# Country keyword resolution
# ---------------------------------------------------------------------------

_COUNTRY_KEYWORDS: dict[str, str] = {
    "us": "US",
    "usa": "US",
    "united states": "US",
    "america": "US",
    "american": "US",
    "china": "CN",
    "chinese": "CN",
    "japan": "JP",
    "japanese": "JP",
    "germany": "DE",
    "german": "DE",
    "uk": "GB",
    "united kingdom": "GB",
    "britain": "GB",
    "british": "GB",
    "france": "FR",
    "french": "FR",
    "india": "IN",
    "canada": "CA",
    "canadian": "CA",
    "australia": "AU",
    "australian": "AU",
    "korea": "KR",
    "south korea": "KR",
    "brazil": "BR",
    "brazilian": "BR",
    "eurozone": "EU",
    "european": "EU",
    "eu": "EU",
    "europe": "EU",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(value: Any) -> float | None:
    """Safely convert a raw API value to float or None."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _query_text(query: MacroQuery) -> str:
    """Build a lower-cased search text from the query."""
    parts = [query.question or "", query.market or "", " ".join(query.symbols or ())]
    return " ".join(part for part in parts if part).lower()


def _infer_capabilities(text: str) -> set[str]:
    """Return the set of relevant capability IDs based on keyword matching."""
    caps: set[str] = set()
    for keyword, capability in _CAPABILITY_KEYWORDS.items():
        if keyword in text:
            caps.add(capability)
    return caps


def _infer_countries(text: str) -> set[str]:
    """Return the set of ISO country codes mentioned in the query text."""
    codes: set[str] = set()
    for keyword, code in _COUNTRY_KEYWORDS.items():
        if keyword in text:
            codes.add(code)
    return codes


def _make_signal(
    *,
    source: str,
    signal_type: str,
    value: float | None,
    interpretation: str,
    time_horizon: str = "mixed",
    confidence: float = 0.55,
    observed_at: str | None = None,
    source_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> MacroSignal:
    """Construct a MacroSignal following the digital_oracle pattern."""
    return MacroSignal(
        source=source,
        signal_type=signal_type,
        value=value,
        interpretation=interpretation,
        time_horizon=time_horizon,
        confidence=max(0.0, min(1.0, confidence)),
        observed_at=observed_at,
        source_url=source_url,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class DBnomicsProvider(MacroProvider):
    """Macro-economic indicators via the DBnomics v22 API.

    DBnomics aggregates 100+ official statistical sources (IMF, OECD, FRED,
    ECB, BIS, Eurostat, …).  This provider maps query keywords to relevant
    datasets and fetches the latest observation for each matched series.
    No API key required.
    """

    provider_id = "dbnomics"
    display_name = "DBnomics"
    capabilities = (
        "gdp",
        "inflation",
        "interest_rates",
        "employment",
        "trade_balance",
        "debt",
    )

    def __init__(self, timeout: int = _REQUEST_TIMEOUT) -> None:
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_signals(self, query: MacroQuery) -> list[MacroSignal]:
        """Fetch latest observations for DBnomics series matching *query*."""
        text = _query_text(query)
        candidates = self._resolve_candidates(text)
        if not candidates:
            # If no keywords matched, return a representative subset
            candidates = self._default_candidates()

        signals: list[MacroSignal] = []
        limit = max(1, query.limit)

        for entry in candidates:
            if len(signals) >= limit:
                break
            signal = self._fetch_one(entry)
            if signal is not None:
                signals.append(signal)

        return signals

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _resolve_candidates(
        self, text: str
    ) -> list[tuple[str, str, str, str, str, str, str]]:
        """Select relevant series catalog entries by keyword matching."""
        caps = _infer_capabilities(text)
        countries = _infer_countries(text)

        if not caps:
            # No specific capability matched — return empty; caller falls
            # back to default candidates.
            return []

        matched: list[tuple[str, str, str, str, str, str, str]] = []
        for entry in SERIES_CATALOG:
            _provider, _dataset, _series, _stype, _label, capability, countries_str = entry
            if capability in caps:
                if not countries or not countries_str:
                    matched.append(entry)
                else:
                    entry_codes = {c.strip() for c in countries_str.split(",")}
                    if countries & entry_codes:
                        matched.append(entry)

        # Prefer shorter (more specific) series codes as tiebreaker
        matched.sort(key=lambda e: len(e[2]))
        return matched

    def _default_candidates(
        self,
    ) -> list[tuple[str, str, str, str, str, str, str]]:
        """Return a broad representative subset when no keywords matched."""
        # One US series per capability
        defaults = [
            ("IMF", "WEO:2025-04", "USA.NGDPRPPPPC.pcent",
             "gdp_growth", "USA GDP growth (IMF WEO)", "gdp", "US"),
            ("IMF", "WEO:2025-04", "USA.PCPIPCH.pcent",
             "inflation", "USA CPI inflation (IMF WEO)", "inflation", "US"),
            ("FRED", "DFF", "DFF", "policy_rate",
             "USA Fed Funds Rate (FRED)", "interest_rates", "US"),
            ("IMF", "WEO:2025-04", "USA.LUR.pcent",
             "unemployment", "USA unemployment rate (IMF WEO)", "employment", "US"),
            ("IMF", "WEO:2025-04", "USA.BCA_NGDPD.pcent",
             "current_account", "USA current account (%GDP) (IMF WEO)",
             "trade_balance", "US"),
            ("IMF", "WEO:2025-04", "USA.GGXWDG_NGDP.pcent",
             "government_debt", "USA government debt (%GDP) (IMF WEO)",
             "debt", "US"),
        ]
        return defaults

    def _fetch_one(
        self,
        entry: tuple[str, str, str, str, str, str, str],
    ) -> MacroSignal | None:
        """Fetch the latest observation for a single series entry.

        Returns a ``MacroSignal`` or ``None`` if the request fails.
        """
        provider_code, dataset_code, series_code, signal_type, label, capability, _countries = entry
        url = f"{BASE_URL}/series/{provider_code}/{dataset_code}/{series_code}"

        try:
            resp = requests.get(
                url,
                params={"observations": "1", "limit": "1"},
                timeout=self._timeout,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            return None

        # Navigate the response structure
        series_container = payload.get("series") if isinstance(payload, dict) else None
        if not isinstance(series_container, dict):
            return None
        docs = series_container.get("docs")
        if not isinstance(docs, list) or not docs:
            return None
        data = docs[0]
        if not isinstance(data, dict):
            return None

        # Extract period value and date
        period_data = data.get("period") if isinstance(data, dict) else None
        if isinstance(period_data, dict):
            value = _to_float(period_data.get("value"))
            period = str(period_data.get("period") or "")
        else:
            value = _to_float(data.get("value"))
            period = str(data.get("period_start_day") or data.get("period") or "")

        # Build signal-type interpretation
        interpretation = self._interpretation(signal_type, label, value, period)

        source_url = (
            f"https://db.nomics.world/{provider_code}/{dataset_code}/{series_code}"
        )

        return _make_signal(
            source=self.provider_id,
            signal_type=signal_type,
            value=value,
            interpretation=interpretation,
            time_horizon="medium" if signal_type in ("policy_rate",) else "long",
            confidence=0.7 if value is not None else 0.4,
            observed_at=period or None,
            source_url=source_url,
            metadata={
                "provider": provider_code,
                "dataset": dataset_code,
                "series": series_code,
                "label": label,
                "capability": capability,
                "period": period,
                "data_quality": f"official_{provider_code.lower()}",
            },
        )

    @staticmethod
    def _interpretation(
        signal_type: str, label: str, value: float | None, period: str
    ) -> str:
        """Build a human-readable interpretation string."""
        value_str = f"{value:.2f}" if value is not None else "N/A"
        period_str = period if period else "latest"
        base = f"{label} = {value_str} ({period_str})"
        hints = {
            "gdp_growth": "GDP growth rate; positive values indicate expansion.",
            "inflation": "CPI inflation rate; target ~2% in most developed economies.",
            "policy_rate": "Central bank policy rate; primary monetary policy tool.",
            "unemployment": "Unemployment rate; lower is healthier for the economy.",
            "current_account": "Current account balance as % of GDP; surplus (+) or deficit (-).",
            "government_debt": "Government debt as % of GDP; higher may indicate fiscal strain.",
        }
        hint = hints.get(signal_type, "")
        return f"{base}. {hint}" if hint else f"{base}."
