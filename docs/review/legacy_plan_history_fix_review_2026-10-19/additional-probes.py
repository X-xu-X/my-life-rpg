"""Independent write-boundary checks for the legacy baseline capture."""
import os,sys,json
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
os.environ['DB_URL']='sqlite://';os.environ['DEEPSEEK_API_KEY']='';os.environ.pop('TEST_PG_URL',None)
from tests.test_full_system import FullSystemTests
from app.models.workflow import PlanSchedule
from app.services.time_service import utc_now,local_day
HERE=Path(__file__).resolve().parent
case=FullSystemTests();case.setUp();checks=[]
def check(name,condition):
 checks.append({'name':name,'passed':bool(condition)});assert condition,name
try:
 case.register();case.adopt();today=local_day(utc_now(),'Asia/Shanghai')
 body={'name':'原20分钟计划','frequency':'daily','start':str(today-timedelta(days=3)),'planned_minutes':20}
 created=case.write('/plan-schedules',body).json();pid=created['id']
 check('new schedule retains exactly one revision',len(created['history'])==1)
 with case.Session() as db:
  row=db.get(PlanSchedule,pid);row.history=[];db.commit()
 invalid=case.write('/plan-schedules/'+str(pid),{**body,'start':str(today-timedelta(days=1))},1,'PUT')
 check('invalid past effective date rejected',invalid.status_code==422)
 with case.Session() as db:check('rejected edit does not capture baseline',db.get(PlanSchedule,pid).history==[])
 key=str(uuid4());future={k:v for k,v in body.items() if k!='planned_minutes'};future.update(name='未来同为20分钟',start=str(today+timedelta(days=2)))
 edited=case.write('/plan-schedules/'+str(pid),future,1,'PUT',key)
 check('omitted minutes preserved on legacy edit',edited.status_code==200 and edited.json()['rule']['planned_minutes']==20)
 replay=case.write('/plan-schedules/'+str(pid),future,1,'PUT',key)
 check('same UUID returns identical original response',replay.status_code==200 and replay.json()==edited.json())
 stale=case.write('/plan-schedules/'+str(pid),{**future,'planned_minutes':45},1,'PUT')
 check('stale version rejected',stale.status_code==409)
 again=case.write('/plan-schedules/'+str(pid),{**future,'planned_minutes':45,'start':str(today+timedelta(days=3))},2,'PUT')
 check('second accepted edit advances version normally',again.status_code==200 and again.json()['version']==3)
 row=next(p for p in case.client.get('/api/plan-schedules').json() if p['id']==pid)
 check('multiple edits capture legacy baseline only once',len(row['history'])==3 and sum(bool(h.get('legacy_baseline')) for h in row['history'])==1)
 check('today keeps original explicit 20 minutes',row['timing']['planned_minutes']==20 and row['timing']['name']=='原20分钟计划')
finally:
 case.tearDown();(HERE/'additional-results.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False))
