from datetime import date
from typing import Literal
import re
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,model_validator,StrictInt
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Goal,UserProfile
from app.models.policies import EconomicRule,Mainline,RewardPreview,DynamicCandidate,HostedAI,AIPreference,HostedUsage
from app.services.workflow_common import WriteIn,begin,finish,version,fields,get_owned
from app.services.user_service import get_or_create_default_user
from app.services import economy,hosted_ai
from app.routers.admin import require_owner,lock,audit

router=APIRouter()
admin=APIRouter(prefix='/admin',dependencies=[Depends(require_owner)])


class Tier(BaseModel):
    code:str=Field(min_length=1,max_length=40)
    min_minutes:float=Field(ge=0,le=1000000,allow_inf_nan=False)
    result_required:bool
    amount:int=Field(ge=0,le=10**12,strict=True)


class RuleIn(WriteIn):
    enabled:bool=False
    approved:bool=False
    effective_from:date
    tiers:list[Tier]=Field(default_factory=list,max_length=20)
    daily_cap:StrictInt|None=Field(None,ge=0,le=10**12)
    per_fact_cap:StrictInt|None=Field(None,ge=0,le=10**12)
    max_active:StrictInt|None=Field(None,ge=1,le=100)
    stacking:Literal['replace_legacy','stack']|None=None
    cap_basis:Literal['content','confirmation']|None=None
    rewards:dict[str,StrictInt]=Field(default_factory=dict,max_length=100)
    fixed_equivalences:dict[str,str]=Field(default_factory=dict,max_length=100)
    user_total_cap:StrictInt|None=Field(None,ge=0,le=10**12)
    allow_fixed_stack:bool|None=None
    reason:str=Field(min_length=1,max_length=2000)


class MainlineIn(WriteIn):
    goal_id:int
    active:bool=True


class PreviewIn(WriteIn):
    mainline_id:int
    mainline_version:int
    event_id:int
    event_version:int
    judgment_id:int
    minutes:float=Field(ge=0,le=1000000,allow_inf_nan=False)
    result:bool
    evidence:str=Field(min_length=1,max_length=2000)


class CandidateIn(WriteIn):
    name:str=Field(min_length=1,max_length=100)
    metric:Literal['event_content_days','event_saved_days','diary_content_days','diary_saved_days']
    shape:Literal['total_days','consecutive_days','calendar_month']
    target:int=Field(ge=1,le=36600)
    start:date|None=None
    end:date|None=None
    @model_validator(mode='after')
    def valid(self):
        if self.start and self.end and self.start>self.end:raise ValueError('日期范围无效。')
        if self.shape=='calendar_month' and (not self.start or not self.end or self.target!=1):raise ValueError('自然月需要明确起止与 target=1。')
        return self


class CandidateDecision(WriteIn):
    action:Literal['ignore','verify','claim']


class PreferenceIn(WriteIn):
    mode:Literal['personal','hosted','off']
    acknowledge:bool=False
    hosted_version:int|None=None


class HostedIn(WriteIn):
    enabled:bool=False
    approved:bool=False
    provider:Literal['deepseek','openai','siliconflow']
    model:str=Field(min_length=1,max_length=100,pattern=r'^[^\s\x00-\x1f\x7f]+$')
    secret_ref:str=Field(min_length=1,max_length=60,pattern=r'^[A-Z][A-Z0-9_]*$')
    user_daily_calls:StrictInt=Field(ge=1,le=10000)
    global_daily_calls:StrictInt=Field(ge=1,le=100000)
    global_daily_tokens:StrictInt=Field(ge=1,le=10**12)
    daily_cost_cap:StrictInt=Field(ge=0,le=10**12)
    input_tokens:StrictInt=Field(ge=1024,le=200000)
    output_tokens:StrictInt=Field(ge=1,le=32000)
    input_rate:StrictInt=Field(ge=0,le=10**12)
    output_rate:StrictInt=Field(ge=0,le=10**12)
    currency_unit:str=Field(min_length=1,max_length=40)
    price_checked_on:date
    reason:str=Field(min_length=1,max_length=2000)


@router.get('/mainlines')
def mainlines(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);rule=economy.latest(db,'mainline')
    return {'items':[fields(row) for row in db.query(Mainline).filter_by(user_id=user.id).all()],
        'rule':fields(rule) if rule else None,'previews':[fields(r) for r in db.query(RewardPreview).filter_by(user_id=user.id).order_by(RewardPreview.id.desc()).limit(100).all()]}


