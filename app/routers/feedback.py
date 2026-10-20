from datetime import timedelta
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.full_system import Feedback,FeedbackReply
from app.routers.admin import require_owner,audit
from app.services.workflow_common import WriteIn,begin,finish,version,fields,get_owned
from app.services.user_service import get_or_create_default_user
from app.services.time_service import utc_now

router=APIRouter()

class FeedbackIn(WriteIn):
    kind:Literal['problem','suggestion','question']
    title:str=Field(min_length=1,max_length=120)
    content:str=Field(min_length=1,max_length=6000)

class ReplyIn(WriteIn):
    content:str=Field(min_length=1,max_length=6000)
    state:Literal['open','answered','closed']='answered'

def out(db,row):return {**fields(row),'replies':[fields(r) for r in db.query(FeedbackReply).filter_by(feedback_id=row.id).order_by(FeedbackReply.id).all()]}

@router.get('/feedback')
def read(offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    user=get_or_create_default_user(db)
    return {'items':[out(db,r) for r in db.query(Feedback).filter_by(user_id=user.id).order_by(Feedback.id.desc()).offset(offset).limit(30).all()]}

@router.post('/feedback')
def create(body:FeedbackIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'feedback-create',body,create=True)
    if prior is not None:return prior
    if not body.title.strip() or not body.content.strip():raise HTTPException(422,'请填写标题和内容。')
    if db.query(Feedback).filter(Feedback.user_id==user.id,Feedback.created_at>utc_now()-timedelta(days=1)).count()>=20:raise HTTPException(429,'今天已提交较多反馈，请稍后再试。')
    row=Feedback(user_id=user.id,kind=body.kind,title=body.title,content=body.content);db.add(row);db.flush()
    return finish(db,user,'feedback-create',body,fp,row,out(db,row))

@router.post('/feedback/{feedback_id}/reply')
def reply(feedback_id:int,body:ReplyIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'feedback-reply:{feedback_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,Feedback,feedback_id);version(row,body.expected_version)
    if not body.content.strip():raise HTTPException(422,'请填写回复。')
    row.version+=1;row.state='open';db.add(FeedbackReply(user_id=user.id,actor_id=user.id,feedback_id=row.id,content=body.content))
    db.flush()
    return finish(db,user,op,body,fp,row,out(db,row))

@router.get('/admin/feedback')
def admin_read(offset:int=Query(0,ge=0),state:Literal['open','answered','closed']|None=None,db:Session=Depends(get_db),owner=Depends(require_owner)):
    db.info['manage_feedback']=True
    query=db.query(Feedback)
    if state:query=query.filter_by(state=state)
    return {'items':[out(db,r) for r in query.order_by(Feedback.id.desc()).offset(offset).limit(30).all()]}

@router.post('/admin/feedback/{feedback_id}/reply')
def admin_reply(feedback_id:int,body:ReplyIn,db:Session=Depends(get_db),owner=Depends(require_owner)):
    op=f'admin-feedback:{feedback_id}';fp,prior=begin(db,owner,op,body)
    if prior is not None:return prior
    db.info['manage_feedback']=True
    row=db.query(Feedback).filter_by(id=feedback_id).populate_existing().with_for_update().first()
    if not row:raise HTTPException(404,'反馈不存在。')
    version(row,body.expected_version)
    if not body.content.strip():raise HTTPException(422,'请填写回复。')
    row.version+=1;row.state=body.state
    db.add(FeedbackReply(user_id=row.user_id,actor_id=owner.id,feedback_id=row.id,content=body.content))
    audit(db,owner,'feedback-reply',str(row.id),'站内私密回复',row.version)
    db.flush()
    return finish(db,owner,op,body,fp,row,out(db,row))
