import hashlib,json
from datetime import datetime
from decimal import Decimal,ROUND_HALF_UP
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
    reward_kind:Literal['item','experience','entertainment']='item'
    minutes:int=Field(30,ge=1,le=1440)
    price_yuan:float|None=Field(None,ge=0,allow_inf_nan=False)
    description:str=Field('',max_length=2000)
    item_id:int|None=None
    item_version:datetime|None=None

@router.get('/reward-quotes')
def read(db:Session=Depends(get_db)):
    user=get_or_create_default_user(db)
    return {'items':[fields(q) for q in db.query(PricingQuote).filter_by(user_id=user.id).order_by(PricingQuote.id.desc()).limit(30).all()]}

@router.post('/reward-quotes')
@model_context
def quote(body:QuoteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op='reward-quote';fp,prior=begin(db,user,op,body,create=True)
    if prior is not None:return prior
    item=get_owned(db,ShopItem,body.item_id) if body.item_id else None
    if item and body.item_version!=item.updated_at:raise HTTPException(409,'商品已更新。')
    versions=analysis_jobs.configuration(db,user.id);item_version=item.updated_at.isoformat() if item else None;economic=economy_context(db,user)
    detail=body.name+('；每次 '+str(body.minutes)+' 分钟' if body.reward_kind=='entertainment' else '')+'；'+body.description
    try:priced=shop_service.price_item(db,user,detail,body.price_yuan)
    except Exception as exc:
        from app.services.llm_service import LLMError
        if isinstance(exc,LLMError):raise HTTPException(503,str(exc)) from None
        raise
    from app.services.transactions import lock_profile
    lock_profile(db,user.id)
    if analysis_jobs.configuration(db,user.id)!=versions:raise HTTPException(409,'模型配置已变化。')
    if economy_context(db,user)!=economic:raise HTTPException(409,'确认收入、购买、使用或主线背景已变化，请重新定价。')
    from app.services import receipts
    fp,prior=receipts.replay(db,user.id,op,body,require_version=False)
    if prior is not None:return prior
    if item:
        db.refresh(item)
        if item.updated_at.isoformat()!=item_version:raise HTTPException(409,'商品已更新，请重试。')
        current=max(1,item.coin_price)
        lower=max(1,int((Decimal(current)*Decimal('0.8')).quantize(Decimal('1'),rounding=ROUND_HALF_UP)))
        upper=max(1,int((Decimal(current)*Decimal('1.2')).quantize(Decimal('1'),rounding=ROUND_HALF_UP)))
        priced={**priced,'model_price':priced['coin_price'],'coin_price':max(lower,min(upper,priced['coin_price'])),'bounds':[lower,upper]}
    row=PricingQuote(user_id=user.id,item_id=item.id if item else None,request_key=str(body.request_key),fingerprint=fp,
        payload=body.model_dump(mode='json',exclude={'request_key','expected_version'}),result=priced,
        context={'config':versions,'item_version':item_version,'sources':ai_context.sources(),'background':ai_context.CURRENT.get()['background'],'economy':economic})
    db.add(row);db.flush()
    return finish(db,user,op,body,fp,row,fields(row))

@router.post('/reward-quotes/{quote_id}/accept')
def accept(quote_id:int,body:WriteIn,db:Session=Depends(get_db)):
    user=get_or_create_default_user(db);op=f'reward-accept:{quote_id}';fp,prior=begin(db,user,op,body)
    if prior is not None:return prior
    row=get_owned(db,PricingQuote,quote_id);version(row,body.expected_version)
    if row.state!='suggested' or analysis_jobs.configuration(db,user.id)!=row.context['config'] or not ai_context.valid(db,row.context['sources'],user.id) or ai_context.background(db,user.id)!=row.context['background']:raise HTTPException(409,'建议或背景已变化，请重新定价。')
    if economy_context(db,user)!=row.context['economy']:raise HTTPException(409,'确认收入或使用背景已变化，请重新定价。')
    item=get_owned(db,ShopItem,row.item_id) if row.item_id else None
    today=trial_rules.day(db,user)
    if item:
        if item.updated_at.isoformat()!=row.context['item_version'] or item.repriced_on==today:raise HTTPException(409,'商品已变化或今天已应用 AI 改价。')
        item.repriced_on=today
    else:
        item=ShopItem(user_id=user.id,name=row.payload['name'],kind='custom',reward_kind=row.payload['reward_kind'],
            duration_seconds=row.payload['minutes']*60 if row.payload['reward_kind']=='entertainment' else None,price_yuan=row.payload['price_yuan'],base_coin_price=row.result['coin_price'])
        db.add(item);db.flush();row.item_id=item.id
    item.coin_price=row.result['coin_price'];item.pricing_reason=row.result['pricing_reason'];item.worth_note=row.result['worth_note']
    row.state='accepted';row.version+=1
    db.flush()
    return finish(db,user,op,body,fp,row,{'quote':fields(row),'item':fields(item)})
