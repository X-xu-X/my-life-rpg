from typing import Literal
from pydantic import Field
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event
from app.models.workflow import FactSettlement,EventFact
from app.models.full_system import FactBundle,FactFragment,FactNote
from app.services import fact_analysis,facts
from app.services.workflow_common import WriteIn,begin,finish,version,fields,get_owned
from app.services.user_service import get_or_create_default_user
from app.services.time_service import utc_now

router=APIRouter()

class DecisionIn(WriteIn):
    fragment_id:int
    decision:Literal['same','distinct','keep','skip']
    mainline:bool=False
    related_fact_id:int|None=None

class NoteIn(WriteIn):
    content:str=Field(min_length=1,max_length=10000)
    bundle_id:int|None=None

@router.get('/events/{event_id}/fact-notes')
def notes(event_id:int,db:Session=Depends(get_db)):
    event=get_owned(db,Event,event_id)
    return {'items':[fields(n) for n in db.query(FactNote).filter_by(event_id=event.id).order_by(FactNote.id).all()]}

@router.post('/events/{event_id}/fact-notes')
def supplement(event_id:int,body:NoteIn,db:Session=Depends(get_db)):
    from app.services import ai_context
    user=get_or_create_default_user(db);op=f'fact-note:{event_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    event=get_owned(db,Event,event_id);ai_context.require(event)
    if event.content_version!=body.expected_version:raise HTTPException(409,'原文已变化，请读取最新版本；补充草稿仍保留。')
    if not body.content.strip():raise HTTPException(422,'请填写相关补充。')
    questions=[]
    if body.bundle_id:
        bundle=get_owned(db,FactBundle,body.bundle_id)
        if bundle.event_id!=event.id:raise HTTPException(404,'建议不存在。')
        questions=bundle.payload.get('questions',[]) if bundle.event_version==event.content_version else []
    row=FactNote(user_id=user.id,event_id=event.id,event_version=event.content_version,permission_version=event.ai_permission_version,content=body.content,question_snapshot=questions)
    db.add(row);db.flush()
    return finish(db,user,op,body,fp,row,fields(row))

@router.get('/events/{event_id}/fact-bundles')
def bundles(event_id:int,db:Session=Depends(get_db)):
    event=get_owned(db,Event,event_id)
    return {'items':[fields(b) for b in db.query(FactBundle).filter_by(event_id=event.id).order_by(FactBundle.id.desc()).limit(30).all()]}

@router.post('/fact-bundles/{bundle_id}/decision')
def decide(bundle_id:int,body:DecisionIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'bundle-decision:{bundle_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    bundle=get_owned(db,FactBundle,bundle_id);version(bundle,body.expected_version);fact_analysis.source_valid(db,bundle)
    if bundle.state=='confirmed':raise HTTPException(409,'已确认建议保留历史，请重新分析新事实。')
    payload={**bundle.payload,'items':[dict(i) for i in bundle.payload['items']]}
    item=next((i for i in payload['items'] if i['fragment_id']==body.fragment_id),None)
    if not item:raise HTTPException(404,'建议不存在。')
    fragment=get_owned(db,FactFragment,body.fragment_id)
    if fragment.version!=item['fragment_version']:raise HTTPException(409,'事实关系已有更正。')
    booked=db.query(FactSettlement).filter_by(fact_id=fragment.fact_id).first()
    if body.decision=='same':
        target=body.related_fact_id or item['candidate_fact_id']
        if target and target not in [item['candidate_fact_id'],*[o['fact_id'] for o in item.get('candidate_options',[])]]:raise HTTPException(422,'请选择本组已有事实候选。')
        if not target:raise HTTPException(422,'此项没有同事实候选。')
        if booked and fragment.fact_id!=target:raise HTTPException(409,'已结算身份不能迁移或重算。')
        origin=fragment.fact_id
        if origin!=target:
            db.query(EventFact).filter_by(fact_id=origin,user_id=user.id).update({EventFact.fact_id:target},synchronize_session=False)
            for related in db.query(FactFragment).filter_by(fact_id=origin,user_id=user.id).all():
                related.fact_id=target;related.version+=1
                related.history=[*related.history,{'decision':'associate','origin_fact_id':origin,'target_fact_id':target,'at':utc_now().isoformat()}]
        fragment.decision='same'
    elif body.decision=='distinct':
        association=next((h for h in reversed(fragment.history) if h['decision']=='associate'),None)
        if association and fragment.decision=='same':
            origin=association['origin_fact_id']
            if db.query(FactSettlement).filter_by(fact_id=origin).first():raise HTTPException(409,'原事实已结算，不能重置奖励身份。')
            fragment.fact_id=origin
            event_link=db.query(EventFact).filter_by(event_id=bundle.event_id).first()
            if event_link:event_link.fact_id=origin
        fragment.decision='distinct'
    item['decision']='skip' if body.decision=='skip' else 'keep';item['mainline']=body.mainline
    fragment.history=[*fragment.history,{'decision':body.decision,'candidate_fact_id':item['candidate_fact_id'],'at':utc_now().isoformat()}]
    fragment.version+=1;item['fragment_version']=fragment.version;item['fact_id']=fragment.fact_id
    bundle.payload=payload;bundle.preview=None;bundle.state='draft';bundle.version+=1
    return finish(db,user,op,body,fp,bundle,fields(bundle))

@router.post('/fact-bundles/{bundle_id}/preview')
def preview(bundle_id:int,body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'bundle-preview:{bundle_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    bundle=get_owned(db,FactBundle,bundle_id);version(bundle,body.expected_version)
    if bundle.state=='confirmed':raise HTTPException(409,'此组已确认。')
    bundle.preview=fact_analysis.preview(db,user,bundle);bundle.state='preview';bundle.version+=1
    return finish(db,user,op,body,fp,bundle,fields(bundle))

@router.post('/fact-bundles/{bundle_id}/confirm')
def confirm(bundle_id:int,body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'bundle-confirm:{bundle_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    bundle=get_owned(db,FactBundle,bundle_id);version(bundle,body.expected_version)
    fact_analysis.confirm(db,user,bundle)
    from app.services.coin_service import balance
    return finish(db,user,op,body,fp,bundle,{'bundle':fields(bundle),'balance':balance(db,user),'coins_gained':bundle.preview['total']})
