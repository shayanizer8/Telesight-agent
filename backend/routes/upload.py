import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from db import customers, pipeline_status
from agents.pipeline import run_pipeline
from routes.mock_apis import get_churn_data, get_monthly_report
from parsers.csv_parser import parse_csv
from parsers.pdf_parser import parse_pdf
from parsers.worldbank_parser import fetch_worldbank_kpi
from parsers.news_parser import fetch_news_articles
from parsers.feed_parser import fetch_wikipedia_feed

logger = logging.getLogger(__name__)

router = APIRouter()

TEMP_DIR = Path(__file__).resolve().parents[1] / "temp"


def _ensure_temp_dir() -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _save_upload(upload_file: UploadFile, destination: Path) -> None:
    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)


def _cleanup_file(path: Path | None) -> None:
    if path and path.exists():
        path.unlink()


def _serialize_pipeline_status_metadata(document: dict) -> dict:
    ingested_data = document.get("ingested_data", {})
    json_data = ingested_data.get("json_data", {})
    return {
        "run_id": document.get("run_id"),
        "status": document.get("status"),
        "current_step": document.get("current_step"),
        "steps_completed": document.get("steps_completed", []),
        "steps_pending": document.get("steps_pending", []),
        "ingested_data": {
            "csv_records_count": ingested_data.get("csv_records_count", 0),
            "pdf_text_length": len(ingested_data.get("pdf_text", "") or ""),
            "json_data_keys_count": len(json_data) if isinstance(json_data, dict) else 0,
            "article_text_length": ingested_data.get("article_text_length", 0),
            "live_feed_event_count": 1 if ingested_data.get("live_feed_event") else 0,
        },
        "created_at": document.get("created_at"),
    }


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload(
    region: Optional[str] = Query(default=None, description="Filter churn data by region (live API mode only)"),
    use_live_apis: bool = Query(default=True, description="If True, fetch data from live APIs; if False, upload files manually"),
    csv_file: Optional[UploadFile] = File(default=None, description="CSV file (required when use_live_apis=False)"),
    pdf_file: Optional[UploadFile] = File(default=None, description="PDF file (required when use_live_apis=False)"),
) -> dict:
    if pipeline_status is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured. Set MONGODB_URI in .env.")

    _ensure_temp_dir()

    newsapi_key = os.getenv("NEWSAPI_KEY", "")
    csv_records: list[dict] = []
    pdf_text: str = ""
    data_sources: list[dict] = []

    # -----------------------------------------------------------------------
    # Mode A: Live API ingestion
    # -----------------------------------------------------------------------
    if use_live_apis:
        churn_response = get_churn_data(region=region)
        csv_records = churn_response.get("records", [])
        churn_source = {
            "input": "churn_data",
            "source": churn_response.get("source", "Telenor CRM API"),
            "records": len(csv_records),
        }
        logger.info("Fetched %d churn records from mock CRM API", len(csv_records))
        data_sources.append(churn_source)

        report_response = get_monthly_report()
        pdf_text = report_response.get("report_text", "")
        report_source = {
            "input": "monthly_report",
            "source": report_response.get("source", "Telenor Reports API"),
        }
        logger.info("Fetched monthly report from mock Reports API (%d chars)", len(pdf_text))
        data_sources.append(report_source)

    # -----------------------------------------------------------------------
    # Mode B: Manual file upload
    # -----------------------------------------------------------------------
    else:
        if csv_file is None or pdf_file is None:
            raise HTTPException(
                status_code=422,
                detail="csv_file and pdf_file are required when use_live_apis=False.",
            )

        csv_path: Optional[Path] = TEMP_DIR / f"{uuid.uuid4().hex}_{csv_file.filename or 'upload.csv'}"
        pdf_path: Optional[Path] = TEMP_DIR / f"{uuid.uuid4().hex}_{pdf_file.filename or 'upload.pdf'}"

        try:
            _save_upload(csv_file, csv_path)
            _save_upload(pdf_file, pdf_path)
            csv_records = parse_csv(str(csv_path))
            pdf_text = parse_pdf(str(pdf_path))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to parse uploaded files: {exc}") from exc
        finally:
            _cleanup_file(csv_path)
            _cleanup_file(pdf_path)

        data_sources.append({"input": "churn_data", "source": "Uploaded CSV file", "records": len(csv_records)})
        data_sources.append({"input": "monthly_report", "source": "Uploaded PDF file"})

    # -----------------------------------------------------------------------
    # Always-live: KPI, news, live feed (both modes)
    # -----------------------------------------------------------------------
    try:
        kpi_data = fetch_worldbank_kpi()
        kpi_source = {"input": "kpi_dashboard", "source": kpi_data.get("source", "World Bank API")}
        data_sources.append(kpi_source)
        logger.info("KPI data fetched from: %s", kpi_data.get("source"))
    except Exception as exc:
        logger.warning("KPI fetch failed, using empty dict: %s", exc)
        kpi_data = {}
        data_sources.append({"input": "kpi_dashboard", "source": "unavailable"})

    articles_fetched = 0
    try:
        article_text = fetch_news_articles(newsapi_key)
        # Count real articles: fallback text has no newlines from article titles
        articles_fetched = len([line for line in article_text.splitlines() if line.strip()]) if "\n" in article_text else 0
        data_sources.append({"input": "news_article", "source": "NewsAPI.org", "articles_fetched": articles_fetched})
        logger.info("News article text fetched (%d chars)", len(article_text))
    except Exception as exc:
        logger.warning("News fetch failed, using empty string: %s", exc)
        article_text = ""
        data_sources.append({"input": "news_article", "source": "unavailable", "articles_fetched": 0})

    try:
        live_feed_event = fetch_wikipedia_feed()
        feed_source = live_feed_event.get("source", "Wikipedia API")
        data_sources.append({"input": "live_feed", "source": feed_source})
        logger.info("Live feed event fetched from: %s", feed_source)
    except Exception as exc:
        logger.warning("Live feed fetch failed, using empty dict: %s", exc)
        live_feed_event = {}
        data_sources.append({"input": "live_feed", "source": "unavailable"})

    # -----------------------------------------------------------------------
    # Persist to MongoDB
    # -----------------------------------------------------------------------
    try:
        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        csv_records_with_run_id = [dict(record, run_id=run_id) for record in csv_records]

        if customers is not None and csv_records_with_run_id:
            customers.insert_many(csv_records_with_run_id)

        pipeline_document = {
            "run_id": run_id,
            "status": "ingested",
            "current_step": "ingestion complete",
            "steps_completed": ["ingest"],
            "steps_pending": ["temporal", "contradiction", "insight", "action"],
            "ingested_data": {
                "csv_records_count": len(csv_records),
                "pdf_text": pdf_text,
                "pdf_text_length": len(pdf_text),
                "json_data": kpi_data,
                "article_text": article_text,
                "article_text_length": len(article_text),
                "live_feed_event": live_feed_event,
            },
            "data_sources": data_sources,
            "created_at": created_at,
        }

        pipeline_status.insert_one(pipeline_document)

        return {
            "run_id": run_id,
            "status": "ingested",
            "data_sources": data_sources,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to persist pipeline data: {exc}") from exc


# ---------------------------------------------------------------------------
# Existing endpoints (unchanged)
# ---------------------------------------------------------------------------

@router.get("/pipeline/status/{run_id}")
def get_pipeline_status(run_id: str) -> dict:
    if pipeline_status is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured. Set MONGODB_URI in .env.")

    document = pipeline_status.find_one({"run_id": run_id})
    if document is None:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found.")

    return _serialize_pipeline_status_metadata(document)


@router.get("/feed/live")
def get_live_feed() -> dict:
    from parsers.feed_parser import generate_live_feed
    return generate_live_feed()


@router.post("/pipeline/run/{run_id}")
def run_pipeline_endpoint(run_id: str) -> dict:
    if pipeline_status is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured. Set MONGODB_URI in .env.")

    document = pipeline_status.find_one({"run_id": run_id})
    if document is None:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found.")

    ingested_data = document.get("ingested_data", {})

    csv_records: list[dict] = []
    stored_csv_records = ingested_data.get("csv_records")
    if isinstance(stored_csv_records, list) and stored_csv_records:
        csv_records = stored_csv_records
    elif customers is not None:
        csv_records = list(customers.find({"run_id": run_id}, {"_id": 0}))

    state_data = {
        "csv_records": csv_records,
        "pdf_text": ingested_data.get("pdf_text", ""),
        "json_data": ingested_data.get("json_data", {}),
        "article_text": ingested_data.get("article_text", ""),
        "live_feed_event": ingested_data.get("live_feed_event", {}),
        "temporal_analysis": {},
        "contradiction_report": {},
        "insight_report": {},
        "action_plan": {},
        "errors": [],
    }

    final_state = run_pipeline(run_id, state_data)
    response_state = dict(final_state)
    response_state.pop("csv_records", None)
    response_state["csv_records_count"] = len(csv_records)
    return response_state