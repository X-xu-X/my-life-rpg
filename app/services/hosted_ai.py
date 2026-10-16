"""Independent site secrets, explicit selection and conservative per-attempt reservations."""
import json,re,hashlib,secrets
from pathlib import Path
from sqlalchemy import text
from app.config import settings
from app.models.policies import HostedAI,AIPreference,HostedUsage
from app.services.time_service import utc_now
from app.services.llm_service import LLMError


def preference(db,user_id):return db.query(AIPreference).filter_by(user_id=user_id).populate_existing().first()


def public(db,user_id):
    row=db.get(HostedAI,1);pref=preference(db,user_id)
    return {'mode':pref.mode if pref else 'personal','version':pref.version if pref else 0,
        'hosted':{'available':bool(settings.cloud and row and row.enabled and row.payload.get('approved') and settings.hosted_secret_file),
            'version':row.version if row else 0,'provider':row.payload.get('provider','') if row else '',
            'model':row.payload.get('model','') if row else '',
            'limits':{k:row.payload[k] for k in ('user_daily_calls','global_daily_calls','global_daily_tokens','daily_cost_cap','currency_unit')} if row and row.enabled else {}}}


def resolve(db,user_id,pref):
    from app.services.llm_config import LLMConfig
    from app.services.credentials import PROVIDERS
    row=db.get(HostedAI,1)
    if not settings.cloud or not row or not row.enabled or not row.payload.get('approved') or not settings.hosted_secret_file:raise LLMError('MODEL_NOT_CONFIGURED：站点默认 AI 未开通。')
    payload=row.payload
    key=read_secret(payload)
    return LLMConfig(api_key=key,base_url=PROVIDERS[payload['provider']],model=payload['model'],user_id=user_id,
        config_version=row.version,scope='hosted',preference_version=pref.version,max_output_tokens=payload['output_tokens'],secret_fingerprint=hashlib.sha256(key.encode()).hexdigest())


def read_secret(payload):
    try:
        values=json.loads(Path(settings.hosted_secret_file).read_text(encoding='utf-8'))
        key=values[payload['secret_ref']]
        if not isinstance(key,str) or len(key)<8:raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):raise LLMError('MODEL_NOT_CONFIGURED：站点模型秘密引用不可用。') from None
    return key


def assert_current(db,config):
    pref=preference(db,config.user_id)
    if (pref.version if pref else 0)!=config.preference_version or (pref.mode if pref else 'personal')!=config.scope:raise ValueError('AI 选择已变化。')
    if config.scope=='hosted':
        row=db.query(HostedAI).filter_by(id=1).populate_existing().first()
        if not row or not row.enabled or not row.payload.get('approved') or row.version!=config.config_version:raise ValueError('站点 AI 配置已变化。')
        if not secrets.compare_digest(hashlib.sha256(read_secret(row.payload).encode()).hexdigest(),config.secret_fingerprint):raise ValueError('站点模型秘密已轮换。')


def cost(payload,input_tokens,output_tokens):
    return (input_tokens*payload['input_rate']+output_tokens*payload['output_rate']+999999)//1000000


def lock(db):
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(61111230)'))


def reserve(factory,config,messages):
    with factory() as db:
        lock(db);assert_current(db,config);row=db.get(HostedAI,1);p=row.payload
        # Conservative UTF-8 byte bound plus protocol allowance; actual usage is checked on settlement.
        input_bound=len(json.dumps(messages,ensure_ascii=False).encode('utf-8'))+1024
        if input_bound>p['input_tokens']:raise LLMError('MODEL_INPUT_LIMIT：内容超过站点模型的输入上限。')
        tokens=p['input_tokens']+p['output_tokens'];reserve_cost=cost(p,p['input_tokens'],p['output_tokens']);day=utc_now().date().isoformat()
        rows=db.query(HostedUsage).filter(HostedUsage.local_date==day,HostedUsage.state!='released').all()
        if sum(r.user_id==config.user_id for r in rows)>=p['user_daily_calls'] or len(rows)>=p['global_daily_calls'] or sum(r.charged_tokens for r in rows)+tokens>p['global_daily_tokens'] or sum(r.charged_cost for r in rows)+reserve_cost>p['daily_cost_cap']:raise LLMError('MODEL_DAILY_LIMIT：站点模型额度或预算已用完。')
        usage=HostedUsage(user_id=config.user_id,local_date=day,hosted_version=row.version,state='reserved',pricing_snapshot={k:p[k] for k in ('input_tokens','output_tokens','input_rate','output_rate','currency_unit')},reserved_tokens=tokens,charged_tokens=tokens,reserved_cost=reserve_cost,charged_cost=reserve_cost)
        db.add(usage);db.commit();return usage.id


def dispatched(factory,config,usage_id):
    with factory() as db:
        lock(db);assert_current(db,config);row=db.get(HostedUsage,usage_id);row.state='sent';db.commit()


def settle(factory,usage_id,response=None,error=''):
    with factory() as db:
        lock(db);row=db.get(HostedUsage,usage_id)
        if response is None and row.state in ('released','settled','overrun'):return row.state
        if row.state=='reserved':row.state='released';row.charged_tokens=0;row.charged_cost=0
        else:
            usage=getattr(response,'usage',None);prompt=getattr(usage,'prompt_tokens',None);completion=getattr(usage,'completion_tokens',None)
            current=db.get(HostedAI,1);p=row.pricing_snapshot
            if type(prompt) is int and type(completion) is int and 0<=prompt<2**63 and 0<=completion<2**63:
                row.charged_tokens=min(2**63-1,prompt+completion);row.charged_cost=min(2**63-1,cost(p,prompt,completion))
                row.state='settled' if prompt<=p['input_tokens'] and completion<=p['output_tokens'] else 'overrun'
                if row.state=='overrun' and current.version==row.hosted_version:current.enabled=False;current.version+=1
            else:row.state='unknown'
        row.safe_error_code='MODEL_USAGE_OVERRUN' if row.state=='overrun' else error
        db.commit();return row.state
