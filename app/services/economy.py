"""Optional, explicitly configured rewards; existing settlement transaction remains authoritative."""
from datetime import date,timedelta
import calendar,hashlib,json
from fastapi import HTTPException
from app.models import Event,Goal,AIJudgment,Achievement
from app.models.policies import EconomicRule,Mainline,RewardPreview,MainlineAward,DynamicCandidate,DynamicAward
from app.services import coin_service
from app.services.workflow_common import get_owned,fields
from app.services.time_service import local_day,utc_now


def latest(db,kind):return db.query(EconomicRule).filter_by(kind=kind).order_by(EconomicRule.version.desc()).first()


def active_rule(db,kind):
    rule=latest(db,kind)
    if not rule or not rule.enabled or not rule.payload.get('approved'):raise HTTPException(409,'正式规则尚未配置确认，此能力未开通。')
    if rule.payload['effective_from']>str(local_day(utc_now(),'Asia/Shanghai')):raise HTTPException(409,'规则尚未生效。')
    return rule


def preview(db,user,body):
    rule=active_rule(db,'mainline');mainline=get_owned(db,Mainline,body.mainline_id);event=get_owned(db,Event,body.event_id);judgment=get_owned(db,AIJudgment,body.judgment_id)
    goal=get_owned(db,Goal,mainline.goal_id)
    if db.query(Mainline).filter_by(user_id=user.id,active=True).count()>rule.payload['max_active']:raise HTTPException(409,'主线数量超过当前已确认上限，请先停用多余主线。')
    if not mainline.active or mainline.version!=body.mainline_version or event.is_deleted or event.record_kind=='diary' or event.origin=='challenge' or event.content_version!=body.event_version or judgment.event_id!=event.id or judgment.status not in ('pending','adjusted'):raise HTTPException(409,'事实、主线或判定版本不可用于预览。')
    tier=next((r for r in sorted(rule.payload['tiers'],key=lambda r:r['amount'],reverse=True) if body.minutes>=r['min_minutes'] and (not r['result_required'] or body.result)),None)
    amount=tier['amount'] if tier else 0
    cap_date=event.occurred_on or str(local_day(event.occurred_at,event.timezone_at_capture)) if rule.payload['cap_basis']=='content' else str(local_day(utc_now(),user.timezone))
    used=sum(a.amount for a in db.query(MainlineAward).filter_by(user_id=user.id,cap_date=cap_date).all())
    amount=min(amount,rule.payload['per_fact_cap'],max(0,rule.payload['daily_cap']-used))
    from app.services.facts import identity
    fact_id=identity(db,event)
    row=RewardPreview(user_id=user.id,mainline_id=mainline.id,event_id=event.id,judgment_id=judgment.id,rule_id=rule.id,amount=amount,
        snapshot={'fact_id':fact_id,'event':fields(event),'judgment_version':judgment.updated_at.isoformat(),'mainline':fields(mainline),'goal':fields(goal),
            'rule':fields(rule),'tier':tier,'minutes':body.minutes,'result':body.result,'evidence':body.evidence,'cap_date':cap_date})
    db.add(row);db.flush();return row


def lock_rules(db):
    from sqlalchemy import text
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(61111220)'))


def prepare(db,user,preview_id,judgment,event):
    lock_rules(db)
    row=get_owned(db,RewardPreview,preview_id);rule=active_rule(db,'mainline');mainline=get_owned(db,Mainline,row.mainline_id);goal=get_owned(db,Goal,mainline.goal_id)
    if row.state!='pending' or row.rule_id!=rule.id or row.judgment_id!=judgment.id or row.event_id!=event.id or row.snapshot['event']['content_version']!=event.content_version or row.snapshot['judgment_version']!=judgment.updated_at.isoformat() or row.snapshot['mainline']['version']!=mainline.version or not mainline.active or row.snapshot['goal']['updated_at']!=goal.updated_at.isoformat():raise HTTPException(409,'预览来源或规则已有变化，请重新预览。')
    from app.services.facts import identity
    if row.snapshot['fact_id']!=identity(db,event):raise HTTPException(409,'事实关联已变化，请重新预览。')
    cap_date=row.snapshot['cap_date']
    if rule.payload['cap_basis']=='confirmation' and cap_date!=str(local_day(utc_now(),user.timezone)):raise HTTPException(409,'已换日，请重新预览。')
    used=sum(a.amount for a in db.query(MainlineAward).filter_by(user_id=user.id,cap_date=cap_date).all())
    if used+row.amount>rule.payload['daily_cap']:raise HTTPException(409,'额度已变化，请重新预览。')
    return row,rule


