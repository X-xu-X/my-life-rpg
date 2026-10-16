"""Explicit diary and review records; no inferred legacy classification or rewards."""
from datetime import datetime
from sqlalchemy import Integer, String, Text, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.time_types import DateTime
from app.services.time_service import utc_now


class DiaryRevision(Base):
    __tablename__ = 'diary_revisions'
    __table_args__ = (UniqueConstraint('event_id', 'version', name='uq_diary_revision'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'))
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ReviewSession(Base):
    __tablename__ = 'review_sessions'
    __table_args__ = (UniqueConstraint('user_id', 'diary_id', 'source_version', name='uq_diary_session'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    diary_id: Mapped[int] = mapped_column(ForeignKey('events.id'))
    source_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(20), default='draft')
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ReviewTurn(Base):
    __tablename__ = 'review_turns'
    __table_args__ = (UniqueConstraint('session_id', 'ordinal', name='uq_review_turn'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    session_id: Mapped[int] = mapped_column(ForeignKey('review_sessions.id'))
    ordinal: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default='')
    state: Mapped[str] = mapped_column(String(20), default='unanswered')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ReviewAnalysis(Base):
    __tablename__ = 'review_analyses'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    session_id: Mapped[int] = mapped_column(ForeignKey('review_sessions.id'))
    session_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class LifeChecklist(Base):
    __tablename__ = 'life_checklists'
    __table_args__ = (UniqueConstraint('user_id', 'local_date', name='uq_checklist_day'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    local_date: Mapped[str] = mapped_column(String(10))
    version: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
