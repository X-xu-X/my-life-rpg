"""Security and operator metadata; excluded from personal game exports."""
from datetime import datetime
from sqlalchemy import ForeignKey,Integer,String,Text,JSON,Boolean
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.time_types import UTCDateTime as DateTime
from app.services.time_service import utc_now


class SitePolicy(Base):
    __tablename__='site_policies'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    payload:Mapped[dict]=mapped_column(JSON)


class EmailToken(Base):
    __tablename__='email_tokens'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    email:Mapped[str]=mapped_column(String(254))
    purpose:Mapped[str]=mapped_column(String(20))
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    credentials_version:Mapped[int|None]=mapped_column(Integer,nullable=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime)
    consumed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    verified:Mapped[bool]=mapped_column(Boolean,default=False)


class Announcement(Base):
    __tablename__='announcements'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    title:Mapped[str]=mapped_column(String(120))
    content:Mapped[str]=mapped_column(Text)
    published:Mapped[bool]=mapped_column(Boolean,default=False)


class AdminAudit(Base):
    __tablename__='admin_audits'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(60))
    target:Mapped[str]=mapped_column(String(80))
    reason:Mapped[str]=mapped_column(Text)
    version:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utc_now)
