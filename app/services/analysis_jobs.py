"""至少一次领取、有限供应商预算、租约防迟到写回；不自动发放属性或金币。"""
import hashlib
import json
import secrets
import threading
from datetime import timedelta, datetime
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import or_, text
from app.models import Event, AIJudgment, User
from app.models.access import LLMCredential
from app.models.analysis import AnalysisJob
from app.services.time_service import utc_now, USER_ZONE
from app.services.transactions import lock_profile
from app.services import judge_service, llm_config, memory_service
from app.services.llm_service import LLMError

ACTIVE = ("queued", "running")
_claim_lock = threading.Lock()


def configuration(db, user_id):
    result={str(r.id):r.config_version for r in db.query(LLMCredential).filter_by(user_id=user_id).populate_existing().all()}
    from app.config import settings
    if not settings.cloud:
        from app.models import Setting
        for row in db.query(Setting).filter(Setting.user_id==user_id,Setting.key.in_(('llm_primary','llm_aux'))).populate_existing().all():
            result[row.key]=row.value.get('config_version',0) if isinstance(row.value,dict) else 0
    from app.models.policies import AIPreference,HostedAI
    pref=db.query(AIPreference).filter_by(user_id=user_id).populate_existing().first()
    if pref:
        result['_preference']=pref.version
        if pref.mode=='hosted':
            hosted=db.query(HostedAI).filter_by(id=1).populate_existing().first();result['_hosted']=hosted.version if hosted else 0
            if hosted and hosted.enabled:
                from app.services.hosted_ai import read_secret
                result['_hosted_secret']=hashlib.sha256(read_secret(hosted.payload).encode()).hexdigest()
    return result


def judgment_version(judgment):
    return judgment.updated_at.isoformat() if judgment and judgment.updated_at else ""


def output(job):
    return {name: getattr(job, name) for name in ("id", "event_id", "event_version", "operation", "state", "attempts",
        "safe_error_code", "result", "created_at", "updated_at")}


def submit(db, user, event, body):
    lock_profile(db, user.id)
    db.refresh(event)
    payload = body.model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    key = str(body.request_key)
    existing = db.query(AnalysisJob).filter_by(user_id=user.id, request_key=key).first()
    if existing:
        if existing.payload_hash != fingerprint:
            raise HTTPException(409, "同一请求标识对应不同分析内容。")
        return existing
    if event.is_deleted or event.content_version != body.event_version:
        raise HTTPException(409, "记录版本已变化。")
    from app.services import ai_context
    ai_context.require(event)
    if event.record_kind == 'diary' and body.operation!='facts':raise HTTPException(409,'日记请使用逐事实分析或独立回顾。')
    if event.is_pure or event.origin == "challenge":
        raise HTTPException(409, "纯享记录不分析；挑战请使用挑战页。")
    current = db.query(AIJudgment).filter_by(event_id=event.id).filter(
        AIJudgment.status.in_(("pending", "adjusted", "confirmed"))).order_by(AIJudgment.id.desc()).first()
    if current and current.status == "confirmed" and body.operation!='facts':
        raise HTTPException(409, "已入账结果冻结。")
    if body.operation in ("supplement", "dispute") and not current:
        raise HTTPException(409, "请先分析记录，再补充或复核。")
    if body.operation in ("supplement", "dispute") and not body.detail.strip():
        raise HTTPException(422, "请填写补充或复核内容。")
    active = db.query(AnalysisJob).filter_by(event_id=event.id).filter(AnalysisJob.state.in_(ACTIVE)).first()
    if active:
        if body.question_job_id is not None:
            raise HTTPException(409, "该问题已提交回答，请读取最新分析。")
        if (active.operation, active.detail, active.event_version) != (body.operation, body.detail, body.event_version):
            raise HTTPException(409, "该记录已有另一项分析，请等待或取消。")
        return active
    latest = db.query(AnalysisJob).filter_by(event_id=event.id).order_by(AnalysisJob.id.desc()).first()
    if body.detail.strip() and latest and latest.state == 'needs_input' and body.question_job_id != latest.id:
        raise HTTPException(409, "问题已变化，请读取最新问题后保留回答并重新提交。")
    if body.question_job_id is not None and (not latest or body.question_job_id != latest.id):
        raise HTTPException(409, "该问题已有新的回答或分析，请读取最新结果。")
    if current and body.operation!='facts' and (body.detail.strip() or body.judgment_version is not None):
        try: matches = datetime.fromisoformat(body.judgment_version or '') == current.updated_at
        except ValueError: matches = False
        if not matches: raise HTTPException(409, "判定已更新，请读取最新结果后重新提交。")
    try:
        llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_JUDGE)
    except LLMError as exc:
        raise HTTPException(422, str(exc)) from None
    job = AnalysisJob(user_id=user.id, event_id=event.id, event_version=event.content_version,
        permission_version=event.ai_permission_version,
        judgment_id=current.id if current and body.operation!='facts' else None, judgment_version=judgment_version(current) if body.operation!='facts' else '',
        request_key=key, payload_hash=fingerprint, operation=body.operation, detail=body.detail,
        config_version=configuration(db, user.id), state="queued")
    db.add(job)
    db.commit()
    return job


