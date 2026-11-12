from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event, AIJudgment
from app.models.analysis import AnalysisJob
from app.models.full_system import FactBundle
from app.services import analysis_jobs
from app.services.user_service import get_or_create_default_user
from app.services.transactions import lock_profile

router = APIRouter()


class JobIn(BaseModel):
    request_key: UUID
    event_version: int = Field(ge=1)
    operation: Literal["judge", "supplement", "dispute",'facts'] = "judge"
    detail: str = Field("", max_length=20000)
    question_job_id: int | None = None
    judgment_version: str | None = None


def owned(db, model, id):
    user = get_or_create_default_user(db)
    row = db.get(model, id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "资源不存在。")
    return user, row


@router.post("/events/{event_id}/analysis-jobs", status_code=202)
def submit(event_id: int, body: JobIn, db: Session = Depends(get_db)):
    user, event = owned(db, Event, event_id)
    return analysis_jobs.output(analysis_jobs.submit(db, user, event, body))


@router.get("/analysis-jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    _, job = owned(db, AnalysisJob, job_id)
    return analysis_jobs.output(job)


@router.post("/analysis-jobs/{job_id}/cancel")
def cancel(job_id: int, db: Session = Depends(get_db)):
    user, job = owned(db, AnalysisJob, job_id)
    lock_profile(db, user.id)
    db.refresh(job)
    if job.state in analysis_jobs.ACTIVE:
        job.state = "cancelled"
        job.lease_token = None
    db.commit()
    return analysis_jobs.output(job)


@router.post("/analysis-jobs/{job_id}/retry", status_code=202)
def retry(job_id: int, body: JobIn, db: Session = Depends(get_db)):
    user, job = owned(db, AnalysisJob, job_id)
    event = db.get(Event, job.event_id)
    if job.state in analysis_jobs.ACTIVE:
        return analysis_jobs.output(job)
    return analysis_jobs.output(analysis_jobs.submit(db, user, event, body))


@router.get('/events/{event_id}/analysis-jobs')
def event_jobs(event_id:int,db:Session=Depends(get_db)):
    user,event=owned(db,Event,event_id)
    return {'items':[analysis_jobs.output(j) for j in db.query(AnalysisJob).filter_by(event_id=event.id,user_id=user.id).order_by(AnalysisJob.id.desc()).limit(20).all()]}


@router.get("/pending")
def pending(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    events = db.query(Event).filter(Event.user_id == user.id, Event.ai_permission=='allowed',Event.is_deleted.is_(False), Event.is_pure.is_(False), Event.origin.is_(None)).order_by(Event.id.desc()).all()
    result = []
    for event in events:
        job = db.query(AnalysisJob).filter_by(event_id=event.id, user_id=user.id).filter(AnalysisJob.operation != 'review').order_by(AnalysisJob.id.desc()).first()
        bundle = db.query(FactBundle).filter_by(event_id=event.id, user_id=user.id,
            event_version=event.content_version, permission_version=event.ai_permission_version).order_by(FactBundle.id.desc()).first()
        if event.record_kind in ('event', 'diary') and (bundle or job and job.operation == 'facts' or event.record_kind == 'diary'):
            # A confirmed zero-award bundle has no confirmed AIJudgment. The bundle
            # itself is authoritative; a later deliberate analysis remains pending.
            if bundle and bundle.state == 'confirmed' and (not job or
                job.state == 'ready' and (job.result or {}).get('bundle_id') == bundle.id):
                continue
            if event.analysis_intent == 'never' and not bundle and not job: continue
            state = job.state if job else 'saved'
            if bundle and (not job or job.state == 'ready'):
                # Relation review is optional; only insufficient evidence keeps this pending.
                state = 'needs_input' if any(i.get('confidence', 0) < .8
                    for i in bundle.payload.get('items', [])) else 'ready'
            result.append({'event_id': event.id, 'event_version': event.content_version,
                'title': event.title, 'content': event.content, 'state': state, 'judgment_id': None,
                'job': analysis_jobs.output(job) if job else None})
            continue
        judgment = db.query(AIJudgment).filter_by(event_id=event.id).filter(
            AIJudgment.status.in_(("pending", "adjusted", "confirmed"))).order_by(AIJudgment.id.desc()).first()
        if judgment and judgment.status == "confirmed": continue
        job = db.query(AnalysisJob).filter_by(event_id=event.id).order_by(AnalysisJob.id.desc()).first()
        if event.analysis_intent == "never" and not judgment and not job: continue
        state = job.state if job else "saved"
        if judgment and (not job or job.state == "ready"):
            state = "needs_input" if judgment.confidence < 0.8 else "ready"
        result.append({"event_id":event.id, "event_version":event.content_version,
            "title":event.title, "content":event.content, "state":state,
            "judgment_id":judgment.id if judgment else None,
            "job":analysis_jobs.output(job) if job else None})
    return {"items":result}
