"""AI 判定闭环服务（产品灵魂）。

流程（PRD 4.3 节）：
事件录入 → AI 判定 → 用户三选一（确认/补充/反驳）→ 复核客观 → 审计可回溯。

本服务提供：
- judge_event：触发 AI 判定，生成 pending 判定记录
- confirm：确认入账（写属性流水 + 更新属性值）
- supplement：补充信息重新判定
- dispute：反驳复核（客观，不迎合）
- 全程写 judgment_logs 审计
"""
import json
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import prompts
from app.constants import ATTRIBUTE_ALIASES
from app.models import AIJudgment, Attribute, AttributeHistory, Event, JudgmentLog, Setting
from app.services import memory_service
from app.services.anchor_service import format_anchors_text
from app.services.llm_service import LLMError, llm_service
from app.services.user_service import get_or_create_default_user

# 单属性单次增减的合理区间（PRD 4.4 节）
DELTA_LIMIT = 5.0

# 低置信度入账拦截阈值（v1.2）：低于该置信度不允许直接入账
CONFIDENCE_CONFIRM_MIN = 0.8

# 不实事件触发诚信减分的累计次数阈值（v1.2）
UNREALISTIC_HONESTY_THRESHOLD = 3
# 每次诚信减分
UNREALISTIC_HONESTY_DELTA = -0.5


def _normalize_attribute_name(name: str) -> str | None:
    """将 AI 返回的属性名规范化到标准维度；无法识别返回 None（保守跳过）。"""
    key = name.strip().lower()
    return ATTRIBUTE_ALIASES.get(key) or ATTRIBUTE_ALIASES.get(name.strip())


def _clamp_delta(delta: float) -> float:
    """将 delta 钳制到 [-DELTA_LIMIT, +DELTA_LIMIT]，防止模型输出异常值。"""
    return max(-DELTA_LIMIT, min(DELTA_LIMIT, delta))


def _recent_same_category_count(db: Session, user_id: int, event: Event) -> int:
    """近 30 天同类别事件次数（累积效应：坚持上浮 / 频繁加重）。"""
    cutoff = datetime.now() - timedelta(days=30)
    return (
        db.query(func.count(Event.id))
        .filter(
            Event.user_id == user_id,
            Event.category == event.category,
            Event.created_at >= cutoff,
        )
        .scalar()
        or 0
    )


def _attribute_context(db: Session, user_id: int) -> str:
    """当前属性值文本（边际递减参考）。"""
    attrs = db.query(Attribute).filter(Attribute.user_id == user_id).all()
    if not attrs:
        return ""
    return "、".join(f"{a.name} {a.current_value:.0f}" for a in attrs)


def _recent_events_context(db: Session, user_id: int, exclude_event_id: int, days: int = 7, limit: int = 10) -> str:
    """用户近期生活记录摘要（AI 上下文记忆：跨会话记住用户近况）。"""
    cutoff = datetime.now() - timedelta(days=days)
    events = (
        db.query(Event)
        .filter(
            Event.user_id == user_id,
            Event.created_at >= cutoff,
            Event.id != exclude_event_id,
            Event.is_pure.is_(False),
        )
        .order_by(Event.created_at.desc())
        .limit(limit)
        .all()
    )
    if not events:
        return ""
    parts = []
    for e in events:
        text = (e.content or e.title or "").strip()
        if len(text) > 60:
            text = text[:60] + "…"
        parts.append(f"{e.created_at.strftime('%m-%d')} {e.category}：{text}")
    return "；".join(parts)


def _get_disabled_attributes(db: Session, user_id: int) -> set[str]:
    """读取用户关闭判定的维度（AI 不分析不加点）。"""
    row = db.query(Setting).filter(Setting.user_id == user_id, Setting.key == "disabled_attributes").first()
    if row and isinstance(row.value, list):
        return set(row.value)
    return set()


