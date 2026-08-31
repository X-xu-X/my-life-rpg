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

from sqlalchemy.orm import Session

from app import prompts
from app.constants import ATTRIBUTE_ALIASES
from app.models import AIJudgment, Attribute, AttributeHistory, Event, JudgmentLog
from app.services.anchor_service import format_anchors_text
from app.services.llm_service import LLMError, llm_service
from app.services.user_service import get_or_create_default_user

# 单属性单次增减的合理区间（PRD 4.4 节）
DELTA_LIMIT = 5.0


def _normalize_attribute_name(name: str) -> str | None:
    """将 AI 返回的属性名规范化到标准维度；无法识别返回 None（保守跳过）。"""
    key = name.strip().lower()
    return ATTRIBUTE_ALIASES.get(key) or ATTRIBUTE_ALIASES.get(name.strip())


def _clamp_delta(delta: float) -> float:
    """将 delta 钳制到 [-DELTA_LIMIT, +DELTA_LIMIT]，防止模型输出异常值。"""
    return max(-DELTA_LIMIT, min(DELTA_LIMIT, delta))


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

def judge_event(db: Session, event: Event) -> AIJudgment:
    """对事件触发 AI 判定，创建 pending 判定记录。

    幂等约束：
    - 事件已入账（confirmed）：拒绝重复判定，避免判定中心出现"同事件双记录"（修复 bug）。
    - 事件已有未确认判定（pending/adjusted）：先清除旧判定（连同审计）再新建，避免重复。
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
    messages = prompts.build_judge_messages(
        anchors_text=anchors_text,
        event_description=format_event_description(event),
        profile_context=_profile_context(db, user.id),
    )
    result = llm_service.chat_json(messages)

    changes = _parse_changes(result.get("affected_attributes", []))
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


# ============ 确认入账 ============

def confirm(db: Session, judgment: AIJudgment) -> AIJudgment:
    """确认判定入账：写属性流水 + 更新属性当前值。"""
    user = get_or_create_default_user(db)
    # 以最新建议增减为准（可能已因补充/反驳被调整）
    changes = judgment.suggested_changes
    for item in changes:
        name = item["name"]
        delta = item["delta"]
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
                reason=item.get("reason", ""),
                evidence=item.get("evidence", ""),
            )
        )
    judgment.status = "confirmed"
    judgment.final_changes = changes
    _log(
        db, judgment.id, user.id, "confirm",
        detail="用户确认入账",
        payload={"final_changes": changes},
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
