"""事件路由：打卡录入（双通道）+ 触发判定。"""
from app.services.time_service import clock_now
from uuid import uuid4
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.access import RequestReceipt
from app.services.transactions import lock_profile
from app.services.time_service import stored_time, date_range
from fastapi.encoders import jsonable_encoder
import hashlib
import json
from datetime import date as Date
from uuid import UUID
from app.models import AttributeHistory, AIJudgment, CheckinItem, Event
from app.schemas import EventCreate, EventOut, EventUpdate, JudgeIn
from app import prompts
from app.services import achievement_service, judge_service, llm_config
from app.services.judge_service import ClarifyNeededError
from app.services.llm_service import LLMError, llm_service
from app.services.user_service import get_or_create_default_user
from app.services import receipts

router = APIRouter()


@router.post("/events", response_model=EventOut)
def create_event(body: EventCreate, db: Session = Depends(get_db)):
    """录入事件。source=form 走打卡项目，source=journal 走日记原文（AI 提取要素）。

    is_pure=True 时为「纯享记录」：跳过 AI 要素提取与判定，仅保留原始记录。

    v1.7 录入改造（决策 3）：打卡通道不再要求 event_type——
    - 传了 item_id → 从打卡项目**派生** category / event_type / title；
    - 未传 item_id（纯自由记一笔）→ event_type="positive"、category 取传入值或"其他"。
    向后兼容：老前端直接传 event_type 时，仍以传入值为准。
    """
    user = get_or_create_default_user(db)

    if settings.cloud and body.client_request_id is None:
        raise HTTPException(422, "保存需要 client_request_id。")
    if not body.content.strip() and not body.title.strip():
        raise HTTPException(422, "请填写记录。")
    request_key = str(body.client_request_id) if body.client_request_id else None
    payload = body.model_dump(mode="json")
    # Keep pre-upgrade pending UUID fingerprints replayable when new fields are absent.
    for name in ('occurred_on', 'time_precision'):
        if name not in body.model_fields_set: payload.pop(name, None)
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if request_key:
        lock_profile(db, user.id)
        prior = db.query(RequestReceipt).filter_by(user_id=user.id, operation="create_event", request_key=request_key).first()
        if prior:
            if prior.payload_hash != payload_hash:
                db.rollback()
                raise HTTPException(409, "同一次提交标识不能用于不同内容。")
            return prior.response_snapshot
    event_type = body.event_type
    category = body.category
    title = body.title
    params = body.params
    item_id = body.item_id

    # v1.7：打卡项目校验 + 派生（传了 item_id 就以其为准）
    item = None
    if item_id is not None:
        item = db.get(CheckinItem, item_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(status_code=404, detail="打卡项目不存在")
        # 从项目派生：类别取项目生活面；负面项目映射为 negative，其余 positive
        category = item.category or category or "其他"
        event_type = "negative" if item.nature == "negative" else "positive"
        # 标题取正文首行（≤40 字），无正文则用项目名
        first_line = (body.content or "").strip().splitlines()
        derived = first_line[0].strip() if first_line else ""
        title = (derived[:40] if derived else item.name) or item.name

    # 兜底：v1.7 起打卡通道不再强制事件类型（决策 3），缺省按正面事件处理
    if not event_type:
        event_type = "positive"
    if not category:
        category = "其他"
    # 标题兜底：无项目、无标题时取正文首行（≤40 字），保证列表可读
    if not title and body.content:
        first_line = body.content.strip().splitlines()
        title = (first_line[0].strip()[:40] if first_line else "") or ""

    # 纯享记录：直接以正文为内容，类型用默认值，不强制分类
    if body.is_pure:
        title = title or "纯享记录"
        category = category or "生活"

    captured_time = stored_time(body.occurred_at, body.timezone)
    captured_on = body.occurred_on
    if body.time_precision == 'date':
        captured_time = date_range(body.occurred_on, body.timezone)[0]  # day-boundary anchor, never a reported clock time
    elif body.time_precision == 'minute':
        from app.services.time_service import local_day
        captured_on = local_day(captured_time, body.timezone)
        if body.occurred_on and captured_on != body.occurred_on:
            raise HTTPException(422, '发生日期与时间不一致。')
    event = Event(
        user_id=user.id,
        event_type=event_type,
        category=category,
        source=body.source,
        title=title,
        params=params,
        content=body.content,
        item_id=item_id,  # v1.7：所属打卡项目（可空）
        is_pure=body.is_pure,
        occurred_at=captured_time, occurred_on=captured_on.isoformat() if captured_on else None,
        time_precision=body.time_precision,
        client_request_id=request_key, content_version=1,
        analysis_intent="never" if body.is_pure else body.intent, timezone_at_capture=body.timezone,
    )
    db.add(event)
    db.flush()
    if request_key:
        db.add(RequestReceipt(user_id=user.id, operation="create_event", request_key=request_key,
            payload_hash=payload_hash, resource_id=event.id,
            response_snapshot=jsonable_encoder(EventOut.model_validate(event))))
    db.commit()
    db.refresh(event)
    return event


@router.get("/events", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    pure: bool | None = None,
    q: str = "",
    date: str = "",
    cursor: int | None = None,
    limit: int = 250,
):
    """事件列表（按创建时间倒序）。支持：pure 纯享过滤、q 关键词（标题/内容/类别）、date 日期（YYYY-MM-DD）。"""
    user = get_or_create_default_user(db)
    query = db.query(Event).filter(Event.user_id == user.id, Event.is_deleted.is_(False))
    if pure is not None:
        query = query.filter(Event.is_pure == pure)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Event.title.like(like), Event.content.like(like), Event.category.like(like)))
    if date:
        try:
            start, end = date_range(Date.fromisoformat(date), user.timezone)
        except ValueError as exc:
            raise HTTPException(422, "日期格式无效。") from exc
        query = query.filter(Event.occurred_at >= start, Event.occurred_at < end)
    if cursor is not None:
        query = query.filter(Event.id < cursor)
    return query.order_by(Event.id.desc()).limit(max(1, min(limit, 500))).all()


