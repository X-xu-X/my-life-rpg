"""Loopback compiled-Vue/real-ASGI fixture. Synthetic DB/models only; no lifespan.

The HTTP bridge gives TestClient the synthetic HTTPS origin/cookie transport.
It does not validate production TLS, a real supplier, mail delivery or a phone.
Never run this helper as a production server.
"""
import os,json,sys,time,threading,tempfile,mimetypes
from pathlib import Path
from datetime import timedelta
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DB_URL']='sqlite://'
os.environ['DEEPSEEK_API_KEY']=''
os.environ['MAIL_HOST']=''
os.environ['MAIL_PASSWORD']=''
os.environ['MAIL_PASSWORD_FILE']=''
os.environ.pop('TEST_PG_URL',None)
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from app.config import settings
from app.database import Base,get_db
from app.main import app
from app.models import UserProfile,Event,Attribute
from app.models.accounts import SitePolicy
from app.models.full_system import TrialAccount
from app.services import auth_service,credentials,coin_service,anchor_service,analysis_jobs,pricing_checks,trial_rules
from app.services.time_service import utc_now,local_day
from app.constants import ATTRIBUTE_DIMENSIONS
from app.services.llm_service import llm_service
from app.schemas import LLMConfigIn

workspace=Path(__file__).resolve().parents[1]
root=(workspace/os.environ.get('DAILY_USE_EVIDENCE_DIR','docs/review/daily_use_2026-10-21/browser')).resolve()
assert root.is_relative_to((workspace/'docs/review').resolve())
root.mkdir(parents=True,exist_ok=True)
temporary=tempfile.TemporaryDirectory(dir=workspace/'backups',prefix='daily_runtime_')
temp_path=Path(temporary.name).resolve();assert (workspace/'backups').resolve() in temp_path.parents
key=temp_path/'synthetic-key.json';key.write_text(json.dumps({'active':'test','keys':{'test':Fernet.generate_key().decode()}}))
settings.run_mode='cloud';settings.public_origin='https://rpg.test';settings.credential_key_file=str(key);settings.allow_cloud_sqlite=True;settings.mail_host='';settings.deepseek_api_key=''
engine=create_engine('sqlite:///'+str(temp_path/'synthetic.db'),connect_args={'check_same_thread':False})
@event.listens_for(engine,'connect')
def configure(connection,record):connection.execute('PRAGMA foreign_keys=ON');connection.execute('PRAGMA busy_timeout=5000')
Base.metadata.create_all(engine)
factory=sessionmaker(bind=engine,autoflush=False)
def dependency():
    with factory() as db:yield db
app.dependency_overrides[get_db]=dependency
clock={'now':utc_now()};model_calls=[];api_calls=[];errors=[];disconnects=[];guard=str(uuid4());stop=threading.Event();client_lock=threading.RLock()


