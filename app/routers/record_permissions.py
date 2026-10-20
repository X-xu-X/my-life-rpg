from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event
from app.services import ai_context
from app.services.workflow_common import WriteIn,begin,finish,get_owned
from app.services.user_service import get_or_create_default_user

router=APIRouter()

class PermissionIn(WriteIn):
    permission:Literal['private','allowed']
    content_version:int
    acknowledge:bool=False

@router.put('/events/{event_id}/ai-permission')
def set_permission(event_id:int,body:PermissionIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'permission:{event_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    event=get_owned(db,Event,event_id)
    if event.is_deleted or event.ai_permission_version!=body.expected_version or event.content_version!=body.content_version:raise HTTPException(409,'原文或许可版本已变化，请保留输入并刷新。')
    if body.permission=='allowed' and (not body.acknowledge or event.is_pure):raise HTTPException(422,'请明确同意将本篇用于分析；旧纯享记录保留原合同。')
    ai_context.change(db,event,body.permission)
    return finish(db,user,op,body,fp,event,{'id':event.id,'ai_permission':event.ai_permission,'ai_permission_version':event.ai_permission_version})