def _today_events_context(db: Session, user_id: int, exclude_event_id: int) -> str:
    """当天已记录的事件摘要（事件去重：日记提到同一件事时，不重复加事实分）。"""
    start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    events = (
        db.query(Event)
        .filter(
            Event.user_id == user_id,
            Event.created_at >= start_of_day,
            Event.id != exclude_event_id,
            Event.is_pure.is_(False),
        )
        .order_by(Event.created_at.asc())
        .all()
    )
    if not events:
        return ""
    parts = []
    for e in events:
        text = (e.content or e.title or "").strip()
        parts.append(f"{e.created_at.strftime('%H:%M')} {e.category}：{text}")
    return "；".join(parts)


class ClarifyNeededError(Exception):
    """判定前信息不足，需要用户补充回答（携带追问问题）。"""

    def __init__(self, questions: list[str]):
        self.questions = questions
        super().__init__("事件信息不足，需要追问补充")


def format_event_description(event: Event) -> str:
    """将事件转成可读文本，供 AI 判定。form 通道格式参数，journal 通道用原文。"""
    lines = [f"事件类型：{event.event_type}"]
    if event.category:
        lines.append(f"类别：{event.category}")
    if event.title:
        lines.append(f"简述：{event.title}")
    if event.source == "journal" and event.content:
        lines.append(f"日记原文：{event.content}")
    elif event.params:
        # 结构化参数转可读文本
        for k, v in event.params.items():
            if v is not None and v != "":
                lines.append(f"{k}：{v}")
    return "\n".join(lines)


def _profile_context(db: Session, user_id: int) -> str:
    """提取用户画像背景，辅助 AI 判断事件相对水平（可选）。"""
    from app.models import UserProfile

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile and profile.basic_profile:
        return json.dumps(profile.basic_profile, ensure_ascii=False, indent=2)
    return ""


def _log(db: Session, judgment_id: int, user_id: int, action: str, detail: str = "", payload: dict | None = None) -> None:
    """写入一条审计日志。"""
    db.add(
        JudgmentLog(
            judgment_id=judgment_id,
            user_id=user_id,
            action=action,
            detail=detail,
            payload=payload or {},
        )
    )


def _ensure_attribute(db: Session, user_id: int, name: str) -> Attribute:
    """确保属性记录存在；不存在则以中性值 50 创建（未做 Onboarding 时兜底）。"""
    attr = db.query(Attribute).filter(Attribute.user_id == user_id, Attribute.name == name).first()
    if attr is None:
        attr = Attribute(user_id=user_id, name=name, current_value=50.0)
        db.add(attr)
        db.flush()
    return attr


def _parse_changes(raw_changes: list[dict]) -> list[dict]:
    """解析并规范化 AI 返回的 affected_attributes。

    - 属性名规范化到标准维度，无法识别则跳过（保守，避免污染数据）。
    - delta 钳制到合理区间。
    """
    cleaned: list[dict] = []
    for item in raw_changes or []:
        name = _normalize_attribute_name(str(item.get("name", "")))
        if name is None:
            continue
        try:
            delta = float(item.get("delta", 0.0))
        except (TypeError, ValueError):
            delta = 0.0
        cleaned.append(
            {
                "name": name,
                "delta": round(_clamp_delta(delta), 2),
                "reason": str(item.get("reason", "")),
                "evidence": str(item.get("evidence", "")),
            }
        )
    return cleaned


# ============ 判定 ============

