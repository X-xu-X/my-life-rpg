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
    try:
        achievement_service.check_and_grant(db, user)
    except IntegrityError:
        db.rollback()
    return achievement_service.wall(db, user)
