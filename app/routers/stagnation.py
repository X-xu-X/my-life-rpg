"""停滞觉察路由（v1.8 B5）：列出停滞维度 + 回答问询。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import StagnationAnswerIn
from app.services import stagnation_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.get("/stagnation")
def get_stagnation(db: Session = Depends(get_db)):
    """停滞维度列表（惰性刷新；已问过且仍在冷却期内的维度不再列出）。"""
    user = get_or_create_default_user(db)
    items = stagnation_service.detect(db, user)
    return {
        "items": items,
        "stagnation_days": stagnation_service.STAGNATION_DAYS,
        "cooldown_days": stagnation_service.STAGNATION_COOLDOWN_DAYS,
    }


@router.post("/stagnation/{name}/answer")
def answer_stagnation(name: str, body: StagnationAnswerIn, db: Session = Depends(get_db)):
    """回答停滞问询。

    - `stopped=true`  确实停了 → 小幅扣分 −0.3 + 生成补课挑战
    - `stopped=false` 在学只是没记 → 不扣分，引导补记并重置计时
    """
    user = get_or_create_default_user(db)
    try:
        return stagnation_service.answer(db, user, name, body.stopped, body.note)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
