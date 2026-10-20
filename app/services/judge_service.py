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
from app.services.ai_context import model_context
from app.services.time_service import clock_now
from app.services.model_validation import provenance
import json
import math
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import prompts
from app.constants import ATTRIBUTE_ALIASES, ATTRIBUTE_FULL
from app.models import AIJudgment, Attribute, AttributeHistory, CheckinItem, Event, JudgmentLog, Setting
from app.services import (
    achievement_service,
    exemption_service,
    item_service,
    llm_config,
    memory_service,
    subdimension_service,
)
from app.services.transactions import rollback_on_error, lock_profile
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


def _normalize_attribute_name(name: str, extra_names: set[str] | None = None) -> str | None:
    """将 AI 返回的属性名规范化到标准维度；无法识别返回 None（保守跳过）。

    v1.10（M3）：`extra_names` 传入该用户的**子维度名**——子维度由用户确认后动态产生，
    不在 `ATTRIBUTE_ALIASES` 里，必须单独放行。
    """
    key = name.strip().lower()
    hit = ATTRIBUTE_ALIASES.get(key) or ATTRIBUTE_ALIASES.get(name.strip())
    if hit:
        return hit
    if extra_names:
        raw = name.strip()
        if raw in extra_names:
            return raw
        # 大小写/空白容错（英文子维度名场景）
        for cand in extra_names:
            if cand.lower() == key:
                return cand
    return None


def _clamp_delta(delta: float) -> float:
    """将 delta 钳制到 [-DELTA_LIMIT, +DELTA_LIMIT]，防止模型输出异常值。"""
    return max(-DELTA_LIMIT, min(DELTA_LIMIT, delta))


def _clamp_attribute_value(value: float, max_value: float) -> float:
    """将属性值钳制到 [0, max_value]（v1.8 A2-5：封顶 100 / 下限 0）。

    **全项目统一的属性值写入夹取工具**——所有写 `Attribute.current_value` 的地方
    都必须调用它，不要各写各的（v1.5 B-03「多入口必须同一写入语义」教训）。

    背景：属性面板是 100 分制，但置信度加权/累积加成/多维度叠加后可能算出
    超过 100 或低于 0 的值；靠既有的「边际递减」机制让越接近 100 越难涨，
    但那是"涨幅打折"，不能替代硬性封顶。
    """
    upper = float(max_value) if max_value is not None else 100.0
    return max(0.0, min(upper, float(value)))


def _recent_same_category_count(db: Session, user_id: int, event: Event) -> int:
    """近 30 天同类别事件次数（累积效应：坚持上浮 / 频繁加重）。"""
    cutoff = clock_now() - timedelta(days=30)
    return (
        db.query(func.count(Event.id))
        .filter(
            Event.user_id == user_id, Event.is_deleted.is_(False),
            Event.category == event.category,
            Event.created_at >= cutoff,
        )
        .scalar()
        or 0
    )


def _attribute_context(db: Session, user_id: int) -> str:
    """当前属性值文本（边际递减参考）。v1.10 M3：只列主维度（子维度另有专门 context）。"""
    attrs = (
        db.query(Attribute)
        .filter(Attribute.user_id == user_id, Attribute.parent_id.is_(None))
        .all()
    )
    if not attrs:
        return ""
    return "、".join(f"{a.name} {a.current_value:.0f}" for a in attrs)


