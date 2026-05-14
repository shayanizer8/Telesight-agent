from datetime import datetime, timezone
from random import choice, randint


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