"""邀请制身份服务。会话/邀请/恢复码仅保存摘要；无默认账号回落。"""
import hashlib
import secrets
import threading
from collections import OrderedDict, deque
from datetime import datetime, timedelta
from time import monotonic

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.services.time_service import utc_now
from app.database import get_db
from app.models import User, UserProfile
from app.models.access import AuthSession, Invitation, RecoveryToken

COOKIE = "__Host-gol_session"
USERNAME_PATTERN = r"^[a-zA-Z0-9_\-\u4e00-\u9fff]+$"
PASSWORDS = PasswordHasher()
_dummy_hash = PASSWORDS.hash(secrets.token_urlsafe(32))
_attempts = OrderedDict()
_rate_lock = threading.Lock()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def throttle(request: Request, operation: str):
    # 单 API 实例的有界限流；反向代理还需限制入口流量。
    key = (request.client.host if request.client else "unknown", operation)
    now = monotonic()
    with _rate_lock:
        attempts = _attempts.setdefault(key, deque())
        while attempts and attempts[0] <= now - 900:
            attempts.popleft()
        if len(attempts) >= 20:
            raise HTTPException(429, "尝试过于频繁，请稍后重试。")
        attempts.append(now)
        _attempts.move_to_end(key)
        while len(_attempts) > 10000:
            _attempts.popitem(last=False)


def check_origin(request):
    if settings.cloud and request.headers.get("origin") != settings.public_origin:
        raise HTTPException(403, "请求来源无效。")


async def current_user(request: Request, db: Session = Depends(get_db)):
    if not settings.cloud:
        from app.services.user_service import get_or_create_default_user
        return get_or_create_default_user(db)
    token = request.cookies.get(COOKIE, "")
    now = utc_now()
    session = db.query(AuthSession).filter(AuthSession.token_hash == digest(token),
        AuthSession.revoked.is_(False), AuthSession.expires_at > now,
        AuthSession.last_seen > now - timedelta(days=7)).first() if token else None
    if session is None:
        raise HTTPException(401, "请登录。")
    user = db.get(User, session.user_id)
    if not user or user.status != "active":
        raise HTTPException(401, "请登录。")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        check_origin(request)
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf_secret):
            raise HTTPException(403, "请求验证失败，请刷新后重试。")
        session.last_seen = now
        path = request.url.path
        game_write = (path.startswith('/api/goals') or path.startswith('/api/stagnation')
            or path.startswith('/api/challenges') or path.startswith('/api/redemptions')
            or path.startswith('/api/exemptions') or '/redeem' in path
            or '/achievement' in path or path == '/api/coins/check-streak'
            or '/confirm' in path and '/judgments/' in path)
        if game_write:
            profile = db.query(UserProfile).filter_by(user_id=user.id).first()
            if not profile or not profile.onboarding_completed:
                raise HTTPException(409, "请先主动选择未评估基线或完成首次问卷。原文保存不受影响。")
    request.state.auth_session = session
    db.info["user_id"] = user.id
    from app.services.time_service import USER_ZONE
    USER_ZONE.set(user.timezone)
    return user


async def require_owner(request: Request, db: Session = Depends(get_db)):
    user = await current_user(request, db)
    if settings.cloud and user.role != "owner":
        raise HTTPException(403, "仅所有者可执行此运维操作。")
    return user


def create_session(db, user, response):
    user.last_login_at = utc_now()
    token = secrets.token_urlsafe(48)
    session = AuthSession(user_id=user.id, token_hash=digest(token),
        csrf_secret=secrets.token_urlsafe(32), expires_at=utc_now() + timedelta(days=30))
    db.add(session)
    response.set_cookie(COOKIE, token, secure=True, httponly=True,
        samesite="lax", path="/", max_age=30 * 86400)
    return session


def issue_invitation(db, owner, hours=72):
    token = secrets.token_urlsafe(40)
    db.add(Invitation(creator_id=owner.id, token_hash=digest(token),
                      expires_at=utc_now() + timedelta(hours=hours)))
    db.flush()
    return token


def new_recovery(db, user):
    code = secrets.token_urlsafe(40)
    db.add(RecoveryToken(user_id=user.id, token_hash=digest(code)))
    return code


def initialize_account(db, username, password, role="user"):
    user = User(username=username, password_hash=PASSWORDS.hash(password), role=role, status="active")
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id))
    from app.models import Attribute
    from app.constants import ATTRIBUTE_DIMENSIONS
    for name in ATTRIBUTE_DIMENSIONS:
        db.add(Attribute(user_id=user.id, name=name, current_value=50,
                         description="未评估；选择基线后才能结算。"))
    db.flush()
    from app.services.shop_service import seed_preset_items
    seed_preset_items(db, user, commit=False)
    return user


def verify_password(user, password):
    try:
        valid = PASSWORDS.verify(user.password_hash if user and user.password_hash else _dummy_hash, password)
        return bool(user and user.password_hash and user.status == "active" and valid)
    except (VerificationError, InvalidHashError):
        return False
