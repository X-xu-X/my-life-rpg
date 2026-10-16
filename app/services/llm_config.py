"""LLM 配置解析层（BYOK：Bring Your Own Key，v1.4）。

按「用户 + 用途」解析本次 LLM 调用应使用的配置，优先级：
1. Setting 表用户自配组：key=llm_primary（判定模型组）/ llm_aux（辅助模型组）
   - purpose="judge"（判定/补充/反驳/要素提取/引导/记忆）读 primary；
   - purpose="aux"（周报等辅助生成）读 aux；
2. 该组缺失/未启用 → judge 回退 aux（标注 quality_note="判定质量一般（使用辅助模型）"）；
   aux 缺失 → aux 用途回退 primary（免费兜底的反向通道，不标注）；
3. 两组都无 → 回退 .env 默认配置（向后兼容，现有部署零改动继续可用）；
4. .env 也没有 → 抛 LLMError（由路由转 503，提示去设置页绑定）。

安全红线：api_key 只存 SQLite（Setting 表），本模块绝不打日志、绝不返回明文给前端
（掩码回显由 settings 路由负责）；数据导出（export.py）不含 settings 表，天然隔离。
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Setting
from app.services.llm_service import LLMError

# Setting 表 key
SETTING_KEY_PRIMARY = "llm_primary"
SETTING_KEY_AUX = "llm_aux"

# 用途 → 首选组（fallback 见 resolve_llm_config）
PURPOSE_JUDGE = "judge"
PURPOSE_AUX = "aux"

# 判定降级到辅助模型时的质量标注（前端显示"判定质量一般"）
QUALITY_NOTE_DEGRADED = "判定质量一般（使用辅助模型）"


@dataclass
class LLMConfig:
    """一次 LLM 调用使用的解析结果配置。"""

    api_key: str
    base_url: str
    model: str
    quality_note: str = ""  # 非空时前端标注（如"判定质量一般"）
    user_id: int | None = None
    config_id: int | None = None
    config_version: int = 0
    scope: str = 'personal'
    preference_version: int = 0
    max_output_tokens: int | None = None
    secret_fingerprint: str = ''


def read_group(db: Session, user_id: int, setting_key: str) -> dict | None:
    """读取某配置组（dict），缺失/未启用/字段不全返回 None。"""
    if settings.cloud:
        from app.models.access import LLMCredential
        from app.services.credentials import decrypt, PROVIDERS
        row = db.query(LLMCredential).filter_by(user_id=user_id,
            group="primary" if setting_key == SETTING_KEY_PRIMARY else "aux").first()
        if not row or not row.enabled or not row.encrypted_key or not row.model:
            return None
        return {"api_key": decrypt(row), "base_url": PROVIDERS[row.provider_id], "model": row.model,
                "user_id": user_id, "config_id": row.id, "config_version": row.config_version}
    row = db.query(Setting).filter(Setting.user_id == user_id, Setting.key == setting_key).first()
    if row is None or not isinstance(row.value, dict):
        return None
    if not row.value.get("enabled"):
        return None
    if not (row.value.get("api_key") and row.value.get("base_url") and row.value.get("model")):
        return None
    return row.value


def _from_group(group: dict, quality_note: str = "") -> LLMConfig:
    return LLMConfig(
        api_key=str(group["api_key"]),
        base_url=str(group["base_url"]),
        model=str(group["model"]),
        quality_note=quality_note,
        user_id=group.get("user_id"), config_id=group.get("config_id"),
        config_version=group.get("config_version", 0), preference_version=group.get("preference_version",0),
    )


def _env_config() -> LLMConfig | None:
    """回退 .env 默认配置；未配置返回 None。"""
    if settings.cloud or not settings.llm_ready:
        return None
    return LLMConfig(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )


def resolve_llm_config(db: Session, user_id: int, purpose: str) -> LLMConfig:
    """按用户与用途解析 LLM 配置（见模块 docstring 优先级）。"""
    from app.services import hosted_ai
    pref=hosted_ai.preference(db,user_id)
    if pref and pref.mode=='off':raise LLMError('MODEL_DISABLED：你已关闭 AI，原文仍可保存。')
    if pref and pref.mode=='hosted':return hosted_ai.resolve(db,user_id,pref)
    primary = read_group(db, user_id, SETTING_KEY_PRIMARY)
    aux = read_group(db, user_id, SETTING_KEY_AUX)
    if primary:primary={**primary,'preference_version':pref.version if pref else 0}
    if aux:aux={**aux,'preference_version':pref.version if pref else 0}
    if settings.cloud and not (primary or aux):
        raise LLMError("MODEL_NOT_CONFIGURED：原文已保存，分析前请绑定自己的模型。")

    if purpose == PURPOSE_AUX:
        # 周报等辅助用途：首选 aux，缺失回退 primary，再回退 .env
        if aux:
            return _from_group(aux)
        if primary:
            return _from_group(primary)
        cfg = _env_config()
        if cfg:
            return cfg
        raise LLMError(
            "尚未配置任何 AI 模型：请到「设置 → AI 模型」绑定你的 API Key（OpenAI 兼容端点均可），"
            "或在服务端 .env 中配置默认密钥。"
        )

    # purpose="judge"（默认）：首选 primary；降级 aux 时标注质量
    if primary:
        return _from_group(primary)
    if aux:
        return _from_group(aux, quality_note=QUALITY_NOTE_DEGRADED)
    cfg = _env_config()
    if cfg:
        return cfg
    raise LLMError(
        "尚未配置任何 AI 模型：请到「设置 → AI 模型」绑定你的 API Key（OpenAI 兼容端点均可），"
        "或在服务端 .env 中配置默认密钥。"
    )


def mask_key(api_key: str) -> str:
    """API Key 掩码回显（sk-****末4位；无 key 返回空串）。"""
    key = (api_key or "").strip()
    if not key:
        return ""
    return f"{key[:3]}****{key[-4:]}" if len(key) > 8 else "****"


def assert_current(db, config):
    """模型结果写回时在用户锁内复核密钥版本。"""
    if not settings.cloud:
        return
    from app.models import User
    user=db.query(User).filter_by(id=config.user_id).populate_existing().first()
    if user is None or user.status!='active':raise ValueError('账号已停用。')
    from app.services import hosted_ai
    hosted_ai.assert_current(db,config)
    if config.scope=='hosted':return
    from app.models.access import LLMCredential
    row = db.query(LLMCredential).filter_by(id=config.config_id,user_id=config.user_id).populate_existing().first()
    if row is None or not row.enabled or row.config_version != config.config_version:
        raise ValueError('模型配置已变化，请重新发起分析。')
