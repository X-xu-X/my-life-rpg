import hashlib,json
from datetime import datetime
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ShopItem
from app.models.full_system import PricingQuote
from app.services import ai_context,analysis_jobs,shop_service,trial_rules
from app.services.ai_context import model_context
from app.services.workflow_common import WriteIn,begin,finish,version,fields,get_owned
from app.services.user_service import get_or_create_default_user

router=APIRouter()

def economy_context(db,user):
    from app.models import CoinLedger,Redemption,Goal
    from app.models.full_system import TimeSession
    from app.models.policies import Mainline
    from sqlalchemy import func
    config=trial_rules.account(db,user)
    mainlines=[(m.id,m.version,g.id,g.updated_at.isoformat()) for m,g in db.query(Mainline,Goal).join(Goal,Goal.id==Mainline.goal_id).filter(Mainline.user_id==user.id,Mainline.active.is_(True)).order_by(Mainline.id).all()]
    value={'day':trial_rules.day(db,user),'rule_version':trial_rules.VERSION,'trial_version':config.version if config else 0,
        'ledger_max':db.query(func.max(CoinLedger.id)).filter(CoinLedger.user_id==user.id).scalar(),
        'vouchers':[(r.id,r.status) for r in db.query(Redemption).filter_by(user_id=user.id).order_by(Redemption.id).all()],
        'activity':shop_service.pricing_activity(db,user),'mainlines':mainlines}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

class QuoteIn(WriteIn):
    name:str=Field(min_length=1,max_length=120)
    # 由 AI 判断是否计时类；前端不再让用户选形式，也不再要求填分钟。
    price_yuan:float|None=Field(None,ge=0,allow_inf_nan=False)
    description:str=Field('',max_length=2000)
    item_id:int|None=None
    item_version:datetime|None=None
    auto_check:bool=False

@router.get('/reward-quotes')
def read(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db)
    return {'items':[fields(q) for q in db.query(PricingQuote).filter_by(user_id=user.id).order_by(PricingQuote.id.desc()).limit(30).all()]}


@router.get('/pricing-checks')
def checks(db:Session=Depends(get_db)):
    from app.models.daily_use import PricingCheck
    user=get_or_create_default_user(db)
    return {'items':[fields(r) for r in db.query(PricingCheck).filter_by(user_id=user.id).order_by(PricingCheck.id.desc()).limit(30).all()]}


@router.post('/pricing-checks')
def check_prices(body:WriteIn,db:Session=Depends(get_db)):
    from app.services.pricing_checks import enqueue
    user=get_or_create_default_user(db);fp,prior=begin(db,user,'pricing-checks',body,create=True)
    if prior is not None:return prior
    result=enqueue(db,user)
    from app.models import UserProfile
    resource=db.query(UserProfile).filter_by(user_id=user.id).one()
    return finish(db,user,'pricing-checks',body,fp,resource,result)


@router.post('/pricing-checks/{check_id}/retry')
def retry_check(check_id:int,body:WriteIn,db:Session=Depends(get_db)):
    from app.models.daily_use import PricingCheck
    from uuid import uuid4
    user=get_or_create_default_user(db);op=f'pricing-retry:{check_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,PricingCheck,check_id);version(row,body.expected_version)
    if row.state!='failed' or row.version>=6 or row.local_date!=trial_rules.day(db,user):raise HTTPException(409,'仅可主动重试今天的失败检查一次；不会无限调用模型。')
    row.state='queued';row.request_key=str(uuid4());row.error_code=None;row.lease_token=None;row.version+=1;db.flush()
    return finish(db,user,op,body,fp,row,fields(row))


def apply_quote(db,user,row):
    from app.services.time_service import utc_now,local_day
    from app.services.pricing_checks import assert_lease
    assert_lease(db)
    today=trial_rules.day(db,user)
    quote_day=row.context.get('day') or str(local_day(row.created_at,user.timezone))
    if row.state!='suggested' or quote_day!=today or analysis_jobs.configuration(db,user.id)!=row.context['config'] or not ai_context.valid(db,row.context['sources'],user.id) or ai_context.background(db,user.id)!=row.context['background']:
        raise HTTPException(409,'价格建议、日期或授权背景已变化，请重新定价。')
    if economy_context(db,user)!=row.context['economy']:raise HTTPException(409,'收入、目标或确认使用量已变化，请重新定价。')
    item=get_owned(db,ShopItem,row.item_id) if row.item_id else None
    if item:
        db.refresh(item)
        if item.updated_at.isoformat()!=row.context['item_version'] or item.repriced_on==today:raise HTTPException(409,'商品已变化或今天已经更新价格。')
        # v1.13 F11：不再做 ±20% 截断，模型给多少就是多少；只记录旧价与涨跌幅。
        previous=max(1,item.coin_price)
        price=row.result['coin_price']
        change_pct=round((price-previous)*100/previous) if previous else 0
        row.result={**row.result,'previous_price':previous,'change_pct':change_pct}
    else:
        timed=bool(row.result.get('is_timed'))
        minutes=row.result.get('minutes_estimate')
        duration=int(minutes)*60 if timed and type(minutes) is int and 1<=minutes<=1440 else None
        item=ShopItem(user_id=user.id,name=row.payload['name'],kind='custom',reward_kind='entertainment' if duration else 'item',
            duration_seconds=duration,pricing_mode='once',
            price_yuan=row.payload['price_yuan'],base_coin_price=row.result['coin_price'],description=row.payload.get('description',''),auto_pricing=row.payload.get('auto_check',False))
        db.add(item);db.flush();row.item_id=item.id
    item.coin_price=row.result['coin_price'];item.pricing_reason=row.result['pricing_reason'];item.worth_note=row.result['worth_note']
    item.priced_at=utc_now();item.repriced_on=today
    row.state='accepted';row.version+=1;db.flush()
    return item


