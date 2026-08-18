import uuid
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.config import get_db
from app.core.security import require_hotel_scope, get_current_user
from app.models import PricingRecommendation, Forecast, DailyPerformance, RoomType, User
from app.services.forecasting_engine import simulate_what_if

router = APIRouter(prefix="/pricing-recommendations", tags=["pricing"])


@router.get("")
def list_recommendations(
    status: str | None = None,
    hotel_id: uuid.UUID = Depends(require_hotel_scope),
    db: Session = Depends(get_db),
):
    q = db.query(PricingRecommendation).filter(PricingRecommendation.hotel_id == hotel_id)
    if status:
        q = q.filter(PricingRecommendation.status == status)
    return q.order_by(PricingRecommendation.date).all()


@router.get("/{rec_id}")
def get_recommendation(rec_id: uuid.UUID, hotel_id: uuid.UUID = Depends(require_hotel_scope), db: Session = Depends(get_db)):
    rec = db.query(PricingRecommendation).filter(
        PricingRecommendation.id == rec_id, PricingRecommendation.hotel_id == hotel_id
    ).first()
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    return rec


@router.post("/{rec_id}/approve")
def approve_recommendation(
    rec_id: uuid.UUID,
    hotel_id: uuid.UUID = Depends(require_hotel_scope),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rec = db.query(PricingRecommendation).filter(
        PricingRecommendation.id == rec_id, PricingRecommendation.hotel_id == hotel_id
    ).first()
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    rec.status = "approved"
    rec.decided_by = user.id
    rec.decided_at = datetime.utcnow()
    db.commit()
    return {"status": "approved"}


@router.post("/{rec_id}/reject")
def reject_recommendation(
    rec_id: uuid.UUID,
    hotel_id: uuid.UUID = Depends(require_hotel_scope),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rec = db.query(PricingRecommendation).filter(
        PricingRecommendation.id == rec_id, PricingRecommendation.hotel_id == hotel_id
    ).first()
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    rec.status = "rejected"
    rec.decided_by = user.id
    rec.decided_at = datetime.utcnow()
    db.commit()
    return {"status": "rejected"}


class WhatIfRequest(BaseModel):
    room_type_id: uuid.UUID
    date: date
    new_rate: float


@router.post("/what-if")
def what_if(req: WhatIfRequest, hotel_id: uuid.UUID = Depends(require_hotel_scope), db: Session = Depends(get_db)):
    forecast = db.query(Forecast).filter(
        Forecast.hotel_id == hotel_id, Forecast.room_type_id == req.room_type_id, Forecast.date == req.date
    ).first()
    room_type = db.query(RoomType).filter(RoomType.id == req.room_type_id).first()
    if not forecast or not room_type:
        raise HTTPException(404, "No forecast available for this date/room type yet")

    current_rec = db.query(PricingRecommendation).filter(
        PricingRecommendation.hotel_id == hotel_id,
        PricingRecommendation.room_type_id == req.room_type_id,
        PricingRecommendation.date == req.date,
    ).first()
    current_rate = current_rec.current_rate if current_rec else room_type.base_rate

    return simulate_what_if(
        current_rate=float(current_rate),
        new_rate=req.new_rate,
        forecast_occupancy_pct=float(forecast.forecast_occupancy_pct),
        rooms_available=room_type.total_units,
    )
