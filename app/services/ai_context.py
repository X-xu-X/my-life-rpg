"""One server permission boundary for record-derived model inputs and late writes.

Conservative snapshots cover every permitted source available during construction.
Legacy derived data without sources stays visible to its owner but is quarantined
from model inputs. Metadata-only UI and financial identity queries are unaffected.
"""
from contextvars import ContextVar
from functools import wraps
import inspect
import json,hashlib
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models import Event,User
from app.services.time_service import utc_now

CURRENT=ContextVar('record_ai_context',default=None)


def allowed(event):
    return bool(event and not event.is_deleted and not event.is_pure and event.ai_permission=='allowed')


def require(event):
    if not allowed(event):raise HTTPException(409,'此篇仅保存；请先明确开启本篇分析。')


def snapshot(db,user_id):
    return [{'id':e.id,'version':e.content_version,'permission_version':e.ai_permission_version}
        for e in db.query(Event).filter_by(user_id=user_id,ai_permission='allowed',is_deleted=False,is_pure=False).all()]


def valid(db,sources,user_id):
    if not isinstance(sources,list):return False
    for source in sources:
        e=db.query(Event).filter_by(id=source['id'],user_id=user_id).populate_existing().first()
        if not allowed(e) or e.content_version!=source['version'] or e.ai_permission_version!=source['permission_version']:return False
    return True


def assert_current(db=None):
    context=CURRENT.get()
    if not context:return
    if db is None:
        # Outbound checks use a fresh read after business code released its transaction.
        with Session(bind=context['bind']) as fresh:
            if not valid(fresh,context['sources'],context['user_id']) or background(fresh,context['user_id'])!=context['background']:raise ValueError('AI_SOURCES_CHANGED')
    elif not valid(db,context['sources'],context['user_id']) or background(db,context['user_id'])!=context['background']:raise ValueError('AI_SOURCES_CHANGED')


def background(db,user_id):
    from app.models import UserProfile
    from app.models.full_system import PersonalPhase,CareConfig,CareItem
    from app.models.daily_use import PersonalInformation,ReturnCheckin
    profile=db.query(UserProfile).filter_by(user_id=user_id).populate_existing().first()
    phase=db.query(PersonalPhase).filter_by(user_id=user_id).populate_existing().first()
    care=db.query(CareConfig).filter_by(user_id=user_id).populate_existing().first()
    items=[(i.id,i.version) for i in db.query(CareItem).filter_by(user_id=user_id).order_by(CareItem.id).all()]
    voluntary=db.query(PersonalInformation).filter_by(user_id=user_id).populate_existing().first()
    recent=db.query(ReturnCheckin).filter_by(user_id=user_id).populate_existing().first()
    from app.models import Goal
    from app.models.policies import Mainline
    mains=[(m.id,m.version,g.id,g.updated_at.isoformat()) for m,g in db.query(Mainline,Goal).join(Goal,Goal.id==Mainline.goal_id).filter(Mainline.user_id==user_id,Mainline.active.is_(True)).order_by(Mainline.id).all()]
    return hashlib.sha256(json.dumps({'profile':profile.basic_profile if profile else None,'phase_version':phase.version if phase else None,
        'care_version':care.version if care else None,'care_items':items,'information_version':voluntary.version if voluntary else None,'return_version':recent.version if recent else None,'mainlines':mains},sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def sources():
    context=CURRENT.get()
    return context['sources'] if context else None


def model_context(function):
    signature=inspect.signature(function)
    @wraps(function)
    def wrapped(*args,**kwargs):
        bound=signature.bind_partial(*args,**kwargs).arguments;db=bound['db']
        if CURRENT.get() is not None:return function(*args,**kwargs)
        user_id=db.info.get('user_id')
        for name in ('event','judgment','user','job'):
            row=bound.get(name)
            if row is not None:user_id=row.id if isinstance(row,User) else row.user_id
        if user_id is None:
            from app.services.user_service import get_or_create_default_user
            user_id=get_or_create_default_user(db).id
        event=bound.get('event')
        if event is None and bound.get('judgment') is not None:event=db.get(Event,bound['judgment'].event_id)
        if event is None and bound.get('job') is not None:event=db.get(Event,bound['job'].event_id)
        if event is not None:require(event)
        from app.models import Attribute
        supplied=(event.content if event else '')+' '+str(bound.get('note',''))
        safe_children=[a.id for a in db.query(Attribute).filter(Attribute.user_id==user_id,Attribute.parent_id.is_not(None)).all()
            if valid(db,a.ai_sources,user_id) or a.name in supplied]
        module=function.__module__
        purpose='pricing' if 'shop' in module or 'reward_quote' in module else 'report' if 'report' in module else 'review' if 'diary_review' in module else 'judge'
        context={'user_id':user_id,'bind':db.get_bind(),'sources':snapshot(db,user_id),'background':background(db,user_id),'safe_children':safe_children,'purpose':purpose}
        if db.info.get('analysis_job_id'):
            from app.models.analysis import AnalysisJob
            job=db.get(AnalysisJob,db.info['analysis_job_id'])
            job.input_snapshot=[*(job.input_snapshot or [])[-2:],{'sources':context['sources'],'background':context['background'],'purpose':job.operation,
                'permission_version':job.permission_version,'at':utc_now().isoformat()}]
            db.flush()
        token=CURRENT.set(context);previous=db.info.get('ai_only')
        db.info['ai_only']=True
        try:return function(*args,**kwargs)
        finally:
            CURRENT.reset(token)
            if previous is None:db.info.pop('ai_only',None)
            else:db.info['ai_only']=previous
    return wrapped


def change(db,event,permission):
    if event.ai_permission==permission:return
    event.ai_permission=permission;event.ai_permission_version=(event.ai_permission_version or 0)+1
    event.ai_permission_changed_at=utc_now();event.analysis_intent='now' if permission=='allowed' else 'never'
    from app.models.analysis import AnalysisJob
    for job in db.query(AnalysisJob).filter(AnalysisJob.event_id==event.id,AnalysisJob.state.in_(('queued','running'))).all():
        job.state='superseded';job.safe_error_code='PERMISSION_CHANGED';job.lease_token=None