def judge_event(db: Session, event: Event, clarification: str = "") -> AIJudgment:
    """对事件触发 AI 判定，创建 pending 判定记录。

    幂等约束：
    - 事件已入账（confirmed）：拒绝重复判定，避免判定中心出现"同事件双记录"（修复 bug）。
    - 事件已有未确认判定（pending/adjusted）：先清除旧判定（连同审计）再新建，避免重复。

    v1.2：信息缺口追问——AI 认为描述不足且未提供 clarification 时抛 ClarifyNeededError；
    用户补充回答后带 clarification 重新判定。
    """
    user = get_or_create_default_user(db)
    existing_confirmed = (
        db.query(AIJudgment)
        .filter(
            AIJudgment.event_id == event.id,
            AIJudgment.user_id == user.id,
            AIJudgment.status == "confirmed",
        )
        .first()
    )
    if existing_confirmed:
        raise ValueError("该事件已确认入账。如需重新判定，请删除该事件后重新记录，或用「补充信息」调整。")
    stale = (
        db.query(AIJudgment)
        .filter(
            AIJudgment.event_id == event.id,
            AIJudgment.user_id == user.id,
            AIJudgment.status.in_(["pending", "adjusted"]),
        )
        .all()
    )
    for j in stale:
        db.query(JudgmentLog).filter(JudgmentLog.judgment_id == j.id).delete()
        db.delete(j)
    db.flush()

    anchors_text = format_anchors_text(db)
    # 长期记忆：每天检查更新一次（失败不影响判定）
    memory = memory_service.maybe_update_memory(db, user)
    memory_text = memory_service.format_memory_text(memory)
    # 维度开关：关闭判定的维度不分析不加点
    disabled = _get_disabled_attributes(db, user.id)
    messages = prompts.build_judge_messages(
        anchors_text=anchors_text,
        event_description=format_event_description(event),
        profile_context=_profile_context(db, user.id),
        recent_count=_recent_same_category_count(db, user.id, event),
        attribute_context=_attribute_context(db, user.id),
        clarification=clarification,
        recent_events_context=_recent_events_context(db, user.id, event.id),
        memory_context=memory_text,
        disabled_attributes=sorted(disabled),
        today_events_context=_today_events_context(db, user.id, event.id),
    )
    result = llm_service.chat_json(messages)

    # 真实性甄别（v1.2）：事件明显不符合科学常理 → 拒绝判定，累计不实提交第 3 次起减诚信
    if not result.get("realistic", True):
        _handle_unrealistic(db, user.id, event, str(result.get("realistic_reason", "事件不符合常理")))

    # 信息缺口（v1.2）：AI 认为描述不足（无论是否已补充）→ 继续追问，直到信息足够
    if result.get("needs_clarify"):
        raise ClarifyNeededError(result.get("questions") or ["请补充一下事件的关键细节。"])

    changes = _parse_changes(result.get("affected_attributes", []))
    # 双保险：过滤掉用户关闭判定的维度（即使 AI 仍返回了）
    if disabled:
        changes = [c for c in changes if c["name"] not in disabled]
    judgment = AIJudgment(
        event_id=event.id,
        user_id=user.id,
        suggested_changes=changes,
        analysis=result.get("analysis", []),  # v1.1：AI 分析过程（推理链路）
        summary=str(result.get("summary", "")),
        confidence=float(result.get("confidence", 0.0)),
        status="pending",
        final_changes=[],
    )
    db.add(judgment)
    db.flush()
    _log(
        db, judgment.id, user.id, "create",
        detail="AI 判定生成",
        payload={"suggested_changes": changes, "analysis": judgment.analysis, "summary": judgment.summary},
    )
    db.commit()
    db.refresh(judgment)
    return judgment


def _handle_unrealistic(db: Session, user_id: int, event: Event, reason: str) -> None:
    """处理不实事件：累计次数，第 3 次起减诚信。以 ValueError 终止判定。"""
    row = db.query(Setting).filter(Setting.user_id == user_id, Setting.key == "unreal_count").first()
    count = 0
    if row:
        try:
            count = int(row.value)
        except (TypeError, ValueError):
            count = 0
    count += 1
    if row:
        row.value = count
    else:
        db.add(Setting(user_id=user_id, key="unreal_count", value=count))

    msg = f"AI 认为该事件不符合常理：{reason}。请修正后重新提交。"
    if count >= UNREALISTIC_HONESTY_THRESHOLD:
        attr = _ensure_attribute(db, user_id, "诚信")
        attr.current_value = round(attr.current_value + UNREALISTIC_HONESTY_DELTA, 2)
        db.add(
            AttributeHistory(
                user_id=user_id,
                attribute_id=attr.id,
                event_id=event.id,
                judgment_id=None,
                delta=UNREALISTIC_HONESTY_DELTA,
                value_after=attr.current_value,
                reason=f"连续 {count} 次提交不实事件，诚信减分",
                evidence=f"AI 真实性甄别：事件明显不符合科学常理（{reason}）。",
            )
        )
        msg += f"（累计 {count} 次不实提交，诚信 {UNREALISTIC_HONESTY_DELTA}）"
    # 不实事件不予保留，直接删除，避免垃圾数据
    db.delete(event)
    db.commit()
    raise ValueError(msg)


