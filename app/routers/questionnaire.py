import json
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import UserProfile,Attribute
from app.models.full_system import Questionnaire
from app.services.question_catalog import GROUPS,QUESTIONS,ALL_QUESTIONS,CATALOG_VERSION
from app.services import onboarding_service,llm_config,analysis_jobs,coin_service
from app.services.workflow_common import WriteIn,begin,finish,version,fields
from app.services.user_service import get_or_create_default_user
from app.constants import ATTRIBUTE_DIMENSIONS
from app.services.time_service import utc_now

router=APIRouter()

class Answer(BaseModel):
    state:Literal['answered','skipped']
    value:str=Field('',max_length=2000)

class SaveIn(WriteIn):
    answers:dict[str,Answer]=Field(default_factory=dict,max_length=60)
    send_groups:list[str]=Field(default_factory=list,max_length=6)
    uses:list[Literal['judge','review','report','pricing']]=Field(default_factory=lambda:['judge','review','report','pricing'],max_length=4)

class GenerateIn(WriteIn):
    use_ai:bool=False
    acknowledge_scope:bool=False

def get(db,user):return db.query(Questionnaire).filter_by(user_id=user.id).first()


def selected_answers(row):
    catalog={q['id']:q for q in ALL_QUESTIONS}
    for batch in row.followups:
        for q in batch['questions']:catalog[q['id']]=q
    return {key:a for key,a in row.answers.items() if catalog.get(key,{}).get('group') in row.send_groups and a['state']=='answered' and a['value'].strip()}


def ensure_basics(row):
    if not row or any(q['id'] not in row.answers or row.answers[q['id']]['state']=='answered' and not row.answers[q['id']]['value'].strip() for q in QUESTIONS):raise HTTPException(409,'请先回答或跳过全部基础题，再整体分析。')


def check_running(row,body):
    if row.stage=='analyzing':raise HTTPException(409,'问卷正在分析或上次结果尚未知；请先查看保存状态，必要时重新保存答案后主动重试。')


def call_model(db,user,row,body,config,messages,validate_result=lambda value:value):
    from app.services.llm_service import llm_service,LLMError
    from app.services.transactions import lock_profile
    captured=row.version;key=str(body.request_key)
    marker=(row.preview or {}).get('processing',{})
    if row.stage=='analyzing' and marker.get('key')!=key:check_running(row,body)
    row.stage='analyzing';row.preview={'processing':{'key':key,'started_at':utc_now().isoformat()}};db.commit()
    try:
        result=llm_service.chat_json(messages,config=config)
        lock_profile(db,user.id);llm_config.assert_current(db,config);db.refresh(row)
        if row.version!=captured or (row.preview or {}).get('processing',{}).get('key')!=key:raise HTTPException(409,'答案或授权范围已变化，旧分析不再写入。')
        validate_result(result)
        return result
    except Exception as exc:
        db.rollback();lock_profile(db,user.id);db.refresh(row)
        if row.version==captured and (row.preview or {}).get('processing',{}).get('key')==key:
            row.stage='failed';row.preview=None;db.commit()
        if isinstance(exc,LLMError):raise HTTPException(503,str(exc)) from None
        raise

@router.get('/questionnaire')
def read(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);row=get(db,user);profile=db.query(UserProfile).filter_by(user_id=user.id).one()
    return {'groups':[{'id':g,'title':label} for g,label,_ in GROUPS if g!='scope'],'questions':QUESTIONS,'catalog_version':CATALOG_VERSION,'draft':fields(row) if row else None,
        'history':row.history if row else [],'history_incomplete':bool(profile.onboarding_completed and (not row or not row.history or not row.history[-1].get('questions'))),
        'onboarding_completed':profile.onboarding_completed,'baseline_kind':profile.baseline_kind,'initial_snapshot':profile.initial_attributes_snapshot,'legacy_state':profile.onboarding_state}

