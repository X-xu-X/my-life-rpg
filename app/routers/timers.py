from datetime import datetime
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Redemption
from app.models.workflow import PlanSchedule
from app.models.full_system import TimeSession,VoucherAllowance,DailyEntitlement
from app.services import timers,trial_rules,llm_config,ai_context
from app.services.workflow_common import WriteIn,begin,finish,version,fields,get_owned
from app.services.user_service import get_or_create_default_user
from app.services.time_service import utc_now,local_day

router=APIRouter()

class StartIn(WriteIn):
    kind:Literal['plan','base','voucher']
    source_id:int
    mode:Literal['gentle','strict','strong']='gentle'
    acknowledge_penalty:bool=False
    planned_minutes:int=Field(30,ge=1,le=1440,strict=True)
    source_version:int|None=Field(None,ge=1,strict=True)
    source_type:Literal['plan','care']='plan'

class EndIn(WriteIn):
    stop_at:datetime|None=None
    actual_seconds:int|None=Field(None,ge=0,le=60*60*24*31)
    explanation:str=Field('',max_length=4000)

@router.get('/timers')
def read(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);rows=db.query(TimeSession).filter_by(user_id=user.id).order_by(TimeSession.id.desc()).limit(100).all()
    return {'server_now':utc_now().isoformat(),'active':next((fields(r) for r in rows if r.state in timers.ACTIVE),None),
        'items':[fields(r) for r in rows],
        'vouchers':[{'redemption':fields(v),'allowance':fields(a) if a else None} for v,a in db.query(Redemption,VoucherAllowance).outerjoin(VoucherAllowance,VoucherAllowance.redemption_id==Redemption.id).filter(Redemption.user_id==user.id,Redemption.duration_seconds>0).order_by(Redemption.id.desc()).all()]}

@router.post('/timers')
def start(body:StartIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'timer-start',body,create=True)
    if prior is not None:return prior
    if db.query(TimeSession).filter(TimeSession.user_id==user.id,TimeSession.state.in_(timers.ACTIVE)).first():raise HTTPException(409,'已有计时尚未确认结束，请先处理原会话。')
    config=trial_rules.account(db,user);now=utc_now();selected=trial_rules.day(db,user);quota=None
    plan_snapshot=None
    if body.kind=='plan':
        from app.models.full_system import CareItem
        plan=get_owned(db,CareItem if body.source_type=='care' else PlanSchedule,body.source_id)
        if body.source_version is None:raise HTTPException(422,'开始计划需携带当前计划版本，请刷新计划后重试。')
        version(plan,body.source_version)
        from app.routers.plans import timing_snapshot
        from app.routers.care import item_snapshot
        effective=(item_snapshot if body.source_type=='care' else timing_snapshot)(plan,local_day(now,plan.rule.get('timezone',user.timezone)))
        if not effective or not effective['enabled']:raise HTTPException(409,'此计划尚未生效或已经停用。')
        if effective.get('removed'):raise HTTPException(409,'项目已移除。')
        configured=effective['rule'].get('planned_minutes',None if body.source_type=='care' else 30)
        if configured is None and 'planned_minutes' not in body.model_fields_set:raise HTTPException(422,'此项目没有固定时长，请先填写本次分钟数。')
        minutes=body.planned_minutes if configured is None else configured
        if configured is not None and 'planned_minutes' in body.model_fields_set and body.planned_minutes!=configured:raise HTTPException(409,'计划预计时长已变化，请刷新后重试。')
        plan_snapshot={'id':plan.id,'origin':body.source_type,'name':effective['name'],'source_version':plan.version,'effective_version':effective['version'],'planned_minutes':minutes,'configured_minutes':configured,'rule':effective['rule']}
        limit=minutes*60
    elif body.kind=='base':
        quota=get_owned(db,DailyEntitlement,body.source_id)
        if quota.local_date!=selected:raise HTTPException(409,'基础时长只用于其解锁当天。')
        limit=quota.base_seconds-quota.used_seconds
    else:
        redemption=get_owned(db,Redemption,body.source_id)
        if not redemption.duration_seconds or redemption.status=='fulfilled':raise HTTPException(409,'此券没有可用计时额度；旧券权益保留。')
        quota=db.query(VoucherAllowance).filter_by(redemption_id=redemption.id).first()
        if not quota:quota=VoucherAllowance(user_id=user.id,redemption_id=redemption.id,total_seconds=redemption.duration_seconds,used_seconds=0);db.add(quota);db.flush()
        limit=quota.total_seconds-quota.used_seconds
    if limit<=0:raise HTTPException(409,'此来源时长已用完。')
    if body.kind!='plan' and body.mode!='gentle' and not body.acknowledge_penalty:raise HTTPException(422,'处罚必须开始前明确同意，本次合同之后不自动加罚。')
    if body.kind!='plan' and body.mode=='strong':
        from app.models.full_system import PersonalPhase
        phase=db.query(PersonalPhase).filter_by(user_id=user.id).first()
        if not phase or phase.payload.get('accepted_mode')!='strong':raise HTTPException(409,'加强约定须先核对阶段建议并明确接受。')
    mode='gentle' if body.kind=='plan' else body.mode
    contract={'mode':mode,'per_5min':4 if mode=='strong' else 2 if mode=='strict' else 0,'session_cap':20 if mode=='strong' else 10 if mode=='strict' else 0,
        'daily_cap':30 if mode=='strong' else 20 if mode=='strict' else 0,'grace_seconds':180,'rule_version':trial_rules.VERSION,
        'config_version':config.version if config else 0,'acknowledged':body.acknowledge_penalty,'source_version':quota.version if quota else None}
    if plan_snapshot:contract['plan_snapshot']=plan_snapshot;contract['source_version']=plan_snapshot['source_version']
    row=TimeSession(user_id=user.id,kind=body.kind,source_id=body.source_id,timezone=trial_rules.zone_for(db,user),local_date=selected,
        limit_seconds=limit,contract=contract,started_at=now,last_sync_at=now,intervals=[{'start':now.isoformat(),'end':None}]);db.add(row);db.flush()
    return finish(db,user,'timer-start',body,fp,row,fields(row))

