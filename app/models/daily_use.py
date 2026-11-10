"""Persistent user-owned daily experience; separate from initial financial state."""
from datetime import datetime
from sqlalchemy import ForeignKey,Integer,String,Text,JSON,Boolean,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.time_types import UTCDateTime
from app.services.time_service import utc_now


class PersonalInformation(Base):
    __tablename__='personal_information'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    entries:Mapped[list]=mapped_column(JSON,default=list)
    updated_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now,onupdate=utc_now)


class ExperiencePreference(Base):
    __tablename__='experience_preferences'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    suppressed:Mapped[list]=mapped_column(JSON,default=list)
    # v1 UI-IA：行级说明句的关闭清单（TipLine）。可空列，老行为 NULL → 读取处一律 `or []`
    suppressed_lines:Mapped[list|None]=mapped_column(JSON,default=list,nullable=True)
    return_disabled:Mapped[bool]=mapped_column(Boolean,default=False)
    review_snoozed_until:Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)


class ReturnCheckin(Base):
    __tablename__='return_checkins'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    answers:Mapped[dict]=mapped_column(JSON,default=dict)
    uses:Mapped[list]=mapped_column(JSON,default=list)
    state:Mapped[str]=mapped_column(String(20),default='draft')
    history:Mapped[list]=mapped_column(JSON,default=list)
    updated_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now,onupdate=utc_now)


class ImportantDay(Base):
    __tablename__='important_days'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    version:Mapped[int]=mapped_column(Integer,default=1)
    name:Mapped[str]=mapped_column(String(120))
    month:Mapped[int]=mapped_column(Integer)
    day:Mapped[int]=mapped_column(Integer)
    year:Mapped[int|None]=mapped_column(Integer,nullable=True)
    annual:Mapped[bool]=mapped_column(Boolean,default=True)
    remind_days:Mapped[int]=mapped_column(Integer,default=3)
    enabled:Mapped[bool]=mapped_column(Boolean,default=True)


class OfficialCalendar(Base):
    __tablename__='official_calendars'
    id:Mapped[int]=mapped_column(primary_key=True)
    year:Mapped[int]=mapped_column(Integer,unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    source_url:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(30),default='verified')
    data:Mapped[dict]=mapped_column(JSON)


class PricingCheck(Base):
    __tablename__='pricing_checks'
    __table_args__=(UniqueConstraint('user_id','item_id','local_date',name='uq_pricing_check_day'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    item_id:Mapped[int]=mapped_column(ForeignKey('shop_items.id'))
    local_date:Mapped[str]=mapped_column(String(10))
    version:Mapped[int]=mapped_column(Integer,default=1)
    state:Mapped[str]=mapped_column(String(20),default='queued')
    request_key:Mapped[str]=mapped_column(String(36))
    lease_token:Mapped[str|None]=mapped_column(String(36),nullable=True)
    started_at:Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)
    completed_at:Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)
    error_code:Mapped[str|None]=mapped_column(String(50),nullable=True)
    quote_id:Mapped[int|None]=mapped_column(ForeignKey('pricing_quotes.id'),nullable=True)


class ModelDispatch(Base):
    """At-most-once dispatch for legacy synchronous, explicitly keyed analyses.

    Completion is the existing atomic business receipt, never this marker.
    A crash after dispatch is deliberately uncertain and cannot trigger a retry.
    """
    __tablename__='model_dispatches'
    __table_args__=(UniqueConstraint('user_id','operation','request_key',name='uq_model_dispatch_key'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    operation:Mapped[str]=mapped_column(String(100))
    request_key:Mapped[str]=mapped_column(String(36))
    payload_hash:Mapped[str]=mapped_column(String(64))
    created_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)