# ============ 确认入账 ============

def confirm(db: Session, judgment: AIJudgment) -> AIJudgment:
    """确认判定入账：写属性流水 + 更新属性当前值。

    v1.2：置信度加权——实际入账 delta = 原始建议 delta × confidence
    （描述越详细真实置信度越高 → 越接近满额加点；含糊/有编造嫌疑 → 打折）。
    v1.2：低置信度拦截——confidence < 80% 不允许入账，引导补充信息重判。
    """
    user = get_or_create_default_user(db)
    if judgment.confidence is not None and judgment.confidence < CONFIDENCE_CONFIRM_MIN:
        raise ValueError(
            f"判定置信度不足（{judgment.confidence:.0%} < {CONFIDENCE_CONFIRM_MIN:.0%}），"
            "请使用「补充信息」补充细节后重新判定，再确认入账。"
        )
    conf = judgment.confidence if judgment.confidence is not None else 1.0
    changes = judgment.suggested_changes
    applied_changes = []
    for item in changes:
        name = item["name"]
        raw_delta = item["delta"]
        delta = round(raw_delta * conf, 2)
        if delta == 0:
            continue  # 加权后为 0，不入账
        attr = _ensure_attribute(db, user.id, name)
        attr.current_value = round(attr.current_value + delta, 2)
        db.add(
            AttributeHistory(
                user_id=user.id,
                attribute_id=attr.id,
                event_id=judgment.event_id,
                judgment_id=judgment.id,
                delta=delta,
                value_after=attr.current_value,
                reason=f"{item.get('reason', '')}（置信度 {conf:.0%} 加权）",
                evidence=item.get("evidence", ""),
            )
        )
        applied_changes.append({**item, "delta": delta})
    judgment.status = "confirmed"
    judgment.final_changes = applied_changes
    _log(
        db, judgment.id, user.id, "confirm",
        detail=f"用户确认入账（置信度 {conf:.0%} 加权）",
        payload={"raw_changes": changes, "applied_changes": applied_changes},
    )
    db.commit()
    db.refresh(judgment)
    return judgment


# ============ 补充信息重判 ============

def supplement(db: Session, judgment: AIJudgment, detail: str) -> AIJudgment:
    """用户补充信息，AI 重新判定。"""
    user = get_or_create_default_user(db)
    _log(db, judgment.id, user.id, "supplement", detail=detail, payload={"detail": detail})

    event = db.get(Event, judgment.event_id)
    anchors_text = format_anchors_text(db)
    # 在原事件描述上附加补充信息
    extra_desc = format_event_description(event) + f"\n\n【用户补充信息】\n{detail}"
    messages = prompts.build_judge_messages(
        anchors_text=anchors_text,
        event_description=extra_desc,
        profile_context=_profile_context(db, user.id),
        recent_count=_recent_same_category_count(db, user.id, event),
        attribute_context=_attribute_context(db, user.id),
    )
    result = llm_service.chat_json(messages)
    changes = _parse_changes(result.get("affected_attributes", []))

    judgment.suggested_changes = changes
    judgment.analysis = result.get("analysis", [])  # v1.1：补充重判同样记录分析过程
    judgment.summary = str(result.get("summary", ""))
    judgment.confidence = float(result.get("confidence", 0.0))
    judgment.status = "adjusted"
    _log(
        db, judgment.id, user.id, "rejudge",
        detail="补充信息后重新判定",
        payload={"suggested_changes": changes, "analysis": judgment.analysis},
    )
    db.commit()
    db.refresh(judgment)
    return judgment


