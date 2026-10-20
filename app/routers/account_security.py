from datetime import timedelta
import secrets
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models import User
from app.models.access import AuthSession,RecoveryToken
from app.models.accounts import EmailToken
from app.services import auth_service as auth,mail_service
from app.services.time_service import utc_now

router=APIRouter(prefix='/auth')


class EmailIn(BaseModel):
    email:str=Field(max_length=254)


class TokenIn(BaseModel):
    token:str=Field(min_length=30,max_length=100)


class ResetIn(TokenIn):
    new_password:str=Field(min_length=12,max_length=256)


class PasswordIn(BaseModel):
    current_password:str=Field(max_length=256)
    new_password:str=Field(min_length=12,max_length=256)
    expected_version:int


def send_token(db,email,purpose,user=None):
    transport=mail_service.mailer()
    if not transport.ready:raise HTTPException(503,'邮件服务未配置，未发送邮件；原恢复码继续可用。')
    token=secrets.token_urlsafe(40)
    row=EmailToken(user_id=user.id if user else None,email=email,purpose=purpose,token_hash=auth.digest(token),
        credentials_version=user.credentials_version if user else None,expires_at=utc_now()+timedelta(minutes=30))
    db.add(row);db.commit()
    transport.send(email,purpose,token)
    return {'status':'sent','expires_in_minutes':30}


def valid_token(db,token,purpose=None):
    row=db.query(EmailToken).filter_by(token_hash=auth.digest(token)).with_for_update().first()
    if not row or row.consumed_at or row.expires_at<=utc_now() or purpose and row.purpose!=purpose:raise HTTPException(400,'验证信息无效或已使用。')
    if row.user_id:
        user=db.query(User).filter_by(id=row.user_id).with_for_update().one()
        if user.status!='active' or user.credentials_version!=row.credentials_version:raise HTTPException(400,'验证信息已失效。')
    return row


@router.get('/options')
def options(db:Session=Depends(get_db)):
    from app.services.site_policy import read
    policy=read(db)
    return {k:policy[k] for k in ('registration','email_required','site_name')}|{'mail_ready':mail_service.mailer().ready}


@router.post('/email/register-request')
def registration_email(body:EmailIn,request:Request,db:Session=Depends(get_db)):
    auth.check_origin(request);auth.throttle(request,'email')
    from app.services.site_policy import read
    if read(db)['registration']=='closed':raise HTTPException(403,'注册已关闭。')
    return send_token(db,mail_service.normalize(body.email),'register')


@router.post('/email/bind-request')
def bind_email(body:EmailIn,request:Request,db:Session=Depends(get_db),user=Depends(auth.current_user)):
    auth.throttle(request,'email');return send_token(db,mail_service.normalize(body.email),'bind',user)


@router.post('/email/verify')
def verify(body:TokenIn,request:Request,db:Session=Depends(get_db)):
    auth.check_origin(request);auth.throttle(request,'verify-email');row=valid_token(db,body.token)
    if row.purpose=='register':row.verified=True
    elif row.purpose=='bind':
        user=db.get(User,row.user_id);user.email=row.email;user.email_verified_at=utc_now();row.consumed_at=utc_now();user.credentials_version+=1
    else:raise HTTPException(400,'验证用途无效。')
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(400,'此邮箱无法绑定。') from None
    return {'status':'verified','purpose':row.purpose}


@router.post('/email/recover-request')
def recover_email(body:EmailIn,request:Request,db:Session=Depends(get_db)):
    auth.check_origin(request);auth.throttle(request,'email-recover')
    email=mail_service.normalize(body.email)
    if not mail_service.mailer().ready:raise HTTPException(503,'邮件服务未配置，仍可使用恢复码。')
    # Identical durable acceptance path. Never resolve account or contact SMTP here.
    from app.models.accounts import MailDelivery
    db.add(MailDelivery(email=email,purpose='recover',expires_at=utc_now()+timedelta(minutes=30)))
    db.commit()
    return {'status':'accepted','message':'若此邮箱有已验证的可用账号，将尝试投递恢复验证码。受理不代表投递成功；未收到时仍可用恢复码。'}


@router.post('/email/reset-password')
def reset_email_password(body:ResetIn,request:Request,db:Session=Depends(get_db)):
    auth.check_origin(request);auth.throttle(request,'email-reset');row=valid_token(db,body.token,'recover');user=db.get(User,row.user_id)
    if user.email!=row.email:raise HTTPException(400,'邮箱已变化。')
    row.consumed_at=utc_now();user.password_hash=auth.PASSWORDS.hash(body.new_password);user.credentials_version+=1
    db.query(AuthSession).filter_by(user_id=user.id).update({AuthSession.revoked:True})
    db.query(RecoveryToken).filter_by(user_id=user.id,consumed_at=None).update({RecoveryToken.consumed_at:utc_now()})
    code=auth.new_recovery(db,user);db.commit();return {'status':'changed','recovery_code':code,'reauthenticate':True}


@router.post('/password')
def change_password(body:PasswordIn,request:Request,response:Response,db:Session=Depends(get_db),user=Depends(auth.current_user)):
    auth.throttle(request,'password');db.refresh(user,with_for_update=True)
    if body.expected_version!=user.credentials_version:raise HTTPException(409,'账号安全版本已变化，请刷新。')
    if not auth.verify_password(user,body.current_password):raise HTTPException(400,'当前密码无效。')
    user.password_hash=auth.PASSWORDS.hash(body.new_password);user.credentials_version+=1
    from app.services.site_policy import read
    query=db.query(AuthSession).filter_by(user_id=user.id)
    all_sessions=read(db)['password_sessions']=='all'
    if not all_sessions:query=query.filter(AuthSession.id!=request.state.auth_session.id)
    query.update({AuthSession.revoked:True})
    db.query(RecoveryToken).filter_by(user_id=user.id,consumed_at=None).update({RecoveryToken.consumed_at:utc_now()})
    recovery=auth.new_recovery(db,user);db.commit()
    if all_sessions:response.delete_cookie(auth.COOKIE,path='/',secure=True,httponly=True,samesite='lax')
    return {'status':'changed','recovery_code':recovery,'reauthenticate':all_sessions,'credentials_version':user.credentials_version}


@router.get('/sessions')
def sessions(request:Request,db:Session=Depends(get_db),user=Depends(auth.current_user)):
    current=getattr(request.state,'auth_session',None)
    return {'items':[{'id':s.id,'created_at':s.created_at,'last_seen':s.last_seen,'expires_at':s.expires_at,'current':bool(current and current.id==s.id)}
        for s in db.query(AuthSession).filter(AuthSession.user_id==user.id,AuthSession.revoked.is_(False),AuthSession.expires_at>utc_now()).order_by(AuthSession.id.desc()).limit(100).all()]}

class RevokeIn(BaseModel):
    expected_version:int

@router.post('/sessions/revoke-others')
def revoke_others(body:RevokeIn,request:Request,db:Session=Depends(get_db),user=Depends(auth.current_user)):
    db.refresh(user,with_for_update=True)
    if user.credentials_version!=body.expected_version:raise HTTPException(409,'安全版本已变化，请刷新。')
    current=getattr(request.state,'auth_session',None)
    query=db.query(AuthSession).filter_by(user_id=user.id,revoked=False)
    if current:query=query.filter(AuthSession.id!=current.id)
    count=query.update({AuthSession.revoked:True});db.commit()
    return {'revoked':count,'status':'revoked'}
