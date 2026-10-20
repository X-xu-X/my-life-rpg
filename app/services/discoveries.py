"""Deterministic discovery and model suggestions share semantic identities, never money."""
from datetime import timedelta,datetime,date
import calendar
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.models import Achievement,CoinLedger
from app.models.policies import DynamicCandidate,DynamicAward,EconomicRule
from app.services import economy,trial_rules,coin_service
from app.services.time_service import utc_now,local_day

def discover(db,user):
    from app.services.record_metrics import metrics
    data=metrics(db,user)['metrics']
    for kind,label in [('event','事件'),('diary','日记')]:
        for target in (3,7,30):
            criteria={'metric':kind+'_saved_days','shape':'consecutive_days','target':target,'start':None,'end':None}
            if data[kind+'_saved_days']['longest_contiguous_days']>=target:propose(db,user,label+'连续保存'+str(target)+'天',criteria)
        if data[kind+'_saved_days']['count']>=100:propose(db,user,label+'累计保存100天',{'metric':kind+'_saved_days','shape':'total_days','target':100,'start':None,'end':None})
        months={d[:7] for d in data[kind+'_saved_days']['dates']}
        for month in sorted(months):
            start=date.fromisoformat(month+'-01');end=date(start.year,start.month,calendar.monthrange(start.year,start.month)[1])
            criteria={'metric':kind+'_saved_days','shape':'calendar_month','target':1,'start':str(start),'end':str(end)}
            if economy.verify(db,user,criteria)['eligible']:propose(db,user,label+'完整自然月保存',criteria)

def propose(db,user,name,criteria):
    if criteria.get('shape')=='calendar_month':criteria={**criteria,'target':1}
    key=economy.semantic(criteria);row=db.query(DynamicCandidate).filter_by(user_id=user.id,semantic_key=key).first()
    policy=terms(type('Candidate',(),{'criteria':criteria})())
    if not row and policy:
        for old in db.query(DynamicCandidate).filter(DynamicCandidate.user_id==user.id,DynamicCandidate.state.in_(('ignored','claimed'))).all():
            prior=terms(old)
            if prior and prior['equivalence']==policy['equivalence']:return old
    if not row:
        row=DynamicCandidate(user_id=user.id,semantic_key=key,name=name[:100],criteria=criteria,evidence=economy.verify(db,user,criteria));db.add(row);db.flush()
    return row

def suggestions(db,user,result):
    candidates=result.get('achievement_candidates',[])
    if not isinstance(candidates,list):return
    for raw in candidates[:5]:
        if not isinstance(raw,dict):continue
        criteria={k:raw.get(k) for k in ('metric','shape','target','start','end')}
        if criteria['metric'] not in ('event_saved_days','diary_saved_days') or criteria['shape'] not in ('total_days','consecutive_days','calendar_month') or type(criteria['target']) is not int or not 1<=criteria['target']<=10000:continue
        try:propose(db,user,str(raw.get('name','已核实记录候选')),criteria)
        except (HTTPException,ValueError,TypeError):continue

def terms(row):
    c=row.criteria
    if c.get('metric') not in ('event_saved_days','diary_saved_days'):return None
    kind=c['metric'].split('_')[0];shape=c['shape'];target=1 if shape=='calendar_month' else c['target']
    # Window variants cannot create a second copy of the same lifetime milestone.
    if shape=='consecutive_days' and target in (3,7,30):
        return {'amount':{3:10,7:30,30:100}[target],'equivalence':f'{kind}_streak_{target}','category':'fixed',
            'legacy_code':f'journal_streak_{target}' if kind=='diary' else None}
    important=shape=='calendar_month' or shape=='consecutive_days' and target>=30 or shape=='total_days' and target>=100
    return {'amount':30 if important else 10,'equivalence':f'{kind}_{shape}_{target}','category':'dynamic','legacy_code':None}

def claim(db,user,row):
    config=trial_rules.account(db,user)
    if not config or not config.enabled:raise HTTPException(409,'请先明确采用试用规则。')
    evidence=economy.verify(db,user,row.criteria);policy=terms(row)
    if not evidence['eligible'] or not policy or row.state!='candidate':raise HTTPException(409,'缺少已批准映射、证据不足或候选已处理。')
    coin_service.require_baseline(db,user)
    legacy=policy['legacy_code'];key='fixed:'+legacy if legacy else 'trial:'+policy['equivalence']
    if db.query(DynamicAward).filter(DynamicAward.user_id==user.id,DynamicAward.equivalence_key.in_((key,'trial:'+policy['equivalence']))).first():raise HTTPException(409,'等价里程碑已领取。')
    if legacy and (db.query(DynamicAward).filter_by(user_id=user.id,equivalence_key='fixed:'+legacy).first() or db.query(Achievement).filter_by(user_id=user.id,code=legacy).filter(Achievement.unlocked_at.is_not(None)).first() or db.query(CoinLedger).filter_by(user_id=user.id,source='journal_streak',reason=f"连续写日记 {row.criteria['target']} 天").first()):raise HTTPException(409,'等价历史坚持奖励已领取。')
    now=utc_now();today=trial_rules.day(db,user);recent=[]
    for award in db.query(DynamicAward).filter_by(user_id=user.id).all():
        if award.evidence.get('trial_category')=='dynamic':recent.append(award)
    if policy['category']=='dynamic':
        daily=sum(a.amount for a in recent if a.evidence.get('claim_day')==today)
        rolling=sum(a.amount for a in recent if datetime.fromisoformat(a.evidence['claimed_at'])>now-timedelta(days=30))
        if daily+policy['amount']>40 or rolling+policy['amount']>100:raise HTTPException(409,'动态成就额度已满；候选保留，可稍后再领取。')
    rule=db.query(EconomicRule).filter_by(kind='trial_discovery',version=1).first()
    if not rule:
        try:
            with db.begin_nested():
                rule=EconomicRule(kind='trial_discovery',version=1,enabled=True,payload={'approved':True,'version':trial_rules.VERSION});db.add(rule);db.flush()
        except IntegrityError:rule=db.query(EconomicRule).filter_by(kind='trial_discovery',version=1).one()
    badge=Achievement(user_id=user.id,code='trial_'+row.semantic_key[:40],name=row.name,description='按首次保存日核实；'+trial_rules.VERSION,kind='verified',coin_reward=policy['amount'],unlocked_at=now)
    db.add(badge);db.flush();evidence={**evidence,'trial_category':policy['category'],'claim_day':today,'claimed_at':now.isoformat()}
    db.add(DynamicAward(user_id=user.id,equivalence_key=key,candidate_id=row.id,rule_id=rule.id,achievement_id=badge.id,amount=policy['amount'],evidence=evidence))
    coin_service.grant(db,user,policy['amount'],'achievement',row.name,'achievement',badge.id)
    row.state='claimed';row.version+=1;row.evidence=evidence
