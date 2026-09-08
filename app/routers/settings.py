"""设置路由：配置管理（模型参数、游戏化模块开关、BYOK 模型配置 v1.4）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Setting
from app.schemas import LLMConfigIn, SettingIn
from app.services.llm_config import SETTING_KEY_AUX, SETTING_KEY_PRIMARY, mask_key
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


# ============ AI 模型配置（BYOK，v1.4） ============

# 安全红线：key 只入 SQLite（Setting 表），GET 回显必须掩码，严禁写日志/入导出


def _group_out(db: Session, user_id: int, setting_key: str) -> dict:
    """读取一组配置并掩码回显。"""
    row = db.query(Setting).filter(Setting.user_id == user_id, Setting.key == setting_key).first()
    value = row.value if row and isinstance(row.value, dict) else {}
    key = str(value.get("api_key", "") or "")
    return {
        "enabled": bool(value.get("enabled")),
        "api_key": mask_key(key),  # 掩码回显，绝不返回明文
        "base_url": str(value.get("base_url", "") or ""),
        "model": str(value.get("model", "") or ""),
        "configured": bool(key),
    }


@router.get("/llm-config")
def get_llm_config(db: Session = Depends(get_db)):
    """读取两组模型配置（api_key 掩码回显）+ .env 默认配置状态。"""
    user = get_or_create_default_user(db)
    return {
        "primary": _group_out(db, user.id, SETTING_KEY_PRIMARY),
        "aux": _group_out(db, user.id, SETTING_KEY_AUX),
        "env_fallback": {
            "ready": settings.llm_ready,
            "model": settings.deepseek_model,
            "base_url": settings.deepseek_base_url,
        },
    }


@router.put("/llm-config")
def put_llm_config(body: LLMConfigIn, db: Session = Depends(get_db)):
    """写入一组模型配置。api_key="__KEEP__" 保持不变；空串清除。

    保存 primary 且模型端点相比旧值有变化时，返回 model_changed=true 供前端弹确认
    （更换判定模型后加点口径可能与之前不同）。
    """
    user = get_or_create_default_user(db)
    setting_key = SETTING_KEY_PRIMARY if body.group == "primary" else SETTING_KEY_AUX
    row = db.query(Setting).filter(Setting.user_id == user.id, Setting.key == setting_key).first()
    old = dict(row.value) if row and isinstance(row.value, dict) else {}

    new = {**old}
    if body.api_key is not None:
        if body.api_key == "__KEEP__":
            pass  # 保持原 key 不变（配合掩码回显）
        else:
            new["api_key"] = body.api_key.strip()
    if body.base_url is not None:
        new["base_url"] = body.base_url.strip().rstrip("/")
    if body.model is not None:
        new["model"] = body.model.strip()
    if body.enabled is not None:
        new["enabled"] = body.enabled

    # 口径变化检测：仅 primary（判定模型），且旧值确实存在并被替换
    key_changed = (
        body.api_key is not None
        and body.api_key not in ("__KEEP__",)
        and bool(old.get("api_key"))
        and new.get("api_key") != old.get("api_key")
    )
    endpoint_changed = bool(old.get("api_key")) and (
        new.get("model") != old.get("model") or new.get("base_url") != old.get("base_url")
    )
    model_changed = body.group == "primary" and (key_changed or endpoint_changed)

    if row is None:
        row = Setting(user_id=user.id, key=setting_key, value=new)
        db.add(row)
    else:
        row.value = new
    db.commit()

    message = ""
    if model_changed:
        message = (
            "更换判定模型后，后续加点口径可能与之前不同（历史数据全部保留；"
            "长期记忆会自动注入新模型衔接上下文）。"
        )
    return {"ok": True, "group": body.group, "model_changed": model_changed, "message": message}
