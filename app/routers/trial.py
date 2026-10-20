from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event,UserProfile
from app.models.full_system import TrialAccount,DailyEntitlement
from app.services import trial_rules,coin_service
from app.services.user_service import get_or_create_default_user
from app.services.workflow_common import WriteIn,begin,finish,version,fields

router=APIRouter()

class TrialIn(WriteIn):
    acknowledge:bool
    enabled:bool=True
    base_minutes:int=Field(0,ge=0,le=1440)
    region:str=Field('',max_length=60)
    timezone:str|None=Field(None,max_length=60)

@router.get('/trial')
def read(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);row=trial_rules.account(db,user);today=trial_rules.day(db,user)
    daily=db.query(DailyEntitlement).filter_by(user_id=user.id,local_date=today).first()
    return {'config':fields(row) if row else None,'rule_version':trial_rules.VERSION,'today':today,
        'baseline_required':not db.query(UserProfile).filter_by(user_id=user.id).one().onboarding_completed,
        'daily':fields(daily) if daily else None,'action_used':trial_rules.cap_used(db,user,today),
        'rules':{'base':trial_rules.BASE,'mainline':trial_rules.MAIN,'per_fact_cap':40,'daily_cap':100,'first_record':3,'strict_default':False}}

@router.put('/trial')
def save(body:TrialIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'trial-adopt',body)
    if prior is not None:return prior
    row=trial_rules.account(db,user);version(row,body.expected_version)
    if not body.acknowledge:raise HTTPException(422,'请确认未来采用此试用规则，旧账不重算。')
    if not row:row=TrialAccount(user_id=user.id,version=0,timezone=user.timezone);db.add(row)
    if body.timezone:
        from app.services.time_service import zone,utc_now,local_day,date_range
        from datetime import timedelta,datetime,time,timezone as utc_timezone
        zone(body.timezone)
        if row.pending_timezone and row.timezone_effective_at and utc_now()>=row.timezone_effective_at:
            row.timezone=row.pending_timezone;row.pending_timezone=None;row.timezone_effective_at=None
        if body.timezone!=row.timezone and body.timezone!=row.pending_timezone:
            row.pending_timezone=body.timezone
            tomorrow=local_day(utc_now(),row.timezone)+timedelta(days=1)
            row.timezone_effective_at=datetime.combine(tomorrow,time.min,zone(row.timezone)).astimezone(utc_timezone.utc)
        elif body.timezone==row.timezone:
            row.pending_timezone=None;row.timezone_effective_at=None
        user.timezone=body.timezone
    row.enabled=body.enabled;row.base_minutes=body.base_minutes;row.region=body.region;row.version+=1
    db.flush()
    first=db.query(Event).filter_by(user_id=user.id,saved_on=trial_rules.day(db,user)).filter(Event.record_kind.in_(('event','diary'))).order_by(Event.id).first()
    if first:trial_rules.qualify(db,user,first,mark_rule=False)
    return finish(db,user,'trial-adopt',body,fp,row,fields(row))

@router.post('/trial/first-record/claim')
def claim(body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op='first-record:'+trial_rules.day(db,user);fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=db.query(DailyEntitlement).filter_by(user_id=user.id,local_date=trial_rules.day(db,user)).first()
    if not row or row.claimed:raise HTTPException(409,'今天尚无首记资格或已经领取。')
    version(row,body.expected_version);coin_service.require_baseline(db,user)
    row.claimed=True;row.version+=1
    coin_service.grant(db,user,3,'daily_first_record','当天首记签到；免费娱乐时长独立','entitlement',row.id)
    return finish(db,user,op,body,fp,row,{'coins_gained':3,'balance':coin_service.balance(db,user),'daily':fields(row)})
