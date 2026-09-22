"""事件路由：打卡录入（双通道）+ 触发判定。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIJudgment, CheckinItem, Event
from app.schemas import EventCreate, EventOut, EventUpdate, JudgeIn
from app import prompts
from app.services import judge_service, llm_config
from app.services.judge_service import ClarifyNeededError
from app.services.llm_service import LLMError, llm_service
from app.services.user_service import get_or_create_default_user

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

    # 自由日记：AI 从原文提取结构化要素（纯享记录跳过提取）
    if not body.is_pure and body.source == "journal" and body.content:
        try:
            # v1.4：走判定模型组（judge）
            config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_JUDGE)
            result = llm_service.chat_json(prompts.build_extract_messages(body.content), config=config)
        except LLMError as exc:
            raise HTTPException(status_code=503, detail=f"日记要素提取失败：{exc}")
        event_type = result.get("event_type") or "positive"
        category = result.get("category") or body.category or "其他"
        title = result.get("title") or body.title or "自由日记"
        params = result.get("params") or {}

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
        occurred_at=body.occurred_at or datetime.now(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/events", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    pure: bool | None = None,
    q: str = "",
    date: str = "",
):
    """事件列表（按创建时间倒序）。支持：pure 纯享过滤、q 关键词（标题/内容/类别）、date 日期（YYYY-MM-DD）。"""
    user = get_or_create_default_user(db)
    query = db.query(Event).filter(Event.user_id == user.id)
    if pure is not None:
        query = query.filter(Event.is_pure == pure)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Event.title.like(like), Event.content.like(like), Event.category.like(like)))
    if date:
        query = query.filter(Event.created_at.like(f"{date}%"))
    return query.order_by(Event.created_at.desc()).all()


@router.get("/events/heatmap")
def get_heatmap(db: Session = Depends(get_db)):
    """月度活动热力图数据：最近 365 天每天的事件数。"""
    user = get_or_create_default_user(db)
    start = datetime.now() - timedelta(days=365)
    rows = (
        db.query(Event.created_at)
        .filter(Event.user_id == user.id, Event.created_at >= start)
        .all()
    )
    counts: dict[str, int] = {}
    for (created_at,) in rows:
        day = created_at.strftime("%Y-%m-%d")
        counts[day] = counts.get(day, 0) + 1
    return [{"date": day, "count": cnt} for day, cnt in sorted(counts.items())]


@router.post("/events/{event_id}/judge")
def judge(event_id: int, body: JudgeIn, db: Session = Depends(get_db)):
    """触发 AI 判定，生成 pending 判定记录。

    信息不足（needs_clarify）时返回追问问题；用户补充回答后带 clarification 重新判定。
    """
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    try:
        judgment = judge_service.judge_event(db, event, clarification=body.clarification)
    except ClarifyNeededError as exc:
        return {"status": "clarify", "needs_clarify": True, "questions": exc.questions}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
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
    }


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """获取单个事件详情（供编辑回填）。"""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return event


@router.put("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventUpdate, db: Session = Depends(get_db)):
    """编辑事件。未确认的判定（pending/adjusted）作废归档（内容变了旧判定不再可信）；
    已入账判定保留。v1.5 A1：作废不物理删除（status=invalidated + 审计记 invalidate），审计只增不删。"""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(event, k, v)
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
def delete_event(event_id: int, db: Session = Depends(get_db)):
    """删除事件（误提交兜底）：含已入账点数回滚与审计留痕（PRD 4.3）。"""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    judge_service.delete_event(db, event)
    return {"status": "deleted", "event_id": event_id}