# ============ 反驳复核 ============

def dispute(db: Session, judgment: AIJudgment, detail: str) -> dict:
    """用户反驳，AI 依据事实复核（客观，不迎合）。

    返回 {judgment, result}：result 含 conclusion/explanation/confidence。
    """
    user = get_or_create_default_user(db)
    _log(db, judgment.id, user.id, "dispute", detail=detail, payload={"detail": detail})

    event = db.get(Event, judgment.event_id)
    anchors_text = format_anchors_text(db)
    messages = prompts.build_dispute_messages(
        anchors_text=anchors_text,
        event_description=format_event_description(event),
        original_judgment={
            "affected_attributes": judgment.suggested_changes,
            "summary": judgment.summary,
            "confidence": judgment.confidence,
        },
        dispute_reason=detail,
    )
    result = llm_service.chat_json(messages)
    conclusion = str(result.get("conclusion", "maintain"))

    if conclusion == "adjust":
        changes = _parse_changes(result.get("affected_attributes", []))
        if changes:  # 仅在模型给出有效调整结果时覆盖
            judgment.suggested_changes = changes
            judgment.summary = str(result.get("explanation", "")) or judgment.summary
            judgment.status = "adjusted"
        else:
            conclusion = "maintain"  # 无有效调整，保守维持原判
        _log(
            db, judgment.id, user.id, "rejudge",
            detail=f"复核结论：{conclusion}",
            payload={"result": result},
        )
    else:
        _log(
            db, judgment.id, user.id, "maintain",
            detail=f"复核结论：坚持原判",
            payload={"result": result},
        )

    judgment.confidence = float(result.get("confidence", judgment.confidence))
    db.commit()
    db.refresh(judgment)
    return {
        "judgment": judgment,
        "conclusion": conclusion,
        "explanation": str(result.get("explanation", "")),
    }


# ============ 事件删除（误提交兜底，v1.1） ============

def delete_event(db: Session, event: Event) -> None:
    """删除事件及其关联判定；已确认入账的点数同步回滚，全程留痕。

    规则（PRD 4.3 节「误提交兜底」）：
    - confirmed 判定：按 final_changes 反向回滚属性值，并写 AttributeHistory 流水
      （delta 取反，reason 注明「事件删除回滚」，保证点数账目可追溯）
    - 物理删除关联 ai_judgments 与 judgment_logs，再删除事件本身
    - 历史入账流水（attribute_history）保留，与回滚流水形成完整账目
    """
    user = get_or_create_default_user(db)
    judgments = (
        db.query(AIJudgment)
        .filter(AIJudgment.event_id == event.id, AIJudgment.user_id == user.id)
        .all()
    )

    for judgment in judgments:
        if judgment.status == "confirmed":
            for item in judgment.final_changes or judgment.suggested_changes:
                name = item.get("name", "")
                try:
                    delta = float(item.get("delta", 0.0))
                except (TypeError, ValueError):
                    delta = 0.0
                if delta == 0 or not name:
                    continue
                attr = _ensure_attribute(db, user.id, name)
                attr.current_value = round(attr.current_value - delta, 2)
                db.add(
                    AttributeHistory(
                        user_id=user.id,
                        attribute_id=attr.id,
                        event_id=None,
                        judgment_id=None,
                        delta=-delta,
                        value_after=attr.current_value,
                        reason=f"事件删除回滚（原判定：{item.get('reason', '')}）",
                        evidence="误提交兜底，删除事件",
                    )
                )
        # 审计留痕后清理判定及其日志
        _log(
            db, judgment.id, user.id, "delete",
            detail=f"删除事件（event_id={event.id}）",
            payload={
                "event_title": event.title or event.content[:40],
                "confirmed_rollback": judgment.status == "confirmed",
            },
        )
        db.flush()
        db.query(JudgmentLog).filter(JudgmentLog.judgment_id == judgment.id).delete()
        db.delete(judgment)

    db.delete(event)
    db.commit()
