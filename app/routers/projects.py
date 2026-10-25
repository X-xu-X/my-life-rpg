"""One project editor over stable plan/care identities; old results stay in place."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.workflow import PlanSchedule,PlanOccurrence
from app.models.full_system import CareItem,CareEntry,CareConfig
from app.services.workflow_common import fields,WriteIn,begin,finish,version
from app.services.user_service import get_or_create_default_user
from app.services.time_service import utc_now,local_day
from app.routers import plans,care

router=APIRouter()


class ProjectIn(plans.ScheduleIn):
    planned_minutes:int|None=Field(None,ge=1,le=1440,strict=True)
    position:int=Field(0,ge=0,le=100000)
    removed:bool=False


class OrderItem(BaseModel):
    key:str
    version:int=Field(ge=1,strict=True)


class OrderIn(WriteIn):
    items:list[OrderItem]=Field(min_length=1,max_length=1000)


@router.post('/projects/reorder')
def reorder(body:OrderIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'project-order',body,create=True)
    if prior is not None:return prior
    current={}
    for origin,model in (('plan',PlanSchedule),('care',CareItem)):
        for row in db.query(model).filter_by(user_id=user.id).populate_existing().all():
            if not (row.removed if origin=='care' else row.rule.get('removed',False)):
                current[f'{origin}:{row.id}']=(origin,row)
    keys=[item.key for item in body.items]
    if len(set(keys))!=len(keys) or set(keys)!=set(current):
        raise HTTPException(409,'项目列表已有变化，请重新读取后排序。')
    for item in body.items:version(current[item.key][1],item.version)
    for position,item in enumerate(body.items):
        origin,row=current[item.key]
        if origin=='care':row.position=position
        else:row.rule={**row.rule,'position':position}
        row.version+=1
        # Order is presentation only. Do not replace dated schedule snapshots.
    return finish(db,user,'project-order',body,fp,current[keys[0]][1],{'order':keys})


@router.get('/projects')
def projects(day:date|None=None,include_removed:bool=False,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);selected=day or local_day(utc_now(),user.timezone);items=[]
    config=db.query(CareConfig).filter_by(user_id=user.id).first()
    care_enabled=bool(config and config.enabled)
    for origin,model,entry_model in (('plan',PlanSchedule,PlanOccurrence),('care',CareItem,CareEntry)):
        for row in db.query(model).filter_by(user_id=user.id).order_by(model.id).all():
            removed=row.removed if origin=='care' else row.rule.get('removed',False)
            if removed and not include_removed:continue
            snapshot=(plans.timing_snapshot if origin=='plan' else care.item_snapshot)(row,selected)
            foreign='schedule_id' if origin=='plan' else 'item_id'
            saved=db.query(entry_model).filter_by(user_id=user.id,local_date=str(selected),**{foreign:row.id}).first()
            if saved:snapshot=saved.schedule_snapshot if origin=='plan' else saved.snapshot
            category=(snapshot or {}).get('rule',{}).get('category',origin)
            effective_rule={'start':'0001-01-01','interval':1,**(snapshot or {}).get('rule',{})}
            scheduled_due=bool(snapshot and snapshot.get('enabled') and not snapshot.get('removed') and not effective_rule.get('removed') and plans.due(effective_rule,selected))
            visible=not removed and (category!='care' or care_enabled)
            dated=[h for h in row.history if 'rule' in h]
            items.append({'origin':origin,'key':f'{origin}:{row.id}','id':row.id,'version':row.version,'name':row.name,'enabled':row.enabled,
                'position':row.position if origin=='care' else row.rule.get('position',0),'removed':removed,
                'category':row.rule.get('category',origin),'rule':row.rule,'goal_id':row.goal_id if origin=='plan' else row.rule.get('goal_id'),
                'effective_from':dated[-1].get('effective_from',dated[-1]['rule'].get('start','0001-01-01')) if dated else row.rule.get('start','0001-01-01'),
                'history':row.history,'effective':snapshot,'result_category':category,'scheduled_due':scheduled_due,'due':scheduled_due and visible,
                'show_today':visible and bool(scheduled_due or saved),'entry':fields(saved) if saved else None,
                'local_date':str(selected)})
    items.sort(key=lambda p:(p['position'],p['origin'],p['id']))
    return {'day':str(selected),'items':items,'care_config':fields(config) if config else None}


@router.post('/projects')
@router.put('/projects/{origin}/{project_id}')
def save_project(body:ProjectIn,origin:Literal['plan','care']|None=None,project_id:int|None=None,db:Session=Depends(get_db)):
    data=body.model_dump(mode='json');origin=origin or ('care' if body.category=='care' else 'plan')
    for key in ('effective_from','position','removed'):
        if key not in body.model_fields_set:data.pop(key,None)
    if origin=='plan':
        return {'origin':origin,'project':plans.save_schedule(plans.ScheduleIn.model_validate(data),project_id,db)}
    return {'origin':origin,'project':care.save_item(care.ItemIn.model_validate(data),project_id,db)}
