"""Versioned full-system workflows. Financial writes still use coin_service."""
from datetime import datetime
from sqlalchemy import String,Text,Integer,BigInteger,ForeignKey,JSON,UniqueConstraint,Boolean,Index,text
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.time_types import UTCDateTime
from app.services.time_service import utc_now


class TrialAccount(Base):
    __tablename__='trial_accounts'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    enabled:Mapped[bool]=mapped_column(Boolean,default=False)
    rule_version:Mapped[str]=mapped_column(String(30),default='trial-2026-10-18-v1')
    timezone:Mapped[str]=mapped_column(String(60))
    pending_timezone:Mapped[str|None]=mapped_column(String(60),nullable=True)
    timezone_effective_at:Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)
    base_minutes:Mapped[int]=mapped_column(Integer,default=0)
    region:Mapped[str]=mapped_column(String(60),default='')
    contract:Mapped[dict]=mapped_column(JSON,default=dict)


class DailyEntitlement(Base):
    __tablename__='daily_entitlements'
    __table_args__=(UniqueConstraint('user_id','local_date',name='uq_entitlement_day'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    local_date:Mapped[str]=mapped_column(String(10))
    timezone:Mapped[str]=mapped_column(String(60))
    first_event_id:Mapped[int]=mapped_column(ForeignKey('events.id'))
    version:Mapped[int]=mapped_column(Integer,default=1)
    claimed:Mapped[bool]=mapped_column(Boolean,default=False)
    base_seconds:Mapped[int]=mapped_column(Integer,default=0)
    used_seconds:Mapped[int]=mapped_column(Integer,default=0)
    rule_version:Mapped[str]=mapped_column(String(30))


class FactFragment(Base):
    __tablename__='fact_fragments'
    __table_args__=(UniqueConstraint('user_id','event_id','fingerprint',name='uq_fact_fragment'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    event_id:Mapped[int]=mapped_column(ForeignKey('events.id'))
    event_version:Mapped[int]=mapped_column(Integer)
    fact_id:Mapped[int]=mapped_column(ForeignKey('fact_identities.id'))
    fingerprint:Mapped[str]=mapped_column(String(64))
    excerpt:Mapped[str]=mapped_column(Text)
    decision:Mapped[str]=mapped_column(String(20),default='new')
    version:Mapped[int]=mapped_column(Integer,default=1)
    history:Mapped[list]=mapped_column(JSON,default=list)


class FactNote(Base):
    __tablename__='fact_notes'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    event_id:Mapped[int]=mapped_column(ForeignKey('events.id'))
    event_version:Mapped[int]=mapped_column(Integer)
    permission_version:Mapped[int]=mapped_column(Integer)
    content:Mapped[str]=mapped_column(Text)
    question_snapshot:Mapped[list]=mapped_column(JSON,default=list)
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class FactBundle(Base):
    __tablename__='fact_bundles'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    event_id:Mapped[int]=mapped_column(ForeignKey('events.id'))
    event_version:Mapped[int]=mapped_column(Integer)
    permission_version:Mapped[int]=mapped_column(Integer)
    version:Mapped[int]=mapped_column(Integer,default=1)
    state:Mapped[str]=mapped_column(String(20),default='draft')
    payload:Mapped[dict]=mapped_column(JSON)
    preview:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    provenance:Mapped[dict]=mapped_column(JSON)
    sources:Mapped[list]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class ActionAward(Base):
    __tablename__='action_awards'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    fact_id:Mapped[int]=mapped_column(ForeignKey('fact_identities.id'),unique=True)
    judgment_id:Mapped[int]=mapped_column(ForeignKey('ai_judgments.id'),unique=True)
    local_date:Mapped[str]=mapped_column(String(10))
    amount:Mapped[int]=mapped_column(BigInteger)
    breakdown:Mapped[dict]=mapped_column(JSON)
    rule_version:Mapped[str]=mapped_column(String(30))


class CareConfig(Base):
    __tablename__='care_configs'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    enabled:Mapped[bool]=mapped_column(Boolean,default=True)
    ai_allowed:Mapped[bool]=mapped_column(Boolean,default=False)
    suggestions:Mapped[list|None]=mapped_column(JSON,nullable=True)
    initialized:Mapped[bool]=mapped_column(Boolean,default=True)


class CareItem(Base):
    __tablename__='care_items'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    version:Mapped[int]=mapped_column(Integer,default=1)
    name:Mapped[str]=mapped_column(String(80))
    position:Mapped[int]=mapped_column(Integer,default=0)
    enabled:Mapped[bool]=mapped_column(Boolean,default=True)
    removed:Mapped[bool]=mapped_column(Boolean,default=False)
    rule:Mapped[dict]=mapped_column(JSON)
    history:Mapped[list]=mapped_column(JSON,default=list)


class CareEntry(Base):
    __tablename__='care_entries'
    __table_args__=(UniqueConstraint('item_id','local_date',name='uq_care_occurrence'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    item_id:Mapped[int]=mapped_column(ForeignKey('care_items.id'))
    local_date:Mapped[str]=mapped_column(String(10))
    version:Mapped[int]=mapped_column(Integer,default=1)
    state:Mapped[str]=mapped_column(String(20))
    event_id:Mapped[int|None]=mapped_column(ForeignKey('events.id'),nullable=True)
    snapshot:Mapped[dict]=mapped_column(JSON)
    history:Mapped[list]=mapped_column(JSON,default=list)


class Feedback(Base):
    __tablename__='feedback'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    version:Mapped[int]=mapped_column(Integer,default=1)
    kind:Mapped[str]=mapped_column(String(20))
    title:Mapped[str]=mapped_column(String(120))
    content:Mapped[str]=mapped_column(Text)
    state:Mapped[str]=mapped_column(String(20),default='open')
    created_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class FeedbackReply(Base):
    __tablename__='feedback_replies'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    feedback_id:Mapped[int]=mapped_column(ForeignKey('feedback.id'))
    actor_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    content:Mapped[str]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)


class PricingQuote(Base):
    __tablename__='pricing_quotes'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    item_id:Mapped[int|None]=mapped_column(ForeignKey('shop_items.id'),nullable=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    state:Mapped[str]=mapped_column(String(20),default='suggested')
    request_key:Mapped[str]=mapped_column(String(36))
    fingerprint:Mapped[str]=mapped_column(String(64))
    payload:Mapped[dict]=mapped_column(JSON)
    context:Mapped[dict]=mapped_column(JSON)
    result:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)
    __table_args__=(UniqueConstraint('user_id','request_key',name='uq_pricing_request'),)


class VoucherAllowance(Base):
    __tablename__='voucher_allowances'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    redemption_id:Mapped[int]=mapped_column(ForeignKey('redemptions.id'),unique=True)
    total_seconds:Mapped[int]=mapped_column(Integer)
    used_seconds:Mapped[int]=mapped_column(Integer,default=0)
    version:Mapped[int]=mapped_column(Integer,default=1)


class TimeSession(Base):
    __tablename__='time_sessions'
    __table_args__=(Index('uq_active_timer','user_id',unique=True,postgresql_where=text("state IN ('running','paused','review')"),sqlite_where=text("state IN ('running','paused','review')")),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    version:Mapped[int]=mapped_column(Integer,default=1)
    kind:Mapped[str]=mapped_column(String(20))
    source_id:Mapped[int]=mapped_column(Integer)
    state:Mapped[str]=mapped_column(String(20),default='running')
    started_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)
    last_sync_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now)
    timezone:Mapped[str]=mapped_column(String(60))
    local_date:Mapped[str]=mapped_column(String(10))
    limit_seconds:Mapped[int]=mapped_column(Integer)
    intervals:Mapped[list]=mapped_column(JSON,default=list)
    contract:Mapped[dict]=mapped_column(JSON)
    explanation:Mapped[str]=mapped_column(Text,default='')
    analysis:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    preview:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    settlement:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    history:Mapped[list]=mapped_column(JSON,default=list)


class Questionnaire(Base):
    __tablename__='questionnaires'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    answers:Mapped[dict]=mapped_column(JSON,default=dict)
    send_groups:Mapped[list]=mapped_column(JSON,default=list)
    preview:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    updated_at:Mapped[datetime]=mapped_column(UTCDateTime,default=utc_now,onupdate=utc_now)


class PersonalPhase(Base):
    __tablename__='personal_phases'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    payload:Mapped[dict]=mapped_column(JSON,default=dict)
    pending:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    return_cooldown_until:Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)
    history:Mapped[list]=mapped_column(JSON,default=list)


class Holiday(Base):
    __tablename__='holidays'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    local_date:Mapped[str]=mapped_column(String(10))
    region:Mapped[str]=mapped_column(String(60))
    name:Mapped[str]=mapped_column(String(120))
    enabled:Mapped[bool]=mapped_column(Boolean,default=True)


class HolidayClaim(Base):
    __tablename__='holiday_claims'
    __table_args__=(UniqueConstraint('user_id','local_date',name='uq_holiday_claim_day'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    local_date:Mapped[str]=mapped_column(String(10))
    amount:Mapped[int]=mapped_column(Integer)
    snapshot:Mapped[list]=mapped_column(JSON)