def synthetic_json(messages,**kwargs):
    from app.services.ai_context import CURRENT
    model_calls.append({'messages':messages,'model':'synthetic-only','purpose':(CURRENT.get() or {}).get('purpose','explicit-direct')})
    (root/'model-payloads.json').write_text(json.dumps(model_calls,ensure_ascii=False,indent=2),encoding='utf-8')
    time.sleep(.45)
    text='\n'.join(m['content'] for m in messages)
    if '【物品名称】' in text:
        if os.environ.get('DAILY_USE_REVIEW_CASES') and 'QUEUE_FAIL' in text:
            from app.services.llm_service import LLMError
            raise LLMError('MODEL_TIMEOUT')
        return {'coin_price':23,'pricing_reason':'合成模型：结合本人每周的奖励偏好与已确认实际用量。','worth_note':'可以在需要时选择，不替代必要休息。'}
    if '整体阅读本人明确授权' in text:return {'questions':[]}
    if '初始属性面板' in text or '初始金币' in text:return {'attributes':[{'name':n,'value':52,'reason':'合成问卷依据'} for n in ATTRIBUTE_DIMENSIONS],'initial_coins':120,'summary':'合成初始评估；非真实模型质量验收','economic_reference':{'basis':'本人期望频率，不设统一汇率'}}
    if '"facts"' in text:
        source=json.loads(messages[-1]['content']);content=source['original'];low='信息不足' in content
        return {'facts':[{'excerpt':content,'summary':'合成事实建议','coins':6,'coins_reason':'合成定价依据','changes':[{'name':'体能','delta':1,'reason':'合成真实动作依据','evidence':content}],'confidence':.799 if low else .8 if '边界80' in content else .9,'reason':'信息不足，请补充投入' if low else '合成可核对行动','relation':'new','effort':False}],'questions':[]}
    if '未来娱乐约定' in text:return {'mode':'gentle','reason':'以本人当前主线与精力为参考，温和提醒。'}
    if 'suggested_seconds' in text:return {'summary':'只核对本人说明，不自动判罚','suggested_seconds':None}
    if 'highlights' in text:return {'highlights':'合成报告摘要','concerns':'不凭缺记录推断能力下降','suggestions':['按自己的节奏记录'],'tone':'平和'}
    return {'questions':[],'summary':'合成回顾摘要','analysis':['只使用明确授权的来源。']}


llm_service.chat_json=synthetic_json
llm_service.chat=lambda *args,**kwargs:'OK'
import app.routers.timers as timer_routes
import app.services.timers as timer_service
timer_routes.utc_now=lambda:clock['now'];timer_service.utc_now=lambda:clock['now']
with factory() as db:
    owner=auth_service.initialize_account(db,'owner_fixture','owner-test-password',role='owner')
    user=auth_service.initialize_account(db,'日常测试','daily-test-password');db.flush()
    profile=db.query(UserProfile).filter_by(user_id=user.id).one();profile.onboarding_completed=True;profile.baseline_kind='neutral_opt_in'
    profile.initial_attributes_snapshot={'attributes':[{'name':n,'value':50,'reason':'合成起点'} for n in ATTRIBUTE_DIMENSIONS],'initial_coins':80}
    db.flush();coin_service.grant_startup_bonus_if_needed(db,user,80)
    db.add(SitePolicy(id=1,version=1,payload={'registration':'open','email_required':False,'site_name':'人生手账'}))
    db.add(TrialAccount(user_id=user.id,timezone='Asia/Shanghai',region='CN',enabled=True,base_minutes=30))
    today=local_day(utc_now(),'Asia/Shanghai')
    for n in (2,1,0):
        day=str(today-timedelta(days=n));row=Event(user_id=user.id,event_type='positive',record_kind='event',content='PRIVATE_PAYLOAD_SENTINEL_ONLY_LOCAL' if n==0 else '合成日常记录',title='先只保存的片段',ai_permission='private',analysis_intent='never',occurred_on=day,saved_on=day,timezone_at_capture='Asia/Shanghai',saved_timezone='Asia/Shanghai',time_precision='date')
        db.add(row);db.flush()
        if n==0:trial_rules.qualify(db,user,row)
    anchor_service.seed_anchors(db);db.commit();uid=user.id
    credentials.save_config(db,uid,LLMConfigIn(group='primary',provider_id='deepseek',enabled=True,model='fixture-chat-only',api_key='sk-synthetic-not-a-real-key'))

