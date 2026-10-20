from datetime import date,timedelta
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Event
from app.models.full_system import PersonalPhase,Holiday,HolidayClaim
from app.services import trial_rules,coin_service
from app.services.workflow_common import WriteIn,begin,finish,version,fields,get_owned
from app.services.user_service import get_or_create_default_user
from app.services.time_service import utc_now,local_day
from app.routers.admin import require_owner,audit,lock

router=APIRouter()
RETURN_POLICY={'version':1,'window_days':30,'min_account_days':30,'sparse_max_records':2,'recent_login_days':7,'cooldown_days':30}

class PhaseIn(WriteIn):
    title:str=Field('',max_length=120)
    goal:str=Field('',max_length=2000)
    deadline:date|None=None
    preferences:str=Field('',max_length=4000)
    ai_allowed:bool=False
    skip_return:bool=False

class HolidayIn(WriteIn):
    name:str=Field(min_length=1,max_length=120)
    region:str=Field(min_length=1,max_length=60)
    local_date:date
    enabled:bool=True
    reason:str=Field(min_length=1,max_length=2000)

def holiday_rows(db,user):
    config=trial_rules.account(db,user)
    if not config or not config.enabled or not config.region:return []
    return db.query(Holiday).filter_by(local_date=trial_rules.day(db,user),region=config.region,enabled=True).order_by(Holiday.id).all()

@router.get('/phase')
def read(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);row=db.query(PersonalPhase).filter_by(user_id=user.id).first();now=utc_now()
    latest=db.query(Event).filter_by(user_id=user.id).order_by(Event.created_at.desc()).first()
    last=latest.created_at if latest else user.created_at
    from app.services.time_service import zone
    if last.tzinfo is None:last=last.replace(tzinfo=zone('Asia/Shanghai'))
    created=user.created_at
    if created.tzinfo is None:created=created.replace(tzinfo=zone('Asia/Shanghai'))
    from app.services.time_service import clock_now
    recent_count=db.query(Event.id).filter(Event.user_id==user.id,Event.is_deleted.is_(False),Event.created_at>=clock_now()-timedelta(days=RETURN_POLICY['window_days'])).count()
    sparse=bool(user.last_login_at and user.last_login_at>=now-timedelta(days=RETURN_POLICY['recent_login_days']) and recent_count<=RETURN_POLICY['sparse_max_records'])
    eligible=(now-last>=timedelta(days=RETURN_POLICY['window_days']) or sparse) and now-created>=timedelta(days=RETURN_POLICY['min_account_days']) and (not row or not row.return_cooldown_until or now>=row.return_cooldown_until)
    return {'phase':fields(row) if row else None,'return_prompt':eligible,'return_policy':RETURN_POLICY,'return_window_days':RETURN_POLICY['window_days'],'cooldown_days':RETURN_POLICY['cooldown_days'],
        'holidays':[fields(h) for h in holiday_rows(db,user)],'holiday_claimed':bool(db.query(HolidayClaim).filter_by(user_id=user.id,local_date=trial_rules.day(db,user)).first())}

@router.put('/phase')
def save(body:PhaseIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'phase-save',body)
    if prior is not None:return prior
    row=db.query(PersonalPhase).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if not row:row=PersonalPhase(user_id=user.id,version=0,history=[]);db.add(row)
    if not body.skip_return:row.payload=body.model_dump(mode='json',exclude={'request_key','expected_version','skip_return'})
    row.pending=None
    row.return_cooldown_until=utc_now()+timedelta(days=RETURN_POLICY['cooldown_days']);row.version+=1
    row.history=[*row.history,{'version':row.version,'skipped':body.skip_return,'payload':row.payload,'return_policy':RETURN_POLICY,'at':utc_now().isoformat()}]
    db.flush();return finish(db,user,'phase-save',body,fp,row,fields(row))


class ConstraintIn(WriteIn):
    acknowledge:bool=False