def claim(factory):
    with _claim_lock, factory() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(61111200)"))
        now = utc_now()
        expired = db.query(AnalysisJob).filter(AnalysisJob.state == "running", AnalysisJob.lease_until < now).all()
        for job in expired:
            job.state = "queued" if job.attempts < 2 else "failed"
            job.safe_error_code = "LEASE_EXPIRED"
            job.lease_token = None
        db.flush()
        if db.query(AnalysisJob.id).filter(AnalysisJob.state == "running", AnalysisJob.lease_until > now).first():
            db.commit(); return None
        job = db.query(AnalysisJob).filter(AnalysisJob.state == "queued",
            or_(AnalysisJob.next_retry_at.is_(None), AnalysisJob.next_retry_at <= now)).order_by(AnalysisJob.id).with_for_update(skip_locked=True).first()
        if not job:
            db.commit(); return None
        job.state = "running"
        job.lease_token = secrets.token_hex(24)
        job.lease_until = now + timedelta(seconds=240)
        result = (job.id, job.lease_token, job.user_id)
        db.commit()
        return result


def process(factory, claimed):
    job_id, token, user_id = claimed
    with factory() as db:
        user = db.get(User, user_id)
        db.info["user_id"] = user_id
        db.info['analysis_job_id']=job_id
        USER_ZONE.set(user.timezone)
        job = db.get(AnalysisJob, job_id)
        event = db.get(Event, job.event_id)

        def validate(session):
            lock_profile(session, user_id)
            current_job = session.query(AnalysisJob).filter_by(id=job_id).populate_existing().with_for_update().one()
            session.refresh(user)
            if user.status!='active':raise ValueError('TASK_SUPERSEDED')
            session.refresh(event)
            if (current_job.state != "running" or current_job.lease_token != token or current_job.lease_until < utc_now()
                or event.is_deleted or event.content_version != current_job.event_version
                or event.ai_permission!='allowed' or event.ai_permission_version!=current_job.permission_version
                or configuration(session, user_id) != current_job.config_version):
                raise ValueError("TASK_SUPERSEDED")
            current_judgment = session.get(AIJudgment, current_job.judgment_id) if current_job.judgment_id else None
            if current_judgment and (current_judgment.status == "confirmed" or judgment_version(current_judgment) != current_job.judgment_version):
                raise ValueError("TASK_SUPERSEDED")

        def reserve():
            with factory() as counter:
                changed = counter.query(AnalysisJob).filter(AnalysisJob.id == job_id,
                    AnalysisJob.lease_token == token, AnalysisJob.state == "running", AnalysisJob.attempts < 2,
                    AnalysisJob.lease_until > utc_now()).update({AnalysisJob.attempts: AnalysisJob.attempts + 1}, synchronize_session=False)
                if changed != 1:
                    counter.rollback(); raise LLMError("MODEL_ATTEMPT_LIMIT")
                counter.commit()

        from app.services.llm_service import CALL_GUARD, USAGE_FACTORY
        guard_token = CALL_GUARD.set(reserve)
        factory_token = USAGE_FACTORY.set(factory)
        try:
            validate(db)
            db.commit()
            if job.operation == 'review':
                from app.services.diary_review import generate
                generate(db,job,validate)
                return
            if job.operation=='facts':
                from app.services.fact_analysis import generate
                generate(db,job,validate)
                return
            if job.operation == "judge":
                judgment = judge_service.judge_event(db, event, clarification=job.detail,
                    before_write=validate, commit_result=False)
            else:
                judgment = db.get(AIJudgment, job.judgment_id)
                function = judge_service.supplement if job.operation == "supplement" else judge_service.dispute
                result = function(db, judgment, job.detail, before_write=validate, commit_result=False)
                if isinstance(result, dict): judgment = result["judgment"]
            job.state = "ready"
            job.result = {"judgment_id": judgment.id, "confidence": judgment.confidence}
            job.safe_error_code = ""
            job.lease_token = None
            from app.models.access import EventDerivation
            db.add(EventDerivation(user_id=user_id, event_id=event.id, event_version=event.content_version,
                kind='judgment', payload={'judgment_id':judgment.id},
                provenance={'job_id':job_id,'operation':job.operation,'rule_version':'legacy-v1.11'}))
            db.commit()  # 建议、日志和任务终态一起提交。
        except Exception as exc:
            db.rollback()
            job = db.query(AnalysisJob).filter_by(id=job_id, state="running", lease_token=token).first()
            if job is None: return
            if isinstance(exc, judge_service.ClarifyNeededError):
                job.state = "needs_input"
                job.result = {"questions": [str(q)[:1000] for q in exc.questions]}
            elif isinstance(exc, ValueError):
                rejected = str(exc) == 'MODEL_FACT_REJECTED'
                job.state = 'failed' if rejected else 'superseded'
                job.safe_error_code = 'MODEL_FACT_REJECTED' if rejected else 'INPUT_CHANGED'
            else:
                code = str(exc).split("：",1)[0] if isinstance(exc, LLMError) else "ANALYSIS_FAILED"
                allowed = {"MODEL_TIMEOUT", "MODEL_UNAVAILABLE", "MODEL_RATE_LIMITED", "MODEL_AUTH_FAILED", "MODEL_BALANCE_INSUFFICIENT", "MODEL_ATTEMPT_LIMIT", "MODEL_NOT_CONFIGURED", "MODEL_DAILY_LIMIT", "MODEL_BUSY", "MODEL_INVALID_RESPONSE", "MODEL_DISABLED", "MODEL_INPUT_LIMIT", "MODEL_SERVICE_ERROR", "MODEL_NOT_FOUND"}
                job.safe_error_code = code if code in allowed else "ANALYSIS_FAILED"
                job.state = "queued" if code in ("MODEL_UNAVAILABLE", "MODEL_RATE_LIMITED", "MODEL_BUSY") and job.attempts < 2 else "failed"
                job.next_retry_at = utc_now() + timedelta(seconds=30)
            job.lease_token = None
            db.commit()
        finally:
            CALL_GUARD.reset(guard_token)
            USAGE_FACTORY.reset(factory_token)
