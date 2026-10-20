"""Targeted independent probes; all users/data/keys are synthetic."""
import os,sys,json,faulthandler
from datetime import timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
os.environ['DB_URL']='sqlite://'
os.environ['DEEPSEEK_API_KEY']=''
os.environ.pop('TEST_PG_URL',None)
HERE=Path(__file__).resolve().parent
debug=(HERE/'probe-stacks.log').open('w',encoding='utf-8')
faulthandler.dump_traceback_later(30,repeat=True,file=debug)
from unittest.mock import patch
from tests.test_full_system import FullSystemTests
from app.services.time_service import utc_now,local_day

results={}
def run(name,fn):
    case=FullSystemTests()
    print('START',name,flush=True)
    case.setUp()
    try:
        case.register();case.configure_model()
        results[name]=fn(case)
        print(json.dumps({name:results[name]},ensure_ascii=False),flush=True)
    finally:case.tearDown()

def plan_minutes(t):
    t.adopt()
    day=str(local_day(utc_now(),'Asia/Shanghai'))
    configured=t.write('/plan-schedules',{'name':'英语学习45分钟','frequency':'daily','start':day,'planned_minutes':45})
    row=configured.json()
    timer=t.write('/timers',{'kind':'plan','source_id':row['id'],'source_version':row['version']},0)
    return {'configure_45_status':configured.status_code,'rule':row.get('rule'),'timer_status':timer.status_code,'timer_limit_seconds':timer.json().get('limit_seconds')}


def legacy_focus(t):
    from app.services import analysis_jobs
    day=str(local_day(utc_now(),'Asia/Shanghai'))
    care=t.client.get('/api/care').json()
    old=t.write('/life-checklists/'+day,{'enabled':False,'entries':{'PRIVATE_FOCUS_SENTINEL':'skipped'}},0,'PUT')
    diary=t.write('/diaries/'+day,{'content':'今天只想分析这段普通文字','ai_permission':'allowed'},0,'PUT').json()['diary']
    session=t.write('/diaries/'+day+'/review-sessions',version=diary['content_version']).json()
    queued=t.write('/review-sessions/'+str(session['id'])+'/analyze',version=session['version'])
    sent=[]
    def fake(messages,**kwargs):
        sent.append(messages)
        return {'questions':[],'summary':'合成回顾','analysis':[]}
    with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):
        analysis_jobs.process(t.Session,analysis_jobs.claim(t.Session))
    return {'care_config':care.get('config'),'legacy_save_status':old.status_code,'queue_status':queued.status_code,
            'marker_in_model_payload':'PRIVATE_FOCUS_SENTINEL' in json.dumps(sent),
            'payload':json.loads(sent[0][-1]['content']) if sent else None}

def before_baseline(t):
    adopted=t.write('/trial',{'acknowledge':True,'base_minutes':30},0,'PUT')
    t.event('建档前先保存一次')
    daily=t.client.get('/api/trial').json()['daily']
    t.client._transport.raise_server_exceptions=False
    claimed=t.write('/trial/first-record/claim',version=daily['version'])
    t.client._transport.raise_server_exceptions=True
    neutral=t.client.post('/api/onboarding/neutral',json={'acknowledge':True})
    retried=t.write('/trial/first-record/claim',version=daily['version'])
    return {'adopt_status':adopted.status_code,'claim_status':claimed.status_code,'claim':claimed.text,
            'neutral_status':neutral.status_code,'retry_status':retried.status_code,'balance_after_retry':t.client.get('/api/coins').json()['balance']}

def pricing_usage(t):
    from app.models.full_system import TimeSession,VoucherAllowance
    from app.models import Redemption
    t.adopt();item=t.reward()
    coupon=t.client.post(f"/api/shop/items/{item['id']}/redeem",json={'request_key':__import__('uuid').uuid4().hex,'expected_version':item['updated_at']}).json()['redemption']
    now=utc_now();uid=t.user_id()
    with t.Session() as db:
        db.get(Redemption,coupon['id']).status='fulfilled'
        db.add(VoucherAllowance(user_id=uid,redemption_id=coupon['id'],total_seconds=1800,used_seconds=1800))
        row=TimeSession(user_id=uid,kind='voucher',source_id=coupon['id'],state='ended',started_at=now-timedelta(hours=3),
            last_sync_at=now,timezone='Asia/Shanghai',local_date=str(local_day(now,'Asia/Shanghai')),limit_seconds=1800,
            contract={'mode':'gentle'},intervals=[{'start':(now-timedelta(hours=3)).isoformat(),'end':now.isoformat()}],
            settlement={'actual_seconds':3600,'day':str(local_day(now,'Asia/Shanghai')),'penalty_charged':0,'ontime_awarded':0,'consumed_seconds':1800},history=[])
        db.add(row);db.commit();timer_id=row.id
    messages=[]
    def fake(sent,**kwargs):
        messages.append(sent)
        return {'coin_price':20,'pricing_reason':'合成价格，非质量评测','worth_note':''}
    with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):
        a=t.write('/reward-quotes',{'name':'再玩半小时','reward_kind':'entertainment','minutes':30})
        with t.Session() as db:
            row=db.get(TimeSession,timer_id);row.settlement={**row.settlement,'actual_seconds':10800};row.version+=1;db.commit()
        b=t.write('/reward-quotes',{'name':'再玩半小时','reward_kind':'entertainment','minutes':30})
    return {'first_status':a.status_code,'second_status':b.status_code,'actual_seconds_histories':[3600,10800],
            'identical_model_payloads':len(messages)==2 and messages[0]==messages[1],
            'model_payload':messages[0] if messages else None}

def export_history(t):
    day=str(local_day(utc_now(),'Asia/Shanghai'))
    old=t.write('/diaries/'+day,{'content':'OLD_DIARY_HISTORY_SENTINEL','ai_permission':'private'},0,'PUT')
    new=t.write('/diaries/'+day,{'content':'当前版本原文','ai_permission':'private'},1,'PUT')
    result=t.client.get('/api/export?format=json&kind=diary&include_history=false&include_game=false')
    readable=t.client.get('/api/export?format=markdown&kind=diary&include_history=false&include_game=false')
    data=result.json()
    return {'save_statuses':[old.status_code,new.status_code],'export_status':result.status_code,
            'selection_records_revisions':data['records'][0]['revisions'],
            'json_contains_old_original':'OLD_DIARY_HISTORY_SENTINEL' in result.text,
            'exported_diary_revisions':data['tables'].get('diary_revisions'),
            'markdown_contains_old_original':'OLD_DIARY_HISTORY_SENTINEL' in readable.text}

try:
    run('plan_minutes',plan_minutes)
    run('legacy_focus_permission',legacy_focus)
    run('signup_claim_before_baseline',before_baseline)
    run('pricing_actual_usage',pricing_usage)
    run('export_history_option',export_history)
finally:
    faulthandler.cancel_dump_traceback_later()
    (HERE/'probe-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    debug.close()
