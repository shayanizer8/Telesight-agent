import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from db import customers, pipeline_status
from agents.pipeline import run_pipeline
from parsers.article_parser import parse_article
from parsers.csv_parser import parse_csv
from parsers.feed_parser import generate_live_feed
from parsers.json_parser import parse_json
from parsers.pdf_parser import parse_pdf

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


def _serialize_document(document: dict) -> dict:
    serialized = dict(document)
    if "_id" in serialized:
        serialized["_id"] = str(serialized["_id"])
    return serialized


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


@router.post("/upload")
async def upload_pipeline_data(
    csv_file: UploadFile = File(...),
    pdf_file: UploadFile = File(...),
    json_file: UploadFile = File(...),
    article_url: Optional[str] = None,
) -> dict:
    if pipeline_status is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured. Set MONGODB_URI in .env.")

    _ensure_temp_dir()

    csv_path = TEMP_DIR / f"{uuid.uuid4().hex}_{csv_file.filename or 'upload.csv'}"
    pdf_path = TEMP_DIR / f"{uuid.uuid4().hex}_{pdf_file.filename or 'upload.pdf'}"
    json_path = TEMP_DIR / f"{uuid.uuid4().hex}_{json_file.filename or 'upload.json'}"

    article_text = ""
    article_text_length = 0

    try:
        _save_upload(csv_file, csv_path)
        _save_upload(pdf_file, pdf_path)
        _save_upload(json_file, json_path)

        csv_records = parse_csv(str(csv_path))
        pdf_text = parse_pdf(str(pdf_path))
        json_data = parse_json(str(json_path))

        if article_url and article_url.startswith("http"):
            article_text = parse_article(article_url)
            article_text_length = len(article_text)
        else:
            article_text = ""
            article_text_length = 0

        live_feed_event = generate_live_feed()
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
                "json_data": json_data,
                "article_text_length": article_text_length,
                "live_feed_event": live_feed_event,
            },
            "created_at": created_at,
        }

        pipeline_status.insert_one(pipeline_document)

        return {"run_id": run_id, "status": "ingested"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to ingest pipeline inputs: {exc}") from exc
    finally:
        _cleanup_file(csv_path)
        _cleanup_file(pdf_path)
        _cleanup_file(json_path)


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
    return generate_live_feed()


@router.post("/pipeline/run/{run_id}")
def run_pipeline_test(run_id: str) -> dict:
    if pipeline_status is None:
        raise HTTPException(status_code=500, detail="MongoDB is not configured. Set MONGODB_URI in .env.")

    document = pipeline_status.find_one({"run_id": run_id})
    if document is None:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found.")

    ingested_data = document.get("ingested_data", {})

    csv_records = []
    stored_csv_records = ingested_data.get("csv_records")
    if isinstance(stored_csv_records, list) and stored_csv_records:
        csv_records = stored_csv_records
    elif customers is not None:
        csv_records = list(customers.find({"run_id": run_id}, {"_id": 0}))

    state_data = {
        "csv_records": csv_records,
        "pdf_text": ingested_data.get("pdf_text", ""),
        "json_data": ingested_data.get("json_data", {}),
        "article_text": "",
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