client=TestClient(app,base_url='https://rpg.test')


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):self.handle_request()
    def do_POST(self):self.handle_request()
    def do_PUT(self):self.handle_request()
    def do_DELETE(self):self.handle_request()
    def write(self,status,content,headers=None):
        try:
            self.send_response(status)
            for name,value in (headers or {}).items():self.send_header(name,value)
            self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):disconnects.append(self.path)
    def handle_request(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        if self.path.startswith('/__qa__/'):
            if self.headers.get('X-QA-Guard')!=guard:self.write(403,b'{}');return
            if self.path=='/__qa__/seed-pricing' and os.environ.get('DAILY_USE_REVIEW_CASES'):
                from app.models import ShopItem
                values=json.loads(body)
                with factory() as db:
                    offset=db.query(ShopItem).filter_by(user_id=uid).count()
                    for n in range(min(30,max(0,values['count']))):
                        db.add(ShopItem(user_id=uid,name=('QUEUE_FAIL_' if values.get('fail_index')==n else 'QUEUE_CASE_')+str(offset+n+1),coin_price=23,enabled=True,auto_pricing=True))
                    db.commit()
            if self.path=='/__qa__/advance':clock['now']+=timedelta(seconds=json.loads(body)['seconds'])
            if self.path=='/__qa__/shutdown':threading.Thread(target=server.shutdown,daemon=True).start()
            self.write(200,json.dumps({'model_calls':len(model_calls),'api_calls':len(api_calls),'errors':errors}).encode(),{'Content-Type':'application/json'});return
        if self.path.startswith('/api/'):
            try:
                with client_lock:
                    response=client.request(self.command,self.path,content=body or None,headers={'Origin':'https://rpg.test','Content-Type':self.headers.get('Content-Type','application/json'),'X-CSRF-Token':self.headers.get('X-CSRF-Token','')})
                entry={'method':self.command,'path':self.path,'status':response.status_code}
                if self.path.startswith('/api/projects') and body:
                    source=json.loads(body);entry['body_fields']=sorted(source)
                    entry['project_input']={k:source[k] for k in ('name','start','effective_from','category','position','removed','enabled') if k in source}
                api_calls.append(entry)
                (root/'api-requests.json').write_text(json.dumps(api_calls,ensure_ascii=False,indent=2),encoding='utf-8')
                self.write(response.status_code,response.content,{k:v for k,v in response.headers.items() if k.lower() in ('content-type','content-disposition','cache-control')})
            except Exception as exc:
                errors.append(type(exc).__name__+': '+str(exc));self.write(500,b'{"detail":"SYNTHETIC_FIXTURE_ERROR"}',{'Content-Type':'application/json'})
            return
        target=(workspace/'frontend/dist'/('.'+self.path.split('?')[0])).resolve() if self.path!='/' else workspace/'frontend/dist/index.html'
        if not target.is_relative_to((workspace/'frontend/dist').resolve()) or not target.is_file():self.write(404,b'');return
        self.write(200,target.read_bytes(),{'Content-Type':mimetypes.guess_type(str(target))[0] or 'application/octet-stream'})


def work():
    while not stop.wait(.12):
        try:
            job=analysis_jobs.claim(factory)
            if job:analysis_jobs.process(factory,job)
            else:
                job=pricing_checks.claim(factory)
                if job:pricing_checks.process(factory,job)
        except Exception as exc:errors.append('worker:'+type(exc).__name__)


server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
runtime={'origin':'http://127.0.0.1:'+str(server.server_address[1]),'guard':guard,'database':'temporary synthetic SQLite','supplier':'fake model callable; actual messages captured','transport':'HTTP loopback to HTTPS TestClient; no real TLS/browser cookie claim','lifespan':'NOT_RUN'}
(root/'runtime.json').write_text(json.dumps(runtime,ensure_ascii=False),encoding='utf-8')
threading.Thread(target=work,daemon=True).start()
print(json.dumps({'origin':runtime['origin'],'mode':'synthetic DB, real ASGI, no real supplier'}),flush=True)
try:server.serve_forever()
finally:
    stop.set();server.server_close();client.close();engine.dispose();app.dependency_overrides.clear()
    (root/'runtime-results.json').write_text(json.dumps({'api_calls':len(api_calls),'model_calls':len(model_calls),'errors':errors,'client_disconnects':disconnects,'external_services':'NOT_RUN'},ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.cleanup()