@router.post('/mainlines')
@router.put('/mainlines/{mainline_id}')
def save_mainline(body:MainlineIn,mainline_id:int|None=None,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'mainline:{mainline_id or "create"}';fp,prior=begin(db,user,op,body,create=mainline_id is None)
    if prior is not None:return prior
    goal=get_owned(db,Goal,body.goal_id);row=get_owned(db,Mainline,mainline_id) if mainline_id else None
    if row:version(row,body.expected_version)
    current=economy.latest(db,'mainline')
    if body.active and (not row or not row.active) and current and current.enabled and db.query(Mainline).filter_by(user_id=user.id,active=True).count()>=current.payload['max_active']:raise HTTPException(409,'达到已确认主线数量上限。')
    if not row:row=Mainline(user_id=user.id,goal_id=goal.id,version=0);db.add(row)
    row.goal_id=goal.id;row.active=body.active;row.version+=1;db.flush()
    return finish(db,user,op,body,fp,row,fields(row))


@router.post('/reward-previews')
def preview(body:PreviewIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'reward-preview',body,create=True)
    if prior is not None:return prior
    row=economy.preview(db,user,body)
    return finish(db,user,'reward-preview',body,fp,row,fields(row))


@router.get('/dynamic-candidates')
def candidates(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);rule=economy.latest(db,'dynamic')
    return {'items':[fields(r) for r in db.query(DynamicCandidate).filter_by(user_id=user.id).order_by(DynamicCandidate.id.desc()).all()],'rule':fields(rule) if rule else None}


@router.post('/dynamic-candidates')
def propose_candidate(body:CandidateIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'dynamic-propose',body,create=True)
    if prior is not None:return prior
    criteria=body.model_dump(mode='json',include={'metric','shape','target','start','end'});key=economy.semantic(criteria)
    row=db.query(DynamicCandidate).filter_by(user_id=user.id,semantic_key=key).first()
    if not row:
        row=DynamicCandidate(user_id=user.id,semantic_key=key,name=body.name,criteria=criteria,evidence=economy.verify(db,user,criteria));db.add(row);db.flush()
    return finish(db,user,'dynamic-propose',body,fp,row,fields(row))


@router.post('/dynamic-candidates/{candidate_id}/decision')
def candidate_decision(candidate_id:int,body:CandidateDecision,db:Session=Depends(get_db)):
    if body.action=='claim':economy.lock_rules(db)
    user=get_or_create_default_user(db);op=f'dynamic-decision:{candidate_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,DynamicCandidate,candidate_id);version(row,body.expected_version)
    if row.state!='candidate':raise HTTPException(409,'候选已处理。')
    if body.action=='claim':economy.claim_dynamic(db,user,row)
    else:
        row.evidence=economy.verify(db,user,row.criteria);row.version+=1
        if body.action=='ignore':row.state='ignored'
    return finish(db,user,op,body,fp,row,fields(row))


@router.get('/ai/preferences')
def ai_preference(db:Session=Depends(get_db)):
    return hosted_ai.public(db,get_or_create_default_user(db).id)


@router.put('/ai/preferences')
def save_preference(body:PreferenceIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'ai-preference',body)
    if prior is not None:return prior
    row=hosted_ai.preference(db,user.id);version(row,body.expected_version)
    if body.mode=='hosted':
        info=hosted_ai.public(db,user.id)
        if not body.acknowledge or not info['hosted']['available'] or body.hosted_version!=info['hosted']['version']:raise HTTPException(409,'站点模型未开通或版本变化，请核对后主动同意。')
        from types import SimpleNamespace
        hosted_ai.resolve(db,user.id,SimpleNamespace(version=(row.version if row else 0)+1))
    if not row:row=AIPreference(user_id=user.id,version=0);db.add(row)
    row.mode=body.mode;row.version+=1;db.flush()
    return finish(db,user,'ai-preference',body,fp,row,hosted_ai.public(db,user.id))


@admin.get('/rules/{kind}')
def rules(kind:Literal['mainline','dynamic'],db:Session=Depends(get_db)):
    return {'items':[fields(r) for r in db.query(EconomicRule).filter_by(kind=kind).order_by(EconomicRule.version.desc()).all()]}


@admin.put('/rules/{kind}')
def save_rule(kind:Literal['mainline','dynamic'],body:RuleIn,db:Session=Depends(get_db),owner=Depends(require_owner)):
    lock(db)
    op='admin-rule:'+kind;fp,prior=begin(db,owner,op,body)
    if prior is not None:return prior
    lock(db);current=economy.latest(db,kind)
    if body.expected_version!=(current.version if current else 0):raise HTTPException(409,'规则版本已变化。')
    if body.enabled:
        if not body.approved:raise HTTPException(422,'正式启用需要明确确认规则。')
        if kind=='mainline' and (not body.tiers or any(getattr(body,k) is None for k in ('daily_cap','per_fact_cap','max_active','stacking','cap_basis'))):raise HTTPException(422,'主线档位、上限、数量、日期与叠加规则必须完整。')
        if kind=='dynamic' and (not body.rewards or body.user_total_cap is None or body.allow_fixed_stack is None):raise HTTPException(422,'动态奖励身份、金额、上限与叠加规则必须完整。')
    if any(not re.fullmatch(r'[0-9a-f]{64}',key) or type(amount) is not int or not 0<=amount<=10**12 for key,amount in body.rewards.items()):raise HTTPException(422,'奖励身份或金额无效。')
    from app.services.achievement_service import CATALOG_BY_CODE
    if any(key not in body.rewards or code not in CATALOG_BY_CODE for key,code in body.fixed_equivalences.items()):raise HTTPException(422,'固定成就等价映射需引用已配置语义身份与固定目录 code。')
    if len({tier.code for tier in body.tiers})!=len(body.tiers):raise HTTPException(422,'档位身份不能重复。')
    row=EconomicRule(kind=kind,version=(current.version if current else 0)+1,enabled=body.enabled,payload=body.model_dump(mode='json',exclude={'request_key','expected_version','reason','enabled'}));db.add(row);db.flush()
    audit(db,owner,'economic-rule',kind,body.reason,row.version)
    return finish(db,owner,op,body,fp,row,fields(row))


@admin.get('/hosted-ai')
def hosted_config(db:Session=Depends(get_db)):
    row=db.get(HostedAI,1)
    return fields(row) if row else {'version':0,'enabled':False,'payload':None}


@admin.put('/hosted-ai')
def save_hosted(body:HostedIn,db:Session=Depends(get_db),owner=Depends(require_owner)):
    lock(db)
    fp,prior=begin(db,owner,'admin-hosted',body)
    if prior is not None:return prior
    lock(db);row=db.query(HostedAI).filter_by(id=1).populate_existing().with_for_update().first()
    if body.expected_version!=(row.version if row else 0):raise HTTPException(409,'站点 AI 版本已更新。')
    if body.enabled and not body.approved:raise HTTPException(422,'未确认供应商和费用预算，不能启用。')
    if not row:row=HostedAI(id=1,version=0,payload={});db.add(row)
    row.version+=1;row.enabled=body.enabled;row.payload=body.model_dump(mode='json',exclude={'request_key','expected_version','reason','enabled'});db.flush()
    if body.enabled:
        from types import SimpleNamespace
        try:hosted_ai.resolve(db,owner.id,SimpleNamespace(version=0))
        except Exception:raise HTTPException(409,'独立服务端秘密未配置，不能开启站点模型。') from None
    audit(db,owner,'hosted-ai','site',body.reason,row.version)
    return finish(db,owner,'admin-hosted',body,fp,row,fields(row))


@admin.get('/hosted-monitor')
def monitor(db:Session=Depends(get_db)):
    from app.services.time_service import utc_now
    # Only numeric usage metadata may cross users; no prompt/content/key is stored here.
    db.info['monitor_hosted_usage']=True
    try:rows=db.query(HostedUsage).filter_by(local_date=utc_now().date().isoformat()).all()
    finally:db.info.pop('monitor_hosted_usage',None)
    return {'date_basis':'UTC','calls':len([r for r in rows if r.state!='released']),
        'tokens':sum(r.charged_tokens for r in rows),'cost':sum(r.charged_cost for r in rows),
        'unknown':sum(r.state in ('unknown','sent') for r in rows),'failures':sum(bool(r.safe_error_code) for r in rows)}
