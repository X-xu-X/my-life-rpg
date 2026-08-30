"""Onboarding 问卷服务（v1.1 重设计）。

流程：
- 首次引导（仅新用户第一次）：AI 出题 → 逐题作答，每轮 AI 自评把握度 →
  把握度 >= 阈值自动生成初始属性面板并存快照 → 标记 onboarding_completed。
- 一次性约束：完成后不可重新走引导，只能「补充长期信息」。
- 补充信息：AI 客观评估（综合用户自述 + 客观记录），用户确认后生效。

会话态持久化到 user_profiles.onboarding_state（离开 / 重启不丢）。
"""
from sqlalchemy.orm import Session

from app import prompts
from app.models import Attribute, AttributeHistory, UserProfile
from app.prompts.onboarding import CONFIDENCE_THRESHOLD
from app.services.llm_service import llm_service
from app.services.user_service import get_or_create_default_user


def _get_profile(db: Session, user) -> UserProfile:
    """获取（或创建）用户画像记录。"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


def get_status(db: Session) -> dict:
    """查询首次引导状态（是否完成、是否有进行中会话）。"""
    user = get_or_create_default_user(db)
    profile = _get_profile(db, user)
    state = profile.onboarding_state or {}
    return {
        "onboarding_completed": bool(profile.onboarding_completed),
        "in_progress": bool(state.get("conversation")),
        "question_count": len(state.get("conversation", [])),
        "confidence": state.get("confidence", 0),
    }


def _evaluate(db: Session, profile: UserProfile, conversation: list[dict]) -> dict:
    """让 AI 基于当前问答评估把握度并出题。返回 {questions, hint, confidence}。"""
    result = llm_service.chat_json(prompts.build_question_messages(conversation))
    questions = result.get("questions", [])
    hint = result.get("hint", "")
    confidence = int(result.get("confidence", 0))
    profile.onboarding_state = {
        "conversation": conversation,
        "questions": questions,
        "hint": hint,
        "confidence": confidence,
    }
    db.commit()
    return {"questions": questions, "hint": hint, "confidence": confidence}


def start_questions(db: Session) -> dict:
    """开始（或恢复）首次引导。已完成则返回锁定提示。"""
    user = get_or_create_default_user(db)
    profile = _get_profile(db, user)

    if profile.onboarding_completed:
        return {
            "completed": True,
            "message": "首次属性建档已完成。如需更新长期信息，请使用「补充信息」入口。",
        }

    state = profile.onboarding_state or {}
    conversation = list(state.get("conversation", []))

    if not conversation:
        # 全新会话：AI 出第一轮题
        return {
            "completed": False,
            **_evaluate(db, profile, conversation),
        }

    # 恢复进行中的会话：AI 基于已有问答重新评估，若已达标则直接生成面板
    result = _evaluate(db, profile, conversation)
    if result["confidence"] >= CONFIDENCE_THRESHOLD:
        panel, summary = _generate_panel(db, profile, conversation)
        return {
            "completed": True,
            "done": True,
            "panel": panel,
            "summary": summary,
            "confidence": result["confidence"],
        }
    return {"completed": False, **result}


def submit_answer(db: Session, answers: list[dict]) -> dict:
    """提交一轮回答。AI 评估把握度，达到阈值则自动生成面板并归档。"""
    user = get_or_create_default_user(db)
    profile = _get_profile(db, user)

    if profile.onboarding_completed:
        return {"completed": True, "message": "首次建档已完成，只能补充长期信息。"}

    state = profile.onboarding_state or {}
    conversation = list(state.get("conversation", []))
    for item in answers:
        conversation.append(
            {"question": item.get("question", ""), "answer": item.get("answer", "")}
        )

    result = _evaluate(db, profile, conversation)
    if result["confidence"] >= CONFIDENCE_THRESHOLD:
        panel, summary = _generate_panel(db, profile, conversation)
        return {
            "completed": True,
            "done": True,
            "panel": panel,
            "summary": summary,
            "confidence": result["confidence"],
        }
    return {"completed": False, "done": False, **result}


def _generate_panel(db: Session, profile: UserProfile, conversation: list[dict]) -> tuple[list, str]:
    """AI 生成初始属性面板，持久化到画像快照与 attributes 表。"""
    result = llm_service.chat_json(prompts.build_panel_messages(conversation))
    panel = result.get("attributes", [])
    summary = result.get("summary", "")

    profile.initial_attributes_snapshot = {"attributes": panel, "summary": summary}
    # 沉淀画像：原始问答 + 空的补充信息列表（后续补充长期信息追加到这里）
    profile.basic_profile = {"conversation": conversation, "supplements": []}
    profile.onboarding_completed = True
    profile.onboarding_state = {}

    # 同步 attributes 表当前值
    for item in panel:
        name = item.get("name", "")
        value = float(item.get("value", 0.0))
        attr = (
            db.query(Attribute)
            .filter(Attribute.user_id == profile.user_id, Attribute.name == name)
            .first()
        )
        if attr is None:
            attr = Attribute(user_id=profile.user_id, name=name, description=item.get("reason", ""))
            db.add(attr)
        attr.current_value = value
        attr.description = item.get("reason", "")

    db.commit()
    return panel, summary


def supplement_profile(db: Session, detail: str) -> dict:
    """补充长期信息（首次引导后）。AI 客观评估，返回调整建议（待用户确认）。"""
    user = get_or_create_default_user(db)
    profile = _get_profile(db, user)

    if not profile.onboarding_completed:
        raise ValueError("尚未完成首次属性建档，请先完成引导问卷。")

    # 收集客观记录：当前属性面板 + 历史事件判定流水
    attrs = db.query(Attribute).filter(Attribute.user_id == user.id).all()
    current_attributes = [
        {"name": a.name, "value": a.current_value, "description": a.description} for a in attrs
    ]
    history_rows = (
        db.query(AttributeHistory)
        .filter(AttributeHistory.user_id == user.id)
        .order_by(AttributeHistory.created_at.desc())
        .limit(50)
        .all()
    )
    history = [
        {
            "delta": h.delta,
            "reason": h.reason,
            "evidence": h.evidence,
            "created_at": str(h.created_at),
        }
        for h in history_rows
    ]

    result = llm_service.chat_json(
        prompts.build_supplement_messages(
            basic_profile=profile.basic_profile or {},
            current_attributes=current_attributes,
            history=history,
            supplement_text=detail,
        )
    )
    adjustments = result.get("adjustments", [])
    explanation = result.get("explanation", "")

    # 沉淀补充信息到画像（无论是否调整属性，信息都要记住，供后续判定参考）
    bp = dict(profile.basic_profile or {})
    supplements = list(bp.get("supplements", []))
    supplements.append(detail)
    bp["supplements"] = supplements
    profile.basic_profile = bp

    # 暂存待确认的调整建议
    profile.pending_adjustment = {"adjustments": adjustments, "explanation": explanation}
    db.commit()

    return {"adjustments": adjustments, "explanation": explanation}


def confirm_adjustment(db: Session) -> dict:
    """确认应用补充信息的调整建议（写属性流水 + 更新属性值）。"""
    user = get_or_create_default_user(db)
    profile = _get_profile(db, user)

    pending = profile.pending_adjustment or {}
    adjustments = pending.get("adjustments", [])
    if not adjustments:
        return {"applied": [], "message": "没有待确认的调整。"}

    applied = []
    for item in adjustments:
        name = item.get("name", "")
        try:
            delta = float(item.get("delta", 0.0))
        except (TypeError, ValueError):
            delta = 0.0
        if delta == 0 or not name:
            continue
        attr = (
            db.query(Attribute)
            .filter(Attribute.user_id == user.id, Attribute.name == name)
            .first()
        )
        if attr is None:
            attr = Attribute(user_id=user.id, name=name, current_value=50.0)
            db.add(attr)
            db.flush()
        attr.current_value = round(attr.current_value + delta, 2)
        db.add(
            AttributeHistory(
                user_id=user.id,
                attribute_id=attr.id,
                event_id=None,
                judgment_id=None,
                delta=delta,
                value_after=attr.current_value,
                reason=item.get("reason", ""),
                evidence=item.get("evidence", ""),
            )
        )
        applied.append({"name": name, "delta": delta, "value_after": attr.current_value})

    profile.pending_adjustment = {}
    db.commit()
    return {"applied": applied, "message": "调整已生效。"}
