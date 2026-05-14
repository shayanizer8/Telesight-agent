import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from db import pipeline_status
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

        pipeline_document = {
            "run_id": run_id,
            "status": "ingested",
            "current_step": "ingestion complete",
            "steps_completed": ["ingest"],
            "steps_pending": ["temporal", "contradiction", "insight", "action"],
            "ingested_data": {
                "csv_records": len(csv_records),
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

    return _serialize_document(document)


@router.get("/feed/live")
def get_live_feed() -> dict:
    return generate_live_feed()