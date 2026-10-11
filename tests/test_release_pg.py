"""Real PG multi-connection/process tests. TEST_PG_URL must name the disposable QA database."""
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.config import settings
from app.database import Base
from app import models as m
from app.models.access import RequestReceipt, Invitation, AuthSession
from app.models.analysis import AnalysisJob
from app.services import analysis_jobs, auth_service
from app.services.time_service import utc_now
import test_release_readiness as release


@unittest.skipUnless(os.environ.get('TEST_PG_URL'),'requires isolated PostgreSQL')
class ReleasePGTests(unittest.TestCase):
    setUp=release.ReleaseTests.setUp
    tearDown=release.ReleaseTests.tearDown
    register=release.ReleaseTests.register
    save=release.ReleaseTests.save
    configure=release.ReleaseTests.configure

    def parallel(self,*functions):
        barrier=threading.Barrier(len(functions))
        def invoke(fn):barrier.wait(timeout=10);return fn()
        with ThreadPoolExecutor(len(functions)) as executor:
            return list(executor.map(invoke,functions))

    def test_import_forced_id_difference_all_semantic_paths_and_atomic_failure(self):
        from app.constants import ATTRIBUTE_DIMENSIONS
        target=self.register()['id']
        spec=importlib.util.spec_from_file_location('release_importer',Path('ops/import-sqlite.py'))
        importer=importlib.util.module_from_spec(spec);spec.loader.exec_module(importer)
        source=Path(self.temp.name)/'synthetic-legacy.sqlite3'
        engine=create_engine('sqlite:///'+str(source))
        with patch.object(settings,'run_mode','local'):
            Base.metadata.create_all(engine,tables=[Base.metadata.tables[name] for name in importer.TABLES])
            with Session(engine) as db:
                user=m.User(id=71,username='legacy');db.add(user);db.flush()
                db.add(m.UserProfile(user_id=71,coins=40,onboarding_completed=True))
                for index,name in enumerate(ATTRIBUTE_DIMENSIONS):db.add(m.Attribute(id=71+index,user_id=71,name=name,current_value=50))
                event=m.Event(id=71,user_id=71,event_type='positive',content='synthetic',params={'_challenge_id':71,'minutes':71},occurred_at=datetime(2026,10,9))
                db.add(event);db.flush()
                judgment=m.AIJudgment(id=71,user_id=71,event_id=71,confidence=1);db.add(judgment);db.flush()
                challenge=m.Challenge(id=71,user_id=71,title='synthetic',scope='daily',period_key='2026-10-09',event_id=71,judgment_id=71)
                exemption=m.Exemption(id=71,user_id=71,target_date='2026-10-09',period='morning',start_time='08:00',end_time='10:00')
                history=m.AttributeHistory(id=71,user_id=71,attribute_id=71,event_id=71,judgment_id=71,delta=0,value_after=50)
                db.add_all([challenge,exemption,history]);db.flush()
                db.add(m.JudgmentLog(user_id=71,judgment_id=71,action='delete',payload={'event_ids':[71],
                    'source_history_ids':[71],'reversed_changes':[{'attribute_id':71,'delta':71}],
                    'exemption':{'id':71,'coin_cost':71},'ordinary':[71]}))
                db.add(m.CoinLedger(user_id=71,delta=0,balance_after=40,source='exemption_purchase',ref_type='exemption',ref_id=71))
                db.commit()
        engine.dispose()
        # Consume target sequence IDs on another user so accidental same-ID success cannot mask a defect.
        with self.Session() as db:
            for table in ('events','ai_judgments','challenges','exemptions','attribute_history'):
                db.execute(text("SELECT setval(pg_get_serial_sequence('"+self.pg_schema+'.'+table+"','id'),150,true)"))
            db.commit()
        data,report=importer.preflight(source);self.assertFalse(report['blocked'],report['issues'])
        url=os.environ['TEST_PG_URL']+'?options=-csearch_path%3D'+self.pg_schema
        # A missing mapping after profile/rows have been written must roll the whole transaction back.
        broken=json.loads(json.dumps(data));broken['events'][0]['params']=json.dumps({'_challenge_id':999})
        with self.assertRaises(ValueError):importer.apply(broken,report,url,71,'friend',report['source_sha256'])
        with self.Session() as db:
            self.assertEqual(db.query(m.Event).count(),0)
            self.assertFalse(db.query(m.UserProfile).filter_by(user_id=target).one().onboarding_completed)
        result=importer.apply(data,report,url,71,'friend',report['source_sha256'])
        mapping=result['id_mapping'];self.assertNotEqual(mapping['challenges'][71],71)
        with self.Session() as db:
            event=db.query(m.Event).filter_by(user_id=target).one()
            self.assertEqual(event.params,{'_challenge_id':mapping['challenges'][71],'minutes':71})
            log=db.query(m.JudgmentLog).filter_by(user_id=target).one().payload
            self.assertEqual(log['source_history_ids'],[mapping['attribute_history'][71]])
            self.assertEqual(log['event_ids'],[mapping['events'][71]])
            self.assertEqual(log['exemption']['id'],mapping['exemptions'][71]);self.assertEqual(log['ordinary'],[71])
            self.assertEqual(db.query(m.CoinLedger).filter_by(user_id=target).one().ref_id,mapping['exemptions'][71])
            self.assertEqual(db.query(m.UserProfile).filter_by(user_id=target).one().coins,40)

    def test_invitation_recovery_concurrent_consumption_sessions_expiry_origin_throttle(self):
        from fastapi.testclient import TestClient
        def register(name):
            client=TestClient(release.baseline.app,base_url='https://rpg.test',headers={'Origin':'https://rpg.test'})
            try:
                response=client.post('/api/auth/register',json={'username':name,'password':'synthetic-password', 'invite_token':self.invite})
                return response.status_code,response.json(),client.cookies.get('__Host-gol_session')
            finally:client.close()
        results=self.parallel(lambda:register('device1'),lambda:register('device2'))
        self.assertEqual(sorted(r[0] for r in results),[201,400])
        success=next(r for r in results if r[0]==201);uid=success[1]['id'];cookie=success[2]
        with self.Session() as db:
            owner=db.get(m.User,self.owner_id);expired=auth_service.issue_invitation(db,owner,hours=-1);db.commit()
        self.assertEqual(self.client.post('/api/auth/register',json={'username':'expired','password':'synthetic-password','invite_token':expired}).status_code,400)
        def recover():
            client=TestClient(release.baseline.app,base_url='https://rpg.test',headers={'Origin':'https://rpg.test'})
            try:
                return client.post('/api/auth/recover',json={'recovery_code':success[1]['recovery_code'],'new_password':'synthetic-new-password'}).status_code
            finally:client.close()
        self.assertEqual(sorted(self.parallel(recover,recover)),[200,400])
        self.assertEqual(self.client.get('/api/auth/me',headers={'Cookie':'__Host-gol_session='+cookie}).status_code,401)
        with self.Session() as db:
            self.assertTrue(all(r.revoked for r in db.query(AuthSession).filter_by(user_id=uid)))
        login=self.client.post('/api/auth/login',json={'username':'device1' if results[0][0]==201 else 'device2','password':'synthetic-new-password'})
        self.assertEqual(login.status_code,200)
        self.client.headers['X-CSRF-Token']=login.json()['csrf_token'];oldcookie=self.client.cookies.get('__Host-gol_session')
        self.assertEqual(self.client.post('/api/events',json={'content':'x'},headers={'X-CSRF-Token':'bad'}).status_code,403)
        self.assertEqual(self.client.post('/api/events',json={'content':'x'},headers={'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.client.post('/api/auth/logout').status_code,200)
        self.assertEqual(self.client.get('/api/auth/me',headers={'Cookie':'__Host-gol_session='+oldcookie}).status_code,401)
        self.client.post('/api/auth/login',json={'username':'owner','password':'test-password-owner'})
        with self.Session() as db:
            for row in db.query(AuthSession).filter_by(user_id=self.owner_id):row.expires_at=utc_now()-timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get('/api/events').status_code,401)
        auth_service._attempts.clear()
        for _ in range(20):self.assertEqual(self.client.post('/api/auth/login',json={'username':'owner','password':'wrong-password-value'}).status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'owner','password':'wrong-password-value'}).status_code,429)

    def test_confirmation_delete_race_and_achievement_delete_race(self):
        uid=self.register()['id'];self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        for kind in ('confirm','achievement'):
            event=self.save(kind).json()
            with self.Session() as db:
                judgment=m.AIJudgment(user_id=uid,event_id=event['id'],status='pending',confidence=1,
                    suggested_changes=[{'name':'健康','delta':1,'reason':'synthetic','evidence':'synthetic'}],
                    achievement_suggestion={'name':'synthetic milestone','reason':'synthetic','state':'pending'})
                db.add(judgment);db.commit();jid=judgment.id;version=judgment.updated_at.isoformat()
            body={'request_key':str(uuid4()),'expected_version':version}
            if kind=='achievement':body['action']='grant'
            result=self.parallel(lambda:self.client.post(f'/api/judgments/{jid}/{kind}',json=body),
                lambda:self.client.request('DELETE',f'/api/events/{event["id"]}',json={'request_key':str(uuid4()),'expected_version':1}))
            self.assertEqual(result[1].status_code,200,result[1].text)
            self.assertIn(result[0].status_code,(200,404,409),result[0].text)
            with self.Session() as db:
                self.assertTrue(db.get(m.Event,event['id']).is_deleted)
                health=db.query(m.Attribute).filter_by(user_id=uid,name='健康').one()
                self.assertEqual(health.current_value,50)
                histories=db.query(m.AttributeHistory).filter_by(event_id=event['id']).all()
                self.assertEqual(sum(h.delta for h in histories),0)
                self.assertLessEqual(db.query(m.CoinLedger).filter_by(source='achievement').count(),1)

    def test_model_deadline_reaps_child_releases_pg_lock_and_allows_next_call(self):
        from app.services.llm_service import llm_service,USAGE_FACTORY,LLMError
        from app.services.llm_config import resolve_llm_config
        from app.services.model_boundary import run_deadline
        uid=self.register()['id'];self.configure()
        with self.Session() as db:config=resolve_llm_config(db,uid,'judge')
        token=USAGE_FACTORY.set(self.Session)
        try:
            def timeout(*args,**kwargs):
                return run_deadline([sys.executable,'-c','import sys,time;sys.stdin.read();time.sleep(30)'],{},.3)
            with patch('app.services.model_boundary.run_deadline',side_effect=timeout):
                with self.assertRaisesRegex(LLMError,'MODEL_TIMEOUT'):llm_service.chat([{'role':'user','content':'synthetic'}],config=config)
            with self.engine.connect() as connection:
                self.assertTrue(connection.execute(text('SELECT pg_try_advisory_lock(61111201)')).scalar())
                connection.execute(text('SELECT pg_advisory_unlock(61111201)'));connection.commit()
            with patch('app.services.model_boundary.run_deadline',return_value={'content':'OK'}):
                self.assertEqual(llm_service.chat([{'role':'user','content':'synthetic'}],config=config),'OK')
        finally:USAGE_FACTORY.reset(token)

    def test_expiry_settle_abandon_race_and_baseline_duplicate(self):
        from app.services import challenge_service
        uid=self.register()['id']
        results=self.parallel(lambda:self.client.post('/api/onboarding/neutral',json={'acknowledge':True}),
            lambda:self.client.post('/api/onboarding/neutral',json={'acknowledge':True}))
        self.assertTrue(all(r.status_code in (200,409) for r in results))
        with self.Session() as db:
            self.assertEqual(db.query(m.UserProfile).filter_by(user_id=uid).one().coins,80)
            self.assertEqual(db.query(m.CoinLedger).filter_by(source='onboarding_bonus').count(),1)
            event=m.Event(user_id=uid,event_type='positive',content='challenge synthetic',origin='challenge');db.add(event);db.flush()
            judgment=m.AIJudgment(user_id=uid,event_id=event.id,status='pending',confidence=1,
                suggested_changes=[{'name':'规划力','delta':1,'reason':'synthetic','evidence':'synthetic'}]);db.add(judgment);db.flush()
            ch=m.Challenge(user_id=uid,scope='daily',period_key='2026-10-09',title='race',status='accepted',
                event_id=event.id,judgment_id=judgment.id,deposit=0,coin_reward=10,outcome='done',
                related_attributes=['规划力'],expires_at=utc_now()-timedelta(seconds=1))
            db.add(ch);db.commit();cid=ch.id;eid=event.id;version=ch.updated_at.isoformat()
        def expire():
            with self.Session() as db:
                user=db.get(m.User,uid);db.info['user_id']=uid
                challenge_service.expire_stale(db,user)
            return 'expired'
        results=self.parallel(expire,
            lambda:self.client.post(f'/api/challenges/{cid}/settle',json={'request_key':str(uuid4()),'expected_version':version}),
            lambda:self.client.post(f'/api/challenges/{cid}/abandon',json={'note':''}))
        with self.Session() as db:
            ch=db.get(m.Challenge,cid);self.assertIn(ch.status,('settled','expired','abandoned'))
            self.assertEqual(db.query(m.Event).filter_by(id=eid).count(),1)
            self.assertEqual(db.query(m.AIJudgment).filter_by(event_id=eid).count(),1)
            self.assertEqual(db.query(m.AttributeHistory).filter_by(event_id=eid).count(),1)
            self.assertLessEqual(db.query(m.CoinLedger).filter_by(source='challenge_reward').count(),1)
            self.assertLessEqual(db.query(m.CoinLedger).filter_by(source='challenge_forfeit').count(),1)

    def start_worker(self,stage,root):
        root.mkdir()
        env={**os.environ,'RUN_MODE':'cloud','PUBLIC_ORIGIN':'https://rpg.test',
            'DB_URL':os.environ['TEST_PG_URL']+'?options=-csearch_path%3D'+self.pg_schema,
            'CREDENTIAL_KEY_FILE':settings.credential_key_file}
        process=subprocess.Popen([sys.executable,'tests/worker_process_fixture.py'],stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        process.stdin.write(json.dumps({'root':str(root.absolute()),'stage':stage}).encode());process.stdin.close()
        return process

    def await_phase(self,process,root):
        for _ in range(500):
            if (root/'phase').exists():return
            if process.poll() is not None:self.fail(process.stderr.read().decode(errors='replace'))
            time.sleep(.02)
        process.kill();process.wait();self.fail('worker barrier timeout')

    def test_real_worker_crashes_claim_request_before_write_and_recovers(self):
        uid=self.register()['id'];self.configure()
        with self.Session() as db:
            db.execute(text('SET LOCAL search_path TO "'+self.pg_schema+'"'))
            db.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
            db.execute(text("INSERT INTO alembic_version VALUES ('b004_reports')"));db.commit()
        for stage in ('claimed','request','before_write'):
            event=self.save(stage).json()
            response=self.client.post(f'/api/events/{event["id"]}/analysis-jobs',json={'request_key':str(uuid4()),'event_version':1})
            self.assertEqual(response.status_code,202,response.text);jid=response.json()['id']
            root=Path(self.temp.name)/stage
            process=self.start_worker(stage,root)
            try:self.await_phase(process,root)
            finally:process.kill();process.wait(timeout=5);process.stderr.close()
            with self.Session() as db:
                job=db.get(AnalysisJob,jid);self.assertEqual(job.state,'running');old=job.lease_token
                self.assertEqual(db.query(m.AIJudgment).filter_by(event_id=event['id']).count(),0)
                job.lease_until=utc_now()-timedelta(seconds=1);db.commit()
            replacement=Path(self.temp.name)/(stage+'-replacement')
            process=self.start_worker('none',replacement)
            try:
                process.wait(timeout=15)
                self.assertEqual(process.returncode,0,process.stderr.read().decode(errors='replace'))
            finally:
                if process.poll() is None:process.kill();process.wait()
                process.stderr.close()
            with self.Session() as db:
                job=db.get(AnalysisJob,jid);self.assertEqual(job.state,'ready');self.assertLessEqual(job.attempts,2)
                self.assertEqual(db.query(m.AIJudgment).filter_by(event_id=event['id']).count(),1)
                self.assertEqual(db.query(m.CoinLedger).count(),0)
                self.assertEqual(db.query(m.AttributeHistory).count(),0)
            analysis_jobs.process(self.Session,(jid,old,uid))
            with self.Session() as db:self.assertEqual(db.get(AnalysisJob,jid).state,'ready')

    def test_real_workers_dual_claim_cancel_edit_delete_key_and_lease_late_results(self):
        uid=self.register()['id'];self.client.post('/api/onboarding/neutral',json={'acknowledge':True});self.configure()
        with self.Session() as db:
            db.execute(text('SET LOCAL search_path TO "'+self.pg_schema+'"'))
            db.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
            db.execute(text("INSERT INTO alembic_version VALUES ('b004_reports')"));db.commit()
        for change in ('dual','cancel','edit','delete','key','lease'):
            event=self.save(change).json()
            result=self.client.post(f'/api/events/{event["id"]}/analysis-jobs',json={'request_key':str(uuid4()),'event_version':1})
            self.assertEqual(result.status_code,202,result.text);jid=result.json()['id']
            root=Path(self.temp.name)/('late-'+change);process=self.start_worker('request',root)
            try:
                self.await_phase(process,root)
                if change=='dual':
                    otherroot=Path(self.temp.name)/'other-worker';other=self.start_worker('claimed',otherroot)
                    try:
                        time.sleep(2)
                        self.assertIsNone(other.poll());self.assertFalse((otherroot/'phase').exists())
                        with self.Session() as db:self.assertEqual(db.query(AnalysisJob).filter_by(state='running').count(),1)
                    finally:other.kill();other.wait(timeout=5);other.stderr.close()
                elif change=='cancel':self.assertEqual(self.client.post(f'/api/analysis-jobs/{jid}/cancel').status_code,200)
                elif change=='edit':self.assertEqual(self.client.put(f'/api/events/{event["id"]}',json={'content':'changed','expected_version':1}).status_code,200)
                elif change=='delete':self.assertEqual(self.client.request('DELETE',f'/api/events/{event["id"]}',json={'request_key':str(uuid4()),'expected_version':1}).status_code,200)
                elif change=='key':self.assertEqual(self.configure(api_key='new-synthetic-key').status_code,200)
                elif change=='lease':
                    with self.Session() as db:db.get(AnalysisJob,jid).lease_until=utc_now()-timedelta(seconds=1);db.commit()
                    replacement=analysis_jobs.claim(self.Session);self.assertEqual(replacement[0],jid)
                (root/'continue').write_text('continue')
                process.wait(timeout=15);self.assertEqual(process.returncode,0,process.stderr.read().decode(errors='replace'))
                with self.Session() as db:
                    job=db.get(AnalysisJob,jid)
                    self.assertEqual(job.state,{'dual':'ready','cancel':'cancelled','lease':'running'}.get(change,'superseded'))
                    self.assertEqual(db.query(m.AIJudgment).filter_by(event_id=event['id']).count(),1 if change=='dual' else 0)
                    self.assertEqual(db.query(m.AttributeHistory).count(),0)
                    if change=='lease':job.state='cancelled';job.lease_token=None;db.commit()
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=5)
                process.stderr.close()
