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
from app.models import Attribute, AttributeHistory, User, UserProfile
from app.prompts.onboarding import CONFIDENCE_THRESHOLD
from app.services import coin_service, llm_config
from app.services.judge_service import _clamp_attribute_value as clamp_attribute_value
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
    """查询首次引导状态（是否完成、是否有进行中会话）。

    v1.9（F1）：附带启动资金与其理由（从快照读取）。
    **老档案的快照里没有这两个键 → 返回 None / 空串，前端据此不显示该行**（优雅降级）。
    """
    user = get_or_create_default_user(db)
    profile = _get_profile(db, user)
    state = profile.onboarding_state or {}
    snapshot = profile.initial_attributes_snapshot or {}
    return {
        "onboarding_completed": bool(profile.onboarding_completed),
        "in_progress": bool(state.get("conversation")),
        "question_count": len(state.get("conversation", [])),
        "confidence": state.get("confidence", 0),
        "initial_coins": snapshot.get("initial_coins"),
        "initial_coins_reason": snapshot.get("initial_coins_reason", "") or "",
    }


def _evaluate(db: Session, profile: UserProfile, conversation: list[dict]) -> dict:
    """让 AI 基于当前问答评估把握度并出题。返回 {questions, hint, confidence}。"""
    # v1.4：走判定模型组（judge）
    config = llm_config.resolve_llm_config(db, profile.user_id, llm_config.PURPOSE_JUDGE)
    result = llm_service.chat_json(prompts.build_question_messages(conversation), config=config)
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
        snapshot = profile.initial_attributes_snapshot or {}
        return {
            "completed": True,
            "done": True,
            "panel": panel,
            "summary": summary,
            "confidence": result["confidence"],
            # v1.9 F1：启动资金（展示用；前端若拿不到则不显示该行）
            "initial_coins": snapshot.get("initial_coins"),
            "initial_coins_reason": snapshot.get("initial_coins_reason", "") or "",
        }
    return {"completed": False, "done": False, **result}


def _assert_unbuilt_profile(db: Session, profile: UserProfile) -> None:
    db.query(UserProfile).filter(UserProfile.id == profile.id).update(
        {UserProfile.id: UserProfile.id}, synchronize_session=False)
    db.refresh(profile)
    if (profile.onboarding_completed or profile.initial_attributes_snapshot
            or db.query(AttributeHistory.id).filter(AttributeHistory.user_id == profile.user_id).first()):
        raise ValueError("已有建档基线或属性流水，不能重新建档。如需撤销请删除事件。")


def _generate_panel(db: Session, profile: UserProfile, conversation: list[dict]) -> tuple[list, str]:
    """AI 生成初始属性面板，持久化到画像快照与 attributes 表。

    v1.9（F1）：启动资金改为**由 AI 依据问卷一并给出**（同一次调用新增输出字段
    `initial_coins` / `initial_coins_reason`，不额外增加 LLM 调用）。
    代码**只做区间夹取**，不实现任何"按短板数计算"之类的兜底公式
    （那是用户在访谈中明确否决的方案）。
    """
    _assert_unbuilt_profile(db, profile)
    # v1.4：走判定模型组（judge）
    config = llm_config.resolve_llm_config(db, profile.user_id, llm_config.PURPOSE_JUDGE)
    result = llm_service.chat_json(prompts.build_panel_messages(conversation), config=config)
    panel = result.get("attributes", [])
    summary = result.get("summary", "")

    # v1.9 F1：解析并夹取启动资金（80~200，整数；非法/缺失取保底 80）
    initial_coins = _clamp_initial_coins(result.get("initial_coins"))
    reason_raw = result.get("initial_coins_reason")
    initial_coins_reason = (
        str(reason_raw).strip()
        if reason_raw and str(reason_raw).strip()
        else "按你的问卷情况给出的启动资金，够你走通一次挑战与兑换。"
    )

    profile.initial_attributes_snapshot = {
        "attributes": panel,
        "initial_coins": initial_coins,
        "initial_coins_reason": initial_coins_reason,
        "summary": summary,
    }
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

    # v1.9 F1：发放启动资金（唯一写入口 coin_service.grant）
    # 幂等由 grant_startup_bonus_if_needed 的"ledger 是否已有 onboarding_bonus"判断兜底，
    # 故此处发放后，GET /api/coins 不会再补发一次。
    user = db.get(User, profile.user_id)
    if user is not None:
        coin_service.grant(
            db,
            user,
            initial_coins,
            source="onboarding_bonus",
            reason=f"角色档案建立，获得启动资金 {initial_coins} 币 —— {initial_coins_reason}",
        )
        db.commit()

    return panel, summary


# 启动资金区间（v1.9 F1：保底 80 保证能走通「周挑战押金 35 + 中档奖励 40」闭环；
# 上限 200 ≈ 一周满打满算收入，再高会削弱挑战动力）
INITIAL_COINS_MIN = 80
INITIAL_COINS_MAX = 200


def _clamp_initial_coins(raw) -> int:
    """把 AI 给出的启动资金夹到 [80, 200] 的整数；非法/缺失取保底 80。"""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return INITIAL_COINS_MIN
    return max(INITIAL_COINS_MIN, min(INITIAL_COINS_MAX, value))


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

    # v1.4：走判定模型组（judge）
    config = llm_config.resolve_llm_config(db, profile.user_id, llm_config.PURPOSE_JUDGE)
    result = llm_service.chat_json(
        prompts.build_supplement_messages(
            basic_profile=profile.basic_profile or {},
            current_attributes=current_attributes,
            history=history,
            supplement_text=detail,
        ),
        config=config,
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
        # v1.8：封顶 100 / 下限 0，以实际变动量记账
        before = attr.current_value
        after = round(clamp_attribute_value(before + delta, attr.max_value), 2)
        actual_delta = round(after - before, 2)
        if actual_delta == 0:
            continue  # 已封顶/已触底，本次实际无变化
        attr.current_value = after
        db.add(
            AttributeHistory(
                user_id=user.id,
                attribute_id=attr.id,
                event_id=None,
                judgment_id=None,
                delta=actual_delta,
                value_after=after,
                reason=item.get("reason", ""),
                evidence=item.get("evidence", ""),
            )
        )
        applied.append({"name": name, "delta": actual_delta, "value_after": after})

    profile.pending_adjustment = {}
    db.commit()
    return {"applied": applied, "message": "调整已生效。"}


def reset_onboarding(db: Session) -> dict:
    """重置角色档案：解锁首次引导，可重新走问卷生成新面板。属性值保留（重新建档时覆盖）。"""
    user = get_or_create_default_user(db)
    profile = _get_profile(db, user)
    _assert_unbuilt_profile(db, profile)
    profile.onboarding_state = {}
    profile.pending_adjustment = {}
    db.commit()
    return {"status": "ok", "message": "角色档案已重置，可重新开始问卷。"}


def reset_all_data(db: Session) -> dict:
    raise ValueError("真实数据清空入口已停用；批量清理必须先整库备份并走事件删除接口。")
