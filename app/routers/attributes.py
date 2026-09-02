"""属性路由：当前属性面板 + 属性流水（可视化数据源）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Attribute, AttributeHistory, Setting, UserProfile
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.get("/attributes")
def get_attributes(db: Session = Depends(get_db)):
    """当前属性面板（含等级/经验，游戏化字段 M3 启用）。

    v1.2：每个属性带 visibility 标记——show 正常显示 / hidden 隐藏（AI 照判）/ disabled 关闭判定。
    """
    user = get_or_create_default_user(db)
    attrs = (
        db.query(Attribute)
        .filter(Attribute.user_id == user.id)
        .order_by(Attribute.id)
        .all()
    )
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()

    # 维度开关
    hidden = _get_list_setting(db, user.id, "hidden_attributes")
    disabled = _get_list_setting(db, user.id, "disabled_attributes")

    def visibility(name: str) -> str:
        if name in disabled:
            return "disabled"
        if name in hidden:
            return "hidden"
        return "show"

    return {
        "attributes": [
            {
                "name": a.name,
                "value": a.current_value,
                "max_value": a.max_value,
                "description": a.description,
                "visibility": visibility(a.name),
            }
            for a in attrs
        ],
        "level": profile.level if profile else 1,
        "exp": profile.exp if profile else 0.0,
    }


def _get_list_setting(db: Session, user_id: int, key: str) -> set[str]:
    """读取列表型设置（如 hidden_attributes/disabled_attributes）。"""
    row = db.query(Setting).filter(Setting.user_id == user_id, Setting.key == key).first()
    if row and isinstance(row.value, list):
        return set(row.value)
    return set()


@router.get("/attributes/history")
def get_history(db: Session = Depends(get_db)):
    """属性变更流水（含属性名，支撑成长趋势折线）。"""
    user = get_or_create_default_user(db)
    rows = (
        db.query(AttributeHistory, Attribute.name)
        .join(Attribute, AttributeHistory.attribute_id == Attribute.id)
        .filter(AttributeHistory.user_id == user.id)
        .order_by(AttributeHistory.created_at.asc())
        .all()
    )
    return [
        {
            "attribute_id": r.attribute_id,
            "name": name,
            "delta": r.delta,
            "value_after": r.value_after,
            "reason": r.reason,
            "evidence": r.evidence,
            "event_id": r.event_id,
            "judgment_id": r.judgment_id,
            "created_at": r.created_at,
        }
        for r, name in rows
    ]