@router.put('/questionnaire')
def save(body:SaveIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'questionnaire-save',body)
    if prior is not None:return prior
    row=get(db,user);version(row,body.expected_version)
    profile=db.query(UserProfile).filter_by(user_id=user.id).one()
    if profile.onboarding_completed:raise HTTPException(409,'初始问卷历史只读；请在长期信息中增改背景，在授权入口调整后续用途。')
    valid={q['id'] for q in ALL_QUESTIONS}|{q['id'] for batch in row.followups for q in batch['questions']} if row else {q['id'] for q in ALL_QUESTIONS}
    groups={g for g,_,_ in GROUPS}
    if not set(body.answers).issubset(valid) or not set(body.send_groups).issubset(groups):raise HTTPException(422,'未知题目或授权范围。')
    if not row:row=Questionnaire(user_id=user.id,version=0,answers={},followups=[],history=[]);db.add(row)
    values={key:{'state':a.state,'value':a.value if a.state=='answered' else ''} for key,a in body.answers.items()}
    base_ids={q['id'] for q in ALL_QUESTIONS}
    if any(row.answers.get(k)!=values.get(k) for k in base_ids):
        row.followups=[];values={k:v for k,v in values.items() if k in base_ids};row.stage='basics'
    row.answers=values;row.send_groups=body.send_groups;row.uses=body.uses;row.preview=None;row.stage='followups' if row.followups else 'basics';row.version+=1
    if not row.question_snapshot:row.question_snapshot=[{**q,'catalog_version':CATALOG_VERSION} for q in QUESTIONS]
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
    if db.query(UserProfile).filter_by(user_id=user.id).one().onboarding_completed:raise HTTPException(409,'已有初始评估不可重做；请维护长期信息。')
    if not row:raise HTTPException(409,'请先保存问卷，所有问题都可跳过。')
    check_running(row,body)
    ensure_basics(row)
    return evaluate(body,db,user,row,'questionnaire-preview',fp)


def evaluate(body,db,user,row,operation,fp):
    selected=selected_answers(row)
    panel=[{'name':name,'value':50,'reason':'资料不足；未评估的游戏起点。'} for name in ATTRIBUTE_DIMENSIONS];coins=80;summary='中性未评估起点；跳过不惩罚。';config_versions=None
    if body.use_ai and selected:
        if not body.acknowledge_scope:raise HTTPException(422,'请明确同意发送选定组的答案。')
        from app.services.llm_service import llm_service,LLMError
        try:config=llm_config.resolve_llm_config(db,user.id,llm_config.PURPOSE_JUDGE)
        except LLMError as exc:raise HTTPException(503,str(exc)) from None
        captured=row.version;config_versions=analysis_jobs.configuration(db,user.id)
        from app import prompts
        catalog={q['id']:q for q in [*row.question_snapshot,*[q for batch in row.followups for q in batch['questions']]]}
        conversation=[{'question':catalog.get(key,{}).get('text','本人补充：'+key),'answer':value['value']} for key,value in selected.items()]
        messages=prompts.build_panel_messages(conversation)
        messages.append({'role':'system','content':'依据本人的奖励偏好、投入与参考物价，可返回economic_reference说明个人购买力依据与不确定项，不设统一金币现金比例。初始金币沿80～200范围，不据家庭资产评价能力。'})
        def valid_panel(value):
            try:onboarding_service._parse_initial_panel(value.get('attributes'))
            except ValueError as exc:raise HTTPException(422,str(exc)) from None
        result=call_model(db,user,row,body,config,messages,valid_panel)
        try:panel=onboarding_service._parse_initial_panel(result.get('attributes'))
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
        coins=onboarding_service._clamp_initial_coins(result.get('initial_coins'));summary=str(result.get('summary',''))[:4000]
    row.preview={'attributes':panel,'initial_coins':coins,'summary':summary,'kind':'questionnaire_v2' if body.use_ai and selected else 'unassessed_questionnaire',
        'authorized_answers':selected if body.acknowledge_scope else {},'uses':row.uses,'model_versions':config_versions,
        'economic_reference':result.get('economic_reference',{}) if body.use_ai and selected and isinstance(result.get('economic_reference',{}),(dict,str)) else {}}
    row.stage='preview'
    row.version+=1;db.flush();return finish(db,user,operation,body,fp,row,fields(row))

