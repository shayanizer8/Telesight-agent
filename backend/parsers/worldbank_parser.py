import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_STATIC_KPI = {
    "report_month": "April 2026",
    "region": "Lahore",
    "active_subscribers": 48200,
    "churn_rate_pct": 6.8,
    "avg_revenue_per_user_pkr": 340,
    "complaint_volume": 1840,
    "network_satisfaction_score": 61,
    "competitor_activity": "Zong launched PKR 500 unlimited package in March 2026",
}

_GDP_URL = (
    "https://api.worldbank.org/v2/country/PK/indicator/NY.GDP.MKTP.CD"
    "?format=json&mrv=1"
)
_POP_URL = (
    "https://api.worldbank.org/v2/country/PK/indicator/SP.POP.TOTL"
    "?format=json&mrv=1"
)


def _extract_latest_value(response_json: list) -> float | None:
    """World Bank returns [metadata_dict, [data_entries]]. Extract the first non-null value."""
    try:
        entries = response_json[1]
        for entry in entries:
            value = entry.get("value")
            if value is not None:
                return float(value)
    except (IndexError, KeyError, TypeError, ValueError):
        pass
    return None


def fetch_worldbank_kpi() -> dict:
    """
    Fetches Pakistan GDP and population from the World Bank Open Data API,
    then merges with static telecom KPIs.

    Falls back to static-only dict on any httpx error.
    """
    pulled_at = datetime.now(timezone.utc).isoformat()
    base = {
        "source": "World Bank Open Data API",
        "pulled_at": pulled_at,
        **_STATIC_KPI,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            gdp_response = client.get(_GDP_URL)
            gdp_response.raise_for_status()
            gdp_value = _extract_latest_value(gdp_response.json())

            pop_response = client.get(_POP_URL)
            pop_response.raise_for_status()
            pop_value = _extract_latest_value(pop_response.json())

        if gdp_value is not None:
            base["pakistan_gdp_usd"] = gdp_value
        if pop_value is not None:
            base["pakistan_population"] = pop_value

        logger.info(
            "World Bank data fetched successfully — GDP: %s, Population: %s",
            gdp_value,
            pop_value,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "World Bank API request failed, returning static KPI only: %s", exc
        )
    except Exception as exc:
        logger.warning(
            "Unexpected error fetching World Bank data, returning static KPI only: %s", exc
        )

    return base
