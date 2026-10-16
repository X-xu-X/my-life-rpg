"""User-confirmed fact identities guard all existing settlement paths."""
from fastapi import HTTPException
from app.models import AIJudgment
from app.models.workflow import FactIdentity,EventFact,FactSettlement


def identity(db,event):
    link=db.query(EventFact).filter_by(event_id=event.id).first()
    if link:return link.fact_id
    fact=FactIdentity(user_id=event.user_id,identity_key='event:'+str(event.id));db.add(fact);db.flush()
    db.add(EventFact(user_id=event.user_id,event_id=event.id,fact_id=fact.id));db.flush()
    # An explicit association to a previously booked legacy event must also block a second booking.
    old=db.query(AIJudgment).filter_by(event_id=event.id,status='confirmed').first()
    if old:db.add(FactSettlement(user_id=event.user_id,fact_id=fact.id,judgment_id=old.id));db.flush()
    return fact.id


def claim(db,event,judgment):
    fact_id=identity(db,event)
    if db.query(FactSettlement).filter_by(fact_id=fact_id).first():raise ValueError('同一事实已有结算；本条原文保留，不再次入账。')
    db.add(FactSettlement(user_id=event.user_id,fact_id=fact_id,judgment_id=judgment.id));db.flush()


def associate(db,source,target):
    if source.id==target.id or source.is_deleted or target.is_deleted:raise HTTPException(409,'关联对象无效。')
    if source.record_kind=='diary' or target.record_kind=='diary':raise HTTPException(409,'日记整篇不能冒充单一行动事实。请关联具体事件。')
    target_fact=identity(db,target);source_fact=identity(db,source)
    if source_fact==target_fact:return
    if db.query(FactSettlement).filter_by(fact_id=source_fact).first():raise HTTPException(409,'来源事实已结算，不能自动合并或重算旧账。')
    if db.query(EventFact).filter_by(fact_id=source_fact).count()>1:raise HTTPException(409,'来源已有其他关联，请保留事实组，不隐式迁移其他记录。')
    db.query(EventFact).filter_by(event_id=source.id).one().fact_id=target_fact
