"""One project editor over stable plan/care identities; old results stay in place."""
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends
from pydantic import Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.workflow import PlanSchedule,PlanOccurrence
from app.models.full_system import CareItem,CareEntry
from app.services.workflow_common import fields,WriteIn
from app.services.user_service import get_or_create_default_user
from app.services.time_service import utc_now,local_day
from app.routers import plans,care

router=APIRouter()


class ProjectIn(plans.ScheduleIn):
    planned_minutes:int|None=Field(None,ge=1,le=1440,strict=True)
    position:int=Field(0,ge=0,le=100000)
    removed:bool=False


@router.get('/projects')
def projects(day:date|None=None,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);selected=day or local_day(utc_now(),user.timezone);items=[]
    for origin,model,entry_model in (('plan',PlanSchedule,PlanOccurrence),('care',CareItem,CareEntry)):
        for row in db.query(model).filter_by(user_id=user.id).order_by(model.id).all():
            if origin=='care' and row.removed:continue
            snapshot=(plans.timing_snapshot if origin=='plan' else care.item_snapshot)(row,selected)
            foreign='schedule_id' if origin=='plan' else 'item_id'
            saved=db.query(entry_model).filter_by(user_id=user.id,local_date=str(selected),**{foreign:row.id}).first()
            if saved:snapshot=saved.schedule_snapshot if origin=='plan' else saved.snapshot
            category=(snapshot or {}).get('rule',{}).get('category',origin)
            effective_rule={'start':'0001-01-01','interval':1,**(snapshot or {}).get('rule',{})}
            due=bool(snapshot and snapshot.get('enabled') and not snapshot.get('removed') and plans.due(effective_rule,selected))
            items.append({'origin':origin,'key':f'{origin}:{row.id}','id':row.id,'version':row.version,'name':row.name,'enabled':row.enabled,
                'category':row.rule.get('category',origin),'rule':row.rule,'goal_id':row.goal_id if origin=='plan' else row.rule.get('goal_id'),
                'history':row.history,'effective':snapshot,'result_category':category,'due':due,'entry':fields(saved) if saved else None,
                'local_date':str(selected)})
    return {'day':str(selected),'items':items}


@router.post('/projects')
@router.put('/projects/{origin}/{project_id}')
def save_project(body:ProjectIn,origin:Literal['plan','care']|None=None,project_id:int|None=None,db:Session=Depends(get_db)):
    data=body.model_dump(mode='json');origin=origin or ('care' if body.category=='care' else 'plan')
    if origin=='plan':
        for key in ('position','removed'):data.pop(key,None)
        return {'origin':origin,'project':plans.save_schedule(plans.ScheduleIn.model_validate(data),project_id,db)}
    return {'origin':origin,'project':care.save_item(care.ItemIn.model_validate(data),project_id,db)}
