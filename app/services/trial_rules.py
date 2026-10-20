"""Approved trial v1; deterministic prices/caps are never model-supplied money."""
from fastapi import HTTPException
from app.models.full_system import TrialAccount,DailyEntitlement,ActionAward
from app.services.time_service import utc_now,local_day
from app.services import coin_service

VERSION='trial-2026-10-18-v1'
BASE={'small':6,'medium':15,'large':25,'none':0}
MAIN={'small':4,'medium':10,'large':15,'none':0}

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
    return sum(row.amount for row in db.query(ActionAward).filter_by(user_id=user.id,local_date=selected).all())

def split(grade,mainline,remaining,holiday=False,effort=False):
    if grade not in BASE:raise HTTPException(422,'模型行动档位不合法。')
    base=BASE[grade];extra=MAIN[grade] if mainline else 0
    bonus=(base+extra)//5 if holiday and effort else 0
    total=min(40,max(0,remaining),base+extra+bonus)
    return {'base':base,'mainline':extra,'holiday':bonus,'before_cap':base+extra+bonus,'amount':total,'cap_reduction':base+extra+bonus-total}

def award(db,user,fact_id,judgment_id,breakdown,selected):
    amount=breakdown['amount']
    db.add(ActionAward(user_id=user.id,fact_id=fact_id,judgment_id=judgment_id,local_date=selected,amount=amount,breakdown=breakdown,rule_version=VERSION))
    if amount:coin_service.grant(db,user,amount,'trial_action','经本人确认的有效行动；'+VERSION,'judgment',judgment_id)
