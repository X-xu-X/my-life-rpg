"""Persistent intervals, independent voucher balances, explicit atomic settlement."""
from datetime import datetime
from fastapi import HTTPException
from app.models import Redemption
from app.models.full_system import TimeSession,VoucherAllowance,DailyEntitlement
from app.services import coin_service
from app.services.time_service import utc_now,local_day

ACTIVE=('running','paused','review')

def used(row,stop=None):
    stop=stop or utc_now();seconds=0
    for interval in row.intervals:
        start=datetime.fromisoformat(interval['start']);end=datetime.fromisoformat(interval['end']) if interval.get('end') else stop
        seconds+=max(0,int((min(stop,end)-start).total_seconds()))
    return seconds

def source(db,row):
    if row.kind=='voucher':return db.query(VoucherAllowance).filter_by(redemption_id=row.source_id,user_id=row.user_id).one()
    if row.kind=='base':return db.query(DailyEntitlement).filter_by(id=row.source_id,user_id=row.user_id).one()
    return None

def amount_preview(db,user,row,seconds):
    day=str(local_day(utc_now(),row.timezone)) if not row.settlement else row.settlement['day']
    other=[s.settlement for s in db.query(TimeSession).filter(TimeSession.user_id==user.id,TimeSession.id!=row.id,TimeSession.state=='ended').all() if s.settlement and s.settlement['day']==day]
    cap=row.contract['daily_cap'];penalty=0
    if row.kind!='plan' and row.contract['mode']!='gentle':
        penalty=min(row.contract['session_cap'],max(0,seconds-row.limit_seconds-180)//300*row.contract['per_5min'],max(0,cap-sum(s['penalty_charged'] for s in other)))
    reward=1 if row.kind!='plan' and seconds>=300 and seconds<=row.limit_seconds+180 and sum(s['ontime_awarded'] for s in other)<2 else 0
    old=row.settlement or {'penalty_charged':0,'ontime_awarded':0,'consumed_seconds':0}
    # Refunds can only return actual prior debits; repeated corrections compare the last settlement.
    available=coin_service.balance(db,user)+old['penalty_charged']-old['ontime_awarded']+reward
    penalty=min(penalty,max(0,available))
    quota=source(db,row)
    consume=min(seconds,row.limit_seconds) if quota else 0
    total=quota.total_seconds if row.kind=='voucher' else quota.base_seconds if quota else 0
    if quota and quota.used_seconds-old['consumed_seconds']+consume>total:raise HTTPException(409,'来源剩余额度已变化，请核对其他会话后重试。')
    return {'actual_seconds':seconds,'day':day,'penalty_charged':penalty,'ontime_awarded':reward,'consumed_seconds':consume,
        'coin_delta':old['penalty_charged']-penalty+reward-old['ontime_awarded'],'source_version':quota.version if quota else None,
        'offline_interval':max(0,int((utc_now()-row.last_sync_at).total_seconds()))>60,'rule':row.contract}

def settle(db,user,row):
    if not row.preview or row.state not in ('review','ended'):raise HTTPException(409,'请先核对结束预览。')
    fresh=amount_preview(db,user,row,row.preview['actual_seconds'])
    for key in ('penalty_charged','ontime_awarded','coin_delta','source_version','day'):
        if fresh[key]!=row.preview[key]:raise HTTPException(409,'余额或当日额度已变化，请刷新预览。')
    if fresh['coin_delta']:coin_service.require_baseline(db,user)
    old=row.settlement or {'consumed_seconds':0}
    quota=source(db,row)
    if quota:
        quota.used_seconds+=fresh['consumed_seconds']-old['consumed_seconds'];quota.version+=1
        if row.kind=='voucher':
            redemption=db.get(Redemption,row.source_id)
            redemption.status='fulfilled' if quota.used_seconds>=quota.total_seconds else 'pending'
            if redemption.status=='fulfilled':
                from app.services.time_service import stored_time
                redemption.fulfilled_at=stored_time(utc_now())
    delta=fresh['coin_delta']
    if delta:coin_service.grant(db,user,delta,'timer_adjustment' if row.settlement else 'timer_reward' if delta>0 else 'timer_penalty','本人确认计时结果；'+row.contract['mode'],'time_session',row.id)
    row.history=[*row.history,{'previous':row.settlement,'confirmed':fresh,'explanation':row.explanation,'at':utc_now().isoformat()}]
    row.settlement=fresh;row.state='ended';row.preview=None;row.version+=1
