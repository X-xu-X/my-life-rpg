"""设置路由：配置管理（模型参数、游戏化模块开关、BYOK 模型配置 v1.4）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.constants import ATTRIBUTE_DIMENSIONS_SET
from app.config import settings
from app.database import get_db
from app.models import Setting
from app.schemas import LLMConfigIn, SettingIn
from app.services.llm_config import SETTING_KEY_AUX, SETTING_KEY_PRIMARY, mask_key
from app.services.user_service import get_or_create_default_user

router = APIRouter()

# 游戏化扩展模块（PRD 4.6 节，V3 交付，开关在此预留）
GAMIFICATION_MODULES = ["achievements", "streak", "tasks", "coin_shop"]
PUBLIC_SETTING_KEYS = frozenset({"gamification_modules", "hidden_attributes", "disabled_attributes"})


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """读取全部设置。"""
    user = get_or_create_default_user(db)
    rows = db.query(Setting).filter(Setting.user_id == user.id, Setting.key.in_(PUBLIC_SETTING_KEYS)).all()
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
    if body.key not in PUBLIC_SETTING_KEYS:
        raise HTTPException(400, "该设置只能由专用接口修改。")
    value = body.value
    if body.key == "gamification_modules":
        valid = (isinstance(value, dict) and set(value) <= set(GAMIFICATION_MODULES)
                 and all(type(v) is bool for v in value.values()))
    else:
        valid = (isinstance(value, list) and all(isinstance(v, str) for v in value)
                 and set(value) <= ATTRIBUTE_DIMENSIONS_SET)
        if valid:
            body.value = list(dict.fromkeys(value))
    if not valid:
        raise HTTPException(400, "设置值不合法。")
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
    from app.services.model_validation import summary, snapshot
    group = 'primary' if setting_key == SETTING_KEY_PRIMARY else 'aux'
    meta = snapshot(db, user_id, group)
    return {
        **meta, 'provider_id': meta['provider'], 'source': 'personal',
        'validation': summary(db, user_id, group, meta['config_version']),
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
    if settings.cloud:
        from app.services.credentials import read_config
        return read_config(db, user.id)
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
    if settings.cloud:
        from app.services.credentials import save_config
        return save_config(db, user.id, body)
    import re
    from app.services.transactions import lock_profile
    lock_profile(db, user.id)
    if body.model is not None and not re.fullmatch(r'[^\s\x00-\x1f\x7f]{1,100}', body.model):
        raise HTTPException(422, '请填写准确模型 ID（不能含空格）。')
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
    new['config_version'] = int(old.get('config_version', 0)) + 1

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


@router.post('/llm-config/test')
def test_llm_config(body: dict, db: Session = Depends(get_db)):
    from app.services import llm_config
    from app.services.llm_service import llm_service, LLMError
    user = get_or_create_default_user(db)
    from app.services.model_validation import snapshot, controlled_error
    from app.services.transactions import lock_profile
    from app.services.time_service import utc_now
    group_name = body.get('group')
    version = body.get('expected_config_version')
    if set(body) != {'group', 'expected_config_version'} or group_name not in ('primary', 'aux') or type(version) is not int or version < 0:
        raise HTTPException(422, '请刷新配置，并携带已保存组的 expected_config_version；不接受未保存配置。')
    # Read version and decrypted configuration under the same short save lock.
    lock_profile(db, user.id)
    captured = snapshot(db, user.id, group_name)
    if captured['config_version'] != version:
        raise HTTPException(409, '配置已变化，请刷新后测试。')
    key = SETTING_KEY_PRIMARY if group_name == 'primary' else SETTING_KEY_AUX
    group = llm_config.read_group(db, user.id, key)
    if not group:
        raise HTTPException(422, '请先保存并启用本组配置。')
    config = llm_config._from_group(group)
    db.commit()
    result = {'status': 'passed', 'group': group_name, **captured,
              'tested_at': utc_now().isoformat(), 'error_code': None,
              'message': '聊天连通测试通过；不代表业务 JSON 分析质量或永久可用。', 'retryable': False}
    try:
        answer = llm_service.chat([{'role':'user','content':'Reply OK.'}], config=config, max_tokens=8)
        if not answer.strip(): raise LLMError('MODEL_INVALID_RESPONSE')
    except Exception as exc:
        code, message, retryable = controlled_error(exc)
        result.update(status='failed', error_code=code, message=message, retryable=retryable)
    result['tested_at'] = utc_now().isoformat()
    lock_profile(db, user.id)
    if snapshot(db, user.id, group_name) != captured:
        db.rollback()
        raise HTTPException(409, '测试期间配置已变化，旧测试结果已失效。')
    row = db.query(Setting).filter_by(user_id=user.id, key='llm_validation_' + group_name).first()
    if row is None:
        db.add(Setting(user_id=user.id, key='llm_validation_' + group_name, value=result))
    else: row.value = result
    db.commit()
    return result
