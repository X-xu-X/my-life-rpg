"""子维度路由（v1.10 M3）。

`GET /api/subdimensions`        —— 可拆分候选（≥95 且未拆过）+ 已拆分的层级
`POST /api/subdimensions/{attr_id}/propose` —— AI 提议 2~4 个细分方向（只提议不创建）
`POST /api/subdimensions/{attr_id}/accept`  —— 用户勾选确认后才真正创建子维度行
`POST /api/subdimensions/{attr_id}/dismiss` —— 忽略本次提议
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import SubdimensionAcceptIn
from app.services import subdimension_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


def _attr_or_404(db: Session, attr_id: int):
    from app.models import Attribute

    user = get_or_create_default_user(db)
    attr = db.get(Attribute, attr_id)
    if attr is None or attr.user_id != user.id:
        raise HTTPException(status_code=404, detail="属性不存在。")
    return user, attr


@router.get("/subdimensions")
def list_subdimensions(db: Session = Depends(get_db)):
    """候选（≥阈值未拆）+ 层级（主维度 → 子维度）一次给全。"""
    from app.constants import SUBDIMENSION_THRESHOLD

    db.rollback()  # 只读接口，先释放可能残留的事务锁
    user = get_or_create_default_user(db)
    return {
        "threshold": SUBDIMENSION_THRESHOLD,
        "candidates": subdimension_service.candidates(db, user),
        "hierarchy": subdimension_service.hierarchy(db, user),
    }


@router.post("/subdimensions/{attr_id}/propose")
def propose_subdimensions(attr_id: int, db: Session = Depends(get_db)):
    """AI 提议（真实 LLM 调用，前端需 loading + 防重复）。"""
    user, attr = _attr_or_404(db, attr_id)
    try:
        proposal = subdimension_service.propose(db, user, attr)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"proposal": proposal}


@router.post("/subdimensions/{attr_id}/accept")
def accept_subdimensions(attr_id: int, body: SubdimensionAcceptIn, db: Session = Depends(get_db)):
    """按用户勾选创建子维度（多选后确认，未勾选的不创建）。"""
    user, attr = _attr_or_404(db, attr_id)
    try:
        created = subdimension_service.accept(db, user, attr, body.names)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "created": [
            {"id": c.id, "name": c.name, "description": c.description,
             "value": c.current_value, "max_value": c.max_value}
            for c in created
        ],
        "children": subdimension_service.serialize_children(db, user, attr.id),
    }


@router.post("/subdimensions/{attr_id}/dismiss")
def dismiss_subdimensions(attr_id: int, db: Session = Depends(get_db)):
    """忽略本次提议（不创建任何子维度）。"""
    user, attr = _attr_or_404(db, attr_id)
    subdimension_service.dismiss(db, user, attr)
    return {"ok": True}
