from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,model_validator
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event,AIJudgment
from app.models.analysis import AnalysisJob
from app.models.workflow import PlanSchedule,PlanOccurrence,FactRelation
from app.services.user_service import get_or_create_default_user
from app.services.time_service import date_range,local_day,utc_now
from app.services.workflow_common import WriteIn,begin,finish,version,fields,get_owned

router=APIRouter()


class ScheduleIn(WriteIn):
    name:str=Field(min_length=1,max_length=120)
    frequency:Literal['daily','weekdays','interval']
    start:date
    weekdays:list[int]=Field(default_factory=list,max_length=7)
    interval:int=Field(1,ge=1,le=366)
    enabled:bool=True
    @model_validator(mode='after')
    def valid(self):
        if self.frequency=='weekdays' and (not self.weekdays or any(d not in range(7) for d in self.weekdays) or len(set(self.weekdays))!=len(self.weekdays)):raise ValueError('请选择不重复的周一至周日。')
        return self


class ResultIn(WriteIn):
    schedule_version:int
    outcome:Literal['done','partial','missed']
    content:str=Field('',max_length=10000)
    actual:float|None=Field(None,ge=0,allow_inf_nan=False)
    unit:str=Field('',max_length=40)
    event_id:int|None=None
    event_version:int|None=None
    correction:bool=False
    reason:str=Field('',max_length=2000)


class RelationIn(WriteIn):
    source_id:int
    target_id:int
    source_version:int
    target_version:int
    reason:str=Field(min_length=1,max_length=2000)


class DecisionIn(WriteIn):
    accept:bool


def historical(row,day):
    return next((item for item in reversed(row.history) if item['rule']['start']<=str(day)),None)


def due(rule,day):
    start=date.fromisoformat(rule['start'])
    return day>=start and (rule['frequency']=='daily' or rule['frequency']=='weekdays' and day.weekday() in rule['weekdays'] or rule['frequency']=='interval' and (day-start).days%rule['interval']==0)


@router.get('/plan-schedules')
def schedules(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db)
    return [fields(r) for r in db.query(PlanSchedule).filter_by(user_id=user.id).order_by(PlanSchedule.id).all()]


