"""Versioned optional economics and independent hosted AI accounting."""
from datetime import datetime
from sqlalchemy import ForeignKey,Integer,String,JSON,Boolean,BigInteger,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
from app.time_types import UTCDateTime as DateTime
from app.services.time_service import utc_now


class EconomicRule(Base):
    __tablename__='economic_rules'
    __table_args__=(UniqueConstraint('kind','version',name='uq_economic_rule_version'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    kind:Mapped[str]=mapped_column(String(20))
    version:Mapped[int]=mapped_column(Integer)
    enabled:Mapped[bool]=mapped_column(Boolean,default=False)
    payload:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utc_now)


class Mainline(Base):
    __tablename__='mainlines'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    goal_id:Mapped[int]=mapped_column(ForeignKey('goals.id'))
    version:Mapped[int]=mapped_column(Integer,default=1)
    active:Mapped[bool]=mapped_column(Boolean,default=True)


class RewardPreview(Base):
    __tablename__='reward_previews'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    mainline_id:Mapped[int]=mapped_column(ForeignKey('mainlines.id'))
    event_id:Mapped[int]=mapped_column(ForeignKey('events.id'))
    judgment_id:Mapped[int]=mapped_column(ForeignKey('ai_judgments.id'))
    rule_id:Mapped[int]=mapped_column(ForeignKey('economic_rules.id'))
    version:Mapped[int]=mapped_column(Integer,default=1)
    state:Mapped[str]=mapped_column(String(20),default='pending')
    snapshot:Mapped[dict]=mapped_column(JSON)
    amount:Mapped[int]=mapped_column(BigInteger)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utc_now)


class MainlineAward(Base):
    __tablename__='mainline_awards'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    fact_id:Mapped[int]=mapped_column(ForeignKey('fact_identities.id'),unique=True)
    preview_id:Mapped[int]=mapped_column(ForeignKey('reward_previews.id'),unique=True)
    rule_id:Mapped[int]=mapped_column(ForeignKey('economic_rules.id'))
    cap_date:Mapped[str]=mapped_column(String(10))
    amount:Mapped[int]=mapped_column(BigInteger)


class DynamicCandidate(Base):
    __tablename__='dynamic_candidates'
    __table_args__=(UniqueConstraint('user_id','semantic_key',name='uq_dynamic_semantics'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    semantic_key:Mapped[str]=mapped_column(String(64))
    name:Mapped[str]=mapped_column(String(100))
    criteria:Mapped[dict]=mapped_column(JSON)
    evidence:Mapped[dict]=mapped_column(JSON)
    version:Mapped[int]=mapped_column(Integer,default=1)
    state:Mapped[str]=mapped_column(String(20),default='candidate')


class DynamicAward(Base):
    __tablename__='dynamic_awards'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(UniqueConstraint('user_id','equivalence_key',name='uq_dynamic_fixed_equivalence'),)
    equivalence_key:Mapped[str|None]=mapped_column(String(80),nullable=True)
    candidate_id:Mapped[int]=mapped_column(ForeignKey('dynamic_candidates.id'),unique=True)
    rule_id:Mapped[int]=mapped_column(ForeignKey('economic_rules.id'))
    achievement_id:Mapped[int]=mapped_column(ForeignKey('achievements.id'),unique=True)
    amount:Mapped[int]=mapped_column(BigInteger)
    evidence:Mapped[dict]=mapped_column(JSON)


class HostedAI(Base):
    __tablename__='hosted_ai'
    id:Mapped[int]=mapped_column(primary_key=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    enabled:Mapped[bool]=mapped_column(Boolean,default=False)
    payload:Mapped[dict]=mapped_column(JSON)


class AIPreference(Base):
    __tablename__='ai_preferences'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    mode:Mapped[str]=mapped_column(String(20),default='personal')


class HostedUsage(Base):
    __tablename__='hosted_usage'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    local_date:Mapped[str]=mapped_column(String(10))
    hosted_version:Mapped[int]=mapped_column(Integer)
    state:Mapped[str]=mapped_column(String(20),default='reserved')
    pricing_snapshot:Mapped[dict]=mapped_column(JSON)
    reserved_tokens:Mapped[int]=mapped_column(BigInteger)
    charged_tokens:Mapped[int]=mapped_column(BigInteger)
    reserved_cost:Mapped[int]=mapped_column(BigInteger)
    charged_cost:Mapped[int]=mapped_column(BigInteger)
    safe_error_code:Mapped[str]=mapped_column(String(50),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utc_now)
