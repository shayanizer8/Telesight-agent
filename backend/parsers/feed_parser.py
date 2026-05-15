import logging
from datetime import datetime, timezone
from random import choice, randint

import httpx

logger = logging.getLogger(__name__)

_WIKIPEDIA_RC_URL = (
    "https://en.wikipedia.org/w/api.php"
    "?action=query&list=recentchanges&rcnamespace=0&rclimit=10&format=json"
)
_RELEVANT_KEYWORDS = {"pakistan", "telecom", "mobile", "telenor", "jazz", "zong"}


def generate_live_feed() -> dict:
    try:
        regions = ["Lahore North", "Lahore South", "Lahore Central"]
        triggers = ["no_recharge_35_days", "usage_drop_60pct", "complaint_spike"]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "customer_id": f"CUST-{randint(100000, 999999)}",
            "region": choice(regions),
            "trigger": choice(triggers),
        }
    except Exception as exc:
        raise RuntimeError(f"Failed to generate live feed event: {exc}") from exc


def fetch_wikipedia_feed() -> dict:
    """
    Polls the Wikipedia Recent Changes API for entries relevant to Pakistan telecom.

    If a relevant article is found, returns a structured signal event.
    Falls back to generate_live_feed() with an 'Internal Signal Generator' source tag.
    """
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(_WIKIPEDIA_RC_URL)
            response.raise_for_status()

        data = response.json()
        changes = data.get("query", {}).get("recentchanges", [])

        for change in changes:
            title: str = change.get("title", "")
            if any(keyword in title.lower() for keyword in _RELEVANT_KEYWORDS):
                logger.info("Wikipedia feed: relevant article found — '%s'", title)
                return {
                    "source": "Wikipedia Recent Changes API",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "title": title,
                    "signal_type": "external_event",
                    "trigger": "wikipedia_change_detected",
                }

        logger.info("Wikipedia feed: no relevant articles found — falling back to internal signal")
    except httpx.HTTPError as exc:
        logger.warning("Wikipedia API HTTP error — falling back to internal signal: %s", exc)
    except Exception as exc:
        logger.warning("Wikipedia API error — falling back to internal signal: %s", exc)

    fallback = generate_live_feed()
    fallback["source"] = "Internal Signal Generator"
    return fallback