@router.get("/events/heatmap")
def get_heatmap(db: Session = Depends(get_db)):
    """月度活动热力图数据：最近 365 天每天的事件数。

    v1.10 P2-2（V3）：口径由 `created_at` 改为 **`occurred_at`（发生日）**——
    补记昨天的事必须落在昨天格子里；`occurred_at` 为 NULL 的老行回落 `created_at`。
    返回结构保持 `[{date, count}]` 不变。
    """
    user = get_or_create_default_user(db)
    start = clock_now() - timedelta(days=365)
    rows = (
        db.query(Event.occurred_at, Event.created_at)
        .filter(Event.user_id == user.id, Event.is_deleted.is_(False), Event.created_at >= start)
        .all()
    )
    counts: dict[str, int] = {}
    for occurred_at, created_at in rows:
        ref = occurred_at or created_at
        if ref is None:
            continue
        from app.services.time_service import local_day
        day = local_day(ref, user.timezone).isoformat()
        counts[day] = counts.get(day, 0) + 1
    return [{"date": day, "count": cnt} for day, cnt in sorted(counts.items())]


@router.post("/events/{event_id}/judge")
def judge(event_id: int, body: JudgeIn, db: Session = Depends(get_db)):
    """触发 AI 判定，生成 pending 判定记录。

    信息不足（needs_clarify）时返回追问问题；用户补充回答后带 clarification 重新判定。
    """
    event = db.get(Event, event_id)
    if event is None or event.is_deleted:
        raise HTTPException(status_code=404, detail="事件不存在")
    try:
        if settings.cloud:
            raise HTTPException(409, "请通过分析任务提交，旧同步入口已关闭。")
        judgment = judge_service.judge_event(db, event, clarification=body.clarification)
    except ClarifyNeededError as exc:
        return {"status": "clarify", "needs_clarify": True, "questions": exc.questions}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    # v1.10 M1：累计型成就顺带检查（写日记/记事件后即可解锁"日记 N 篇/记录 N 条"类成就）
    unlocked: list[dict] = []
    try:
        user = get_or_create_default_user(db)
        for row in ([] if settings.cloud else achievement_service.check_and_grant(db, user)):
            unlocked.append({"code": row.code, "name": row.name, "icon": row.icon,
                             "coin_reward": row.coin_reward})
    except Exception:
        db.rollback()

    return {
        "judgment_id": judgment.id,
        "status": judgment.status,
        "suggested_changes": judgment.suggested_changes,
        "analysis": judgment.analysis,
        "summary": judgment.summary,
        "confidence": judgment.confidence,
        "confidence_reason": judgment.confidence_reason or "",  # v1.4：置信度说明
        "revision_notes": judgment.revision_notes or [],  # v1.6：本次修订说明
        "merged_with": judgment.merged_with or [],  # v1.7：跨来源合并明细
        "unlocked_achievements": unlocked,  # v1.10：本次新解锁的成就
        "achievement_suggestion": judgment.achievement_suggestion or {},  # v1.10：AI 里程碑建议
    }


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """获取单个事件详情（供编辑回填）。"""
    event = db.get(Event, event_id)
    if event is None or event.is_deleted:
        raise HTTPException(status_code=404, detail="事件不存在")
    return event


