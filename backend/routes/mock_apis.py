import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import pdfplumber
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CHURN_CSV_PATH = DATA_DIR / "churn_data.csv"
MONTHLY_REPORT_PDF_PATH = DATA_DIR / "monthly_report.pdf"


def get_churn_data(region: str = None, limit: int = 5000) -> dict:
    """Simulates the Telenor Internal CRM API — returns customer churn records."""
    if not CHURN_CSV_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Churn data file not found at {CHURN_CSV_PATH}. Run data/generate_mock_data.py first.",
        )

    try:
        dataframe = pd.read_csv(CHURN_CSV_PATH)
    except Exception as exc:
        logger.error("Failed to read churn CSV: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to read churn data: {exc}") from exc

    region_label = "All"
    if region:
        filtered = dataframe[dataframe["region"].str.lower() == region.strip().lower()]
        if filtered.empty:
            logger.warning("No records found for region='%s'", region)
        dataframe = filtered
        region_label = region.strip()

    dataframe = dataframe.head(limit)
    records = dataframe.to_dict(orient="records")

    return {
        "source": "Telecom Internal CRM API",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "region": region_label,
        "report_month": "April 2026",
        "total_records": len(records),
        "records": records,
    }


def get_monthly_report() -> dict:
    """Simulates the Telenor Regional Performance Reports API — returns extracted PDF text."""
    if not MONTHLY_REPORT_PDF_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Monthly report PDF not found at {MONTHLY_REPORT_PDF_PATH}. Run data/generate_mock_data.py first.",
        )

    try:
        extracted_lines: list[str] = []
        with pdfplumber.open(str(MONTHLY_REPORT_PDF_PATH)) as pdf_file:
            for page in pdf_file.pages:
                page_text = page.extract_text() or ""
                for line in page_text.splitlines():
                    cleaned = " ".join(line.split()).strip()
                    if cleaned:
                        extracted_lines.append(cleaned)
        report_text = "\n".join(extracted_lines)
    except Exception as exc:
        logger.error("Failed to parse monthly report PDF: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {exc}") from exc

    return {
        "source": "Telecom Regional Performance Reports API",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "region": "Lahore",
        "report_month": "April 2026",
        "report_text": report_text,
    }


@router.get("/churn-data")
def churn_data_endpoint(
    region: Optional[str] = Query(default=None, description="Filter by region name"),
    limit: int = Query(default=5000, ge=1, le=50000, description="Max number of records to return"),
) -> dict:
    data = get_churn_data(region, limit)
    records = data.get("records", [])

    return {
        "source": data.get("source", "Telecom Internal CRM API"),
        "pulled_at": data.get("pulled_at", datetime.now(timezone.utc).isoformat()),
        "region": data.get("region", region.strip() if region else "All"),
        "report_month": data.get("report_month", "April 2026"),
        "total_records": len(records),
        "high_risk_count": sum(1 for record in records if str(record.get("churn_risk", "")).lower() == "high"),
        "low_risk_count": sum(1 for record in records if str(record.get("churn_risk", "")).lower() == "low"),
        "sample_records": records[:5],
        "message": "Full dataset available internally for agent processing",
    }


@router.get("/monthly-report")
def monthly_report_endpoint() -> dict:
    return get_monthly_report()
