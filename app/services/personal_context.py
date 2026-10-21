"""Purpose-scoped voluntary background, never an alternate attribute baseline."""
from app.models import UserProfile
from app.models.daily_use import PersonalInformation,ReturnCheckin
from app.models.full_system import PersonalPhase
USES=('judge','review','report','pricing')


def background(db,user_id,purpose='judge'):
    profile=db.query(UserProfile).filter_by(user_id=user_id).first()
    value=dict(profile.basic_profile or {}) if profile else {}
    if purpose not in value.get('questionnaire_uses',USES):value.pop('questionnaire',None)
    value.pop('questionnaire_uses',None)
    result={'profile':value}
    phase=db.query(PersonalPhase).filter_by(user_id=user_id).first()
    if phase and phase.payload.get('ai_allowed'):result['phase']={k:phase.payload[k] for k in ('title','preferences','accepted_mode') if k in phase.payload}
    from app.models import Goal
    from app.models.policies import Mainline
    result['current_mainline']=[{'goal_id':g.id,'title':g.description,'deadline':g.deadline.isoformat() if g.deadline else None} for m,g in db.query(Mainline,Goal).join(Goal,Goal.id==Mainline.goal_id).filter(Mainline.user_id==user_id,Mainline.active.is_(True),Goal.status=='active').all()]
    info=db.query(PersonalInformation).filter_by(user_id=user_id).first()
    if info:result['voluntary_information']=[{'id':e['id'],'text':e['text'],'source':'self_report','updated_at':e.get('updated_at')} for e in info.entries if purpose in e['uses']]
    recent=db.query(ReturnCheckin).filter_by(user_id=user_id).first()
    if recent and recent.state=='completed' and purpose in recent.uses:
        result['recent_checkin']={k:v['value'] for k,v in recent.answers.items() if v['state']=='answered'}
    return result
