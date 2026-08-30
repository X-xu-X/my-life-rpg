"""事件路由：打卡录入（双通道）+ 触发判定。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event
from app.schemas import EventCreate, EventOut
from app.services import judge_service
from app.services.llm_service import LLMError
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.post("/events", response_model=EventOut)
def create_event(body: EventCreate, db: Session = Depends(get_db)):
    """录入事件。source=form 走结构化参数，source=journal 走日记原文。"""
    user = get_or_create_default_user(db)
    event = Event(
        user_id=user.id,
        event_type=body.event_type,
        category=body.category,
        source=body.source,
        title=body.title,
        params=body.params,
        content=body.content,
        occurred_at=body.occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    """事件列表（按创建时间倒序）。"""
    user = get_or_create_default_user(db)
    return (
        db.query(Event)
        .filter(Event.user_id == user.id)
        .order_by(Event.created_at.desc())
        .all()
    )


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
