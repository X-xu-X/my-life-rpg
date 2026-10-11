"""成就墙在访问时惰性追溯；追授入口统一在 judgments 路由。"""
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.services import achievement_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.get("/achievements")
def list_achievements(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    from app.config import settings
    if settings.cloud:
        return achievement_service.wall(db, user)
    try:
        achievement_service.check_and_grant(db, user)
    except IntegrityError:
        db.rollback()
    return achievement_service.wall(db, user)


@router.post("/achievements/check")
def check_achievements(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    from app.services.transactions import lock_profile
    lock_profile(db, user.id)
    try:
        achievement_service.check_and_grant(db, user)
    except IntegrityError:
        db.rollback()
    return achievement_service.wall(db, user)