@router.post('/timers/{timer_id}/{action}')
def update(timer_id:int,action:Literal['pause','resume','sync','end-preview','confirm','explain','analyze-explanation'],body:EndIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'timer-{action}:{timer_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,TimeSession,timer_id);version(row,body.expected_version);now=utc_now()
    if action=='confirm':
        timers.settle(db,user,row)
        return finish(db,user,op,body,fp,row,fields(row))
    if action=='explain':
        if not body.explanation.strip():raise HTTPException(422,'请先保存具体说明。')
        row.explanation=body.explanation;row.analysis=None
    elif action=='analyze-explanation':
        if not row.explanation:raise HTTPException(422,'请先保存说明，单次分析可选。')
        from app.services.llm_service import LLMError
        try:config=llm_config.resolve_llm_config(db,user.id,llm_config.PURPOSE_AUX)
        except LLMError as exc:raise HTTPException(503,str(exc)) from None
        captured={'kind':row.kind,'intervals':row.intervals,'limit_seconds':row.limit_seconds,'explanation':row.explanation};captured_version=row.version
        import json
        from app.services.llm_service import llm_service
        from app.services.model_dispatch import mark
        mark(db,user,op,body,fp)
        try:
            result=llm_service.chat_json([{'role':'system','content':'仅根据本次计时说明给核对建议，不推定离线违规，不改账。返回JSON {"summary":"依据与不确定性","suggested_seconds":整数或null}。'},
                {'role':'user','content':json.dumps(captured,ensure_ascii=False)}],config=config)
        except LLMError as exc:raise HTTPException(503,str(exc)) from None
        from app.services.transactions import lock_profile
        lock_profile(db,user.id);llm_config.assert_current(db,config);db.refresh(row)
        if row.version!=captured_version:raise HTTPException(409,'说明或会话已变化。')
        seconds=result.get('suggested_seconds')
        if seconds is not None and (type(seconds) is not int or not 0<=seconds<=max(0,int((now-row.started_at).total_seconds()))):raise HTTPException(422,'分析建议无效。')
        row.analysis={'summary':str(result.get('summary',''))[:4000],'suggested_seconds':seconds,'model':config.model}
    elif action=='end-preview':
        if row.state not in ('running','paused','review','ended'):raise HTTPException(409,'会话状态无效。')
        stop=body.stop_at or now
        if stop.tzinfo is None or stop<row.started_at or stop>now:raise HTTPException(422,'实际停止时间需带时区且位于开始与现在之间。')
        seconds=body.actual_seconds if body.actual_seconds is not None else timers.used(row,stop)
        if seconds>int((now-row.started_at).total_seconds())+1:raise HTTPException(422,'实际时长超过会话经过时间。')
        if row.state=='ended' and db.query(TimeSession).filter(TimeSession.user_id==user.id,TimeSession.state.in_(timers.ACTIVE)).first():raise HTTPException(409,'请先结束活动会话再更正历史。')
        row.preview=timers.amount_preview(db,user,row,seconds);row.explanation=body.explanation or row.explanation
        if row.state!='ended':
            intervals=[dict(i) for i in row.intervals]
            for interval in intervals:
                if not interval.get('end'):interval['end']=stop.isoformat()
            row.intervals=intervals;row.state='review'
    else:
        if action=='pause' and row.state=='running':
            intervals=[dict(i) for i in row.intervals];intervals[-1]['end']=now.isoformat();row.intervals=intervals;row.state='paused'
        elif action=='resume' and row.state=='paused':row.intervals=[*row.intervals,{'start':now.isoformat(),'end':None}];row.state='running'
        elif action!='sync' or row.state not in ('running','paused'):raise HTTPException(409,'计时状态已变化。')
        row.last_sync_at=now
    row.version+=1
    return finish(db,user,op,body,fp,row,fields(row))
