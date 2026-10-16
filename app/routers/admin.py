"""Owner capability workspace. Only account/operator metadata; no diary/key access."""
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import text,func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.models.access import AuthSession
from app.models.accounts import SitePolicy,Announcement,AdminAudit
from app.services.auth_service import current_user


def require_owner(user=Depends(current_user)):
    if user.role!='owner':raise HTTPException(403,'需要站点管理能力。')
    return user
from app.services.workflow_common import WriteIn,begin,finish,fields
from app.services.site_policy import read

router=APIRouter(prefix='/admin',dependencies=[Depends(require_owner)])


class PolicyIn(WriteIn):
    site_name:str=Field(min_length=1,max_length=80)
    description:str=Field('',max_length=500)
    registration:Literal['open','invite','closed']
    email_required:bool=False
    password_sessions:Literal['all','others']='all'
    reason:str=Field(min_length=1,max_length=2000)


class StatusIn(WriteIn):
    status:Literal['active','disabled']
    reason:str=Field(min_length=1,max_length=2000)


class AnnouncementIn(WriteIn):
    title:str=Field(min_length=1,max_length=120)
    content:str=Field(max_length=4000)
    published:bool=False
    reason:str=Field(min_length=1,max_length=2000)


def lock(db):
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(61111220)'))


def audit(db,owner,action,target,reason,version):
    db.add(AdminAudit(actor_id=owner.id,action=action,target=target,reason=reason,version=version))


@router.get('/overview')
def overview(db:Session=Depends(get_db)):
    return {'users':db.query(User).count(),'active':db.query(User).filter_by(status='active').count(),
        'published_announcements':db.query(Announcement).filter_by(published=True).count(),'site':read(db)}


@router.get('/users')
def users(offset:int=0,limit:int=50,db:Session=Depends(get_db)):
    return {'items':[{'id':u.id,'username':u.username,'status':u.status,'role':u.role,'version':u.credentials_version,
        'email_verified':bool(u.email_verified_at),'created_at':u.created_at.isoformat()} for u in db.query(User).order_by(User.id).offset(max(0,offset)).limit(min(100,max(1,limit))).all()]}


@router.post('/users/{user_id}/status')
def status(user_id:int,body:StatusIn,db:Session=Depends(get_db),owner=Depends(require_owner)):
    lock(db)
    op=f'admin-status:{user_id}';fp,prior=begin(db,owner,op,body)
    if prior is not None:return prior
    lock(db);user=db.query(User).filter_by(id=user_id).populate_existing().with_for_update().first()
    if not user:raise HTTPException(404,'账号不存在。')
    if user.credentials_version!=body.expected_version:raise HTTPException(409,'账号版本已变化。')
    if body.status=='disabled' and user.role=='owner' and db.query(User).filter_by(role='owner',status='active').count()<=1:raise HTTPException(409,'不能停用唯一可用管理账号。')
    if user.id==owner.id and body.status=='disabled':raise HTTPException(409,'不能在当前会话停用自己。')
    from app.services.transactions import lock_profile
    db.info['manage_profile_locks']=True
    try:lock_profile(db,user.id)
    finally:db.info.pop('manage_profile_locks',None)
    user.status=body.status;user.credentials_version+=1
    # Explicit security capability applies only to auth-session metadata. All diary/game scopes remain bound.
    db.info['manage_auth_sessions']=True
    if user.status=='disabled':db.query(AuthSession).filter_by(user_id=user.id).update({AuthSession.revoked:True})
    db.info.pop('manage_auth_sessions',None)
    audit(db,owner,'account-status',str(user.id),body.reason,user.credentials_version)
    return finish(db,owner,op,body,fp,user,{'id':user.id,'status':user.status,'version':user.credentials_version})


@router.get('/site')
def site(db:Session=Depends(get_db)):return read(db)


@router.put('/site')
def save_site(body:PolicyIn,db:Session=Depends(get_db),owner=Depends(require_owner)):
    lock(db)
    fp,prior=begin(db,owner,'admin-site',body)
    if prior is not None:return prior
    lock(db);row=db.query(SitePolicy).filter_by(id=1).populate_existing().with_for_update().first()
    if body.expected_version!=(row.version if row else 0):raise HTTPException(409,'站点设置已更新。')
    if body.email_required:
        from app.services.mail_service import mailer
        if not mailer().ready:raise HTTPException(409,'邮件服务未配置，不能开启新注册强制验证。')
    if not row:row=SitePolicy(id=1,version=0,payload={});db.add(row)
    row.payload=body.model_dump(exclude={'request_key','expected_version','reason'});row.version+=1
    audit(db,owner,'site-policy','site',body.reason,row.version);db.flush()
    return finish(db,owner,'admin-site',body,fp,row,read(db))


@router.get('/announcements')
def announcements(offset:int=0,db:Session=Depends(get_db)):
    return {'items':[fields(row) for row in db.query(Announcement).order_by(Announcement.id.desc()).offset(max(0,offset)).limit(50).all()]}


@router.post('/announcements')
@router.put('/announcements/{announcement_id}')
def save_announcement(body:AnnouncementIn,announcement_id:int|None=None,db:Session=Depends(get_db),owner=Depends(require_owner)):
    lock(db)
    op=f'admin-notice:{announcement_id or "create"}';fp,prior=begin(db,owner,op,body,create=announcement_id is None)
    if prior is not None:return prior
    lock(db);row=db.get(Announcement,announcement_id) if announcement_id else None
    if announcement_id and not row:raise HTTPException(404,'公告不存在。')
    if row and row.version!=body.expected_version:raise HTTPException(409,'公告已更新。')
    if not row:row=Announcement(version=0,title='',content='');db.add(row)
    row.title=body.title;row.content=body.content;row.published=body.published;row.version+=1;db.flush()
    audit(db,owner,'announcement',str(row.id),body.reason,row.version)
    return finish(db,owner,op,body,fp,row,fields(row))


@router.get('/audit')
def logs(offset:int=0,db:Session=Depends(get_db)):
    return {'items':[fields(row) for row in db.query(AdminAudit).order_by(AdminAudit.id.desc()).offset(max(0,offset)).limit(50).all()]}


public=APIRouter()
@public.get('/announcements')
def published(db:Session=Depends(get_db)):
    return {'items':[fields(row) for row in db.query(Announcement).filter_by(published=True).order_by(Announcement.id.desc()).limit(20).all()]}
