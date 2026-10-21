"""Fresh per-round authorized sources; plan/checklist metadata carries no raw text."""
from datetime import date
from app.models import Event
from app.models.workflow import PlanOccurrence,LifeChecklist
from app.services.time_service import date_range


def capture(db,diary):
    day=diary.occurred_on;start,end=date_range(date.fromisoformat(day),diary.timezone_at_capture)
    events=db.query(Event).filter(Event.user_id==diary.user_id,Event.ai_permission=='allowed',Event.is_deleted.is_(False),Event.is_pure.is_(False),Event.occurred_at>=start,Event.occurred_at<end).order_by(Event.id).all()
    sources=[{'id':e.id,'version':e.content_version,'permission_version':e.ai_permission_version,'kind':e.record_kind or 'legacy_unknown','content':e.content} for e in events]
    plans=[{'id':p.id,'schedule_id':p.schedule_id,'version':p.version,'outcome':p.outcome,'event_id':p.event_id,
        'actual':p.facts.get('actual'),'unit':p.facts.get('unit') if p.facts.get('unit') in ('分钟','小时','次','页','公里','米','个','组','字','天','') else '自定单位'} for p in db.query(PlanOccurrence).filter_by(user_id=diary.user_id,local_date=day).all()]
    checklist=db.query(LifeChecklist).filter_by(user_id=diary.user_id,local_date=day).first()
    from app.models.full_system import CareConfig,CareItem,CareEntry
    from app.routers.care import due
    config=db.query(CareConfig).filter_by(user_id=diary.user_id).first()
    focused=[{'id':i.id,'version':i.version,'name':i.name} for i in db.query(CareItem).filter_by(user_id=diary.user_id).all() if config and config.enabled and config.ai_allowed and due(i,date.fromisoformat(day))]
    entries=[{'item_id':e.item_id,'version':e.version,'state':e.state,'event_id':e.event_id} for e in db.query(CareEntry).filter_by(user_id=diary.user_id,local_date=day).all()]
    # Legacy map keys are arbitrary user text, not anonymous status metadata.
    # Only explicitly mapped, currently permitted CareItems may expose names above.
    legacy=None
    if checklist:
        states=list(checklist.payload.get('entries',{}).values())
        legacy={'id':checklist.id,'version':checklist.version,'enabled':bool(checklist.payload.get('enabled')),
            'counts':{state:states.count(state) for state in ('recorded','skipped','not_recorded')}}
    from app.services.personal_context import background
    from app.services.ai_context import CURRENT
    purpose=(CURRENT.get() or {}).get('purpose','review')
    return {'sources':sources,'plans':plans,'checklist':legacy,'focus_items':focused,'care_entries':entries,'personal_background':background(db,diary.user_id,purpose)}
