"""Owner capability workspace. Only account/operator metadata; no diary/key access."""
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from datetime import timedelta
from app.services.time_service import utc_now,local_day,date_range
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
def overview(db:Session=Depends(get_db),owner=Depends(require_owner)):
    now=utc_now();start,end=date_range(local_day(now,owner.timezone),owner.timezone)
    groups={}
    for role,label in [('user','ordinary'),('owner','administrators')]:
        query=db.query(User).filter_by(role=role)
        groups[label]={'total':query.count(),'active':query.filter_by(status='active').count(),
            'disabled':query.filter_by(status='disabled').count(),
            'created_today':query.filter(User.created_at>=start,User.created_at<end).count(),
            'logged_in_7_days':query.filter(User.last_login_at>=now-timedelta(days=7)).count()}
    return {'users':db.query(User).count(),'active':db.query(User).filter_by(status='active').count(),
        'groups':groups,'timezone':owner.timezone,'as_of':now.isoformat(),
        'published_announcements':db.query(Announcement).filter_by(published=True).count(),'site':read(db)}


@router.get('/users')
def users(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),q:str=Query('',max_length=50),
          role:Literal['user','owner']|None=None,status:Literal['active','disabled']|None=None,db:Session=Depends(get_db)):
    query=db.query(User)
    if q:query=query.filter(User.username.contains(q,autoescape=True))
    if role:query=query.filter_by(role=role)
    if status:query=query.filter_by(status=status)
    return {'total':query.count(),'items':[{'id':u.id,'username':u.username,'status':u.status,'role':u.role,'version':u.credentials_version,
        'email_verified':bool(u.email_verified_at),'last_login_at':u.last_login_at.isoformat() if u.last_login_at else None,
        'created_at':u.created_at.isoformat()} for u in query.order_by(User.id).offset(offset).limit(limit).all()]}


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
