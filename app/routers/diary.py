"""Explicit diary drafts, resumable review questions and optional no-reward checklist."""
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event
from app.models.workflow import DiaryRevision, ReviewSession, ReviewTurn, ReviewAnalysis, LifeChecklist
from app.models.analysis import AnalysisJob
from app.services.user_service import get_or_create_default_user
from app.services.time_service import date_range
from app.services.workflow_common import WriteIn, begin, finish, version, fields, get_owned

router = APIRouter()


class DiaryIn(WriteIn):
    content: str = Field(min_length=1, max_length=20000)


class AnswerIn(WriteIn):
    session_version: int
    answer: str = Field('', max_length=10000)
    skip: bool = False


class ChecklistIn(WriteIn):
    enabled: bool = False
    entries: dict[str, str] = Field(default_factory=dict, max_length=20)
    event_ids: list[int] = Field(default_factory=list, max_length=20)


def diary_row(db, user, day):
    return db.query(Event).filter_by(user_id=user.id, diary_key=f'{user.id}:{day}').first()


@router.get('/diaries/{day}')
def get_diary(day: date, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    row = diary_row(db, user, day)
    return {'diary': fields(row) if row else None,
        'revisions': [fields(r) for r in db.query(DiaryRevision).filter_by(event_id=row.id).order_by(DiaryRevision.version).all()] if row else [],
        'sessions': [fields(r) for r in db.query(ReviewSession).filter_by(diary_id=row.id).order_by(ReviewSession.id.desc()).all()] if row else []}


@router.put('/diaries/{day}')
def put_diary(day: date, body: DiaryIn, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    op = f'diary:{day}'
    fingerprint, prior = begin(db, user, op, body)
    if prior is not None: return prior
    row = diary_row(db, user, day)
    if body.expected_version != (row.content_version if row else 0):
        raise HTTPException(409, '日记已更新，请保留原文并比较最新版本。')
    if row and row.is_deleted: raise HTTPException(409, '此日原稿已撤销，仍保留历史，不新建第二篇。')
    if not body.content.strip(): raise HTTPException(422, '请先写下原文。')
    if not row:
        row = Event(user_id=user.id, diary_key=f'{user.id}:{day}', record_kind='diary',
            event_type='positive', source='journal', title=f'{day} 晚间日记', content='',
            occurred_on=str(day), occurred_at=date_range(day,user.timezone)[0], time_precision='date',
            timezone_at_capture=user.timezone, analysis_intent='later', content_version=0)
        db.add(row); db.flush()
    row.content = body.content
    row.content_version += 1
    db.add(DiaryRevision(user_id=user.id, event_id=row.id, version=row.content_version, content=row.content))
    db.flush()
    return finish(db,user,op,body,fingerprint,row,{'diary':fields(row)})


@router.post('/diaries/{day}/review-sessions')
def start_session(day: date, body: WriteIn, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    op = f'review-start:{day}'
    fingerprint, prior = begin(db,user,op,body)
    if prior is not None: return prior
    diary = diary_row(db,user,day)
    if not diary or diary.is_deleted: raise HTTPException(409,'请先保存当日原文。')
    if diary.content_version != body.expected_version: raise HTTPException(409,'原文已变化，请重新读取。')
    row = db.query(ReviewSession).filter_by(diary_id=diary.id,source_version=diary.content_version).first()
    if not row:
        start,end=date_range(day,diary.timezone_at_capture)
        sources=db.query(Event).filter(Event.user_id==user.id,Event.is_deleted.is_(False),Event.occurred_at>=start,Event.occurred_at<end).all()
        row=ReviewSession(user_id=user.id,diary_id=diary.id,source_version=diary.content_version,
            sources=[{'id':e.id,'version':e.content_version,'kind':e.record_kind or 'legacy_unknown','content':e.content} for e in sources])
        db.add(row);db.flush()
    return finish(db,user,op,body,fingerprint,row,fields(row))


@router.get('/review-sessions/{session_id}')
def read_session(session_id: int, db: Session = Depends(get_db)):
    row=get_owned(db,ReviewSession,session_id)
    diary=get_owned(db,Event,row.diary_id)
    return {**fields(row),'source_changed':diary.content_version!=row.source_version or diary.is_deleted,
        'turns':[fields(t) for t in db.query(ReviewTurn).filter_by(session_id=row.id).order_by(ReviewTurn.ordinal).all()],
        'analyses':[fields(a) for a in db.query(ReviewAnalysis).filter_by(session_id=row.id).order_by(ReviewAnalysis.id).all()],
        'jobs':[{'id':j.id,'state':j.state,'safe_error_code':j.safe_error_code} for j in db.query(AnalysisJob).filter_by(review_session_id=row.id).order_by(AnalysisJob.id.desc()).limit(10).all()]}


@router.put('/review-sessions/{session_id}/turns/{turn_id}')
def answer(session_id: int, turn_id: int, body: AnswerIn, db: Session = Depends(get_db)):
    user=get_or_create_default_user(db);op=f'review-answer:{turn_id}'
    fingerprint,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,ReviewSession,session_id);turn=get_owned(db,ReviewTurn,turn_id)
    if turn.session_id!=row.id:raise HTTPException(404,'问题不存在。')
    version(row,body.session_version);version(turn,body.expected_version)
    diary=get_owned(db,Event,row.diary_id)
    if diary.is_deleted or diary.content_version!=row.source_version:raise HTTPException(409,'原文已变化；旧问答保留，请新建回顾。')
    if turn.state!='unanswered' or db.query(AnalysisJob).filter(AnalysisJob.review_session_id==row.id,AnalysisJob.state.in_(('queued','running'))).first():raise HTTPException(409,'问题已处理或分析中，不能覆盖。')
    if not body.skip and not body.answer.strip():raise HTTPException(422,'填写回答或明确跳过。')
    turn.answer='' if body.skip else body.answer;turn.state='skipped' if body.skip else 'answered';turn.version+=1
    row.version+=1;row.state='draft'
    return finish(db,user,op,body,fingerprint,turn,{'version':row.version,'turn':fields(turn)})


@router.post('/review-sessions/{session_id}/analyze')
def analyze(session_id:int,body:WriteIn,db:Session=Depends(get_db)):
    from app.services import analysis_jobs,llm_config
    import hashlib,json
    user=get_or_create_default_user(db);op=f'review-analyze:{session_id}'
    fingerprint,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,ReviewSession,session_id);version(row,body.expected_version)
    diary=get_owned(db,Event,row.diary_id)
    if diary.is_deleted or diary.content_version!=row.source_version:raise HTTPException(409,'原文已变化，请新建回顾。')
    if db.query(AnalysisJob).filter(AnalysisJob.event_id==diary.id,AnalysisJob.state.in_(analysis_jobs.ACTIVE)).first():raise HTTPException(409,'已有活动任务，请等待或取消。')
    from app.services.llm_service import LLMError
    try: llm_config.resolve_llm_config(db,user.id,llm_config.PURPOSE_JUDGE)
    except LLMError as exc: raise HTTPException(422,str(exc)) from None
    job=AnalysisJob(user_id=user.id,event_id=diary.id,event_version=diary.content_version,
        review_session_id=row.id,session_version=row.version,operation='review',request_key=str(body.request_key),
        payload_hash=hashlib.sha256(json.dumps(body.model_dump(mode='json'),sort_keys=True).encode()).hexdigest(),
        config_version=analysis_jobs.configuration(db,user.id),state='queued')
    db.add(job);row.state='running';db.flush()
    return finish(db,user,op,body,fingerprint,job,{'id':job.id,'state':job.state})


@router.get('/life-checklists/{day}')
def get_checklist(day:date,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);row=db.query(LifeChecklist).filter_by(user_id=user.id,local_date=str(day)).first()
    return fields(row) if row else {'version':0,'payload':{'enabled':False,'entries':{},'event_ids':[]}}


@router.put('/life-checklists/{day}')
def put_checklist(day:date,body:ChecklistIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'checklist:{day}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=db.query(LifeChecklist).filter_by(user_id=user.id,local_date=str(day)).first();version(row,body.expected_version)
    if any(v not in ('not_recorded','skipped','recorded') for v in body.entries.values()) or any(len(k)>80 for k in body.entries):raise HTTPException(422,'清单状态无效。')
    for event_id in body.event_ids:get_owned(db,Event,event_id)
    if not row:row=LifeChecklist(user_id=user.id,local_date=str(day),version=0);db.add(row)
    row.version+=1;row.payload={'enabled':body.enabled,'entries':body.entries,'event_ids':body.event_ids}
    db.flush()
    return finish(db,user,op,body,fp,row,fields(row))