@router.post('/plan-schedules')
@router.put('/plan-schedules/{schedule_id}')
def save_schedule(body:ScheduleIn,schedule_id:int|None=None,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'schedule:{schedule_id or "create"}';fp,prior=begin(db,user,op,body,create=schedule_id is None)
    if prior is not None:return prior
    row=get_owned(db,PlanSchedule,schedule_id) if schedule_id else None
    if row:version(row,body.expected_version)
    rule=body.model_dump(mode='json',include={'frequency','start','weekdays','interval'})
    rule['timezone']=user.timezone
    if row and body.start<local_day(utc_now(),user.timezone):raise HTTPException(422,'周期修改需明确今天或未来的生效日，历史安排保留。')
    if not row:row=PlanSchedule(user_id=user.id,name=body.name,rule=rule,version=0,history=[]);db.add(row)
    row.history=[*row.history,{'version':row.version+1,'name':body.name,'rule':rule,'enabled':body.enabled,'at':utc_now().isoformat()}]
    row.name=body.name;row.rule=rule;row.enabled=body.enabled;row.version+=1;db.flush()
    return finish(db,user,op,body,fp,row,fields(row))


@router.get('/plan-occurrences')
def occurrences(day:date|None=None,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db)
    if day is None:return {'history':[fields(r) for r in db.query(PlanOccurrence).filter_by(user_id=user.id).order_by(PlanOccurrence.id.desc()).limit(500).all()]}
    rows=db.query(PlanOccurrence).filter_by(user_id=user.id,local_date=str(day)).all();by_schedule={r.schedule_id:r for r in rows}
    items=[]
    for row in db.query(PlanSchedule).filter_by(user_id=user.id).all():
        saved=by_schedule.get(row.id)
        snapshot=historical(row,day)
        if saved or snapshot and snapshot['enabled'] and due(snapshot['rule'],day):items.append({'schedule':fields(row),'occurrence':fields(saved) if saved else None})
    return {'date':str(day),'items':items}


@router.put('/plan-schedules/{schedule_id}/occurrences/{day}')
def result(schedule_id:int,day:date,body:ResultIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'plan-result:{schedule_id}:{day}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    schedule=get_owned(db,PlanSchedule,schedule_id)
    row=db.query(PlanOccurrence).filter_by(schedule_id=schedule.id,local_date=str(day)).first();version(row,body.expected_version)
    if row and not body.correction:raise HTTPException(409,'当次结果已锁定，请使用显式纠错并填写原因。')
    if row and not body.reason.strip():raise HTTPException(422,'纠错需要原因。')
    if schedule.version!=body.schedule_version:raise HTTPException(409,'日程已更新，请重新读取。')
    snapshot=historical(schedule,day)
    if not row and (not snapshot or not snapshot['enabled'] or not due(snapshot['rule'],day)):raise HTTPException(409,'此日没有到期安排。')
    if day>local_day(utc_now(),user.timezone):raise HTTPException(422,'不能提前记录未来结果。')
    if body.outcome!='missed' and not body.content.strip() and not body.event_id:raise HTTPException(422,'先保存实际事实，不默认完成比例。')
    event=None
    if body.outcome!='missed' and body.event_id:
        event=get_owned(db,Event,body.event_id)
        if event.is_deleted or event.record_kind=='diary' or event.content_version!=body.event_version:raise HTTPException(409,'关联事件无效或版本变化。')
    if not row:row=PlanOccurrence(user_id=user.id,schedule_id=schedule.id,local_date=str(day),schedule_snapshot={**snapshot,'timezone':snapshot['rule']['timezone']},version=0,history=[]);db.add(row)
    old_event=get_owned(db,Event,row.event_id) if row.event_id else None
    booked=bool(old_event and db.query(AIJudgment).filter_by(event_id=old_event.id,status='confirmed').first())
    if booked and event and event.id!=old_event.id:raise HTTPException(409,'当次已结算，纠错不能换成另一事实再次领奖。')
    if not event and body.outcome!='missed':
        if old_event:
            event=old_event
            if not booked:
                event.content=body.content;event.content_version+=1
                for judgment in db.query(AIJudgment).filter(AIJudgment.event_id==event.id,AIJudgment.status.in_(('pending','adjusted'))).all():judgment.status='invalidated'
                for job in db.query(AnalysisJob).filter(AnalysisJob.event_id==event.id,AnalysisJob.state.in_(('queued','running'))).all():job.state='superseded';job.lease_token=None
        else:
            event=Event(user_id=user.id,event_type='positive',source='form',record_kind='event',title=schedule.name,content=body.content,
                occurred_on=str(day),time_precision='date',occurred_at=date_range(day,user.timezone)[0],timezone_at_capture=user.timezone,analysis_intent='later')
            db.add(event);db.flush()
    row.version+=1;row.outcome=body.outcome;row.facts={'content':body.content,'actual':body.actual,'unit':body.unit,'correction_reason':body.reason}
    if event:row.event_id=event.id
    row.history=[*row.history,{'version':row.version,'outcome':row.outcome,'facts':row.facts,'event_id':row.event_id,'at':utc_now().isoformat(),'prior_booking_retained':booked}]
    db.flush()
    return finish(db,user,op,body,fp,row,fields(row))


@router.get('/fact-relations')
def relations(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db)
    return [fields(r) for r in db.query(FactRelation).filter_by(user_id=user.id).order_by(FactRelation.id.desc()).limit(200).all()]


@router.post('/fact-relations')
def propose(body:RelationIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'fact-propose',body,create=True)
    if prior is not None:return prior
    source=get_owned(db,Event,body.source_id);target=get_owned(db,Event,body.target_id)
    if source.id==target.id or source.is_deleted or target.is_deleted or source.content_version!=body.source_version or target.content_version!=body.target_version:raise HTTPException(409,'引用或版本无效。')
    row=FactRelation(user_id=user.id,source_id=source.id,target_id=target.id,source_version=source.content_version,target_version=target.content_version,reason=body.reason)
    db.add(row);db.flush();return finish(db,user,'fact-propose',body,fp,row,fields(row))


@router.post('/fact-relations/{relation_id}/decision')
def decide(relation_id:int,body:DecisionIn,db:Session=Depends(get_db)):
    from app.services.facts import associate
    user=get_or_create_default_user(db);op=f'fact-decide:{relation_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,FactRelation,relation_id);version(row,body.expected_version)
    if row.state!='candidate':raise HTTPException(409,'关联已处理。')
    source=get_owned(db,Event,row.source_id);target=get_owned(db,Event,row.target_id)
    if source.content_version!=row.source_version or target.content_version!=row.target_version:raise HTTPException(409,'来源已有新版，请重新核对。')
    if body.accept:associate(db,source,target)
    row.state='accepted' if body.accept else 'rejected';row.version+=1
    return finish(db,user,op,body,fp,row,fields(row))
