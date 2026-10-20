"""下一阶段 HTTP 验收：显式隔离库，绝不运行真实库 lifespan。"""
import json
import tempfile
import os
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool, NullPool
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app import models as m
from app.models.access import Invitation, RequestReceipt, LLMCredential, AuthSession
from app.services import auth_service, credentials, coin_service, anchor_service


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="backups", prefix="next_test_")
        key_file = Path(self.temp.name) / 'key.json'
        key_file.write_text(json.dumps({'active':'v1','keys':{'v1':Fernet.generate_key().decode()}}))
        self.patches = [patch.object(settings, 'run_mode', 'cloud'),
            patch.object(settings, 'public_origin', 'https://rpg.test'),
            patch.object(settings, 'credential_key_file', str(key_file))]
        for p in self.patches: p.start()
        self.pg_schema = None
        if os.environ.get('TEST_PG_URL'):
            from sqlalchemy.schema import CreateSchema
            self.pg_schema = 'qa_' + uuid4().hex
            self.pg_engine = create_engine(os.environ['TEST_PG_URL'])
            with self.pg_engine.begin() as connection: connection.execute(CreateSchema(self.pg_schema))
            self.engine = self.pg_engine.execution_options(schema_translate_map={None:self.pg_schema})
        else:
            self.engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
            @event.listens_for(self.engine, 'connect')
            def foreign_keys(connection, record): connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        def dependency():
            with self.Session() as db: yield db
        app.dependency_overrides[get_db] = dependency
        with self.Session() as db:
            owner = auth_service.initialize_account(db, 'owner', 'test-password-owner', role='owner')
            self.owner_id = owner.id
            self.invite = auth_service.issue_invitation(db, owner)
            anchor_service.seed_anchors(db)
            db.commit()
        self.client = TestClient(app, base_url='https://rpg.test', headers={'Origin':'https://rpg.test'})

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        for p in reversed(self.patches): p.stop()
        self.engine.dispose()
        if self.pg_schema:
            from sqlalchemy.schema import DropSchema
            with self.pg_engine.begin() as connection: connection.execute(DropSchema(self.pg_schema, cascade=True))
            self.pg_engine.dispose()
        self.temp.cleanup()
        auth_service._attempts.clear()

    def register(self, username='friend'):
        result = self.client.post('/api/auth/register', json={'invite_token':self.invite,
            'username':username,'password':'friend-test-password'})
        self.assertEqual(result.status_code,201,result.text)
        self.client.headers['X-CSRF-Token'] = result.json()['csrf_token']
        return result.json()

    def save(self, content='今天走了十分钟', key=None, **extra):
        return self.client.post('/api/events',json={'content':content, 'source':'journal','ai_permission':'private' if extra.get('intent')=='never' or extra.get('is_pure') else 'allowed',
            'client_request_id':key or str(uuid4()), **extra})

    def test_auth_session_invitation_recovery_and_csrf(self):
        self.assertEqual(self.client.get('/api/events').status_code,401)
        registered = self.register()
        self.assertEqual(self.client.get('/api/auth/me').json()['username'],'friend')
        self.assertEqual(self.client.post('/api/auth/register', json={'invite_token':self.invite,
            'username':'other','password':'friend-test-password'}).status_code,400)
        self.assertEqual(self.save().status_code,200)
        self.assertEqual(self.client.post('/api/events',json={'content':'跨站'},headers={'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.client.post('/api/auth/logout').status_code,200)
        self.assertEqual(self.client.get('/api/events').status_code,401)
        recovery = self.client.post('/api/auth/recover', json={'recovery_code':registered['recovery_code'],
            'new_password':'new-test-password'} )
        self.assertEqual(recovery.status_code,200,recovery.text)
        self.assertEqual(self.client.post('/api/auth/recover',json={'recovery_code':registered['recovery_code'],
            'new_password':'other-test-password'}).status_code,400)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'friend','password':'friend-test-password'}).status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'friend','password':'new-test-password'}).status_code,200)

    def test_save_without_model_replay_conflict_and_edit_version(self):
        self.register()
        request_id = str(uuid4())
        with patch('app.services.llm_service.llm_service.chat_json', side_effect=AssertionError('保存不能调用AI')):
            first = self.save(key=request_id)
        self.assertEqual(first.status_code,200,first.text)
        row = first.json()
        self.assertEqual(self.save(key=request_id).json()['id'],row['id'])
        self.assertEqual(self.save('不同正文',key=request_id).status_code,409)
        self.assertEqual(self.client.get('/api/event-submissions/'+request_id).json()['id'],row['id'])
        self.assertEqual(self.client.put('/api/events/'+str(row['id']),json={'content':'修订','expected_version':1}).status_code,200)
        self.assertEqual(self.client.put('/api/events/'+str(row['id']),json={'content':'迟到','expected_version':1}).status_code,409)
        self.assertEqual(self.client.get('/api/events/'+str(row['id'])).json()['content'],'修订')
        with self.Session() as db:
            self.assertEqual(db.query(m.Event).count(),1)
            self.assertEqual(db.query(RequestReceipt).count(),1)

    def test_two_users_owned_reads_writes_nested_references_and_export(self):
        registered = self.register()
        record = self.save('朋友私密正文').json()
        item = self.client.post('/api/items',json={'name':'朋友项目'}).json()
        self.client.post('/api/auth/logout')
        login = self.client.post('/api/auth/login',json={'username':'owner','password':'test-password-owner'})
        self.client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        for method,path,body in [('get',f"/api/events/{record['id']}",None),
            ('put',f"/api/events/{record['id']}",{'content':'盗改','expected_version':1}),
            ('delete',f"/api/events/{record['id']}",None),
            ('post',f"/api/events/{record['id']}/judge",{}),
            ('put',f"/api/items/{item['id']}",{'name':'盗改项目'})]:
            response = getattr(self.client,method)(path,**({'json':body} if body is not None else {}))
            self.assertEqual(response.status_code,404,response.text)
        self.assertEqual(self.save('嵌套盗用',item_id=item['id']).status_code,404)
        export = self.client.get('/api/export')
        self.assertNotIn('朋友私密正文',export.text)
        self.assertNotIn('password_hash',export.text)
        self.assertNotIn('朋友项目',self.client.get('/api/items').text)

    def test_cross_user_all_resource_action_families(self):
        from app.models.analysis import AnalysisJob, GrowthReport, DailyReview
        from datetime import date
        friend=self.register()['id']
        self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        event=self.save('禁止泄漏的原文').json()
        with self.Session() as db:
            goal=m.Goal(user_id=friend,description='禁止泄漏的目标');db.add(goal)
            judgment=m.AIJudgment(user_id=friend,event_id=event['id'],status='pending',confidence=1);db.add(judgment)
            db.flush()
            db.add(m.JudgmentLog(user_id=friend,judgment_id=judgment.id,action='create',detail='禁止泄漏的审计'))
            challenge=m.Challenge(user_id=friend,scope='daily',period_key='2026-10-09',title='私密挑战',status='accepted',event_id=event['id'],judgment_id=judgment.id)
            item=db.query(m.ShopItem).filter_by(user_id=friend).first()
            redemption=m.Redemption(user_id=friend,shop_item_id=item.id,status='pending')
            attribute=db.query(m.Attribute).filter_by(user_id=friend).first()
            report=GrowthReport(user_id=friend,period='week',timezone='Asia/Shanghai',payload={'private':'禁止泄漏的报告'})
            job=AnalysisJob(user_id=friend,event_id=event['id'],event_version=1,request_key=str(uuid4()),payload_hash='x'*64)
            db.add_all([challenge,redemption,report,job,DailyReview(user_id=friend,local_date=date(2026,10,9),timezone='Asia/Shanghai',note='禁止泄漏的回顾')]);db.commit()
            gid,jid,cid,sid,rid,aid,reportid,jobid=goal.id,judgment.id,challenge.id,item.id,redemption.id,attribute.id,report.id,job.id
        self.client.post('/api/auth/logout')
        login=self.client.post('/api/auth/login',json={'username':'owner','password':'test-password-owner'})
        self.client.headers['X-CSRF-Token']=login.json()['csrf_token']
        self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        matrix=[('GET',f'/judgments/{jid}',None),('GET',f'/judgments/{jid}/logs',None),
            ('POST',f'/judgments/{jid}/confirm',{}),('POST',f'/judgments/{jid}/achievement',{'action':'grant'}),
            ('POST',f'/judgments/{jid}/supplement',{'detail':'盗改'}),('POST',f'/judgments/{jid}/dispute',{'detail':'盗改'}),
            ('GET',f'/goals/{gid}',None),('POST',f'/goals/{gid}/achieve',{}),('POST',f'/goals/{gid}/fail',{}),
            ('POST',f'/goals/{gid}/cancel',{}),('PUT',f'/goals/{gid}',{'description':'盗改'}),
            ('POST',f'/challenges/{cid}/accept',{}),('POST',f'/challenges/{cid}/complete',{'note':'盗改'}),
            ('POST',f'/challenges/{cid}/settle',{}),('POST',f'/challenges/{cid}/abandon',{'note':'盗改'}),
            ('PUT',f'/challenges/{cid}/variant',{'variant_index':0}),('PUT',f'/shop/items/{sid}',{'name':'盗改'}),
            ('DELETE',f'/shop/items/{sid}',None),('POST',f'/shop/items/{sid}/reprice',{}),('POST',f'/shop/items/{sid}/redeem',{}),
            ('POST',f'/redemptions/{rid}/fulfill',{}),('POST',f'/subdimensions/{aid}/propose',{}),
            ('POST',f'/subdimensions/{aid}/accept',{'names':['盗用']}),('POST',f'/subdimensions/{aid}/dismiss',{}),
            ('GET',f'/reports/{reportid}',None),('GET',f'/analysis-jobs/{jobid}',None),
            ('POST',f'/analysis-jobs/{jobid}/cancel',{}),('POST',f'/analysis-jobs/{jobid}/retry',{'request_key':str(uuid4()),'event_version':1})]
        for method,path,body in matrix:
            response=self.client.request(method,'/api'+path,**({'json':body} if body is not None else {}))
            self.assertEqual(response.status_code,404,(method,path,response.text))
        for path in ['export','pending','daily-reviews/2026-10-09','goals','judgments','challenges','llm-config']:
            self.assertNotIn('禁止泄漏',self.client.get('/api/'+path).text,path)

    def test_neutral_once_no_get_funding_and_no_second_build(self):
        self.register()
        for path in ('/api/coins','/api/attributes','/api/onboarding/status'):
            self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],0)
        self.assertEqual(self.client.post('/api/onboarding/neutral',json={'acknowledge':True}).json()['balance'],80)
        self.assertEqual(self.client.post('/api/onboarding/neutral',json={'acknowledge':True}).json()['balance'],80)
        with self.Session() as db:
            self.assertEqual(db.query(m.CoinLedger).count(),1)
            self.assertEqual(db.query(m.Attribute).filter_by(user_id=self.client.get('/api/auth/me').json()['id']).count(),13)

    def test_credentials_encrypted_masked_no_env_fallback_and_endpoint_rejection(self):
        user = self.register()
        key = 'sk-fake-test-only-12345678'
        response = self.client.put('/api/llm-config',json={'group':'primary','provider_id':'deepseek',
            'model':'qa-model','api_key':key,'enabled':True})
        self.assertEqual(response.status_code,200,response.text)
        config = self.client.get('/api/llm-config')
        self.assertNotIn(key,config.text)
        self.assertFalse(config.json()['env_fallback']['ready'])
        with self.Session() as db:
            row = db.query(LLMCredential).one()
            self.assertNotIn(key,row.encrypted_key)
            self.assertEqual(credentials.decrypt(row),key)
            self.assertEqual(db.query(m.Setting).count(),0)
        self.assertEqual(self.client.put('/api/llm-config',json={'group':'primary','base_url':'http://169.254.169.254'}).status_code,422)
        self.assertNotIn(key,self.client.get('/api/export').text)
        with patch.object(credentials.socket,'getaddrinfo',return_value=[(None,None,None,None,('127.0.0.1',443))]):
            with self.assertRaises(ValueError): credentials.public_addresses('api.deepseek.com')

    def configure_model(self):
        response = self.client.put('/api/llm-config', json={'group':'primary','provider_id':'deepseek',
            'model':'qa-model','api_key':'sk-fake-test-only-key','enabled':True})
        self.assertEqual(response.status_code,200,response.text)

    def test_worker_ready_and_cancelled_lease_cannot_write(self):
        from app.services import analysis_jobs, judge_service
        from app.models.analysis import AnalysisJob
        from app.services.llm_service import CALL_GUARD
        self.register(); self.configure_model()
        record = self.save().json()
        body = {'request_key':str(uuid4()),'event_version':1}
        response = self.client.post(f"/api/events/{record['id']}/analysis-jobs",json=body)
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(self.client.post(f"/api/events/{record['id']}/analysis-jobs",json=body).json()['id'],response.json()['id'])
        claimed = analysis_jobs.claim(self.Session)
        self.assertIsNotNone(claimed)
        self.assertIsNone(analysis_jobs.claim(self.Session))
        def fake(*args,**kwargs):
            CALL_GUARD.get()()
            return {'realistic':True,'confidence':1,'affected_attributes':[{'name':'体能','delta':1}]}
        with patch.object(judge_service.llm_service,'chat_json',side_effect=fake):
            analysis_jobs.process(self.Session, claimed)
        job = self.client.get(f"/api/analysis-jobs/{claimed[0]}").json()
        self.assertEqual(job['state'],'ready',job)
        self.assertEqual(job['attempts'],1)
        with self.Session() as db:
            self.assertEqual(db.query(m.AIJudgment).count(),1)
            self.assertEqual(db.query(m.AttributeHistory).count(),0)
            self.assertEqual(db.query(m.CoinLedger).count(),0)
        second = self.client.post(f"/api/events/{record['id']}/analysis-jobs",json={**body,'request_key':str(uuid4())}).json()
        claimed = analysis_jobs.claim(self.Session)
        self.client.post(f"/api/analysis-jobs/{second['id']}/cancel")
        with patch.object(judge_service.llm_service,'chat_json',side_effect=AssertionError('取消后不得调用模型')):
            analysis_jobs.process(self.Session,claimed)
        self.assertEqual(self.client.get(f"/api/analysis-jobs/{second['id']}").json()['state'],'cancelled')

    def test_mutation_receipts_stale_confirmation_and_delete_replay(self):
        from app.services.time_service import utc_now
        self.register()
        self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        event = self.save().json()
        with self.Session() as db:
            judgment=m.AIJudgment(user_id=event['user_id'] if 'user_id' in event else self.client.get('/api/auth/me').json()['id'],
                event_id=event['id'],status='pending',confidence=1,source_snapshot=[{'id':event['id'],'version':1,'permission_version':1}],suggested_changes=[{'name':'体能','delta':1}],summary='测试')
            db.add(judgment);db.commit();jid=judgment.id
        current=self.client.get(f'/api/judgments/{jid}').json()
        body={'request_key':str(uuid4()),'expected_version':current['updated_at']}
        stale=self.client.post(f'/api/judgments/{jid}/confirm',json={**body,'expected_version':'2000-01-01T00:00:00Z'})
        self.assertEqual(stale.status_code,409,stale.text)
        first=self.client.post(f'/api/judgments/{jid}/confirm',json=body)
        self.assertEqual(first.status_code,200,first.text)
        replay=self.client.post(f'/api/judgments/{jid}/confirm',json=body)
        self.assertEqual(replay.json(),first.json())
        delete={'request_key':str(uuid4()),'expected_version':1}
        first=self.client.request('DELETE',f"/api/events/{event['id']}",json=delete)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.client.request('DELETE',f"/api/events/{event['id']}",json=delete).json(),first.json())
        with self.Session() as db:
            values=db.query(m.Attribute).filter_by(user_id=current_user_id(self.client),name='体能').one()
            self.assertEqual(values.current_value,50)
            self.assertEqual(db.query(m.AttributeHistory).count(),2)
            self.assertEqual(db.query(m.CoinLedger).count(),2)

    def test_all_gets_readonly_without_model_or_startup_awards(self):
        self.register()
        def snapshot():
            with self.engine.connect() as connection:
                return {table.name:connection.execute(table.select().order_by(*table.primary_key.columns)).fetchall()
                    for table in Base.metadata.sorted_tables}
        before=snapshot()
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=AssertionError('GET不能调用模型')):
            paths=['events','events/heatmap','attributes','attributes/history','anchors','items','items/stats',
                'goals','coins','challenges','challenges/current','shop/items','redemptions','stagnation',
                'achievements','exemptions','subdimensions','onboarding/status','settings','llm-config',
                'pending','daily-reviews','reports','daily-reviews/2026-10-09','export','auth/me']
            for path in paths:
                response=self.client.get('/api/'+path)
                self.assertEqual(response.status_code,200,(path,response.text))
        self.assertEqual(before,snapshot())

    def test_expired_lease_old_token_and_edit_during_model_cannot_write(self):
        from datetime import timedelta
        from app.services import analysis_jobs, judge_service
        from app.services.time_service import utc_now
        from app.models.analysis import AnalysisJob
        self.register();self.configure_model()
        event=self.save().json()
        response=self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1})
        self.assertEqual(response.status_code,202,response.text)
        old=analysis_jobs.claim(self.Session)
        with self.Session() as db:
            db.get(AnalysisJob,old[0]).lease_until=utc_now()-timedelta(seconds=1);db.commit()
        new=analysis_jobs.claim(self.Session)
        self.assertNotEqual(old[1],new[1])
        with patch.object(judge_service.llm_service,'chat_json',side_effect=AssertionError('旧租约不得调用')):
            analysis_jobs.process(self.Session,old)
        def edit(*args,**kwargs):
            response=self.client.put(f"/api/events/{event['id']}",json={'content':'新版原文','expected_version':1})
            self.assertEqual(response.status_code,200,response.text)
            return {'realistic':True,'confidence':1,'affected_attributes':[{'name':'体能','delta':1}]}
        with patch.object(judge_service.llm_service,'chat_json',side_effect=edit):
            analysis_jobs.process(self.Session,new)
        self.assertEqual(self.client.get(f'/api/analysis-jobs/{new[0]}').json()['state'],'superseded')
        with self.Session() as db:
            self.assertEqual(db.query(m.AIJudgment).count(),0)
            self.assertEqual(db.query(m.CoinLedger).count(),0)

    def test_worker_two_real_call_budget_and_permanent_error(self):
        from types import SimpleNamespace
        from app.services import analysis_jobs, judge_service
        from app.services.llm_service import LLMError
        self.register();self.configure_model();event=self.save().json()
        self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1})
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=''))]))),close=lambda:None)
        with patch.object(judge_service.llm_service,'_get_client',return_value=client),patch('app.services.llm_service.time.sleep'):
            analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        job=self.client.get('/api/pending').json()['items'][0]['job']
        self.assertEqual(job['attempts'],2,job)
        self.assertEqual(job['state'],'failed',job)
        self.assertIsNone(analysis_jobs.claim(self.Session))

    def test_pg_concurrent_redemption_and_int64_balance(self):
        if not self.pg_schema: self.skipTest('真实 PostgreSQL 并发用例')
        from concurrent.futures import ThreadPoolExecutor
        self.register();self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        with self.Session() as db:
            item=db.query(m.ShopItem).filter_by(user_id=current_user_id(self.client),name='一小时游戏时间').one()
            item.coin_price=60;db.commit();iid=item.id;version=item.updated_at.isoformat()
        def redeem():
            return self.client.post(f'/api/shop/items/{iid}/redeem',json={'request_key':str(uuid4()),'expected_version':version})
        with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(lambda _:redeem(),range(2)))
        self.assertEqual(sorted(r.status_code for r in responses),[200,400],[r.text for r in responses])
        with self.Session() as db:
            user=db.get(m.User,current_user_id(self.client))
            self.assertEqual(coin_service.balance(db,user),20)
            self.assertEqual(db.query(m.Redemption).count(),1)
            coin_service.grant(db,user,2**31+5,source='test',reason='大整数验收');db.commit()
            self.assertEqual(coin_service.balance(db,user),2**31+25)
            with self.assertRaises(ValueError):coin_service.grant(db,user,2**63,source='test',reason='必须拒绝')
            db.rollback()
            self.assertEqual(coin_service.balance(db,user),2**31+25)
            coin_service.grant(db,user,(2**63-1)-(2**31+25),source='test',reason='接近64位上限');db.commit()
            with self.assertRaises(ValueError):coin_service.grant(db,user,1,source='test',reason='不能溢出')
            db.rollback()
            self.assertEqual(coin_service.balance(db,user),2**63-1)

    def test_challenge_accept_and_settle_atomic_receipts(self):
        self.register();self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        uid=current_user_id(self.client)
        with self.Session() as db:
            challenge=m.Challenge(user_id=uid,scope='daily',period_key='2026-10-09',title='合成挑战',
                status='candidate',coin_reward=40,deposit=12,difficulty=1)
            db.add(challenge);db.commit();cid=challenge.id;version=challenge.updated_at.isoformat()
        body={'request_key':str(uuid4()),'expected_version':version}
        first=self.client.post(f'/api/challenges/{cid}/accept',json=body)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['balance'],68)
        self.assertEqual(self.client.post(f'/api/challenges/{cid}/accept',json=body).json(),first.json())
        with self.Session() as db:
            event=m.Event(user_id=uid,event_type='positive',origin='challenge',content='已完成合成挑战')
            db.add(event);db.flush()
            judgment=m.AIJudgment(user_id=uid,event_id=event.id,status='pending',confidence=1,
                suggested_changes=[{'name':'体能','delta':1}]);db.add(judgment);db.flush()
            challenge=db.get(m.Challenge,cid)
            challenge.event_id=event.id;challenge.judgment_id=judgment.id;challenge.outcome='done'
            db.commit();version=challenge.updated_at.isoformat()
        settle={'request_key':str(uuid4()),'expected_version':version}
        first=self.client.post(f'/api/challenges/{cid}/settle',json=settle)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['balance'],120)
        self.assertEqual(self.client.post(f'/api/challenges/{cid}/settle',json=settle).json(),first.json())
        with self.Session() as db:
            self.assertEqual(db.query(m.AttributeHistory).count(),1)
            self.assertEqual(db.query(m.CoinLedger).count(),4)

    def test_pg_import_synthetic_legacy40_atomic_mapping(self):
        if not self.pg_schema:self.skipTest('真实 PostgreSQL 导入用例')
        import importlib.util
        from app.constants import ATTRIBUTE_DIMENSIONS
        from datetime import datetime
        self.register()
        spec=importlib.util.spec_from_file_location('importer',Path('ops/import-sqlite.py'))
        importer=importlib.util.module_from_spec(spec);spec.loader.exec_module(importer)
        source=Path(self.temp.name)/'legacy.sqlite3'
        source_engine=create_engine('sqlite:///'+str(source),poolclass=NullPool)
        with patch.object(settings,'run_mode','local'):
            Base.metadata.create_all(source_engine,tables=[Base.metadata.tables[name] for name in importer.TABLES])
            with __import__('sqlalchemy.orm',fromlist=['Session']).Session(source_engine) as db:
                user=m.User(username='default');db.add(user);db.flush();uid=user.id
                db.add(m.UserProfile(user_id=uid,coins=40,onboarding_completed=True,initial_attributes_snapshot={'initial_coins':40}))
                for name in ATTRIBUTE_DIMENSIONS:db.add(m.Attribute(user_id=uid,name=name,current_value=50))
                db.add(m.Event(id=34,user_id=uid,event_type='positive',title='合成旧数据',content='导入合成原文',occurred_at=datetime(2026,10,9,7,30)))
                db.flush()
                db.add(m.AIJudgment(id=35,user_id=uid,event_id=34,status='pending',confidence=1))
                db.add(m.CoinLedger(user_id=uid,delta=40,balance_after=40,source='startup',reason='历史40币'))
                db.add(m.Setting(user_id=uid,key='llm_primary',value={'api_key':'sk-synthetic-do-not-import'}))
                db.commit()
        source_engine.dispose()
        data,report=importer.preflight(source)
        self.assertFalse(report['blocked'],report['issues'])
        url=os.environ['TEST_PG_URL']+'?options=-csearch_path%3D'+self.pg_schema
        result=importer.apply(data,report,url,uid,'friend',report['source_sha256'])
        event=self.client.get('/api/events').json()[0]
        self.assertEqual(event['content'],'导入合成原文')
        self.assertEqual(result['written']['ai_judgments'],1)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],40)
        self.assertNotIn('sk-synthetic-do-not-import',self.client.get('/api/export').text)
        with self.assertRaises(ValueError):importer.apply(data,report,url,uid,'friend',report['source_sha256'])

    def test_review_reuses_original_fact_and_version_conflicts(self):
        from app.services.time_service import clock_now
        self.register()
        record = self.save().json()
        day = clock_now().date().isoformat()
        first = self.client.get('/api/daily-reviews/'+day).json()
        self.assertEqual([row['id'] for row in first['events']],[record['id']])
        body = {'note':'值得记住的一小步','completion':True,'expected_version':0}
        self.assertEqual(self.client.put('/api/daily-reviews/'+day,json=body).status_code,200)
        self.assertEqual(self.client.put('/api/daily-reviews/'+day,json=body).status_code,409)
        self.assertEqual(self.client.put('/api/daily-reviews/'+day,json={**body,'expected_version':1}).status_code,200)
        with self.Session() as db:
            self.assertEqual(db.query(m.Event).count(),1)
            self.assertEqual(db.query(m.CoinLedger).count(),0)

    def test_credentials_keep_replace_rotate_clear_and_explicit_test(self):
        from types import SimpleNamespace
        from app.services import llm_config
        from ops import manage
        self.register(); self.configure_model()
        with self.Session() as db:
            original = db.query(LLMCredential).one()
            old = SimpleNamespace(encrypted_key=original.encrypted_key,key_id=original.key_id)
            old_version = original.config_version
        with patch('app.services.llm_service.llm_service.chat',return_value='OK') as model:
            keep=self.client.put('/api/llm-config',json={'group':'primary','api_key':'__KEEP__','model':'qa-new-model'})
            self.assertEqual(keep.status_code,200,keep.text)
            self.assertEqual(model.call_count,0)
            response=self.client.post('/api/llm-config/test',json={'group':'primary','expected_config_version':self.client.get('/api/llm-config').json()['primary']['config_version']})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(model.call_count,1)
        with self.Session() as db:
            row=db.query(LLMCredential).one()
            self.assertEqual(credentials.decrypt(row),'sk-fake-test-only-key')
            self.assertGreater(row.config_version,old_version)
            snapshot=llm_config.resolve_llm_config(db,row.user_id,llm_config.PURPOSE_JUDGE)
        replacement='sk-replacement-synthetic-only'
        self.assertEqual(self.client.put('/api/llm-config',json={'group':'primary','api_key':replacement}).status_code,200)
        with self.Session() as db:
            with self.assertRaises(ValueError): llm_config.assert_current(db,snapshot)
            self.assertEqual(credentials.decrypt(db.query(LLMCredential).one()),replacement)
        key_file=Path(settings.credential_key_file)
        keys=json.loads(key_file.read_text());keys['keys']['v2']=Fernet.generate_key().decode();keys['active']='v2'
        key_file.write_text(json.dumps(keys))
        with patch.dict(os.environ,{'DB_URL':'explicit-test-factory'}), patch('sys.argv',['manage.py','rotate-credentials']), patch('app.database.SessionLocal',self.Session):
            manage.main()
        with self.Session() as db:
            row=db.query(LLMCredential).one()
            self.assertEqual(row.key_id,'v2');self.assertEqual(credentials.decrypt(row),replacement)
        self.assertEqual(credentials.decrypt(old),'sk-fake-test-only-key')
        self.assertEqual(self.client.put('/api/llm-config',json={'group':'primary','api_key':''}).status_code,200)
        self.assertFalse(self.client.get('/api/llm-config').json()['primary']['configured'])
        self.assertEqual(self.client.post('/api/llm-config/test',json={'group':'primary'}).status_code,422)
        self.assertNotIn(replacement,self.client.get('/api/export').text)

    def test_endpoint_dns_pinning_ipv6_and_redirect_block(self):
        import httpx, socket
        def answer(address): return (socket.AF_INET6 if ':' in address else socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))
        for address in ['127.0.0.1','169.254.169.254','::1','fd00::1','::ffff:127.0.0.1']:
            with patch('app.services.credentials.socket.getaddrinfo',return_value=[answer('8.8.8.8'),answer(address)]):
                with self.assertRaises(ValueError): credentials.public_addresses('api.deepseek.com')
        calls=[]
        def response(transport,request):
            calls.append(request)
            self.assertEqual(request.url.host,'8.8.8.8')
            self.assertEqual(request.headers['Host'],'api.deepseek.com')
            self.assertEqual(request.extensions['sni_hostname'],'api.deepseek.com')
            return httpx.Response(302,headers={'Location':'http://169.254.169.254/latest/meta-data/'})
        with patch('app.services.credentials.socket.getaddrinfo',return_value=[answer('8.8.8.8')]),patch.object(httpx.HTTPTransport,'handle_request',response):
            with credentials.http_client() as client:
                self.assertEqual(client.post('https://api.deepseek.com/chat/completions').status_code,302)
        self.assertEqual(len(calls),1)

    def test_worker_config_replacement_and_transient_permanent_budget(self):
        from types import SimpleNamespace
        from datetime import timedelta
        from app.models.analysis import AnalysisJob
        from app.services import analysis_jobs,judge_service
        from app.services.time_service import utc_now
        self.register();self.configure_model()
        event=self.save().json()
        self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1})
        def change_config(*args,**kwargs):
            self.client.put('/api/llm-config',json={'group':'primary','api_key':'sk-new-synthetic-only'})
            return {'realistic':True,'confidence':1,'affected_attributes':[{'name':'体能','delta':1}]}
        claimed=analysis_jobs.claim(self.Session)
        with patch.object(judge_service.llm_service,'chat_json',side_effect=change_config):analysis_jobs.process(self.Session,claimed)
        self.assertEqual(self.client.get(f'/api/analysis-jobs/{claimed[0]}').json()['state'],'superseded')
        with self.Session() as db:self.assertEqual(db.query(m.AIJudgment).count(),0)
        for status,attempts in [(429,2),(401,1)]:
            event=self.save('重试预算测试').json()
            self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1})
            class FakeError(Exception): status_code=status
            def fail(**kwargs):raise FakeError('供应商原文含秘密，不应透出')
            client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)),close=lambda:None)
            with patch.object(judge_service.llm_service,'_get_client',return_value=client):
                claimed=analysis_jobs.claim(self.Session);analysis_jobs.process(self.Session,claimed)
                if status==429:
                    self.assertEqual(self.client.get(f'/api/analysis-jobs/{claimed[0]}').json()['state'],'queued')
                    with self.Session() as db:db.get(AnalysisJob,claimed[0]).next_retry_at=utc_now()-timedelta(seconds=1);db.commit()
                    analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
            job=self.client.get(f'/api/analysis-jobs/{claimed[0]}')
            self.assertEqual(job.json()['attempts'],attempts);self.assertEqual(job.json()['state'],'failed')
            self.assertNotIn('供应商原文',job.text)
        self.assertIsNone(analysis_jobs.claim(self.Session))

    def test_timezone_dst_and_backfill_review_uses_occurred_day(self):
        from datetime import date
        from app.services.time_service import date_range
        self.register()
        first,last=date_range(date(2026,3,8),'America/New_York')
        self.assertEqual((last-first).total_seconds(),23*3600)
        first,last=date_range(date(2026,11,1),'America/New_York')
        self.assertEqual((last-first).total_seconds(),25*3600)
        before=self.save('午夜前补录',occurred_at='2026-10-08T23:59:59+08:00').json()
        after=self.save('午夜后补录',occurred_at='2026-10-09T00:00:00+08:00').json()
        self.assertEqual([row['id'] for row in self.client.get('/api/daily-reviews/2026-10-08').json()['events']],[before['id']])
        self.assertEqual([row['id'] for row in self.client.get('/api/daily-reviews/2026-10-09').json()['events']],[after['id']])

    def test_worker_maintenance_expires_once_and_legacy_analysis_never_awards(self):
        from datetime import timedelta
        from app.services.time_service import clock_now
        from app.services import judge_service,achievement_service
        from app.worker import maintain
        self.register();self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        uid=current_user_id(self.client)
        with self.Session() as db:
            challenge=m.Challenge(user_id=uid,scope='daily',period_key='2026-10-09',title='到期维护测试',
                status='candidate',coin_reward=40,deposit=12,difficulty=1,expires_at=clock_now()+timedelta(hours=1))
            db.add(challenge);db.commit();cid=challenge.id;version=challenge.updated_at.isoformat()
        self.assertEqual(self.client.post(f'/api/challenges/{cid}/accept',json={'request_key':str(uuid4()),'expected_version':version}).status_code,200)
        with self.Session() as db:
            db.get(m.Challenge,cid).expires_at=clock_now()-timedelta(seconds=1);db.commit()
        self.assertEqual(self.client.get('/api/challenges').json()['challenges'][0]['status'],'accepted')
        maintain(self.Session)
        with self.Session() as db:
            self.assertEqual(db.get(m.Challenge,cid).status,'expired')
            counts=(db.query(m.Event).count(),db.query(m.AIJudgment).count(),db.query(m.AttributeHistory).count(),db.query(m.CoinLedger).count())
        maintain(self.Session)
        with self.Session() as db:
            self.assertEqual(counts,(db.query(m.Event).count(),db.query(m.AIJudgment).count(),db.query(m.AttributeHistory).count(),db.query(m.CoinLedger).count()))
        event=self.save('分析本身不得自动追授').json()
        with self.Session() as db:
            judgment=m.AIJudgment(user_id=uid,event_id=event['id'],status='pending',confidence=1)
            db.add(judgment);db.commit();db.refresh(judgment);db.expunge(judgment)
        with patch.object(judge_service,'judge_event',side_effect=AssertionError('云端不得同步分析')),patch.object(achievement_service,'check_and_grant',side_effect=AssertionError('分析不得发奖')):
            self.assertEqual(self.client.post(f"/api/events/{event['id']}/judge",json={}).status_code,409)
        for action in ('supplement','dispute'):
            with patch.object(judge_service,action,side_effect=AssertionError('云端不得同步重判')):
                self.assertEqual(self.client.post(f'/api/judgments/{judgment.id}/{action}',json={'detail':'保留回答'}).status_code,409)


def current_user_id(client):
    return client.get('/api/auth/me').json()['id']


if __name__ == '__main__': unittest.main()