@router.post('/questionnaire/confirm')
def confirm(body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'questionnaire-confirm',body)
    if prior is not None:return prior
    row=get(db,user);version(row,body.expected_version)
    if not row or not row.preview or 'attributes' not in row.preview:raise HTTPException(409,'请先查看建档预览。')
    if row.preview['model_versions'] is not None and analysis_jobs.configuration(db,user.id)!=row.preview['model_versions']:raise HTTPException(409,'模型版本已变化，请重新生成预览。')
    profile=db.query(UserProfile).filter_by(user_id=user.id).populate_existing().one();proposal=row.preview
    if profile.onboarding_completed:raise HTTPException(409,'初始评估已完成，不重新发放资金或覆盖属性。')
    if not profile.onboarding_completed:
        onboarding_service._assert_unbuilt_profile(db,profile)
        profile.basic_profile={**(profile.basic_profile or {}),'questionnaire':proposal['authorized_answers'],'questionnaire_uses':proposal.get('uses',[])}
        profile.initial_attributes_snapshot={**proposal,'model_versions':None};profile.baseline_kind=proposal['kind'];profile.onboarding_completed=True
        for item in proposal['attributes']:
            attr=db.query(Attribute).filter_by(user_id=user.id,name=item['name']).one();attr.current_value=item['value'];attr.description=item['reason']
        db.flush()  # coin_service refreshes the profile; persist the baseline in this transaction first.
        coin_service.grant_startup_bonus_if_needed(db,user,amount=proposal['initial_coins'])
    else:profile.basic_profile={**(profile.basic_profile or {}),'questionnaire':proposal['authorized_answers']}
    # Existing evaluations and coins are unchanged; only explicitly authorized background updates.
    row.history=[*row.history,{'questions':row.question_snapshot,'followups':row.followups,'answers':row.answers,'assessment':proposal,'confirmed_at':utc_now().isoformat()}]
    row.preview=None;row.stage='completed';row.version+=1;db.flush()
    return finish(db,user,'questionnaire-confirm',body,fp,row,{'completed':True,'baseline_kind':profile.baseline_kind,'balance':coin_service.balance(db,user),'version':row.version})


