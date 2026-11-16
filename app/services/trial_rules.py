"""Approved trial v2; the model prices each action and rules only guard the value."""
from fastapi import HTTPException
from app.models.full_system import TrialAccount,DailyEntitlement,ActionAward
from app.services.time_service import utc_now,local_day
from app.services import coin_service

VERSION='trial-2026-11-16-v2'
MAX_COINS=10**9

def account(db,user):return db.query(TrialAccount).filter_by(user_id=user.id).first()

def zone_for(db,user):
    row=account(db,user)
    if not row:return user.timezone
    return row.pending_timezone if row.pending_timezone and row.timezone_effective_at and utc_now()>=row.timezone_effective_at else row.timezone

def day(db,user):
    row=account(db,user)
    return str(local_day(utc_now(),zone_for(db,user)))

def qualify(db,user,event,mark_rule=True):
    config=account(db,user)
    if mark_rule and config and config.enabled:event.economy_version=VERSION
    if not config or not config.enabled or event.record_kind not in ('event','diary'):return
    selected=day(db,user)
    if db.query(DailyEntitlement).filter_by(user_id=user.id,local_date=selected).first():return
    db.add(DailyEntitlement(user_id=user.id,local_date=selected,timezone=zone_for(db,user),first_event_id=event.id,
        base_seconds=config.base_minutes*60,rule_version=VERSION))

def cap_used(db,user,selected):
    """Only for display ("today earned N"), never a cap on new awards."""
    return sum(row.amount for row in db.query(ActionAward).filter_by(user_id=user.id,local_date=selected).all())

def validate(coins,reason=''):
    """The model sets the amount; we only reject dirty values (no tiers, no caps)."""
    if type(coins) is not int or coins<0 or coins>MAX_COINS:raise HTTPException(422,'模型给出的金币数不合法。')
    return coins

def award(db,user,fact_id,judgment_id,breakdown,selected):
    amount=breakdown['amount']
    db.add(ActionAward(user_id=user.id,fact_id=fact_id,judgment_id=judgment_id,local_date=selected,amount=amount,breakdown=breakdown,rule_version=VERSION))
    if amount:coin_service.grant(db,user,amount,'trial_action','经本人确认的有效行动；'+VERSION,'judgment',judgment_id)
