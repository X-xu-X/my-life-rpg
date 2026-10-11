"""认证入口与一次性恢复码；从未向外回传摘要或密码哈希。"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import settings
from app.services.time_service import utc_now
from app.database import get_db
from app.models import User, UserProfile
from app.models.access import Invitation, RecoveryToken, AuthSession
from app.services import auth_service as auth

router = APIRouter(prefix="/auth")


class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-]+$")
    password: str = Field(min_length=12, max_length=256)


class RegisterIn(LoginIn):
    invite_token: str = Field(min_length=20, max_length=100)


class RecoverIn(BaseModel):
    recovery_code: str = Field(min_length=20, max_length=100)
    new_password: str = Field(min_length=12, max_length=256)


@router.get("/me")
async def me(request: Request, db: Session = Depends(get_db)):
    user = await auth.current_user(request, db)
    profile = db.query(UserProfile).filter_by(user_id=user.id).first()
    session = getattr(request.state, "auth_session", None)
    return {"id": user.id, "username": user.username, "role": user.role,
        "timezone": user.timezone, "mode": settings.run_mode,
        "onboarding_completed": bool(profile and profile.onboarding_completed),
        "csrf_token": session.csrf_secret if session else ""}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth.check_origin(request); auth.throttle(request, "register")
    claimed = db.query(Invitation).filter(Invitation.token_hash == auth.digest(body.invite_token),
        Invitation.consumed_at.is_(None), Invitation.expires_at > utc_now()).update(
            {Invitation.consumed_at: utc_now()}, synchronize_session=False)
    if claimed != 1:
        db.rollback(); raise HTTPException(400, "邀请无效或注册信息不可用。")
    try:
        user = auth.initialize_account(db, body.username, body.password)
        recovery = auth.new_recovery(db, user)
        session = auth.create_session(db, user, response)
        db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(400, "邀请无效或注册信息不可用。") from exc
    return {"id": user.id, "recovery_code": recovery, "csrf_token": session.csrf_secret}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth.check_origin(request); auth.throttle(request, "login")
    # Serialize password verification/session creation against recovery revocation.
    user = db.query(User).filter(User.username == body.username).with_for_update().first()
    if not auth.verify_password(user, body.password):
        raise HTTPException(401, "登录信息无效。")
    old = request.cookies.get(auth.COOKIE)
    if old:
        db.query(AuthSession).filter_by(token_hash=auth.digest(old)).update({AuthSession.revoked: True})
    if auth.PASSWORDS.check_needs_rehash(user.password_hash):
        user.password_hash = auth.PASSWORDS.hash(body.password)
    session = auth.create_session(db, user, response)
    db.commit()
    return {"id": user.id, "csrf_token": session.csrf_secret}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), user=Depends(auth.current_user)):
    session = getattr(request.state, "auth_session", None)
    if session:
        session.revoked = True
        db.commit()
    response.delete_cookie(auth.COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return {"status": "logged_out"}


@router.post("/recover")
def recover(body: RecoverIn, request: Request, db: Session = Depends(get_db)):
    auth.check_origin(request); auth.throttle(request, "recover")
    token = db.query(RecoveryToken).filter_by(token_hash=auth.digest(body.recovery_code)).first()
    if not token:
        raise HTTPException(400, "恢复信息无效。")
    claimed = db.query(RecoveryToken).filter(RecoveryToken.id == token.id,
        RecoveryToken.consumed_at.is_(None)).update({RecoveryToken.consumed_at: utc_now()}, synchronize_session=False)
    if claimed != 1:
        db.rollback(); raise HTTPException(400, "恢复信息无效。")
    user = db.query(User).filter_by(id=token.user_id).populate_existing().with_for_update().one()
    user.password_hash = auth.PASSWORDS.hash(body.new_password)
    db.query(AuthSession).filter_by(user_id=user.id).update({AuthSession.revoked: True})
    code = auth.new_recovery(db, user)
    db.commit()
    return {"recovery_code": code}


@router.post("/invitations", status_code=201)
def invite(db: Session = Depends(get_db), owner=Depends(auth.require_owner)):
    token = auth.issue_invitation(db, owner)
    db.commit()
    return {"invite_token": token, "expires_in_hours": 72}