@router.post('/phase/analyze')
def analyze_phase(body:WriteIn,db:Session=Depends(get_db)):
    from app.services import llm_config
    from app.services.llm_service import llm_service,LLMError
    import json
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'phase-analyze',body)
    if prior is not None:return prior
    row=db.query(PersonalPhase).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if not row or not row.payload.get('ai_allowed'):raise HTTPException(409,'请先保存并明确授权本次阶段背景。')
    captured=row.version
    try:config=llm_config.resolve_llm_config(db,user.id,llm_config.PURPOSE_JUDGE)
    except LLMError as exc:raise HTTPException(503,str(exc)) from None
    messages=[{'role':'system','content':'仅基于本次近期阶段建议未来娱乐约定。不要推定临考、不要改变已开始合同。必要休息免费，不凭负面情绪扣币。返回JSON {"mode":"gentle或strict或strong","reason":"可核对依据与不确定性"}。温和默认；strong仅建议未来明确接受后每5分钟4币、单次20每日30，宽限3分钟。'},
        {'role':'user','content':json.dumps(row.payload,ensure_ascii=False)}];db.commit()
    try:result=llm_service.chat_json(messages,config=config)
    except LLMError as exc:raise HTTPException(503,str(exc)) from None
    from app.services.transactions import lock_profile
    lock_profile(db,user.id);llm_config.assert_current(db,config);db.refresh(row)
    if row.version!=captured:raise HTTPException(409,'阶段或许可已变化。')
    if result.get('mode') not in ('gentle','strict','strong') or not isinstance(result.get('reason'),str) or not result['reason'].strip():raise HTTPException(422,'未生成有效约定建议。')
    row.pending={'mode':result['mode'],'reason':result['reason'][:2000],'model':config.model};row.version+=1;db.flush()
    return finish(db,user,'phase-analyze',body,fp,row,fields(row))

@router.post('/phase/accept-constraint')
def accept_constraint(body:ConstraintIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'phase-constraint',body)
    if prior is not None:return prior
    row=db.query(PersonalPhase).filter_by(user_id=user.id).first();version(row,body.expected_version)
    if not row or not row.pending or not body.acknowledge:raise HTTPException(422,'需明确接受当前建议，仅用于未来开始的会话。')
    row.payload={**row.payload,'accepted_mode':row.pending['mode']};row.history=[*row.history,{'accepted_constraint':row.pending,'at':utc_now().isoformat()}];row.pending=None;row.version+=1;db.flush()
    return finish(db,user,'phase-constraint',body,fp,row,fields(row))

@router.post('/holidays/claim')
def claim(body:WriteIn,db:Session=Depends(get_db)):
    lock(db)
    user=get_or_create_default_user(db);op='holiday:'+trial_rules.day(db,user);fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    holidays=holiday_rows(db,user);today=trial_rules.day(db,user)
    if not holidays or db.query(HolidayClaim).filter_by(user_id=user.id,local_date=today).first():raise HTTPException(409,'今天没有匹配且未领取的配置节日。')
    coin_service.require_baseline(db,user)
    row=HolidayClaim(user_id=user.id,local_date=today,amount=10,snapshot=[fields(h) for h in holidays]);db.add(row);db.flush()
    coin_service.grant(db,user,10,'holiday_gift','本人地区节日礼金；同日只领一次','holiday_claim',row.id)
    return finish(db,user,op,body,fp,row,fields(row))

@router.get('/admin/holidays')
def admin_read(db:Session=Depends(get_db),owner=Depends(require_owner)):
    return {'items':[fields(h) for h in db.query(Holiday).order_by(Holiday.local_date.desc()).limit(100).all()]}

@router.post('/admin/holidays')
@router.put('/admin/holidays/{holiday_id}')
def configure(body:HolidayIn,holiday_id:int|None=None,db:Session=Depends(get_db),owner=Depends(require_owner)):
    lock(db);op=f'holiday-config:{holiday_id or "create"}';fp,prior=begin(db,owner,op,body,create=holiday_id is None)
    if prior is not None:return prior
    row=db.get(Holiday,holiday_id) if holiday_id else None
    if holiday_id and not row:raise HTTPException(404,'节日配置不存在。')
    if row:version(row,body.expected_version)
    else:row=Holiday(version=0);db.add(row)
    row.name=body.name;row.region=body.region;row.local_date=str(body.local_date);row.enabled=body.enabled;row.version+=1;db.flush()
    audit(db,owner,'holiday-config',str(row.id),body.reason,row.version)
    return finish(db,owner,op,body,fp,row,fields(row))
