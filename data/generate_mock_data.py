import json
import random
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "churn_data.csv"
JSON_PATH = BASE_DIR / "kpi_dashboard.json"
TXT_PATH = BASE_DIR / "monthly_report.txt"

RANDOM_SEED = 42
TOTAL_ROWS = 5000
AT_RISK_ROWS = 3200
NORMAL_ROWS = TOTAL_ROWS - AT_RISK_ROWS
REGIONS = ["Lahore North", "Lahore South", "Lahore Central"]
PLAN_TYPES = ["prepaid", "postpaid"]


def _generate_normal_row(customer_number: int) -> dict:
    usage_2_months_ago = random.randint(2000, 8000)
    usage_last_month = max(1000, int(usage_2_months_ago * random.uniform(0.92, 1.08)))
    usage_this_month = max(500, int(usage_last_month * random.uniform(0.95, 1.05)))

    return {
        "customer_id": f"C-{customer_number:05d}",
        "region": random.choice(REGIONS),
        "data_usage_mb_2_months_ago": usage_2_months_ago,
        "data_usage_mb_last_month": usage_last_month,
        "data_usage_mb_this_month": usage_this_month,
        "days_since_recharge": random.randint(1, 20),
        "complaints_last_30_days": random.randint(0, 1),
        "plan_type": random.choice(PLAN_TYPES),
        "account_age_months": random.randint(3, 60),
        "churn_risk": "low",
    }


def _generate_at_risk_row(customer_number: int) -> dict:
    usage_2_months_ago = random.randint(2000, 8000)
    usage_last_month = max(1000, int(usage_2_months_ago * random.uniform(0.85, 1.02)))
    usage_this_month = max(100, int(usage_last_month * random.uniform(0.20, 0.40)))

    return {
        "customer_id": f"C-{customer_number:05d}",
        "region": random.choice(REGIONS),
        "data_usage_mb_2_months_ago": usage_2_months_ago,
        "data_usage_mb_last_month": usage_last_month,
        "data_usage_mb_this_month": usage_this_month,
        "days_since_recharge": random.randint(30, 89),
        "complaints_last_30_days": random.randint(2, 5),
        "plan_type": random.choice(PLAN_TYPES),
        "account_age_months": random.randint(3, 60),
        "churn_risk": "high",
    }


def generate_churn_data() -> pd.DataFrame:
    rows = []

    for customer_number in range(1, AT_RISK_ROWS + 1):
        rows.append(_generate_at_risk_row(customer_number))

    for customer_number in range(AT_RISK_ROWS + 1, TOTAL_ROWS + 1):
        rows.append(_generate_normal_row(customer_number))

    random.shuffle(rows)
    return pd.DataFrame(rows)


def generate_kpi_dashboard() -> dict:
    return {
        "report_month": "April 2026",
        "region": "Lahore",
        "active_subscribers": 48200,
        "churn_rate_pct": 6.8,
        "avg_revenue_per_user_pkr": 340,
        "complaint_volume": 1840,
        "network_satisfaction_score": 61,
        "competitor_activity": "Zong launched PKR 500 unlimited package in March 2026",
    }


def generate_monthly_report_text() -> str:
    return (
        "April 2026 showed mixed performance across Lahore's telecom market. "
        "Active subscriber engagement remained stable in core urban clusters, while field teams reported "
        "continued pressure from competitor pricing and sustained complaint volumes in high-density pockets.\n\n"
        "Operational reviews indicate that network stability improved modestly during the month, especially in "
        "Lahore Central, where throughput optimization reduced some peak-hour congestion. Customer satisfaction "
        "surveys show improvement of 15%, suggesting that service interventions and localized support had a "
        "positive effect on sentiment, even as churn risk stayed elevated in the broader base.\n\n"
        "Overall, the region closed April with stronger engagement signals in selected segments, but churn and "
        "complaint trends still require close monitoring as competitive offers continue to influence customer behavior."
    )


def main() -> None:
    random.seed(RANDOM_SEED)

    data_frame = generate_churn_data()
    data_frame.to_csv(CSV_PATH, index=False)

    with JSON_PATH.open("w", encoding="utf-8") as json_file:
        json.dump(generate_kpi_dashboard(), json_file, indent=2)

    TXT_PATH.write_text(generate_monthly_report_text(), encoding="utf-8")

    print(f"Wrote {CSV_PATH.name}, {JSON_PATH.name}, and {TXT_PATH.name} to {BASE_DIR}")


if __name__ == "__main__":
    main()