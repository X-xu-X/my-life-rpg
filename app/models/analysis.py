"""持久任务和按日回顾；只关联既有事实，任务不自动结算。"""
from datetime import date, datetime
from sqlalchemy import Integer, String, Text, JSON, Date, ForeignKey, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.time_types import DateTime
from app.services.time_service import utc_now


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (UniqueConstraint("user_id", "request_key", name="uq_job_request"),
        Index("uq_active_event_job", "user_id", "event_id", unique=True,
            postgresql_where=text("state IN ('queued','running')"), sqlite_where=text("state IN ('queued','running')")),
        Index("ix_job_queue", "state", "next_retry_at", "lease_until"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    event_version: Mapped[int] = mapped_column(Integer)
    judgment_id: Mapped[int | None] = mapped_column(ForeignKey("ai_judgments.id"))
    judgment_version: Mapped[str] = mapped_column(String(60), default="")
    review_session_id: Mapped[int | None] = mapped_column(ForeignKey('review_sessions.id'), nullable=True)
    session_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operation: Mapped[str] = mapped_column(String(20), default="judge")
    request_key: Mapped[str] = mapped_column(String(36))
    payload_hash: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime)
    config_version: Mapped[dict] = mapped_column(JSON, default=dict)
    safe_error_code: Mapped[str] = mapped_column(String(50), default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class DailyReview(Base):
    __tablename__ = "daily_reviews"
    __table_args__ = (UniqueConstraint("user_id", "local_date", "timezone", name="uq_daily_review"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    local_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(60))
    note: Mapped[str] = mapped_column(Text, default="")
    completion: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ReviewLink(Base):
    __tablename__ = "review_links"
    __table_args__ = (UniqueConstraint("review_id", "event_id", name="uq_review_event"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    review_id: Mapped[int] = mapped_column(ForeignKey("daily_reviews.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    event_version: Mapped[int] = mapped_column(Integer)


class ModelUsage(Base):
    __tablename__ = "model_usage"
    __table_args__ = (UniqueConstraint("user_id", "local_date", name="uq_model_usage_day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    local_date: Mapped[date] = mapped_column(Date)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class GrowthReport(Base):
    __tablename__ = "growth_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    period: Mapped[str] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
