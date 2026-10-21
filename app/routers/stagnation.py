"""停滞觉察路由（v1.8 B5）：列出停滞维度 + 回答问询。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import StagnationAnswerIn
from app.services import stagnation_service
from app.services.user_service import get_or_create_default_user
from app.services import receipts
from app.services.transactions import lock_profile
from app.models import Attribute
from fastapi.encoders import jsonable_encoder

router = APIRouter()


@router.get("/stagnation")
def get_stagnation(db: Session = Depends(get_db)):
    """停滞维度列表（惰性刷新；已问过且仍在冷却期内的维度不再列出）。"""
    user = get_or_create_default_user(db)
    items = []  # Missing records are not evidence for deductions or corrective challenges.
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
        lock_profile(db,user.id)
        attr=db.query(Attribute).filter_by(user_id=user.id,name=name,parent_id=None).first()
        if attr is None:
            from app.config import settings
            raise HTTPException(404 if settings.cloud else 400,'维度不存在')
        fingerprint,prior=receipts.replay(db,user.id,f'stagnation:{name}',body)
        if prior is not None:return prior
        raise HTTPException(410,'缺记录问询和扣点入口已退出；可以在今天自愿记录，原历史保留。')
        if body.expected_version is not None and body.expected_version != attr.updated_at:
            raise HTTPException(409,'维度状态已变化，请重新读取。')
        result=jsonable_encoder(stagnation_service.answer(db,user,name,body.stopped,body.note,commit=False))
        receipts.record(db,user.id,f'stagnation:{name}',body,fingerprint,attr.id,result)
        db.commit();return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