def _recent_events_context(db: Session, user_id: int, exclude_event_id: int, days: int = 7, limit: int = 10) -> str:
    """用户近期生活记录摘要（AI 上下文记忆：跨会话记住用户近况）。"""
    cutoff = clock_now() - timedelta(days=days)
    events = (
        db.query(Event)
        .filter(
            Event.user_id == user_id, Event.is_deleted.is_(False),
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


def _recent_24h_context(db: Session, user_id: int, exclude_event_id: int, limit: int = 10) -> str:
    """近 24 小时记录（v1.7 跨来源合并专用）。

    与 `_recent_events_context`（近 7 天，用于"理解连续状态"）区分：本块**仅用于判断
    本条是否与已记录的某件事是同一件事**，不得当作"要一起判定的内容"给分——
    注入文本里会明确标注这一用途，避免 AI 误用。
    """
    cutoff = clock_now() - timedelta(hours=24)
    events = (
        db.query(Event)
        .filter(
            Event.user_id == user_id, Event.is_deleted.is_(False),
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
        parts.append(f"{e.created_at.strftime('%m-%d %H:%M')} {e.category}：{text}")
    return "；".join(parts)


def _get_disabled_attributes(db: Session, user_id: int) -> set[str]:
    """读取用户关闭判定的维度（AI 不分析不加点）。"""
    row = db.query(Setting).filter(Setting.user_id == user_id, Setting.key == "disabled_attributes").first()
    if row and isinstance(row.value, list):
        return set(row.value)
    return set()


def _today_events_context(db: Session, user_id: int, exclude_event_id: int) -> str:
    """当天已记录的事件摘要（事件去重：日记提到同一件事时，不重复加事实分）。"""
    start_of_day = clock_now().replace(hour=0, minute=0, second=0, microsecond=0)
    events = (
        db.query(Event)
        .filter(
            Event.user_id == user_id, Event.is_deleted.is_(False),
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


def item_context_text(db: Session, event: Event) -> str:
    """v1.7：打卡项目上下文块（供判定 prompt 理解本条记录的"项目身份"）。

    item_id 为 NULL（全部老数据、纯自由记录）时返回空串——整块不输出（兼容红线）。
    """
    item_id = getattr(event, "item_id", None)
    if not item_id:
        return ""
    item = db.get(CheckinItem, item_id)
    if item is None:
        return ""  # 项目已被物理删除（理论不会，删=停用）——保守跳过
    nature_label = {"planned": "规划内", "optional": "可选", "negative": "负面", "other": "其他"}.get(
        item.nature, item.nature
    )
    freq_label = {"daily": "每天", "weekly": f"每周 {item.frequency_target} 次", "none": "不限频率"}.get(
        item.frequency_type, "不限频率"
    )
    parts = [nature_label, freq_label]
    if item.category:
        parts.append(item.category)
    lines = [f"打卡项目：{item.name}（{' · '.join(parts)}）"]
    # 频率进度：本周/今日已完成几次（供 optional 判断"规划内是否已完成"、planned 判断是否达标）
    if item.frequency_type in ("daily", "weekly"):
        done = item_service.count_in_period(db, event.user_id, item)
        target = item_service.item_target(item)
        period = "今天" if item.frequency_type == "daily" else "本周"
        if target:
            lines.append(f"项目频率：{period}已完成 {done}/{target} 次")
        else:
            lines.append(f"项目频率：{period}已完成 {done} 次")
    if item.related_attribute:
        lines.append(f"主要影响维度：{item.related_attribute}")
    return "\n".join(lines)


def format_event_description(event: Event, item_context: str = "") -> str:
    """将事件转成可读文本，供 AI 判定。form 通道用正文 + 数字键值对，journal 通道用原文。

    v1.7：新增打卡项目上下文块（item_context 非空时插在"事件类型"之后）；
    老数据 item_id 为 NULL → item_context 为空 → 整块不出现（兼容全部老数据）。
    """
    lines = [f"事件类型：{event.event_type}"]
    if item_context:
        lines.append(item_context)
    if event.category:
        lines.append(f"类别：{event.category}")
    if event.title:
        lines.append(f"简述：{event.title}")
    if event.source == "journal" and event.content:
        lines.append(f"日记原文：{event.content}")
    else:
        # v1.7：打卡正文（用户手写的正文，与 params 并存）
        if event.content:
            lines.append(f"记录正文：{event.content}")
        if event.params:
            # 结构化参数转可读文本（跳过 "_" 开头的内部键，如 _clarify_history）
            for k, v in event.params.items():
                if v is not None and v != "" and not k.startswith("_"):
                    lines.append(f"{k}：{v}")
    return "\n".join(lines)


def _profile_context(db: Session, user_id: int) -> str:
    """提取用户画像背景，辅助 AI 判断事件相对水平（可选）。"""
    from app.models import UserProfile

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    from app.models.full_system import PersonalPhase
    phase=db.query(PersonalPhase).filter_by(user_id=user_id).first()
    background={'profile':profile.basic_profile if profile else {}}
    if phase and phase.payload.get('ai_allowed'):background['phase']=phase.payload
    return json.dumps(background,ensure_ascii=False)


def _log(db: Session, judgment_id: int, user_id: int, action: str, detail: str = "", payload: dict | None = None) -> None:
    """写入一条审计日志，模型来源保存为当次不可变快照。"""
    payload = dict(payload or {})
    source = db.query(AIJudgment).filter_by(id=judgment_id, user_id=user_id).first()
    if source and source.model_provenance:
        payload['model_provenance'] = dict(source.model_provenance)
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


def _event_version(event):
    return (event.content_version, event.event_type, event.source, event.item_id, event.is_pure, event.origin,
            event.title, event.category, event.content, event.occurred_at, event.occurred_on, event.time_precision,
            json.dumps(event.params or {}, sort_keys=True, ensure_ascii=False))


def _lock_event(db, event_id, user_id, version=None):
    lock_profile(db, user_id)
    changed = db.query(Event).filter(Event.id == event_id, Event.user_id == user_id,
        Event.is_deleted.is_(False)).update(
        {Event.id: Event.id}, synchronize_session=False)
    if changed != 1:
        raise ValueError("事件不存在或已删除。")
    event = db.query(Event).filter(Event.id == event_id).populate_existing().one()
    if version is not None and _event_version(event) != version:
        raise ValueError("判定期间事件已被编辑，请重新判定。")
    return event


def _require_reviewable(db, judgment, *, allow_challenge=False):
    db.refresh(judgment)
    event = db.get(Event, judgment.event_id)
    if event is None or event.is_deleted or judgment.status in ("deleted", "invalidated", "claimed"):
        raise ValueError("判定已失效，请刷新后重试。")
    if judgment.status == "confirmed":
        raise ValueError("该判定已入账，不能重复修订。如需撤销请删除事件。")
    if event.origin == "challenge" and not allow_challenge:
        raise ValueError("挑战判定请在挑战页补充自述或结算。")


def _finite_float(raw, fallback=0.0):
    if isinstance(raw, bool):
        return fallback
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return value if math.isfinite(value) else fallback


def _parse_confidence(raw) -> float:
    if isinstance(raw, bool):
        return 0.0
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) and 0 <= value <= 1 else 0.0


def _parse_changes(raw_changes, extra_names: set[str] | None = None) -> list[dict]:
    """先合并规范名称，再整体夹取；畸形数值不进入账目。"""
    if not isinstance(raw_changes, list):
        return []
    grouped = {}
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        name = _normalize_attribute_name(str(item.get("name", "")), extra_names)
        if name is None:
            continue
        group = grouped.setdefault(name, {"delta": 0.0, "reason": [], "evidence": []})
        group["delta"] += _finite_float(item.get("delta"), 0.0)
        for key in ("reason", "evidence"):
            text = str(item.get(key, "")).strip()
            if text: group[key].append(text)
    return [{"name": name, "delta": round(_clamp_delta(_finite_float(g["delta"])), 2),
             "reason": "；".join(dict.fromkeys(g["reason"])),
             "evidence": "；".join(dict.fromkeys(g["evidence"]))}
            for name, g in grouped.items()]


def _parse_revision_notes(raw) -> list[str]:
    """规范化 AI 返回的 revision_notes（字符串数组，v1.6）。"""
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _parse_merged_with(raw) -> list[dict]:
    """规范化 AI 返回的 merged_with（v1.7 跨来源合并明细）。

    期望 [{ref, note}]；容错处理模型可能的字符串数组（降级为 {ref, note:""}）。
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            ref = str(item.get("ref", "")).strip()
            note = str(item.get("note", "")).strip()
            if ref or note:
                out.append({"ref": ref, "note": note})
        elif isinstance(item, str) and item.strip():
            out.append({"ref": item.strip(), "note": ""})
    return out


def _apply_exemption(db: Session, user, event: Event, changes: list[dict]) -> tuple[list[dict], dict | None]:
    """v1.10（M2）豁免券：**判定链路里的唯一插入点**。

    落在用户已购券时段内的**负向变化一律归零**（该时段内不扣分），正向原样保留
    ——绝不整条事件跳过判定（其他维度照常加点）。
    只在此处查一次券，不重构既有分支。

    返回 `(changes, hit)`；`hit` 为 None 表示本次没有券生效。
    """
    at = event.occurred_at or event.created_at or clock_now()
    return exemption_service.apply_to_changes(changes, at, db, user)


def _exemption_note(hit: dict) -> str:
    """把豁免结果写进判定总结，让用户知道"为什么这次没扣分"。"""
    return (
        f"【豁免券】本次事件落在你购买的豁免时段（{hit['label']}）内，"
        f"{hit['zeroed']} 项扣分已豁免；其他正面表现照常加点。"
    )


def _subdimension_context(db: Session, user) -> str:
    """v1.10（M3）：已拆分的子维度清单，供 prompt 决定"加点落主维度还是子维度"。

    只列**有子维度**的主维度（没拆过的维度加不加这行都一样，避免 prompt 冗长）。
    """
    kids = subdimension_service.all_children(db, user)
    if not kids:
        return ""
    grouped: dict[int, list] = {}
    for k in kids:
        grouped.setdefault(k.parent_id, []).append(k)
    lines: list[str] = []
    for pid, rows in grouped.items():
        parent = db.get(Attribute, pid)
        if parent is None:
            continue
        full = float(parent.current_value or 0) >= ATTRIBUTE_FULL
        tag = "已满 100 → 加点写下列子维度名" if full else "未满 100 → 加点仍写主维度名"
        lines.append(
            f"- {parent.name}（{float(parent.current_value or 0):.1f}/100，{tag}）："
            + "、".join(r.name for r in rows)
        )
    return "\n".join(lines)


def _prior_snapshot(judgment: AIJudgment, db: Session) -> dict:
    """基准判定快照（v1.6 增量修订契约：重判时注入，要求相干维度逐字保留）。"""
    from app.services import ai_context
    if not ai_context.valid(db,judgment.source_snapshot,judgment.user_id):return {}
    return {
        "affected_attributes": judgment.suggested_changes or [],
        "analysis": judgment.analysis or [],
        "summary": judgment.summary or "",
        "confidence": judgment.confidence,
        "confidence_reason": judgment.confidence_reason or "",
    }


# ============ 判定 ============

@rollback_on_error
@model_context
def judge_event(db: Session, event: Event, clarification: str = "", *, before_write=None, commit_result=True) -> AIJudgment:
    """对事件触发 AI 判定，生成判定记录。

    幂等约束（v1.5 A1 统一重判链路）：
    - 事件已入账（confirmed）：拒绝重复判定，避免判定中心出现"同事件双记录"。
    - 事件已有未确认判定（pending/adjusted）：**就地更新现行判定（id 不变）**，
      与判定中心 supplement 链路行为一致——审计只增不删，前端 id 引用（审计面板/
      sessionStorage 预览）不会失效，杜绝"重判后结果随机漂移 + 旧审计被连带删除"。

    v1.2：信息缺口追问——AI 认为描述不足且未提供 clarification 时抛 ClarifyNeededError；
    用户补充回答后带 clarification 重新判定。
    v1.4：追问历史累积——每次用户的补充回答持久化到 event.params["_clarify_history"]，
    后续轮次全部注入 prompt，AI 才能做到「问过即止」（同一面已答过不再重复问）。
    """
    if event.is_deleted:
        raise ValueError("事件已删除。")
    if event.origin == "challenge":
        raise ValueError("挑战记录请在挑战页补充自述。")
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
        raise ValueError("该事件已确认入账。如需重新判定，请删除该事件后重新记录。")
    # v1.5 A1：现行判定（不删除，重判时就地更新）；invalidated 归档判定不参与
    current = (
        db.query(AIJudgment)
        .filter(
            AIJudgment.event_id == event.id,
            AIJudgment.user_id == user.id,
            AIJudgment.status.in_(["pending", "adjusted", "invalidated"]),
        )
        .order_by((AIJudgment.status == "invalidated").asc(), AIJudgment.id.desc())
        .first()
    )

    anchors_text = format_anchors_text(db)
    # 长期记忆：每天检查更新一次（失败不影响判定）
    from app.config import settings
    memory = memory_service.get_long_term_memory(db, user.id) if settings.cloud else memory_service.maybe_update_memory(db, user)
    memory_text = memory_service.format_memory_text(memory)
    # 维度开关：关闭判定的维度不分析不加点
    disabled = _get_disabled_attributes(db, user.id)
    # v1.4：追问历史累积（含本轮回答），供 AI「问过即止」
    clarify_history = list((event.params or {}).get("_clarify_history") or [])
    if clarification.strip():
        clarify_history.append(clarification.strip())
        event.params = {**(event.params or {}), "_clarify_history": clarify_history}
        db.flush()  # 立即持久化，下一轮追问可见
    # v1.10（M3）：子维度层级——已拆分的用户才有内容，未拆分的用户行为完全不变
    child_names = subdimension_service.child_name_set(db, user)
    messages = prompts.build_judge_messages(
        anchors_text=anchors_text,
        event_description=format_event_description(event, item_context_text(db, event)),
        profile_context=_profile_context(db, user.id),
        recent_count=_recent_same_category_count(db, user.id, event),
        attribute_context=_attribute_context(db, user.id),
        clarification=clarification,
        clarify_history=clarify_history,
        prior_judgment=(_prior_snapshot(current,db) if current is not None else None),  # v1.6：增量修订基准
        recent_events_context=_recent_events_context(db, user.id, event.id),
        memory_context=memory_text,
        disabled_attributes=sorted(disabled),
        today_events_context=_today_events_context(db, user.id, event.id),
        recent_24h_context=_recent_24h_context(db, user.id, event.id),  # v1.7：合并判断专用
        event_source=event.source,
        subdimension_context=_subdimension_context(db, user),  # v1.10 M3
    )
    # v1.4：按用户解析判定模型配置（BYOK；降级用辅助模型时 quality_note 非空）
    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_JUDGE)
    version = _event_version(event)
    prior_version = (current.id, current.updated_at) if current is not None else None
    db.commit()  # 保存追问回答并释放读事务；模型响应须通过版本检查才可写入
    result = llm_service.chat_json(messages, config=config)
    if before_write:
        before_write(db)
    event = _lock_event(db, event.id, user.id, version)
    llm_config.assert_current(db, config)
    rows = db.query(AIJudgment).filter(AIJudgment.event_id == event.id,
        AIJudgment.user_id == user.id).order_by((AIJudgment.status == "invalidated").asc(), AIJudgment.id.desc()).populate_existing().all()
    if any(j.status == "confirmed" for j in rows):
        raise ValueError("该事件已确认入账，不能重新判定。")
    current = next((j for j in rows if j.status in ("pending", "adjusted", "invalidated")), None)
    if ((current.id, current.updated_at) if current else None) != prior_version:
        raise ValueError("判定期间已有新的判定结果，请刷新。")


    # 真实性甄别（v1.2）：事件明显不符合科学常理 → 拒绝判定，累计不实提交第 3 次起减诚信
    if not result.get("realistic", True):
        if settings.cloud:
            raise ValueError("MODEL_FACT_REJECTED：请修正事实后再分析。")
        _handle_unrealistic(db, user.id, event, str(result.get("realistic_reason", "事件不符合常理")))

    # 信息缺口（v1.2）：AI 认为描述不足（无论是否已补充）→ 继续追问，直到信息足够
    if result.get("needs_clarify"):
        raise ClarifyNeededError(result.get("questions") or ["请补充一下事件的关键细节。"])

    changes = _parse_changes(result.get("affected_attributes", []), child_names)
    # 双保险：过滤掉用户关闭判定的维度（即使 AI 仍返回了）
    if disabled:
        changes = [c for c in changes if c["name"] not in disabled]
    # v1.10（M2）：豁免券——落在已购券时段内的负向变化一律归零（正向照常加点）
    changes, exemption_hit = _apply_exemption(db, user, event, changes)
    summary = str(result.get("summary", ""))
    if config.quality_note:
        # v1.4：判定经降级路径（辅助模型）时，summary 末尾附质量标注（前端显示小标签）
        summary = (summary + "\n" + config.quality_note).strip()
    if exemption_hit:
        # v1.10（M2）：说明"本次为什么没扣分"，否则用户会以为 AI 判错了
        summary = (summary + "\n" + _exemption_note(exemption_hit)).strip()
    merged_with = _parse_merged_with(result.get("merged_with"))  # v1.7：跨来源合并明细
    # v1.10（M1）：AI 发现型成就建议（可选字段）。**不自动发放**——只落库供前端展示追授卡，
    # 用户点【追授】才走 achievement_service.grant_discovered()。
    suggestion = achievement_service.parse_suggestion(result.get("achievement_suggestion"))
    if current is not None:
        # v1.5 A1：就地更新现行判定（id 不变，审计追加 rejudge）
        current.suggested_changes = changes
        current.analysis = result.get("analysis", [])
        current.summary = summary
        current.confidence = _parse_confidence(result.get("confidence"))
        current.confidence_reason = str(result.get("confidence_reason", ""))
        current.revision_notes = _parse_revision_notes(result.get("revision_notes"))  # v1.6：本次修订说明
        current.merged_with = merged_with  # v1.7
        current.model_provenance = provenance(config)
        # 重判时只在本次真的给出新建议时覆盖，避免把上一轮还没处理的建议冲掉
        if suggestion:
            current.achievement_suggestion = suggestion
        current.status = "adjusted"
        judgment = current
        db.flush()
        rejudge_detail = "追问补充后重新判定"
        if clarification.strip():
            rejudge_detail += f"（回答摘要：{clarification.strip()[:60]}）"
        _log(
            db, judgment.id, user.id, "rejudge",
            detail=rejudge_detail,
            payload={
                "suggested_changes": changes,
                "analysis": judgment.analysis,
                "summary": summary,
                "revision_notes": judgment.revision_notes,
                "merged_with": merged_with,  # v1.7
                "achievement_suggestion": suggestion,  # v1.10
                "exemption": exemption_hit,  # v1.10 M2：本次生效的豁免券（无则 None）
                "clarification": clarification.strip(),  # v1.5 A4：完整回答入审计，供「我的补充」展示
            },
        )
    else:
        judgment = AIJudgment(
            event_id=event.id,
            user_id=user.id,
            suggested_changes=changes,
            analysis=result.get("analysis", []),  # v1.1：AI 分析过程（推理链路）
            summary=summary,
            confidence=_parse_confidence(result.get("confidence")),
            confidence_reason=str(result.get("confidence_reason", "")),  # v1.4：置信度说明
            revision_notes=[],  # v1.6：首判无修订
            merged_with=merged_with, model_provenance=provenance(config),  # v1.7：跨来源合并明细
            achievement_suggestion=suggestion,  # v1.10：AI 发现型成就建议（可为 {}）
            status="pending",
            final_changes=[],
        )
        db.add(judgment)
        db.flush()
        _log(
            db, judgment.id, user.id, "create",
            detail="AI 判定生成",
            payload={
                "suggested_changes": changes,
                "analysis": judgment.analysis,
                "summary": judgment.summary,
                "merged_with": merged_with,  # v1.7
                "exemption": exemption_hit,  # v1.10 M2：本次生效的豁免券（无则 None）
            },
        )
    from app.services import ai_context
    judgment.source_snapshot=ai_context.sources()
    if commit_result:
        db.commit()
    else:
        db.flush()
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
        before = attr.current_value
        after = round(_clamp_attribute_value(before + UNREALISTIC_HONESTY_DELTA, attr.max_value), 2)
        actual_delta = round(after - before, 2)
        attr.current_value = after
        db.add(
            AttributeHistory(
                user_id=user_id,
                attribute_id=attr.id,
                event_id=event.id,
                judgment_id=None,
                delta=actual_delta,
                value_after=after,
                reason=f"连续 {count} 次提交不实事件，诚信减分",
                evidence=f"AI 真实性甄别：事件明显不符合科学常理（{reason}）。",
            )
        )
        msg += f"（累计 {count} 次不实提交，诚信 {UNREALISTIC_HONESTY_DELTA}）"
    event.is_deleted = True
    judgments = db.query(AIJudgment).filter(AIJudgment.event_id == event.id).all()
    if not judgments:
        rejected = AIJudgment(event_id=event.id, user_id=user_id, status="deleted", confidence=0.0,
                              suggested_changes=[], final_changes=[], summary=reason)
        db.add(rejected)
        db.flush()
        judgments = [rejected]
    for judgment in judgments:
        judgment.status = "deleted"
        _log(db, judgment.id, user_id, "reject", detail=reason,
             payload={"event_id": event.id, "unreal_count": count})
    db.commit()
    raise ValueError(msg)


# ============ 确认入账 ============

@rollback_on_error
def confirm(db: Session, judgment: AIJudgment, *, commit: bool = True, fact_id: int | None = None) -> AIJudgment:
    """确认判定入账：写属性流水 + 更新属性当前值。

    v1.2：置信度加权——实际入账 delta = 原始建议 delta × confidence
    （描述越详细真实置信度越高 → 越接近满额加点；含糊/有编造嫌疑 → 打折）。
    v1.2：低置信度拦截——confidence < 80% 不允许入账，引导补充信息重判。
    """
    user = get_or_create_default_user(db)
    lock_profile(db, user.id)
    _lock_event(db, judgment.event_id, user.id)
    from app.config import settings
    if settings.cloud:
        from app.models import UserProfile
        profile = db.query(UserProfile).filter_by(user_id=user.id).one()
        if not profile.onboarding_completed:
            raise ValueError("记录已保存；确认结算前请先选择角色基线。")
    _require_reviewable(db, judgment, allow_challenge=True)
    claimed = db.query(AIJudgment).filter(
        AIJudgment.id == judgment.id, AIJudgment.user_id == user.id,
        AIJudgment.status.in_(["pending", "adjusted"]),
    ).update({AIJudgment.status: "claimed"}, synchronize_session=False)
    if claimed != 1:
        raise ValueError("该判定已入账或正在处理中，请刷新后重试。")
    db.refresh(judgment)
    conf = _parse_confidence(judgment.confidence)
    if conf < CONFIDENCE_CONFIRM_MIN:
        raise ValueError("判定置信度不足或不合法，请补充信息后重新判定。")
    event = db.get(Event, judgment.event_id)
    if event is None or event.is_deleted:
        raise ValueError("事件不存在。")
    from app.services.facts import claim
    if fact_id is None:
        if event.record_kind=='diary':raise ValueError('日记须通过逐事实整组确认。')
        claim(db,event,judgment)
    else:
        from app.models.workflow import FactIdentity,FactSettlement
        fact=db.get(FactIdentity,fact_id)
        if not fact or fact.user_id!=user.id or db.query(FactSettlement).filter_by(fact_id=fact_id).first():raise ValueError('事实已入账，请刷新整组预览。')
        db.add(FactSettlement(user_id=user.id,fact_id=fact_id,judgment_id=judgment.id));db.flush()
    raw_changes = judgment.suggested_changes
    normalized = _parse_changes(raw_changes, subdimension_service.child_name_set(db, user))
    changes, exemption_hit = _apply_exemption(db, user, event, normalized)
    disabled = _get_disabled_attributes(db, user.id)
    attrs = db.query(Attribute).filter(Attribute.user_id == user.id).populate_existing().all()
    by_name = {a.name: a for a in attrs}
    by_id = {a.id: a for a in attrs}
    def is_disabled(attr):
        parent = by_id.get(attr.parent_id)
        return attr.name in disabled or (parent is not None and parent.name in disabled)
    targets = {}
    for item in changes:
        attr = by_name.get(item["name"])
        if attr is None or is_disabled(attr):
            continue
        target, note = subdimension_service.resolve_write_target(db, user, attr, delta=item["delta"])
        if is_disabled(target):
            continue
        group = targets.setdefault(target.id, {"attr": target, "delta": 0.0, "reason": [], "evidence": []})
        group["delta"] += item["delta"] * conf
        group["reason"].append(item.get("reason", "") + note)
        group["evidence"].append(item.get("evidence", ""))
    applied_changes = []
    for group in targets.values():
        attr = group["attr"]
        delta = round(_clamp_delta(group["delta"]), 2)
        before = attr.current_value
        after = round(_clamp_attribute_value(before + delta, attr.max_value), 2)
        actual = round(after - before, 2)
        if actual == 0:
            continue
        attr.current_value = after
        reason = "；".join(dict.fromkeys(group["reason"])) + f"（置信度 {conf:.0%} 加权）"
        evidence = "；".join(dict.fromkeys(group["evidence"]))
        db.add(AttributeHistory(user_id=user.id, attribute_id=attr.id,
            event_id=judgment.event_id, judgment_id=judgment.id, delta=actual,
            value_after=after, reason=reason, evidence=evidence))
        applied_changes.append({"name": attr.name, "delta": actual, "reason": reason, "evidence": evidence})
    judgment.status = "confirmed"
    judgment.final_changes = applied_changes
    _log(
        db, judgment.id, user.id, "confirm",
        detail=f"用户确认入账（置信度 {conf:.0%} 加权）",
        payload={"raw_changes": raw_changes, "applied_changes": applied_changes, "exemption": exemption_hit},
    )
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(judgment)
    return judgment


# ============ 补充信息重判 ============

@rollback_on_error
@model_context
def supplement(db: Session, judgment: AIJudgment, detail: str, *, before_write=None, commit_result=True) -> AIJudgment:
    """用户补充信息，AI 重新判定。"""
    _require_reviewable(db, judgment)
    user = get_or_create_default_user(db)
    _log(db, judgment.id, user.id, "supplement", detail=detail, payload={"detail": detail})

    event = db.get(Event, judgment.event_id)
    if event is None or event.is_deleted:
        raise ValueError("事件不存在或已删除。")
    anchors_text = format_anchors_text(db)
    # 在原事件描述上附加补充信息（v1.7：同样带打卡项目上下文）
    item_ctx = item_context_text(db, event)
    extra_desc = format_event_description(event, item_ctx) + f"\n\n【用户补充信息】\n{detail}"
    # v1.5 A4 修复：补充重判同样注入追问历史，避免 AI"失忆"——
    # 把此前追问中已回答的面当未提及，维度漂移、置信度虚低（实测 0.9→0.72 被拦截）
    clarify_history = list((event.params or {}).get("_clarify_history") or [])
    messages = prompts.build_judge_messages(
        anchors_text=anchors_text,
        event_description=extra_desc,
        profile_context=_profile_context(db, user.id),
        recent_count=_recent_same_category_count(db, user.id, event),
        attribute_context=_attribute_context(db, user.id),
        clarify_history=clarify_history,
        prior_judgment=_prior_snapshot(judgment,db),  # v1.6：增量修订基准（注入后只改受影响维度）
        event_source=event.source,
        today_events_context=_today_events_context(db, user.id, event.id),  # v1.7：合并判断依据
        subdimension_context=_subdimension_context(db, user),  # v1.10 M3
    )
    # v1.4：按用户解析判定模型配置（BYOK）
    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_JUDGE)
    version = _event_version(event)
    prior_updated_at = judgment.updated_at
    db.commit()
    result = llm_service.chat_json(messages, config=config)
    if before_write:
        before_write(db)
    event = _lock_event(db, event.id, user.id, version)
    llm_config.assert_current(db, config)
    _require_reviewable(db, judgment)
    if judgment.updated_at != prior_updated_at:
        raise ValueError("判定已被修订，请刷新后重试。")

    changes = _parse_changes(result.get("affected_attributes", []), subdimension_service.child_name_set(db, user))
    # v1.10（M2）：豁免券同样作用于补充重判（同一插入点，保证重判前后语义一致）
    changes, exemption_hit = _apply_exemption(db, user, event, changes)

    judgment.suggested_changes = changes
    judgment.analysis = result.get("analysis", [])  # v1.1：补充重判同样记录分析过程
    summary = str(result.get("summary", ""))
    if config.quality_note:
        summary = (summary + "\n" + config.quality_note).strip()
    if exemption_hit:
        summary = (summary + "\n" + _exemption_note(exemption_hit)).strip()
    judgment.summary = summary
    judgment.confidence = _parse_confidence(result.get("confidence"))
    judgment.confidence_reason = str(result.get("confidence_reason", ""))  # v1.4：补充重判后同步更新
    judgment.revision_notes = _parse_revision_notes(result.get("revision_notes"))  # v1.6：本次修订说明
    judgment.merged_with = _parse_merged_with(result.get("merged_with"))  # v1.7
    from app.services import ai_context
    judgment.source_snapshot=ai_context.sources()
    judgment.model_provenance = provenance(config)
    judgment.status = "adjusted"
    _log(
        db, judgment.id, user.id, "rejudge",
        detail="补充信息后重新判定",
        payload={
            "suggested_changes": changes,
            "analysis": judgment.analysis,
            "revision_notes": judgment.revision_notes,
            "merged_with": judgment.merged_with,  # v1.7
            "exemption": exemption_hit,  # v1.10 M2
        },
    )
    if commit_result:
        db.commit()
    else:
        db.flush()
    db.refresh(judgment)
    return judgment


# ============ 反驳复核 ============

@rollback_on_error
@model_context
def dispute(db: Session, judgment: AIJudgment, detail: str, *, before_write=None, commit_result=True) -> dict:
    """用户反驳，AI 依据事实复核（客观，不迎合）。

    返回 {judgment, result}：result 含 conclusion/explanation/confidence。
    """
    _require_reviewable(db, judgment)
    user = get_or_create_default_user(db)
    _log(db, judgment.id, user.id, "dispute", detail=detail, payload={"detail": detail})

    event = db.get(Event, judgment.event_id)
    if event is None or event.is_deleted:
        raise ValueError("事件不存在或已删除。")
    anchors_text = format_anchors_text(db)
    messages = prompts.build_dispute_messages(
        anchors_text=anchors_text,
        event_description=format_event_description(event, item_context_text(db, event)),  # v1.7：带项目上下文
        original_judgment=_prior_snapshot(judgment,db),
        dispute_reason=detail,
    )
    # v1.4：按用户解析判定模型配置（BYOK）
    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_JUDGE)
    version = _event_version(event)
    prior_updated_at = judgment.updated_at
    db.commit()
    result = llm_service.chat_json(messages, config=config)
    if before_write:
        before_write(db)
    event = _lock_event(db, event.id, user.id, version)
    llm_config.assert_current(db, config)
    _require_reviewable(db, judgment)
    if judgment.updated_at != prior_updated_at:
        raise ValueError("判定已被修订，请刷新后重试。")

    conclusion = str(result.get("conclusion", "maintain"))
    notes = _parse_revision_notes(result.get("revision_notes"))  # v1.6：本次修订说明
    merged = _parse_merged_with(result.get("merged_with"))  # v1.7：跨来源合并明细
    explanation = str(result.get("explanation", ""))

    if conclusion == "adjust":
        changes = _parse_changes(
            result.get("affected_attributes", []),
            subdimension_service.child_name_set(db, user),  # v1.10 M3：子维度名合法
        )
        # v1.10（M2）：豁免券同样作用于反驳复核（同一插入点）
        changes, exemption_hit = _apply_exemption(db, user, event, changes)
        if changes:  # 仅在模型给出有效调整结果时覆盖
            judgment.suggested_changes = changes
            judgment.summary = explanation or judgment.summary
            if exemption_hit:
                judgment.summary = (judgment.summary + "\n" + _exemption_note(exemption_hit)).strip()
            judgment.revision_notes = notes  # v1.6
            judgment.merged_with = merged  # v1.7
            judgment.status = "adjusted"
        else:
            conclusion = "maintain"  # 无有效调整，保守维持原判
    from app.services import ai_context
    judgment.source_snapshot=ai_context.sources()
    judgment.model_provenance = provenance(config)
    if conclusion == "maintain":
        # v1.6：维持原判时也用修订说明承载"维持原判的理由"
        judgment.revision_notes = notes or ([f"维持原判：{explanation}"] if explanation else [])
        if merged:
            judgment.merged_with = merged  # v1.7：维持原判也可能补充合并说明

    if conclusion == "adjust":
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

    judgment.confidence = _parse_confidence(result.get("confidence"))
    if commit_result:
        db.commit()
    else:
        db.flush()
    db.refresh(judgment)
    return {
        "judgment": judgment,
        "conclusion": conclusion,
        "explanation": str(result.get("explanation", "")),
    }


# ============ 事件删除（误提交兜底，v1.1） ============

@rollback_on_error
def delete_event(db: Session, event: Event, *, commit: bool = True) -> None:
    """逻辑删除；按真实入账流水反向记账，审计和金币完整保留。"""
    user = get_or_create_default_user(db)
    lock_profile(db, user.id)
    from app.models import Challenge
    active = db.query(Challenge).filter(Challenge.user_id == user.id,
        Challenge.event_id == event.id, Challenge.status == "accepted").with_for_update().first()
    if active is not None:
        raise ValueError("该记录关联待结算挑战，请前往挑战页结算或放弃后再删除。")
    claimed = db.query(Event).filter(Event.id == event.id, Event.user_id == user.id,
        Event.is_deleted.is_(False)).update({Event.is_deleted: True}, synchronize_session=False)
    if claimed != 1:
        raise ValueError("事件已删除或不存在。")
    db.refresh(event)
    judgments = db.query(AIJudgment).filter(AIJudgment.event_id == event.id,
                                           AIJudgment.user_id == user.id).order_by((AIJudgment.status == "invalidated").asc(), AIJudgment.id.desc()).populate_existing().all()
    from app.models.workflow import EventFact,FactSettlement
    from app.models.full_system import FactFragment
    referenced={r.fact_id for r in db.query(EventFact).filter_by(event_id=event.id).all()}|{r.fact_id for r in db.query(FactFragment).filter_by(event_id=event.id).all()}
    # A canonical booking may originate in an already withdrawn diary. The last
    # surviving source reverses its points once; a shared live source preserves them.
    canonical=db.query(AIJudgment).join(FactSettlement,FactSettlement.judgment_id==AIJudgment.id).filter(FactSettlement.fact_id.in_(referenced),AIJudgment.status=='confirmed').all()
    judgments=list({j.id:j for j in [*judgments,*canonical]}.values());retained=set()
    for settlement in db.query(FactSettlement).filter(FactSettlement.judgment_id.in_([j.id for j in judgments])).all():
        other_fragment=db.query(FactFragment.id).join(Event,Event.id==FactFragment.event_id).filter(FactFragment.fact_id==settlement.fact_id,Event.id!=event.id,Event.is_deleted.is_(False)).first()
        other_event=db.query(EventFact.id).join(Event,Event.id==EventFact.event_id).filter(EventFact.fact_id==settlement.fact_id,Event.id!=event.id,Event.is_deleted.is_(False)).first()
        if other_fragment or other_event:retained.add(settlement.judgment_id)
    histories = db.query(AttributeHistory).filter(AttributeHistory.user_id == user.id,
        AttributeHistory.judgment_id.in_([j.id for j in judgments if j.id not in retained and j.status!='deleted'])).all()
    totals = {}
    for h in histories:
        totals[h.attribute_id] = totals.get(h.attribute_id, 0.0) + h.delta
    reversed_changes = []
    for attr_id, delta in totals.items():
        attr = db.query(Attribute).filter(Attribute.id == attr_id, Attribute.user_id == user.id).populate_existing().one()
        before = attr.current_value
        after = round(_clamp_attribute_value(before - delta, attr.max_value), 2)
        actual = round(after - before, 2)
        if actual:
            attr.current_value = after
            db.add(AttributeHistory(user_id=user.id, attribute_id=attr.id, event_id=event.id,
                judgment_id=None, delta=actual, value_after=after,
                reason=f"事件删除回滚（event_id={event.id}）", evidence="按原始真实流水反向并夹取。"))
            reversed_changes.append({"attribute_id": attr.id, "name": attr.name, "delta": actual})
    for judgment in judgments:
        if judgment.id not in retained:judgment.status = "deleted"
        _log(db, judgment.id, user.id, "delete", detail=f"删除事件（event_id={event.id}）",
             payload={"source_history_ids": [h.id for h in histories], "reversed_changes": reversed_changes,'withdrawn_source_id':event.id,'shared_booking_retained':judgment.id in retained,
                      "coins_rolled_back": False, "coins_note": "日常/成就/挑战金币不随事件删除回滚"})
    if commit:
        db.commit()
