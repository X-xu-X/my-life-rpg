"""增量身份、凭据和文字记录模型；历史业务流水不重算。"""
from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String, Text, JSON, Float, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.time_types import DateTime
from app.services.time_service import utc_now


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_secret: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)


class RecoveryToken(Base):
    __tablename__ = "recovery_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)


class LLMCredential(Base):
    __tablename__ = "llm_credentials"
    __table_args__ = (UniqueConstraint("user_id", "group", name="uq_credential_group"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    group: Mapped[str] = mapped_column(String(10))
    provider_id: Mapped[str] = mapped_column(String(30))
    base_url: Mapped[str | None] = mapped_column(String(300),nullable=True)
    model: Mapped[str] = mapped_column(String(100))
    encrypted_key: Mapped[str] = mapped_column(Text, default="")
    key_id: Mapped[str] = mapped_column(String(30), default="v1")
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class AnchorOverride(Base):
    __tablename__ = "anchor_overrides"
    __table_args__ = (UniqueConstraint("user_id", "anchor_id", name="uq_anchor_override"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    anchor_id: Mapped[int] = mapped_column(ForeignKey("anchors.id"))
    calibrated_value: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, default=1)


class RequestReceipt(Base):
    __tablename__ = "request_receipts"
    __table_args__ = (UniqueConstraint("user_id", "operation", "request_key", name="uq_request_receipt"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(50))
    request_key: Mapped[str] = mapped_column(String(36))
    payload_hash: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[int] = mapped_column(Integer)
    response_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class EventDerivation(Base):
    __tablename__ = "event_derivations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    event_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