@router.post('/reward-quotes')
@model_context
def quote(body:QuoteIn,db:Session=Depends(get_db)):
    from app.services.transactions import lock_profile
    from app.services import receipts
    from app.services.pricing_checks import assert_lease
    user=get_or_create_default_user(db);op='reward-quote';fp,prior=begin(db,user,op,body,create=True)
    if prior is not None:return prior
    assert_lease(db)
    existing=db.query(PricingQuote).filter_by(user_id=user.id,request_key=str(body.request_key)).first()
    if existing:
        if existing.fingerprint!=fp:raise HTTPException(409,'同一价格请求的内容已变化。')
        if existing.state=='accepted':
            item=get_owned(db,ShopItem,existing.item_id)
            return finish(db,user,op,body,fp,existing,{**fields(existing),'item':fields(item)})
        raise HTTPException(409 if existing.state=='running' else 503,'定价仍在进行或上次请求已结束；请查看记录，失败后保留草稿再主动重试。')
    item=get_owned(db,ShopItem,body.item_id) if body.item_id else None
    if item and (body.item_version!=item.updated_at or not item.enabled or item.repriced_on==trial_rules.day(db,user)):raise HTTPException(409,'商品已更新、停用或今天已处理价格，请刷新后查看。')
    versions=analysis_jobs.configuration(db,user.id);item_version=item.updated_at.isoformat() if item else None;economic=economy_context(db,user)
    # Persist the request before the paid call: same-key concurrent/unknown retries
    # see running/failed instead of calling the supplier a second time.
    row=PricingQuote(user_id=user.id,item_id=item.id if item else None,state='running',request_key=str(body.request_key),fingerprint=fp,
        payload=body.model_dump(mode='json',exclude={'request_key','expected_version'}),result={},
        context={'config':versions,'item_version':item_version,'day':trial_rules.day(db,user),'sources':ai_context.sources(),
            'background':ai_context.CURRENT.get()['background'],'economy':economic,'automatic_permission':body.auto_check})
    db.add(row);db.flush();row_id=row.id;db.commit()
    detail=body.name+('；'+body.description if body.description else '')
    try:
        priced=shop_service.price_item(db,user,detail,body.price_yuan)
        lock_profile(db,user.id);assert_lease(db)
        db.refresh(row)
        row.result=priced;row.state='suggested'
        applied=apply_quote(db,user,row)
        return finish(db,user,op,body,fp,row,{**fields(row),'item':fields(applied)})
    except Exception as exc:
        db.rollback();lock_profile(db,user.id)
        failed=db.query(PricingQuote).filter_by(id=row_id,state='running').first()
        if failed:
            from app.services.model_validation import controlled_error
            code='CONTEXT_CHANGED' if isinstance(exc,ValueError) and str(exc)=='AI_SOURCES_CHANGED' else controlled_error(exc)[0] if not isinstance(exc,HTTPException) else 'CONTEXT_CHANGED' if exc.status_code==409 else 'PRICING_FAILED'
            failed.state='failed';failed.result={'error_code':code};failed.version+=1;db.commit()
        from app.services.llm_service import LLMError
        if isinstance(exc,LLMError):raise HTTPException(503,str(exc)) from None
        if isinstance(exc,ValueError) and str(exc)=='AI_SOURCES_CHANGED':raise HTTPException(409,'资料或用途许可已变化，旧价格结果不应用。') from None
        raise


@router.post('/reward-quotes/{quote_id}/accept')
def accept(quote_id:int,body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'reward-accept:{quote_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,PricingQuote,quote_id)
    # Compatibility for old clients receiving an already auto-applied result.
    if row.state=='accepted':
        item=get_owned(db,ShopItem,row.item_id)
        return finish(db,user,op,body,fp,row,{'quote':fields(row),'item':fields(item)})
    version(row,body.expected_version);item=apply_quote(db,user,row)
    return finish(db,user,op,body,fp,row,{'quote':fields(row),'item':fields(item)})