@router.put("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventUpdate, db: Session = Depends(get_db)):
    """编辑事件。未确认的判定（pending/adjusted）作废归档（内容变了旧判定不再可信）；
    已入账判定保留。v1.5 A1：作废不物理删除（status=invalidated + 审计记 invalidate），审计只增不删。"""
    event = db.get(Event, event_id)
    if event is None or event.is_deleted:
        raise HTTPException(status_code=404, detail="事件不存在")
    try:
        lock_profile(db, event.user_id)
        event = judge_service._lock_event(db, event.id, event.user_id)
        if event.origin == "challenge":
            raise ValueError("挑战记录请在挑战页补充自述。")
        if (db.query(AttributeHistory.id).filter(AttributeHistory.event_id == event.id).first()
                or db.query(AIJudgment.id).filter(AIJudgment.event_id == event.id,
                    AIJudgment.status == "confirmed").first()):
            raise ValueError("事件已入账，不能编辑。如需撤销请删除事件。")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    if settings.cloud and body.expected_version is None:
        db.rollback()
        raise HTTPException(422, "编辑需要 expected_version。")
    if body.expected_version is not None and body.expected_version != event.content_version:
        db.rollback()
        raise HTTPException(409, "记录已更新，请重新读取。")
    from app.models.access import EventDerivation
    db.add(EventDerivation(user_id=event.user_id,event_id=event.id,event_version=event.content_version,
        kind='original_version',payload=jsonable_encoder(EventOut.model_validate(event)),
        provenance={'source':'user_edit'}))
    data = body.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "occurred_at" in data and data["occurred_at"] is not None:
        data["occurred_at"] = stored_time(data["occurred_at"], event.timezone_at_capture)
        data['occurred_on'] = None
        data['time_precision'] = None  # old edit clients never declare precision
    if data.get("item_id") is not None:
        item = db.get(CheckinItem, data["item_id"])
        if item is None or item.user_id != event.user_id:
            db.rollback()
            raise HTTPException(404, "打卡项目不存在。")
    event.content_version += 1
    for k, v in data.items():
        setattr(event, k, v)
    event.params = {**(event.params or {}), "_edit_revision": uuid4().hex}
    # 作废未确认判定：事件内容变化后，旧判定结果不再可信（归档保留，可追溯）
    stale = (
        db.query(AIJudgment)
        .filter(AIJudgment.event_id == event.id, AIJudgment.status.in_(["pending", "adjusted"]))
        .all()
    )
    for j in stale:
        j.status = "invalidated"
        db.flush()
        judge_service._log(
            db, j.id, event.user_id, "invalidate",
            detail="事件被编辑，旧判定作废归档（判定结果不再可信，需重新判定）",
            payload={"event_id": event.id},
        )
    db.commit()
    db.refresh(event)
    return event


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db), body: receipts.MutationIn = receipts.MutationIn()):
    """删除事件（误提交兜底）：含已入账点数回滚与审计留痕（PRD 4.3）。"""
    user = get_or_create_default_user(db)
    lock_profile(db, user.id)
    operation = f"delete_event:{event_id}"
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "事件不存在")
    fingerprint, prior = receipts.replay(db, user.id, operation, body)
    if prior is not None:
        return prior
    if event is None or event.is_deleted:
        raise HTTPException(status_code=404, detail="事件不存在")
    try:
        event = judge_service._lock_event(db, event.id, user.id)
        if body.expected_version is not None and body.expected_version != event.content_version:
            raise ValueError("记录已更新，请重新读取后撤销。")
        judge_service.delete_event(db, event, commit=False)
        result = {"status": "deleted", "event_id": event_id}
        receipts.record(db, user.id, operation, body, fingerprint, event_id, result)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return result


@router.get("/event-submissions/{client_request_id}")
def submission(client_request_id: UUID, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    prior = db.query(RequestReceipt).filter_by(user_id=user.id, operation="create_event", request_key=str(client_request_id)).first()
    if prior is None:
        raise HTTPException(404, "尚未查询到本次提交，请继续使用同一标识重试。")
    return prior.response_snapshot
