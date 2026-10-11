"""按当地日关联原记录；手写回顾不创建事件、不发奖、不请求 AI。"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event, AIJudgment
from app.models.analysis import DailyReview, ReviewLink
from app.schemas import EventOut
from app.services.user_service import get_or_create_default_user
from app.services.time_service import date_range
from app.services.transactions import lock_profile

router = APIRouter()


class ReviewIn(BaseModel):
    note: str = Field("", max_length=20000)
    completion: bool = False
    expected_version: int = Field(0, ge=0)
    timezone: str | None = None


def collect(db, user, day, timezone):
    start, end = date_range(day, timezone)
    events = db.query(Event).filter(Event.user_id == user.id, Event.is_deleted.is_(False),
        Event.occurred_at >= start, Event.occurred_at < end).order_by(Event.occurred_at, Event.id).all()
    review = db.query(DailyReview).filter_by(user_id=user.id, local_date=day, timezone=timezone).first()
    return review, events


@router.get('/daily-reviews')
def list_reviews(db: Session = Depends(get_db)):
    user=get_or_create_default_user(db)
    return {'items':[{'id':r.id,'date':r.local_date,'timezone':r.timezone,'version':r.version,
        'completion':r.completion} for r in db.query(DailyReview).filter_by(user_id=user.id)
        .order_by(DailyReview.local_date.desc(),DailyReview.id.desc()).limit(365).all()]}


@router.get("/daily-reviews/{day}")
def get_review(day: date, timezone: str | None = None, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    timezone = timezone or user.timezone
    review, events = collect(db, user, day, timezone)
    return {"date":day, "timezone":timezone, "note":review.note if review else "",
        "completion":bool(review and review.completion), "version":review.version if review else 0,
        "events":[EventOut.model_validate(event) for event in events],
        "judgments":[{"id":j.id,"event_id":j.event_id,"status":j.status,"confidence":j.confidence,"summary":j.summary}
            for j in db.query(AIJudgment).filter(AIJudgment.event_id.in_([event.id for event in events]),
                AIJudgment.status.in_(("pending","adjusted","confirmed"))).all()]}


@router.put("/daily-reviews/{day}")
def put_review(day: date, body: ReviewIn, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    lock_profile(db, user.id)
    timezone = body.timezone or user.timezone
    review, events = collect(db, user, day, timezone)
    if (review.version if review else 0) != body.expected_version:
        db.rollback(); raise HTTPException(409, "回顾已更新，请重新读取。")
    if not review:
        review = DailyReview(user_id=user.id, local_date=day, timezone=timezone, version=0)
        db.add(review)
    review.note = body.note
    review.completion = body.completion
    review.version += 1
    db.flush()
    existing = {link.event_id:link for link in db.query(ReviewLink).filter_by(review_id=review.id).all()}
    for event in events:
        if event.id not in existing:
            db.add(ReviewLink(user_id=user.id, review_id=review.id, event_id=event.id,
                              event_version=event.content_version))
        else:
            existing[event.id].event_version = event.content_version
    db.commit()
    return {"version":review.version,"completion":review.completion}
