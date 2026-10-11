"""Release checks use disposable SQLite/PG schemas and synthetic secrets only."""
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import test_next_iteration as baseline
from app import models as m
from app.models.access import LLMCredential, RequestReceipt
from app.models.analysis import AnalysisJob
from app.services import credentials, analysis_jobs
from app.services.model_boundary import run_deadline, ModelBoundaryError
from ops.import_references import transform, audit


class ReleaseTests(unittest.TestCase):
    setUp = baseline.CloudTests.setUp
    tearDown = baseline.CloudTests.tearDown
    register = baseline.CloudTests.register
    save = baseline.CloudTests.save

    def configure(self, group='primary', **extra):
        return self.client.put('/api/llm-config', json={'group':group,'provider_id':'deepseek',
            'model':'synthetic-model','api_key':'synthetic-provider-A-key','enabled':True, **extra})

    def test_frontend_real_http_redemption_chain(self):
        import socket
        import threading
        import subprocess
        import uvicorn
        uid=self.register()['id'];self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        item=self.client.get('/api/shop/items').json()['items'][0]
        self.client.put(f'/api/shop/items/{item["id"]}',json={'coin_price':7})
        item=self.client.get('/api/shop/items').json()['items'][0]
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(baseline.app,lifespan='off',log_level='error'))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.02)
            self.assertTrue(server.started)
            config={'url':f'http://127.0.0.1:{port}','uid':uid,'item':item,
                'cookie':'__Host-gol_session='+self.client.cookies.get('__Host-gol_session'),
                'csrf':self.client.headers['X-CSRF-Token']}
            result=subprocess.run(['node','tests/frontend_release.mjs'],input=json.dumps(config),
                text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            with self.Session() as db:
                self.assertEqual(db.query(m.Redemption).count(),2)
                self.assertEqual(db.query(m.CoinLedger).filter_by(source='shop_redeem').count(),2)
                self.assertEqual(db.query(m.UserProfile).filter_by(user_id=uid).one().coins,66)
        finally:
            server.should_exit=True;thread.join(5);sock.close()

    def test_goal_receipt_replay_stale_version_and_atomic_history(self):
        uid=self.register()['id'];self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        goal=self.client.post('/api/goals',json={'metric':'one synthetic action'}).json()
        body={'request_key':str(uuid4()),'expected_version':goal['updated_at']}
        path=f'/api/goals/{goal["id"]}/achieve'
        first=self.client.post(path,json=body);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.client.post(path,json=body).json(),first.json())
        self.assertEqual(self.client.post(path,json={**body,'request_key':str(uuid4())}).status_code,409)
        with self.Session() as db:
            self.assertEqual(db.query(m.AttributeHistory).filter_by(user_id=uid).count(),1)
            self.assertEqual(len(db.get(m.Goal,goal['id']).audit),1)

    def test_reviews_timezone_history_conflict_and_report_sources(self):
        from app.models.analysis import GrowthReport
        uid=self.register()['id'];event=self.save().json()
        for zone in ('Asia/Shanghai','America/New_York'):
            response=self.client.put('/api/daily-reviews/2026-10-09',json={'note':zone,'expected_version':0,'timezone':zone})
            self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(self.client.get('/api/daily-reviews').json()['items']),2)
        response=self.client.put('/api/daily-reviews/2026-10-09',json={'note':'stale','expected_version':0,'timezone':'Asia/Shanghai'})
        self.assertEqual(response.status_code,409)
        with self.Session() as db:
            db.get(m.User,uid).timezone='UTC'
            row=GrowthReport(user_id=uid,period='week',timezone='Asia/Shanghai',payload={'report':'frozen'},
                provenance={'events':[{'id':event['id'],'version':1},{'id':99999,'version':1}]})
            db.add(row);db.commit();rid=row.id
        self.assertEqual(self.client.get('/api/daily-reviews/2026-10-09?timezone=Asia/Shanghai').json()['note'],'Asia/Shanghai')
        self.client.put(f'/api/events/{event["id"]}',json={'content':'changed','expected_version':1})
        saved=self.client.get(f'/api/reports/{rid}').json()
        self.assertEqual(saved['report'],'frozen')
        self.assertEqual([s['state'] for s in saved['sources']],['edited','unavailable'])
        self.assertEqual(len(self.client.get('/api/reports').json()['items']),1)

    def test_all_business_routes_require_auth_and_confirmation_fault_stages_rollback(self):
        from ops.route_inventory import inventory
        paths=[]
        for route in inventory():
            if not route['path'].startswith('/api/') or route['path'].startswith('/api/auth') or route['path'] in ('/api/health','/api/ready'):continue
            path=__import__('re').sub(r'\{[^}]+\}','99999',route['path']);method=route['method']
            response=self.client.request(method,path,json={} if method not in ('GET','HEAD') else None)
            self.assertEqual(response.status_code,401,(method,path,response.text));paths.append((method,path))
        self.assertGreater(len(paths),80)
        uid=self.register()['id'];self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        from app.services import coin_service, judge_service
        for stage in ('after-coins','after-history','before-receipt'):
            event=self.save(stage).json()
            with self.Session() as db:
                judgment=m.AIJudgment(user_id=uid,event_id=event['id'],status='pending',confidence=1,
                    suggested_changes=[{'name':'健康','delta':1,'reason':'synthetic','evidence':'synthetic'}])
                db.add(judgment);db.commit();jid=judgment.id;version=judgment.updated_at.isoformat()
            reward=coin_service.reward_event_confirm
            log=judge_service._log
            def after_coins(*args,**kwargs):reward(*args,**kwargs);raise RuntimeError('synthetic fault')
            def after_history(*args,**kwargs):
                result=log(*args,**kwargs)
                if args[3]=='confirm':raise RuntimeError('synthetic fault')
                return result
            target={'after-coins':('app.services.coin_service.reward_event_confirm',after_coins),
                'after-history':('app.services.judge_service._log',after_history),
                'before-receipt':('app.services.receipts.record',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('synthetic fault')))}[stage]
            with patch(target[0],side_effect=target[1]):
                with self.assertRaises(RuntimeError):self.client.post(f'/api/judgments/{jid}/confirm',json={'request_key':str(uuid4()),'expected_version':version})
            with self.Session() as db:
                self.assertEqual(db.get(m.AIJudgment,jid).status,'pending')
                self.assertEqual(db.query(m.AttributeHistory).filter_by(event_id=event['id']).count(),0)
                self.assertEqual(db.query(m.Attribute).filter_by(user_id=uid,name='健康').one().current_value,50)
                self.assertEqual(db.query(m.UserProfile).filter_by(user_id=uid).one().coins,80)

    def test_exemption_replay_and_config_change_during_model_prevents_writes(self):
        uid=self.register()['id'];self.client.post('/api/onboarding/neutral',json={'acknowledge':True});self.configure()
        from app.services.time_service import clock_now
        body={'target_date':clock_now().date().isoformat(),'period':'morning','reason':'synthetic', 'request_key':str(uuid4())}
        priced={'coin_cost':10,'motive':'legitimate','motive_note':'synthetic','extra_penalty':0}
        with patch('app.services.exemption_service.llm_service.chat_json',return_value=priced) as model:
            first=self.client.post('/api/exemptions',json=body);self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(self.client.post('/api/exemptions',json=body).json(),first.json());self.assertEqual(model.call_count,1)
        def changed(*args,**kwargs):self.configure(api_key='replacement-synthetic');return priced
        with patch('app.services.exemption_service.llm_service.chat_json',side_effect=changed):
            second=self.client.post('/api/exemptions',json={**body,'request_key':str(uuid4())})
            self.assertEqual(second.status_code,400,second.text)
        with self.Session() as db:
            self.assertEqual(db.query(m.Exemption).count(),1)
            self.assertEqual(db.query(m.UserProfile).filter_by(user_id=uid).one().coins,70)

    def test_provider_binding_atomic_keep_replace_clear_both_groups(self):
        uid = self.register()['id']
        for group in ('primary','aux'):
            self.assertEqual(self.configure(group).status_code,200)
            with self.Session() as db:
                row = db.query(LLMCredential).filter_by(user_id=uid,group=group).one()
                initial = (row.provider_id,row.model,row.encrypted_key,row.key_id,row.config_version)
            for key in (None,'__KEEP__'):
                body={'group':group,'provider_id':'openai','model':'other-model','enabled':True}
                if key is not None: body['api_key']=key
                self.assertEqual(self.client.put('/api/llm-config',json=body).status_code,422)
                with self.Session() as db:
                    row=db.query(LLMCredential).filter_by(user_id=uid,group=group).one()
                    self.assertEqual((row.provider_id,row.model,row.encrypted_key,row.key_id,row.config_version),initial)
            self.assertEqual(self.client.put('/api/llm-config',json={'group':group,'model':'same-provider-new-model'}).status_code,200)
            with self.Session() as db:
                row=db.query(LLMCredential).filter_by(user_id=uid,group=group).one()
                self.assertEqual(credentials.decrypt(row),'synthetic-provider-A-key')
            self.assertEqual(self.configure(group,provider_id='openai',api_key='synthetic-provider-B-key').status_code,200)
            with self.Session() as db:
                from app.services.llm_config import read_group
                config=read_group(db,uid,'llm_'+group)
                self.assertEqual((config['base_url'],config['api_key']),('https://api.openai.com/v1','synthetic-provider-B-key'))
                from app.services.llm_config import _from_group
                from app.services.llm_service import LLMService
                with patch('app.services.model_boundary.run_deadline',return_value={'content':'OK'}) as intercepted:
                    client=LLMService()._get_client(_from_group(config))
                    client.chat.completions.create(model=config['model'],messages=[])
                    outbound=intercepted.call_args.args[1]
                    self.assertEqual((outbound['base_url'],outbound['api_key']),('https://api.openai.com/v1','synthetic-provider-B-key'))
            self.assertEqual(self.client.put('/api/llm-config',json={'group':group,'provider_id':'siliconflow','enabled':False}).status_code,200)
            with self.Session() as db:
                row=db.query(LLMCredential).filter_by(user_id=uid,group=group).one()
                self.assertEqual(credentials.decrypt(row),'')
            self.assertEqual(self.client.put('/api/llm-config',json={'group':group,'enabled':True}).status_code,422)
            self.assertEqual(self.configure(group).status_code,200)
            self.assertEqual(self.client.put('/api/llm-config',json={'group':group,'provider_id':'openai','api_key':''}).status_code,200)
            self.assertFalse(self.client.get('/api/llm-config').json()[group]['configured'])

    def test_redemption_replay_receipt_ownership_conflict_and_fault_rollback(self):
        uid=self.register()['id'];self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        item=self.client.get('/api/shop/items').json()['items'][0]
        self.client.put(f'/api/shop/items/{item["id"]}',json={'coin_price':7})
        item=self.client.get('/api/shop/items').json()['items'][0]
        body={'request_key':str(uuid4()),'expected_version':item['updated_at'],'note':'same operation'}
        path=f'/api/shop/items/{item["id"]}/redeem'
        with patch('app.services.receipts.record',side_effect=RuntimeError('fault before receipt')):
            with self.assertRaises(RuntimeError): self.client.post(path,json=body)
        with self.Session() as db:
            self.assertEqual(db.query(m.UserProfile).filter_by(user_id=uid).one().coins,80)
            self.assertEqual(db.query(m.Redemption).count(),0)
        first=self.client.post(path,json=body);self.assertEqual(first.status_code,200,first.text)
        receipt=f'/api/shop/items/{item["id"]}/redemption-submissions/{body["request_key"]}'
        self.assertEqual(self.client.get(receipt).json(),first.json())
        self.assertEqual(self.client.post(path,json=body).json(),first.json())
        self.assertEqual(self.client.post(path,json={**body,'note':'different'}).status_code,409)
        self.assertEqual(self.client.post(path,json={**body,'request_key':str(uuid4())}).status_code,200)
        with self.Session() as db:
            self.assertEqual(db.query(m.Redemption).count(),2)
            self.assertEqual(db.query(m.UserProfile).filter_by(user_id=uid).one().coins,66)
            self.assertEqual(db.query(RequestReceipt).filter_by(operation=f'redeem:{item["id"]}').count(),2)
        self.client.post('/api/auth/logout')
        result=self.client.post('/api/auth/login',json={'username':'owner','password':'test-password-owner'})
        self.client.headers['X-CSRF-Token']=result.json()['csrf_token']
        self.assertEqual(self.client.get(receipt).status_code,404)

    def test_question_two_devices_stale_after_first_completed(self):
        uid=self.register()['id'];self.configure()
        event=self.save().json()
        with self.Session() as db:
            question=AnalysisJob(user_id=uid,event_id=event['id'],event_version=1,request_key=str(uuid4()),
                payload_hash='x'*64,state='needs_input',result={'questions':['多久？']})
            db.add(question);db.commit();qid=question.id
        body={'request_key':str(uuid4()),'event_version':1,'detail':'十分钟','question_job_id':qid}
        path=f'/api/events/{event["id"]}/analysis-jobs'
        first=self.client.post(path,json=body);self.assertEqual(first.status_code,202,first.text)
        second={**body,'request_key':str(uuid4())}
        self.assertEqual(self.client.post(path,json=second).status_code,409)
        with self.Session() as db:
            job=db.get(AnalysisJob,first.json()['id']);job.state='ready';db.commit()
        self.assertEqual(self.client.post(path,json=second).status_code,409)
        self.assertEqual(self.client.post(path,json=body).json()['id'],first.json()['id'])
        with self.Session() as db:
            judgment=m.AIJudgment(user_id=uid,event_id=event['id'],status='pending',confidence=1)
            db.add(judgment);db.commit();db.refresh(judgment)
            version=judgment.updated_at.isoformat().replace('+00:00','Z')
        revision={'request_key':str(uuid4()),'event_version':1,'operation':'supplement','detail':'保留补充',
            'judgment_version':'2000-01-01T00:00:00Z'}
        self.assertEqual(self.client.post(path,json=revision).status_code,409)
        revision.update(request_key=str(uuid4()),judgment_version=version)
        self.assertEqual(self.client.post(path,json=revision).status_code,202)


