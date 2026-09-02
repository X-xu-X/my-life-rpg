"""设置路由：配置管理（模型参数、游戏化模块开关）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Setting
from app.schemas import SettingIn
from app.services.user_service import get_or_create_default_user

router = APIRouter()

# 游戏化扩展模块（PRD 4.6 节，V3 交付，开关在此预留）
GAMIFICATION_MODULES = ["achievements", "streak", "tasks", "coin_shop"]


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """读取全部设置。"""
    user = get_or_create_default_user(db)
    rows = db.query(Setting).filter(Setting.user_id == user.id).all()
    result = {r.key: r.value for r in rows}
    # 游戏化模块开关默认关闭
    if "gamification_modules" not in result:
        result["gamification_modules"] = {m: False for m in GAMIFICATION_MODULES}
    # 属性维度开关默认全显示、全判定
    if "hidden_attributes" not in result:
        result["hidden_attributes"] = []
    if "disabled_attributes" not in result:
        result["disabled_attributes"] = []
    return result


@router.post("/settings")
def upsert_setting(body: SettingIn, db: Session = Depends(get_db)):
    """写入/更新某项设置。"""
    user = get_or_create_default_user(db)
    row = db.query(Setting).filter(Setting.user_id == user.id, Setting.key == body.key).first()
    if row is None:
        row = Setting(user_id=user.id, key=body.key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    db.commit()
    return {"key": body.key, "value": body.value}
