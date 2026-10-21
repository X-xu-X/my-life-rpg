from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,model_validator
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event,AIJudgment
from app.models.full_system import CareConfig,CareItem,CareEntry
from app.models.workflow import LifeChecklist
from app.services import ai_context,trial_rules
from app.services.workflow_common import WriteIn,begin,finish,version,fields,get_owned
from app.services.user_service import get_or_create_default_user
from app.services.time_service import local_day,utc_now,date_range,capture_saved_day

router=APIRouter()

class ConfigIn(WriteIn):
    enabled:bool=True
    initialize_examples:bool=False
    ai_allowed:bool=False

class ItemIn(WriteIn):
    name:str=Field(min_length=1,max_length=80)
    position:int=Field(0,ge=0,le=100000)
    frequency:Literal['daily','workdays','weekends','weekdays','interval','once','manual']='daily'
    start:date|None=None
    interval:int=Field(1,ge=1,le=366)
    category:Literal['plan','care']='care'
    planned_minutes:int|None=Field(None,ge=1,le=1440,strict=True)
    goal_id:int|None=None
    weekdays:list[int]=Field(default_factory=list,max_length=7)
    enabled:bool=True
    removed:bool=False
    @model_validator(mode='after')
    def valid(self):
        if self.frequency=='weekdays' and (not self.weekdays or any(d not in range(7) for d in self.weekdays)):raise ValueError('请选有效星期。')
        return self

class EntryIn(WriteIn):
    item_version:int
    state:Literal['recorded','skipped','done','partial','missed']
    correction:bool=False
    reason:str=Field('',max_length=2000)
    content:str=Field('',max_length=20000)
    ai_permission:Literal['private','allowed']='private'

def item_snapshot(item,day):
    dated=[h for h in item.history if 'rule' in h]
    snapshot=next((h for h in reversed(dated) if h['rule'].get('start','0001-01-01')<=str(day)),None)
    if snapshot is None and not dated and item.rule.get('start','0001-01-01')<=str(day):snapshot=fields(item)
    return snapshot


def due(item,day):
    from app.routers.plans import due as scheduled
    snapshot=item_snapshot(item,day)
    return bool(snapshot and snapshot['enabled'] and not snapshot.get('removed') and scheduled({'start':'0001-01-01','interval':1,**snapshot['rule']},day))

@router.get('/care')
def read(day:date|None=None,offset:int=0,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);selected=day or local_day(utc_now(),user.timezone)
    config=db.query(CareConfig).filter_by(user_id=user.id).first()
    items=db.query(CareItem).filter_by(user_id=user.id,removed=False).order_by(CareItem.position,CareItem.id).offset(max(0,offset)).limit(100).all()
    entries={e.item_id:e for e in db.query(CareEntry).filter_by(user_id=user.id,local_date=str(selected)).all()}
    legacy=db.query(LifeChecklist).filter_by(user_id=user.id,local_date=str(selected)).first()
    return {'config':fields(config) if config else None,'day':str(selected),'items':[fields(i) for i in items],
        'legacy_history':[fields(l) for l in db.query(LifeChecklist).filter_by(user_id=user.id).order_by(LifeChecklist.id.desc()).limit(30).all()],
        'today':[{'item':fields(i),'entry':fields(entries[i.id]) if i.id in entries else None} for i in items if config and config.enabled and due(i,selected)],
        'legacy':fields(legacy) if legacy else None}

@router.put('/care/config')
def configure(body:ConfigIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'care-config',body)
    if prior is not None:return prior
    row=db.query(CareConfig).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if not row:
        row=CareConfig(user_id=user.id,version=0);db.add(row)
        if body.initialize_examples:
            for n,name in enumerate(('睡眠','饮食','活动')):db.add(CareItem(user_id=user.id,name=name,position=n,rule={'frequency':'daily','weekdays':[]}))
    row.enabled=body.enabled;row.ai_allowed=body.ai_allowed;row.version+=1
    db.flush()
    return finish(db,user,'care-config',body,fp,row,fields(row))

class LegacyIn(WriteIn):
    legacy_id:int
    legacy_version:int

