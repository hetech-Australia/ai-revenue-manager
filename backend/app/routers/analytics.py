import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import get_db
from app.core.security import require_hotel_scope
from app.models import DailyPerformance

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/today")
def today_performance(hotel_id: uuid.UUID = Depends(require_hotel_scope), db: Session = Depends(get_db)):
    row = (
        db.query(DailyPerformance)
        .filter(
            DailyPerformance.hotel_id == hotel_id,
            DailyPerformance.room_type_id.is_(None),  # whole-hotel rollup row
            DailyPerformance.date == date.today(),
        )
        .first()
    )
    if not row:
        return {"occupancy_pct": None, "adr": None, "revpar": None, "revenue": None, "message": "No data for today yet"}
    return {
        "date": row.date,
        "occupancy_pct": row.occupancy_pct,
        "adr": row.adr,
        "revpar": row.revpar,
        "revenue": row.revenue,
        "rooms_sold": row.rooms_sold,
        "rooms_available": row.rooms_available,
        "pickup_7d": row.pickup_7d,
    }


@router.get("/daily")
def daily_series(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    hotel_id: uuid.UUID = Depends(require_hotel_scope),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(DailyPerformance)
        .filter(
            DailyPerformance.hotel_id == hotel_id,
            DailyPerformance.room_type_id.is_(None),
            DailyPerformance.date >= from_date,
            DailyPerformance.date <= to_date,
        )
        .order_by(DailyPerformance.date)
        .all()
    )
    return [
        {
            "date": r.date, "occupancy_pct": r.occupancy_pct, "adr": r.adr,
            "revpar": r.revpar, "revenue": r.revenue,
        }
        for r in rows
    ]


@router.get("/summary")
def summary(period: str = "30d", hotel_id: uuid.UUID = Depends(require_hotel_scope), db: Session = Depends(get_db)):
    days = {"30d": 30, "60d": 60, "90d": 90}.get(period, 30)
    start = date.today()
    end = start + timedelta(days=days)

    result = (
        db.query(
            func.avg(DailyPerformance.occupancy_pct).label("avg_occupancy"),
            func.avg(DailyPerformance.adr).label("avg_adr"),
            func.sum(DailyPerformance.revenue).label("total_revenue"),
        )
        .filter(
            DailyPerformance.hotel_id == hotel_id,
            DailyPerformance.room_type_id.is_(None),
            DailyPerformance.date >= start,
            DailyPerformance.date < end,
        )
        .first()
    )
    return {
        "period": period,
        "avg_occupancy_pct": round(result.avg_occupancy, 1) if result.avg_occupancy else None,
        "avg_adr": round(result.avg_adr, 2) if result.avg_adr else None,
        "total_forecast_revenue": round(result.total_revenue, 2) if result.total_revenue else None,
    }
