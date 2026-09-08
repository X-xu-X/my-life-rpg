"""长期记忆服务（智能体式）：用 LLM 把历史事件压缩成五类摘要，跨会话记住用户。

设计：
- 短期记忆 = 近 7 天日记原文（judge_service 里已有）。
- 长期记忆 = 五类摘要（长期目标/关键经历/性格/偏好/当前状态），存 UserProfile.long_term_memory。
- 每天自动更新一次（maybe_update_memory 检查间隔），失败不影响主流程。
"""
import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import prompts
from app.models import Event, User, UserProfile
from app.services import llm_config
from app.services.llm_service import llm_service

# 记忆更新间隔（每天一次）
MEMORY_UPDATE_INTERVAL_HOURS = 24


def _get_profile(db: Session, user: User) -> UserProfile | None:
    return db.query(UserProfile).filter(UserProfile.user_id == user.id).first()


def get_long_term_memory(db: Session, user_id: int) -> dict:
    """获取长期记忆（解析 JSON），无则空 dict。"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile or not profile.long_term_memory:
        return {}
    try:
        return json.loads(profile.long_term_memory)
    except (json.JSONDecodeError, TypeError):
        return {}


def _events_summary(db: Session, user_id: int, days: int = 30, limit: int = 50) -> str:
    """近 N 天事件摘要（供记忆压缩）。"""
    cutoff = datetime.now() - timedelta(days=days)
    events = (
        db.query(Event)
        .filter(Event.user_id == user_id, Event.created_at >= cutoff, Event.is_pure.is_(False))
        .order_by(Event.created_at.asc())
        .limit(limit)
        .all()
    )
    lines = []
    for e in events:
        text = (e.content or e.title or "").strip()
        lines.append(f"{e.created_at.strftime('%m-%d')} [{e.category}] {text}")
    return "\n".join(lines)


def update_long_term_memory(db: Session, user: User) -> dict | None:
    """用 LLM 把历史事件压缩成五类记忆，存入 profile。失败返回 None（不影响主流程）。"""
    profile = _get_profile(db, user)
    if profile is None:
        return None
    existing = profile.long_term_memory or ""
    summary = _events_summary(db, user.id)
    if not summary.strip():
        return None  # 无事件，不更新
    messages = prompts.build_memory_messages(existing, summary)
    try:
        # v1.4：走判定模型组（judge），缺失自动回退；失败不影响主流程
        config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_JUDGE)
        result = llm_service.chat_json(messages, config=config)
    except Exception:
        return None  # 记忆更新失败不影响主流程
    profile.long_term_memory = json.dumps(result, ensure_ascii=False)
    profile.memory_updated_at = datetime.now()
    db.commit()
    return result


def maybe_update_memory(db: Session, user: User) -> dict:
    """检查是否需要更新长期记忆（超过 24 小时或从未更新），需要则更新。返回当前记忆 dict。"""
    profile = _get_profile(db, user)
    needs_update = True
    if profile and profile.memory_updated_at:
        age = datetime.now() - profile.memory_updated_at
        needs_update = age > timedelta(hours=MEMORY_UPDATE_INTERVAL_HOURS)
    if needs_update:
        update_long_term_memory(db, user)
    return get_long_term_memory(db, user.id)


def format_memory_text(memory: dict) -> str:
    """把长期记忆 dict 转成可读文本（供注入 prompt）。"""
    if not memory:
        return ""
    labels = {
        "long_term_goals": "长期目标",
        "key_experiences": "关键经历",
        "personality": "性格",
        "preferences": "偏好",
        "current_status": "当前状态",
    }
    parts = []
    for key, label in labels.items():
        items = memory.get(key, [])
        if items:
            parts.append(f"{label}：{'；'.join(items)}")
    return "\n".join(parts)