class BoundaryAndReferenceTests(unittest.TestCase):
    def test_wall_clock_bounds_continuous_http_chunks_not_read_timeout(self):
        from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
        import threading
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Type','text/plain');self.end_headers()
                try:
                    while True:self.wfile.write(b' ');self.wfile.flush();time.sleep(.02)
                except (OSError,ConnectionError):pass
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            script='import sys,json,httpx; p=json.load(sys.stdin); httpx.get(p["url"],timeout=.15,trust_env=False)'
            started=time.monotonic()
            with self.assertRaisesRegex(ModelBoundaryError,'MODEL_TIMEOUT'):
                run_deadline([sys.executable,'-c',script],{'url':f'http://127.0.0.1:{server.server_port}'},1.2)
            self.assertLess(time.monotonic()-started,4)
        finally:server.shutdown();server.server_close();thread.join(3)
    def test_wall_clock_kills_continuous_output_and_next_call_runs(self):
        script='import sys,time; sys.stdin.read();\nwhile True:\n sys.stdout.write(" ");sys.stdout.flush();time.sleep(.02)'
        start=time.monotonic()
        with self.assertRaisesRegex(ModelBoundaryError,'MODEL_TIMEOUT'):
            run_deadline([sys.executable,'-c',script],{'key':'synthetic'},.4)
        self.assertLess(time.monotonic()-start,3)
        self.assertEqual(run_deadline([sys.executable,'-c','import sys;sys.stdin.read();print(\'{"content":"ok"}\')'],{},3)['content'],'ok')

    def test_semantic_paths_lists_no_integer_replacement_missing_cross_user(self):
        seen=[]
        def resolve(table,old,path): seen.append((table,old,path));return old+100
        value={'exemption':{'id':4,'coin_cost':4},'event_ids':[1,2],'source_history_ids':[3],
            'reversed_changes':[{'attribute_id':5,'delta':5}],'ordinary':[1,2,3]}
        result=transform('judgment_logs','payload',value,resolve)
        self.assertEqual(result['exemption'],{'id':104,'coin_cost':4})
        self.assertEqual(result['event_ids'],[101,102]);self.assertEqual(result['ordinary'],[1,2,3])
        self.assertEqual(transform('events','params',{'_challenge_id':9,'minutes':9},resolve),{'_challenge_id':109,'minutes':9})
        data={'events':[{'id':1,'user_id':1,'params':{'_challenge_id':2}}],
            'challenges':[{'id':2,'user_id':2}],
            'coin_ledger':[{'id':3,'user_id':1,'ref_type':'exemption','ref_id':7}]}
        spec=importlib.util.spec_from_file_location('importer_release',Path('ops/import-sqlite.py'))
        importer=importlib.util.module_from_spec(spec);spec.loader.exec_module(importer)
        issues,count=audit(data,importer.MAPPERS)
        self.assertEqual(count,2)
        self.assertEqual({v['reason'] for v in issues},{'NON_FK_CROSS_USER_REFERENCE','NON_FK_MISSING_REFERENCE'})


if __name__=='__main__':unittest.main()
