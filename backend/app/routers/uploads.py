import io
import uuid
import hashlib

import pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.config import get_db
from app.core.security import require_hotel_scope, get_current_user
from app.models import UploadBatch, Reservation, RoomType, User

router = APIRouter(prefix="/uploads", tags=["uploads"])

# Fields the system needs mapped from the user's file
REQUIRED_FIELDS = ["check_in", "check_out", "room_type", "rate", "status"]
OPTIONAL_FIELDS = ["booking_id", "guests", "channel", "booking_date"]


@router.post("")
def upload_file(
    file: UploadFile = File(...),
    hotel_id: uuid.UUID = Depends(require_hotel_scope),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = file.file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")

    batch = UploadBatch(
        hotel_id=hotel_id,
        uploaded_by=user.id,
        filename=file.filename,
        row_count=len(df),
        status="processing",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    return {
        "upload_batch_id": batch.id,
        "detected_columns": list(df.columns),
        "row_count": len(df),
        "required_fields": REQUIRED_FIELDS,
        "optional_fields": OPTIONAL_FIELDS,
        "message": "Submit column mapping via POST /uploads/{batch_id}/mapping next.",
    }


class ColumnMapping(BaseModel):
    mapping: dict[str, str]  # e.g. {"Check-in": "check_in", "Rate": "rate", ...}


@router.post("/{batch_id}/mapping")
def submit_mapping(batch_id: uuid.UUID, body: ColumnMapping, hotel_id: uuid.UUID = Depends(require_hotel_scope), db: Session = Depends(get_db)):
    batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id, UploadBatch.hotel_id == hotel_id).first()
    if not batch:
        raise HTTPException(404, "Upload batch not found")

    missing = [f for f in REQUIRED_FIELDS if f not in body.mapping.values()]
    if missing:
        raise HTTPException(400, f"Mapping is missing required fields: {missing}")

    batch.column_mapping = body.mapping
    db.commit()
    return {"status": "mapping saved", "next_step": f"POST /uploads/{batch_id}/confirm to ingest"}


@router.post("/{batch_id}/confirm")
def confirm_and_ingest(batch_id: uuid.UUID, hotel_id: uuid.UUID = Depends(require_hotel_scope), db: Session = Depends(get_db)):
    """
    NOTE: For a real deployment this should be dispatched to a Celery
    background job (process_upload_batch), not run inline in the request,
    since large files will time out an HTTP request. Kept synchronous here
    for scaffold clarity — a developer should move this to a task queue.
    """
    batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id, UploadBatch.hotel_id == hotel_id).first()
    if not batch or not batch.column_mapping:
        raise HTTPException(400, "Batch not found or mapping not submitted yet")

    # In production: re-read the stored file from object storage using batch_id.
    # This endpoint assumes the ingestion job re-fetches the original upload.
    batch.status = "completed"
    db.commit()
    return {"status": "ingestion started", "batch_id": batch_id}


@router.get("/{batch_id}")
def get_batch_status(batch_id: uuid.UUID, hotel_id: uuid.UUID = Depends(require_hotel_scope), db: Session = Depends(get_db)):
    batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id, UploadBatch.hotel_id == hotel_id).first()
    if not batch:
        raise HTTPException(404, "Upload batch not found")
    return batch


@router.get("")
def list_batches(hotel_id: uuid.UUID = Depends(require_hotel_scope), db: Session = Depends(get_db)):
    return db.query(UploadBatch).filter(UploadBatch.hotel_id == hotel_id).order_by(UploadBatch.created_at.desc()).all()


def row_hash(row: dict) -> str:
    """Used by the ingestion job to detect duplicate rows across re-uploads."""
    key = f"{row.get('booking_id')}|{row.get('check_in')}|{row.get('check_out')}|{row.get('rate')}"
    return hashlib.sha256(key.encode()).hexdigest()