def award(db,user,row,rule,event):
    from app.services.facts import identity
    fact_id=identity(db,event)
    if db.query(MainlineAward).filter_by(fact_id=fact_id).first():raise HTTPException(409,'此事实的主线奖励已领取。')
    db.add(MainlineAward(user_id=user.id,fact_id=fact_id,preview_id=row.id,rule_id=rule.id,cap_date=row.snapshot['cap_date'],amount=row.amount))
    if row.amount:coin_service.grant(db,user,row.amount,'mainline_reward',reason='经确认主线规则 v'+str(rule.version),ref_type='event',ref_id=event.id)
    row.state='confirmed';row.version+=1


def verify(db,user,criteria):
    from app.services.record_metrics import metrics
    metric=metrics(db,user)['metrics'][criteria['metric']]
    days=sorted(date.fromisoformat(d) for d in metric['dates'] if (not criteria.get('start') or d>=criteria['start']) and (not criteria.get('end') or d<=criteria['end']))
    if criteria['shape']=='calendar_month':
        start=date.fromisoformat(criteria['start']);end=date.fromisoformat(criteria['end'])
        if start.day!=1 or end!=date(start.year,start.month,calendar.monthrange(start.year,start.month)[1]):raise HTTPException(422,'一个月需明确完整自然月起止，不等同30天。')
        count=len(days);target=end.day
    elif criteria['shape']=='consecutive_days':
        count=run=0;last=None
        for day in days:run=run+1 if last and day-last==timedelta(days=1) else 1;count=max(count,run);last=day
        target=criteria['target']
    else:count=len(days);target=criteria['target']
    events=db.query(Event).filter(Event.user_id==user.id,Event.id.in_(metric['event_ids']),Event.is_deleted.is_(False)).all()
    dates={str(d) for d in days}
    events=[e for e in events if (e.occurred_on or str(local_day(e.occurred_at,e.timezone_at_capture)) if '_content_' in criteria['metric'] else e.saved_on) in dates]
    return {'eligible':count>=target,'count':count,'target':target,'dates':[str(d) for d in days],
        'sources':[{'id':e.id,'version':e.content_version} for e in events],'policy_version':'candidate-date-v1'}


def semantic(criteria):return hashlib.sha256(json.dumps({'policy':'candidate-date-v1',**criteria},sort_keys=True).encode()).hexdigest()


def claim_dynamic(db,user,row):
    lock_rules(db)
    rule=active_rule(db,'dynamic');evidence=verify(db,user,row.criteria)
    if row.state!='candidate' or not evidence['eligible']:raise HTTPException(409,'证据不满足或已处理。')
    amount=rule.payload['rewards'].get(row.semantic_key)
    if amount is None:raise HTTPException(409,'此语义身份尚未配置授奖金额，候选保留。')
    if db.query(DynamicAward).filter_by(candidate_id=row.id).first():raise HTTPException(409,'已领取。')
    used=sum(a.amount for a in db.query(DynamicAward).filter_by(user_id=user.id,rule_id=rule.id).all())
    if used+amount>rule.payload['user_total_cap']:raise HTTPException(409,'已达此版本授奖上限。')
    fixed_code=rule.payload.get('fixed_equivalences',{}).get(row.semantic_key)
    equivalence_key=('fixed:'+fixed_code) if fixed_code and not rule.payload['allow_fixed_stack'] else None
    if equivalence_key and (db.query(Achievement).filter(Achievement.user_id==user.id,Achievement.code==fixed_code,Achievement.unlocked_at.is_not(None)).first() or db.query(DynamicAward).filter_by(user_id=user.id,equivalence_key=equivalence_key).first()):raise HTTPException(409,'等价固定/动态奖励已领取，当前规则不允许叠加。')
    evidence={**evidence,'fixed_equivalence':fixed_code,'allow_fixed_stack':rule.payload['allow_fixed_stack']}
    badge=Achievement(user_id=user.id,code='verified_'+row.semantic_key[:40],name=row.name,description='已核实 '+str(evidence['count'])+' 天；candidate-date-v1',kind='verified',coin_reward=amount,unlocked_at=utc_now())
    db.add(badge);db.flush()
    db.add(DynamicAward(user_id=user.id,candidate_id=row.id,equivalence_key=equivalence_key,rule_id=rule.id,achievement_id=badge.id,amount=amount,evidence=evidence))
    if amount:coin_service.grant(db,user,amount,'achievement',reason=row.name,ref_type='achievement',ref_id=badge.id)
    row.evidence=evidence;row.state='claimed';row.version+=1