@router.post('/care/legacy-import')
def import_legacy(body:LegacyIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op='care-legacy-import';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    source=get_owned(db,LifeChecklist,body.legacy_id);version(source,body.legacy_version)
    config=db.query(CareConfig).filter_by(user_id=user.id).first();version(config,body.expected_version)
    if not config:config=CareConfig(user_id=user.id,version=0,enabled=bool(source.payload.get('enabled')),ai_allowed=False);db.add(config)
    mapped=[]
    for name,state in source.payload.get('entries',{}).items():
        if state not in ('recorded','skipped','not_recorded'):continue
        item=next((i for i in db.query(CareItem).filter_by(user_id=user.id).all() if any(h.get('legacy_key')==name for h in i.history)),None)
        if not item:
            item=CareItem(user_id=user.id,name=name,position=0,rule={'frequency':'daily','weekdays':[]},history=[{'legacy_key':name,'source_id':source.id}]);db.add(item);db.flush()
        entry=db.query(CareEntry).filter_by(item_id=item.id,local_date=source.local_date).first()
        if not entry and state!='not_recorded':
            entry=CareEntry(user_id=user.id,item_id=item.id,local_date=source.local_date,state=state,snapshot={'name':name,'legacy_source_id':source.id},history=[{'legacy_id':source.id,'legacy_version':source.version,'state':state,'event_mapping':'unknown'}]);db.add(entry)
        mapped.append({'name':name,'item_id':item.id,'state':state})
    config.version+=1;db.flush()
    return finish(db,user,op,body,fp,config,{'mapped':mapped,'config':fields(config),'notice':'旧 JSON 保留；未猜测正文归属，不创建原文、分析或奖励。'})

@router.post('/care/items')
@router.put('/care/items/{item_id}')
def save_item(body:ItemIn,item_id:int|None=None,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'care-item:{item_id or "create"}';fp,prior=begin(db,user,op,body,create=item_id is None)
    if prior is not None:return prior
    row=get_owned(db,CareItem,item_id) if item_id else None
    if row:version(row,body.expected_version)
    if body.goal_id:
        from app.models import Goal
        goal=get_owned(db,Goal,body.goal_id)
        if goal.status!='active':raise HTTPException(409,'请选择进行中的本人目标。')
    if row and body.start and body.start<local_day(utc_now(),user.timezone):raise HTTPException(422,'修改请选今天或未来生效。')
    if not row:row=CareItem(user_id=user.id,version=0,history=[]);db.add(row)
    elif not any('rule' in h for h in row.history):row.history=[*row.history,{**fields(row),'legacy_baseline':True,'at':utc_now().isoformat()}]
    old_rule=row.rule or {}
    rule={'frequency':body.frequency,'weekdays':body.weekdays,'start':str(body.start) if body.start else old_rule.get('start','0001-01-01'),'interval':body.interval,'timezone':user.timezone}
    for key,default in (('category','care'),('planned_minutes',None),('goal_id',None)):
        rule[key]=getattr(body,key) if key in body.model_fields_set else old_rule.get(key,default)
    row.name=body.name;row.position=body.position;row.enabled=body.enabled;row.removed=body.removed;row.rule=rule;row.version+=1
    row.history=[*row.history,{'version':row.version,'name':row.name,'position':row.position,'enabled':row.enabled,'removed':row.removed,'rule':row.rule,'at':utc_now().isoformat()}]
    if not db.query(CareConfig).filter_by(user_id=user.id).first():db.add(CareConfig(user_id=user.id))
    db.flush()
    return finish(db,user,op,body,fp,row,fields(row))

@router.put('/care/items/{item_id}/entries/{day}')
def save_entry(item_id:int,day:date,body:EntryIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'care-entry:{item_id}:{day}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    item=get_owned(db,CareItem,item_id)
    if item.version!=body.item_version or item.removed:raise HTTPException(409,'项目已变更，请刷新。')
    if day>local_day(utc_now(),user.timezone):raise HTTPException(422,'不提前记录未来。')
    row=db.query(CareEntry).filter_by(item_id=item.id,local_date=str(day)).first();version(row,body.expected_version)
    snapshot=row.snapshot if row else item_snapshot(item,day)
    if not snapshot:raise HTTPException(409,'此日没有生效的项目。')
    category=snapshot.get('rule',{}).get('category','care')
    if body.state not in (('recorded','skipped') if category=='care' else ('done','partial','missed')):raise HTTPException(422,'沿用当次项目结果类型，不转换旧语义。')
    if row and category=='plan' and (not body.correction or not body.reason.strip()):raise HTTPException(409,'当次结果已锁定；纠正须明确说明原因。')
    if not row:row=CareEntry(user_id=user.id,item_id=item.id,local_date=str(day),version=0,state=body.state,snapshot=snapshot,history=[]);db.add(row)
    event=get_owned(db,Event,row.event_id) if row.event_id else None
    if body.state in ('recorded','done','partial'):
        if not body.content.strip():raise HTTPException(422,'请写下真实内容。')
        if event:
            if event.content!=body.content:
                if db.query(AIJudgment).filter_by(event_id=event.id,status='confirmed').first():raise HTTPException(409,'原事实已结算；请从手账进行显式纠错，历史内容保留。')
                event.content=body.content;event.content_version+=1
            ai_context.change(db,event,body.ai_permission)
        else:
            event=Event(user_id=user.id,event_type='positive',source='care',record_kind='event',title=item.name,content=body.content,
                occurred_on=str(day),occurred_at=date_range(day,user.timezone)[0],time_precision='date',timezone_at_capture=user.timezone,
                analysis_intent='now' if body.ai_permission=='allowed' else 'never',ai_permission=body.ai_permission)
            db.add(event);db.flush();capture_saved_day(event,user.timezone,db);trial_rules.qualify(db,user,event);row.event_id=event.id
    row.state=body.state;row.version+=1
    row.history=[*row.history,{'version':row.version,'state':row.state,'event_id':row.event_id,'event_version':event.content_version if event else None,'content':event.content if event else '', 'at':utc_now().isoformat()}]
    db.flush()
    return finish(db,user,op,body,fp,row,{'entry':fields(row),'event':fields(event) if event else None})


class SuggestIn(WriteIn):
    topic:str=Field('',max_length=2000)

@router.post('/care/suggestions')
def suggest(body:SuggestIn,db:Session=Depends(get_db)):
    from app.services import llm_config
    from app.services.llm_service import llm_service,LLMError
    import json
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'care-suggest',body)
    if prior is not None:return prior
    config=db.query(CareConfig).filter_by(user_id=user.id).first();version(config,body.expected_version)
    captured=config.version if config else 0
    item_versions=[(i.id,i.version) for i in db.query(CareItem).filter_by(user_id=user.id).order_by(CareItem.id).all()]
    names=[i.name for i in db.query(CareItem).filter_by(user_id=user.id,removed=False,enabled=True).all()] if config and config.ai_allowed else []
    try:model=llm_config.resolve_llm_config(db,user.id,llm_config.PURPOSE_AUX)
    except LLMError as exc:raise HTTPException(503,str(exc)) from None
    messages=[{'role':'system','content':'根据本人主动提供的关注方向建议可选照顾项目，可以建议零项；不要求固定睡眠/饮食/活动，不替用户添加。必要休息免费。不调用任何历史记录。返回JSON {"items":[最多8个简短名称]}。'},
        {'role':'user','content':json.dumps({'topic':body.topic,'authorized_current_names':names},ensure_ascii=False)}]
    from app.services.model_dispatch import mark
    mark(db,user,'care-suggest',body,fp)
    try:result=llm_service.chat_json(messages,config=model)
    except LLMError as exc:raise HTTPException(503,str(exc)) from None
    from app.services.transactions import lock_profile
    lock_profile(db,user.id);llm_config.assert_current(db,model)
    config=db.query(CareConfig).filter_by(user_id=user.id).populate_existing().first()
    current=[(i.id,i.version) for i in db.query(CareItem).filter_by(user_id=user.id).populate_existing().order_by(CareItem.id).all()]
    if (config.version if config else 0)!=captured or current!=item_versions:raise HTTPException(409,'项目或许可已变化，请重新请求。')
    items=result.get('items')
    if not isinstance(items,list) or len(items)>8 or any(not isinstance(n,str) or not n.strip() or len(n)>80 for n in items):raise HTTPException(422,'没有生成有效项目候选。')
    if not config:config=CareConfig(user_id=user.id,version=0);db.add(config)
    config.suggestions=[{'name':name.strip(),'state':'suggested'} for name in dict.fromkeys(items)];config.version+=1;db.flush()
    return finish(db,user,'care-suggest',body,fp,config,fields(config))

@router.post('/care/suggestions/{position}/accept')
def accept_suggestion(position:int,body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'care-accept:{position}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    config=db.query(CareConfig).filter_by(user_id=user.id).first();version(config,body.expected_version)
    if not config or not config.suggestions or position<0 or position>=len(config.suggestions):raise HTTPException(404,'候选不存在。')
    suggestions=[dict(i) for i in config.suggestions];choice=suggestions[position]
    if choice['state']!='suggested':raise HTTPException(409,'此候选已接受。')
    item=CareItem(user_id=user.id,name=choice['name'],rule={'frequency':'daily','weekdays':[]},history=[]);db.add(item);db.flush()
    choice['state']='accepted';choice['item_id']=item.id;config.suggestions=suggestions;config.version+=1;db.flush()
    return finish(db,user,op,body,fp,config,{'config':fields(config),'item':fields(item)})