@router.post('/questionnaire/analyze')
def analyze(body:GenerateIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'questionnaire-analyze',body)
    if prior is not None:return prior
    row=get(db,user);version(row,body.expected_version);ensure_basics(row)
    check_running(row,body)
    if db.query(UserProfile).filter_by(user_id=user.id).one().onboarding_completed:raise HTTPException(409,'初始问卷已完成，只读历史。')
    selected=selected_answers(row)
    if not body.use_ai or not selected or len(row.followups)>=2:
        # Neutral/all-skipped and bounded followup paths always have an exit.
        return evaluate(body,db,user,row,'questionnaire-analyze',fp)
    if not body.acknowledge_scope:raise HTTPException(422,'请明确同意发送已选答案。')
    if any(q['id'] not in row.answers for batch in row.followups for q in batch['questions']):raise HTTPException(409,'请先回答或跳过本轮补题。')
    from app.services.llm_service import llm_service,LLMError
    try:config=llm_config.resolve_llm_config(db,user.id,llm_config.PURPOSE_JUDGE)
    except LLMError as exc:raise HTTPException(503,str(exc)) from None
    captured=row.version;round_number=len(row.followups)+1
    skipped={k for k,v in row.answers.items() if v['state']=='skipped'}
    blocked=set(skipped)
    for batch in reversed(row.followups):
        for q in batch['questions']:
            if q['id'] in blocked:blocked.update(q['based_on'])
    gap_selected={k:v for k,v in selected.items() if k not in blocked}
    if not gap_selected:return evaluate(body,db,user,row,'questionnaire-analyze',fp)
    messages=[{'role':'system','content':'整体阅读本人明确授权的问卷答案，信息已足够时questions为空；只针对有价值的本人信息缺口补题。不要重问已经充分回答或明确跳过/不愿谈的话题，不问资产、精确收入、真实姓名，不凭性格加减点。返回JSON {"questions":[{"text":"引用本人回答的个性化问题","based_on":["已回答题ID"]}]}，最多3题。'},
        {'role':'user','content':json.dumps({'answered':gap_selected,'skipped_ids':sorted(blocked),'previous_rounds':row.followups,'round':round_number},ensure_ascii=False)}]
    def valid_questions(value):
        questions=value.get('questions')
        if not isinstance(questions,list) or len(questions)>3:raise HTTPException(422,'补题结果不符合数量上限。')
        for q in questions:
            if not isinstance(q,dict) or not isinstance(q.get('text'),str) or not 1<=len(q['text'])<=1000 or not isinstance(q.get('based_on'),list) or not q['based_on'] or any(not isinstance(k,str) or k not in gap_selected for k in q['based_on']):raise HTTPException(422,'补题需引用本人已授权且没有跳过补问的主题。')
    result=call_model(db,user,row,body,config,messages,valid_questions)
    questions=result.get('questions')
    if not isinstance(questions,list) or len(questions)>3:raise HTTPException(422,'补题结果不符合数量上限。')
    saved=[];seen={q['text'] for batch in row.followups for q in batch['questions']}
    for n,q in enumerate(questions):
        if not isinstance(q,dict) or not isinstance(q.get('text'),str) or not 1<=len(q['text'])<=1000 or not isinstance(q.get('based_on'),list) or not q['based_on'] or any(not isinstance(k,str) or k not in selected for k in q['based_on']):raise HTTPException(422,'补题需明确引用本人已授权的回答。')
        if q['text'] in seen or any(word in q['text'] for word in ('身份证','银行卡','真实姓名','精确收入','资产总额')):continue
        catalog={q['id']:q for q in [*ALL_QUESTIONS,*[q for batch in row.followups for q in batch['questions']]]}
        seen.add(q['text']);saved.append({'id':f'followup_{round_number}_{n+1}','text':q['text'],'based_on':q['based_on'],'group':catalog[q['based_on'][0]]['group']})
    if not saved:
        # No new question: keep the same user intent, then evaluate once.
        return evaluate(body,db,user,row,'questionnaire-analyze',fp)
    row.followups=[*row.followups,{'round':round_number,'questions':saved,'model_version':analysis_jobs.configuration(db,user.id)}];row.stage='followups';row.version+=1
    row.preview=None
    db.flush();return finish(db,user,'questionnaire-analyze',body,fp,row,fields(row))


class PermissionIn(WriteIn):
    send_groups:list[str]=Field(default_factory=list,max_length=6)
    uses:list[Literal['judge','review','report','pricing']]=Field(default_factory=list,max_length=4)


@router.put('/questionnaire/permissions')
def permissions(body:PermissionIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'questionnaire-permissions',body)
    if prior is not None:return prior
    row=get(db,user);version(row,body.expected_version)
    if not row:raise HTTPException(409,'没有可调整授权的问卷，旧资料保持原范围。')
    if not set(body.send_groups)<={g for g,_,_ in GROUPS}:raise HTTPException(422,'未知组。')
    row.send_groups=body.send_groups;row.uses=body.uses;row.version+=1
    profile=db.query(UserProfile).filter_by(user_id=user.id).one()
    profile.basic_profile={**(profile.basic_profile or {}),'questionnaire':selected_answers(row),'questionnaire_uses':body.uses}
    db.flush();return finish(db,user,'questionnaire-permissions',body,fp,row,fields(row))
