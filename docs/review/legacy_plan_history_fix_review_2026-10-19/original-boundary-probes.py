"""Independent boundary probes for the repaired paths. Synthetic SQLite only."""
import os,sys,json
from pathlib import Path
from datetime import timedelta
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
os.environ['DB_URL']='sqlite://';os.environ['DEEPSEEK_API_KEY']='';os.environ.pop('TEST_PG_URL',None)
from tests.test_full_system import FullSystemTests
from app.services.time_service import utc_now,local_day
from app.models.workflow import PlanSchedule
HERE=Path(__file__).resolve().parent
results={}
def run(name,fn):
 t=FullSystemTests();t.setUp()
 try:t.register();results[name]=fn(t)
 finally:t.tearDown()
def csv_history(t):
 day=str(local_day(utc_now(),'Asia/Shanghai'))
 a=t.write('/diaries/'+day,{'content':'OLD_ORIGINAL_NO_REVIEW_SENTINEL','ai_permission':'private'},0,'PUT')
 b=t.write('/diaries/'+day,{'content':'CURRENT_ORIGINAL_NO_REVIEW','ai_permission':'private'},1,'PUT')
 out={}
 for history in ('true','false'):
  for fmt in ('json','markdown','html','csv'):
   r=t.client.get(f'/api/export?format={fmt}&kind=diary&include_history={history}&include_game=false')
   out[fmt+'_'+history]={'status':r.status_code,'old_present':'OLD_ORIGINAL_NO_REVIEW_SENTINEL' in r.text,'current_present':'CURRENT_ORIGINAL_NO_REVIEW' in r.text}
   (HERE/('no-review-history-'+history+'.'+{'markdown':'md'}.get(fmt,fmt))).write_text(r.text,encoding='utf-8')
 return {'save_statuses':[a.status_code,b.status_code],'exports':out}
def legacy_plan_future(t):
 t.adopt();today=local_day(utc_now(),'Asia/Shanghai')
 r=t.write('/plan-schedules',{'name':'旧日程','frequency':'daily','start':str(today)})
 plan=r.json()
 with t.Session() as db:
  p=db.get(PlanSchedule,plan['id']);p.rule={k:v for k,v in p.rule.items() if k!='planned_minutes'};p.history=[];db.commit()
 before=t.client.get('/api/plan-schedules').json()[0]
 edited=t.write('/plan-schedules/'+str(plan['id']),{'name':'明日起45分钟','frequency':'daily','start':str(today+timedelta(days=1)),'planned_minutes':45},1,'PUT')
 after=t.client.get('/api/plan-schedules').json()[0]
 started=t.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':2})
 return {'before':before,'edit_status':edited.status_code,'after':after,'start_today_status':started.status_code,'start_today_response':started.json()}
run('csv_history_without_review',csv_history)
run('legacy_plan_future_edit',legacy_plan_future)
(HERE/'boundary-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
