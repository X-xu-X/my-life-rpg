"""事件路由：打卡录入（双通道）+ 触发判定。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event
from app.schemas import EventCreate, EventOut
from app import prompts
from app.services import judge_service
from app.services.llm_service import LLMError, llm_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.post("/events", response_model=EventOut)
def create_event(body: EventCreate, db: Session = Depends(get_db)):
    """录入事件。source=form 走结构化参数，source=journal 走日记原文（AI 提取要素）。

    is_pure=True 时为「纯享记录」：跳过 AI 要素提取与判定，仅保留原始记录。
    """
    user = get_or_create_default_user(db)

    event_type = body.event_type
    category = body.category
    title = body.title
    params = body.params

    # 自由日记：AI 从原文提取结构化要素（纯享记录跳过提取）
    if not body.is_pure and body.source == "journal" and body.content:
        try:
            result = llm_service.chat_json(prompts.build_extract_messages(body.content))
        except LLMError as exc:
            raise HTTPException(status_code=503, detail=f"日记要素提取失败：{exc}")
        event_type = result.get("event_type") or "positive"
        category = result.get("category") or body.category or "其他"
        title = result.get("title") or body.title or "自由日记"
        params = result.get("params") or {}

    # 纯享记录：直接以正文为内容，类型用默认值，不强制分类
    if body.is_pure:
        event_type = event_type or "positive"
        title = title or "纯享记录"
        category = category or "生活"

    # 兜底：结构化打卡未指定类型时报错；日记提取失败给默认值
    if not event_type:
        if body.source == "form":
            raise HTTPException(status_code=400, detail="结构化打卡必须指定事件类型")
        event_type = "positive"

    event = Event(
        user_id=user.id,
        event_type=event_type,
        category=category,
        source=body.source,
        title=title,
        params=params,
        content=body.content,
        is_pure=body.is_pure,
        occurred_at=body.occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db), pure: bool | None = None):
    """事件列表（按创建时间倒序）。pure=True 只看纯享记录，pure=False 只看判定记录，缺省全量。"""
    user = get_or_create_default_user(db)
    query = db.query(Event).filter(Event.user_id == user.id)
    if pure is not None:
        query = query.filter(Event.is_pure == pure)
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
def judge(event_id: int, db: Session = Depends(get_db)):
    """触发 AI 判定，生成 pending 判定记录。"""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    try:
        judgment = judge_service.judge_event(db, event)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {
        "judgment_id": judgment.id,
        "status": judgment.status,
        "suggested_changes": judgment.suggested_changes,
        "analysis": judgment.analysis,
        "summary": judgment.summary,
        "confidence": judgment.confidence,
    }


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    """删除事件（误提交兜底）：含已入账点数回滚与审计留痕（PRD 4.3）。"""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    judge_service.delete_event(db, event)
    return {"status": "deleted", "event_id": event_id}
