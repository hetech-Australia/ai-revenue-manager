"""
SQLAlchemy models — AI Revenue Manager Phase 1
Matches schema.sql. Target: SQLAlchemy 2.0 style, PostgreSQL.
"""
import uuid
import enum
from datetime import date, datetime

from sqlalchemy import (
    String, Text, Integer, Numeric, Date, DateTime, ForeignKey, Enum,
    Boolean, UniqueConstraint, CheckConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def gen_uuid():
    return uuid.uuid4()


# ---------------- ENUMS ----------------
class UserRole(str, enum.Enum):
    admin = "admin"
    hotel_manager = "hotel_manager"


class ReservationStatus(str, enum.Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    no_show = "no_show"


class UploadStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class DemandClass(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    very_high = "very_high"


class RecommendationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ReportType(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


# ---------------- HOTELS ----------------
class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Asia/Kolkata")
    total_rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    city: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    room_types: Mapped[list["RoomType"]] = relationship(back_populates="hotel")
    users: Mapped[list["User"]] = relationship(back_populates="hotel")


# ---------------- USERS ----------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.hotel_manager)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    hotel: Mapped["Hotel"] = relationship(back_populates="users")


# ---------------- ROOM TYPES ----------------
class RoomType(Base):
    __tablename__ = "room_types"
    __table_args__ = (UniqueConstraint("hotel_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False)
    base_rate: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    hotel: Mapped["Hotel"] = relationship(back_populates="room_types")


# ---------------- UPLOAD BATCHES ----------------
class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    column_mapping: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[UploadStatus] = mapped_column(Enum(UploadStatus, name="upload_status"), default=UploadStatus.processing)
    error_log: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------- RESERVATIONS ----------------
class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("check_out > check_in"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    room_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("room_types.id"))
    upload_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("upload_batches.id"))
    booking_id: Mapped[str] = mapped_column(Text, nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    booking_date: Mapped[date | None] = mapped_column(Date)
    rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    guests: Mapped[int | None] = mapped_column(Integer)
    channel: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReservationStatus] = mapped_column(Enum(ReservationStatus, name="reservation_status"), default=ReservationStatus.confirmed)
    source_row_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------- DAILY PERFORMANCE ----------------
class DailyPerformance(Base):
    __tablename__ = "daily_performance"
    __table_args__ = (UniqueConstraint("hotel_id", "room_type_id", "date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    room_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("room_types.id"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    rooms_sold: Mapped[int] = mapped_column(Integer, default=0)
    rooms_available: Mapped[int] = mapped_column(Integer, default=0)
    occupancy_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    adr: Mapped[float | None] = mapped_column(Numeric(10, 2))
    revpar: Mapped[float | None] = mapped_column(Numeric(10, 2))
    revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    pickup_7d: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------- FORECASTS ----------------
class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (UniqueConstraint("hotel_id", "room_type_id", "date", "model_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    room_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("room_types.id"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_occupancy_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))
    forecast_adr: Mapped[float | None] = mapped_column(Numeric(10, 2))
    forecast_revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    demand_class: Mapped[DemandClass | None] = mapped_column(Enum(DemandClass, name="demand_class"))
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    model_version: Mapped[str] = mapped_column(Text, default="rules-v1")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------- PRICING RECOMMENDATIONS ----------------
class PricingRecommendation(Base):
    __tablename__ = "pricing_recommendations"
    __table_args__ = (UniqueConstraint("hotel_id", "room_type_id", "date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    room_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("room_types.id"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    current_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    recommended_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    reason_text: Mapped[str | None] = mapped_column(Text)
    reason_factors: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    status: Mapped[RecommendationStatus] = mapped_column(Enum(RecommendationStatus, name="recommendation_status"), default=RecommendationStatus.pending)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------- AI COPILOT ----------------
class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["AIMessage"]] = relationship(back_populates="conversation")


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_conversations.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["AIConversation"] = relationship(back_populates="messages")


# ---------------- REPORTS ----------------
class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    hotel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hotels.id", ondelete="CASCADE"))
    type: Mapped[ReportType] = mapped_column(Enum(ReportType, name="report_type"))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    file_url: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
