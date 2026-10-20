import json
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import UserProfile,Attribute
from app.models.full_system import Questionnaire
from app.services.question_catalog import GROUPS,QUESTIONS
from app.services import onboarding_service,llm_config,analysis_jobs,coin_service
from app.services.workflow_common import WriteIn,begin,finish,version,fields
from app.services.user_service import get_or_create_default_user
from app.constants import ATTRIBUTE_DIMENSIONS

router=APIRouter()

class Answer(BaseModel):
    state:Literal['answered','skipped']
    value:str=Field('',max_length=2000)

class SaveIn(WriteIn):
    answers:dict[str,Answer]=Field(default_factory=dict,max_length=40)
    send_groups:list[str]=Field(default_factory=list,max_length=6)

class GenerateIn(WriteIn):
    use_ai:bool=False
    acknowledge_scope:bool=False

def get(db,user):return db.query(Questionnaire).filter_by(user_id=user.id).first()

@router.get('/questionnaire')
def read(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);row=get(db,user);profile=db.query(UserProfile).filter_by(user_id=user.id).one()
    return {'groups':[{'id':g,'title':label} for g,label,_ in GROUPS],'questions':QUESTIONS,'draft':fields(row) if row else None,
        'onboarding_completed':profile.onboarding_completed,'baseline_kind':profile.baseline_kind,'initial_snapshot':profile.initial_attributes_snapshot,'legacy_state':profile.onboarding_state}

@router.put('/questionnaire')
def save(body:SaveIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'questionnaire-save',body)
    if prior is not None:return prior
    row=get(db,user);version(row,body.expected_version)
    valid={q['id'] for q in QUESTIONS};groups={g for g,_,_ in GROUPS}
    if not set(body.answers).issubset(valid) or not set(body.send_groups).issubset(groups):raise HTTPException(422,'未知题目或授权范围。')
    if not row:row=Questionnaire(user_id=user.id,version=0);db.add(row)
    row.answers={key:{'state':a.state,'value':a.value if a.state=='answered' else ''} for key,a in body.answers.items()};row.send_groups=body.send_groups;row.preview=None;row.version+=1
    # Revocation is immediate for subsequent context uses; adding answers alone never authorizes them.
    profile=db.query(UserProfile).filter_by(user_id=user.id).one()
    existing=(profile.basic_profile or {}).get('questionnaire',{})
    profile.basic_profile={**(profile.basic_profile or {}),'questionnaire':{key:value for key,value in existing.items() if key.split('_')[0] in body.send_groups and key in row.answers and row.answers[key]==value}}
    db.flush();return finish(db,user,'questionnaire-save',body,fp,row,fields(row))

@router.post('/questionnaire/preview')
def preview(body:GenerateIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'questionnaire-preview',body)
    if prior is not None:return prior
    row=get(db,user);version(row,body.expected_version)
    if not row:raise HTTPException(409,'请先保存问卷，所有问题都可跳过。')
    selected={key:a for key,a in row.answers.items() if key.split('_')[0] in row.send_groups and a['state']=='answered' and a['value'].strip()}
    panel=[{'name':name,'value':50,'reason':'资料不足；未评估的游戏起点。'} for name in ATTRIBUTE_DIMENSIONS];coins=80;summary='中性未评估起点；跳过不惩罚。';config_versions=None
    if body.use_ai and selected:
        if not body.acknowledge_scope:raise HTTPException(422,'请明确同意发送选定组的答案。')
        from app.services.llm_service import llm_service,LLMError
        try:config=llm_config.resolve_llm_config(db,user.id,llm_config.PURPOSE_JUDGE)
        except LLMError as exc:raise HTTPException(503,str(exc)) from None
        captured=row.version;config_versions=analysis_jobs.configuration(db,user.id)
        from app import prompts
        messages=prompts.build_panel_messages([{'role':'user','content':json.dumps(selected,ensure_ascii=False)}]);db.commit()
        try:result=llm_service.chat_json(messages,config=config)
        except LLMError as exc:raise HTTPException(503,str(exc)) from None
        from app.services.transactions import lock_profile
        lock_profile(db,user.id);llm_config.assert_current(db,config);db.refresh(row)
        if row.version!=captured:raise HTTPException(409,'答案或授权范围已变化。')
        try:panel=onboarding_service._parse_initial_panel(result.get('attributes'))
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
        coins=onboarding_service._clamp_initial_coins(result.get('initial_coins'));summary=str(result.get('summary',''))[:4000]
    row.preview={'attributes':panel,'initial_coins':coins,'summary':summary,'kind':'questionnaire_v2' if body.use_ai and selected else 'unassessed_questionnaire',
        'authorized_answers':selected if body.acknowledge_scope else {},'model_versions':config_versions}
    row.version+=1;db.flush();return finish(db,user,'questionnaire-preview',body,fp,row,fields(row))

@router.post('/questionnaire/confirm')
def confirm(body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'questionnaire-confirm',body)
    if prior is not None:return prior
    row=get(db,user);version(row,body.expected_version)
    if not row or not row.preview:raise HTTPException(409,'请先查看建档预览。')
    if row.preview['model_versions'] is not None and analysis_jobs.configuration(db,user.id)!=row.preview['model_versions']:raise HTTPException(409,'模型版本已变化，请重新生成预览。')
    profile=db.query(UserProfile).filter_by(user_id=user.id).populate_existing().one();proposal=row.preview
    if not profile.onboarding_completed:
        onboarding_service._assert_unbuilt_profile(db,profile)
        profile.basic_profile={**(profile.basic_profile or {}),'questionnaire':proposal['authorized_answers']}
        profile.initial_attributes_snapshot={**proposal,'model_versions':None};profile.baseline_kind=proposal['kind'];profile.onboarding_completed=True
        for item in proposal['attributes']:
            attr=db.query(Attribute).filter_by(user_id=user.id,name=item['name']).one();attr.current_value=item['value'];attr.description=item['reason']
        db.flush()  # coin_service refreshes the profile; persist the baseline in this transaction first.
        coin_service.grant_startup_bonus_if_needed(db,user,amount=proposal['initial_coins'])
    else:profile.basic_profile={**(profile.basic_profile or {}),'questionnaire':proposal['authorized_answers']}
    # Existing evaluations and coins are unchanged; only explicitly authorized background updates.
    row.preview=None;row.version+=1;db.flush()
    return finish(db,user,'questionnaire-confirm',body,fp,row,{'completed':True,'baseline_kind':profile.baseline_kind,'balance':coin_service.balance(db,user),'version':row.version})
