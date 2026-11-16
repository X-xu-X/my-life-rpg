"""Bounded, explicit POST-enqueued daily price checks, consumed by the worker."""
from contextvars import ContextVar
from datetime import timedelta
from uuid import uuid4
import threading
from fastapi import HTTPException
from sqlalchemy import func
from app.models import User,ShopItem
from app.models.daily_use import PricingCheck
from app.services.time_service import utc_now,USER_ZONE
from app.services.transactions import lock_profile
from app.services import trial_rules,llm_config

LEASE=ContextVar('pricing_check_lease',default=None)
_claim_lock=threading.Lock()
MAX_DAILY=10


def assert_lease(db):
    value=LEASE.get()
    if value:
        row=db.query(PricingCheck).filter_by(id=value[0]).populate_existing().first()
        if not row or row.state!='running' or row.lease_token!=value[1] or row.started_at<utc_now()-timedelta(minutes=5):raise HTTPException(409,'定价任务已结束或租约过期，晚回结果不应用。')


def enqueue(db,user):
    from app.services.llm_service import LLMError
    try:llm_config.resolve_llm_config(db,user.id,llm_config.PURPOSE_JUDGE)
    except LLMError:return {'queued':0,'reason':'model_not_ready'}
    today=trial_rules.day(db,user)
    previous=db.query(PricingCheck).filter_by(user_id=user.id,local_date=today).all()
    budget=max(0,MAX_DAILY-len(previous));ids={r.item_id for r in previous};created=[]
    attempted=dict(db.query(PricingCheck.item_id,func.max(PricingCheck.local_date)).filter_by(user_id=user.id).group_by(PricingCheck.item_id).all())
    eligible=[item for item in db.query(ShopItem).filter_by(user_id=user.id,enabled=True,auto_pricing=True).all() if item.id not in ids and item.repriced_on!=today]
    # Never-attempted / least-recently-served first, including failed attempts.
    # The daily cap must not permanently favor low IDs after each midnight.
    eligible.sort(key=lambda item:(max(attempted.get(item.id,''),item.repriced_on or ''),item.id))
    for item in eligible[:min(3,budget)]:
        row=PricingCheck(user_id=user.id,item_id=item.id,local_date=today,request_key=str(uuid4()))
        db.add(row);created.append(row)
    remaining=len(eligible)-len(created);budget_remaining=budget-len(created)
    db.flush();return {'queued':len(created),'ids':[r.id for r in created],'remaining':remaining,'budget_remaining':budget_remaining,
        'has_more':remaining>0 and budget_remaining>0,'reason':'daily_limit' if remaining and not budget_remaining else 'covered' if not remaining else 'next_batch'}


def claim(factory):
    with _claim_lock,factory() as db:
        stale=db.query(PricingCheck).filter(PricingCheck.state=='running',PricingCheck.started_at<utc_now()-timedelta(minutes=5)).all()
        for row in stale:row.state='failed';row.error_code='RESULT_UNKNOWN';row.lease_token=None;row.version+=1
        row=db.query(PricingCheck).filter_by(state='queued').order_by(PricingCheck.id).with_for_update(skip_locked=True).first()
        if not row:db.commit();return None
        row.state='running';row.lease_token=str(uuid4());row.started_at=utc_now();row.version+=1
        result=(row.id,row.lease_token);db.commit();return result


def process(factory,claimed):
    if not claimed:return
    from app.services.llm_service import USAGE_FACTORY
    token=LEASE.set(claimed);usage_token=USAGE_FACTORY.set(factory);zone_token=None
    try:
        with factory() as db:
            row=db.get(PricingCheck,claimed[0])
            if not row or row.lease_token!=claimed[1]:return
            user=db.get(User,row.user_id);db.info['user_id']=user.id;zone_token=USER_ZONE.set(user.timezone)
            assert_lease(db)
            item=db.get(ShopItem,row.item_id)
            if user.status!='active' or not item or not item.enabled or not item.auto_pricing or row.local_date!=trial_rules.day(db,user):raise HTTPException(409,'价格检查的日期或授权已变化。')
            from app.routers.reward_quotes import QuoteIn,quote
            result=quote(QuoteIn(request_key=row.request_key,expected_version=0,name=item.name,
                description=item.description,price_yuan=item.price_yuan,
                item_id=item.id,item_version=item.updated_at,auto_check=True),db)
            lock_profile(db,user.id);db.refresh(row);assert_lease(db)
            row.state='completed';row.quote_id=result['id'];row.completed_at=utc_now();row.lease_token=None;row.version+=1;db.commit()
    except Exception as exc:
        with factory() as db:
            row=db.query(PricingCheck).filter_by(id=claimed[0],lease_token=claimed[1],state='running').first()
            if row:
                from app.services.model_validation import controlled_error
                row.state='failed';row.error_code='CONTEXT_CHANGED' if isinstance(exc,HTTPException) and exc.status_code==409 else controlled_error(exc)[0]
                row.completed_at=utc_now();row.lease_token=None;row.version+=1;db.commit()
    finally:
        LEASE.reset(token);USAGE_FACTORY.reset(usage_token)
        if zone_token is not None:USER_ZONE.reset(zone_token)
