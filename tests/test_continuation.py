"""Synthetic continuation contracts. PG is optional and never inferred from .env."""
import unittest
from uuid import uuid4
from unittest.mock import patch
import tests.test_next_iteration as fixtures
from app.models import Event
from app.models.workflow import ReviewTurn,ReviewAnalysis,DiaryRevision
from app.services import analysis_jobs


class ContinuationTests(unittest.TestCase):
    setUp=fixtures.CloudTests.setUp
    tearDown=fixtures.CloudTests.tearDown
    register=fixtures.CloudTests.register
    configure_model=fixtures.CloudTests.configure_model

    def write(self,path,body=None,version=0,method='POST',key=None):
        return self.client.request(method,'/api'+path,json={'request_key':key or str(uuid4()),'expected_version':version,**(body or {})})

    def diary(self,day='2026-10-16',content='今天部署了项目。',version=0):
        response=self.write('/diaries/'+day,{'content':content,'ai_permission':'allowed'},version,'PUT')
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['diary']

    def session(self):
        diary=self.diary()
        response=self.write('/diaries/2026-10-16/review-sessions',version=diary['content_version'])
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def run_review(self,session,result):
        response=self.write(f"/review-sessions/{session['id']}/analyze",version=session['version'])
        self.assertEqual(response.status_code,200,response.text)
        with patch('app.services.diary_review.llm_service.chat_json',return_value=result):
            analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        return self.client.get(f"/api/review-sessions/{session['id']}").json()

    def test_diary_single_original_revisions_replay_and_legacy_unchanged(self):
        self.register();key=str(uuid4())
        body={'content':'原文','request_key':key,'expected_version':0}
        first=self.client.put('/api/diaries/2026-10-16',json=body)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.client.put('/api/diaries/2026-10-16',json=body).json(),first.json())
        self.assertEqual(self.write('/diaries/2026-10-16',{'content':'冲突'},0,'PUT').status_code,409)
        second=self.diary(content='修改后的原文',version=1)
        self.assertEqual(second['id'],first.json()['diary']['id'])
        result=self.client.get('/api/diaries/2026-10-16').json()
        self.assertEqual([r['content'] for r in result['revisions']],['原文','修改后的原文'])
        self.assertEqual(self.client.post('/api/events',json={'content':'旧 journal','source':'journal','client_request_id':str(uuid4())}).status_code,200)
        with self.Session() as db:
            self.assertIsNone(db.query(Event).filter_by(content='旧 journal').one().record_kind)

    def test_review_exact_questions_answers_skip_and_old_source_snapshot(self):
        self.register();self.configure_model();session=self.session()
        state=self.run_review(session,{'questions':['部署中最大的困难？','还有需要补充的吗？'],'summary':'等待回答','analysis':[]})
        self.assertEqual(state['jobs'][0]['state'],'ready',state)
        first,second=state['turns']
        response=self.write(f"/review-sessions/{state['id']}/turns/{first['id']}",{'session_version':state['version'],'answer':'解决了迁移冲突。'},first['version'],'PUT')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.write(f"/review-sessions/{state['id']}/turns/{first['id']}",{'session_version':state['version'],'answer':'覆盖'},first['version'],'PUT').status_code,409)
        state=self.client.get(f"/api/review-sessions/{state['id']}").json()
        response=self.write(f"/review-sessions/{state['id']}/turns/{second['id']}",{'session_version':state['version'],'skip':True},second['version'],'PUT')
        self.assertEqual(response.status_code,200,response.text)
        state=self.client.get(f"/api/review-sessions/{state['id']}").json()
        state=self.run_review(state,{'questions':[],'summary':'完成迁移验证','analysis':['依据对应回答']})
        self.assertEqual(state['analyses'][-1]['payload']['turns_snapshot'][0]['question'],'部署中最大的困难？')
        self.assertEqual(state['analyses'][-1]['payload']['turns_snapshot'][1]['state'],'skipped')
        self.assertEqual(self.client.get('/api/diaries/2026-10-16').json()['diary']['content'],'今天部署了项目。')
        self.diary(content='新版原文',version=1)
        old=self.client.get(f"/api/review-sessions/{state['id']}").json()
        self.assertTrue(old['source_changed']);self.assertEqual(old['sources'][0]['content'],'今天部署了项目。')
        self.assertEqual(self.write(f"/review-sessions/{state['id']}/analyze",version=old['version']).status_code,409)

    def test_review_late_answer_cannot_publish_after_source_edit(self):
        self.register();self.configure_model();session=self.session()
        response=self.write(f"/review-sessions/{session['id']}/analyze",version=1)
        self.assertEqual(response.status_code,200,response.text)
        def edit(*args,**kwargs):
            with self.Session() as db:
                event=db.query(Event).filter_by(record_kind='diary').one();event.content_version+=1;db.commit()
            return {'questions':['迟到问题'],'summary':'旧结果','analysis':[]}
        with patch('app.services.diary_review.llm_service.chat_json',side_effect=edit):analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        result=self.client.get(f"/api/review-sessions/{session['id']}").json()
        self.assertEqual(result['jobs'][0]['state'],'superseded');self.assertEqual(result['turns'],[])

    def test_checklist_no_events_or_rewards_and_owned_references(self):
        self.register()
        before=self.client.get('/api/coins').json()['balance']
        result=self.write('/life-checklists/2026-10-16',{'enabled':True,'entries':{'活动':'skipped'}},0,'PUT')
        self.assertEqual(result.status_code,200,result.text)
        self.assertIsInstance(result.json()['id'],int)
        self.assertEqual(self.client.get('/api/events').json(),[])
        self.assertEqual(self.client.get('/api/coins').json()['balance'],before)
        self.assertEqual(self.write('/life-checklists/2026-10-16',{'event_ids':[999999]},1,'PUT').status_code,404)

    def schedule(self,**extra):
        response=self.write('/plan-schedules',{'name':'运动','frequency':'daily','start':'2026-10-01',**extra})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_schedule_dates_interval_and_missed_lock_without_event(self):
        from app.routers.plans import due
        from datetime import date
        self.register();schedule=self.schedule(frequency='weekdays',weekdays=[0])
        self.assertEqual(len(self.client.get('/api/plan-occurrences?day=2026-10-12').json()['items']),1)
        self.assertEqual(self.client.get('/api/plan-occurrences?day=2026-10-13').json()['items'],[])
        self.assertTrue(due({'start':'2026-12-30','frequency':'interval','interval':3},date(2027,1,2)))
        body={'outcome':'missed','schedule_version':1};path=f"/plan-schedules/{schedule['id']}/occurrences/2026-10-12"
        key=str(uuid4());first=self.write(path,body,0,'PUT',key)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.write(path,body,0,'PUT',key).json(),first.json())
        self.assertEqual(self.write(path,{'outcome':'done','content':'偷偷改完成','schedule_version':1},1,'PUT').status_code,409)
        self.assertEqual(self.client.get('/api/events').json(),[])
        fixed=self.write(path,{'outcome':'partial','content':'实际运动十分钟','actual':10,'unit':'分钟','schedule_version':1,'correction':True,'reason':'纠正误选'},1,'PUT')
        self.assertEqual(fixed.status_code,200,fixed.text)
        self.assertEqual(fixed.json()['facts']['actual'],10)
        self.assertEqual(len(fixed.json()['history']),2)
        self.assertEqual(len(self.client.get('/api/events').json()),1)

    def test_fact_relation_guards_second_booking_and_atomic_rollback(self):
        from app.models import AIJudgment,UserProfile
        from app.models.workflow import FactSettlement
        from app.services import judge_service
        self.register();self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        ids=[]
        for content in ('晨跑','同一次晨跑补充'):
            response=self.client.post('/api/events',json={'content':content,'record_kind':'event','client_request_id':str(uuid4())})
            self.assertEqual(response.status_code,200,response.text);ids.append(response.json()['id'])
        proposal=self.write('/fact-relations',{'source_id':ids[1],'target_id':ids[0],'source_version':1,'target_version':1,'reason':'用户确认同一晨跑'})
        self.assertEqual(proposal.status_code,200,proposal.text)
        response=self.write('/fact-relations/'+str(proposal.json()['id'])+'/decision',{'accept':True},1)
        self.assertEqual(response.status_code,200,response.text)
        with self.Session() as db:
            user_id=db.query(Event).first().user_id;db.info['user_id']=user_id
            first=AIJudgment(user_id=user_id,event_id=ids[0],status='pending',confidence=1,suggested_changes=[],analysis=[])
            second=AIJudgment(user_id=user_id,event_id=ids[1],status='pending',confidence=1,suggested_changes=[],analysis=[])
            db.add_all([first,second]);db.commit()
            judge_service.confirm(db,first)
            with self.assertRaisesRegex(ValueError,'同一事实'):judge_service.confirm(db,second)
            self.assertEqual(db.query(FactSettlement).count(),1)
            self.assertEqual(db.get(AIJudgment,second.id).status,'pending')

    def test_exports_safe_formats_exact_questions_and_named_date_metrics(self):
        import csv,io
        self.register();self.configure_model()
        session=self.session()
        state=self.run_review(session,{'questions':['确切问题 <script>alert(1)</script>'],'summary':'总结','analysis':['依据']})
        malicious='=HYPERLINK("evil")\n<script>alert(1)</script>\n```text\n多行中文'
        from datetime import datetime,timezone
        with patch('app.models.clock_now',return_value=datetime(2026,10,16,0,30,tzinfo=timezone.utc)):
            self.client.post('/api/events',json={'content':malicious,'title':'=危险公式','record_kind':'event','client_request_id':str(uuid4()),'occurred_on':'2026-10-16','time_precision':'date'})
            self.client.post('/api/events',json={'content':'第二件事','record_kind':'event','client_request_id':str(uuid4()),'occurred_on':'2026-10-16','time_precision':'date'})
        data=self.client.get('/api/export').json()
        self.assertEqual(data['format_version'],5)
        self.assertIn('review_turns',data['tables']);self.assertIn('fact_settlements',data['tables'])
        self.assertFalse(data['restore_supported'])
        legacy=self.client.get('/api/export?schema_version=3').json()
        self.assertEqual(legacy['format_version'],3);self.assertNotIn('review_turns',legacy['tables'])
        page=self.client.get('/api/export?format=html').text
        self.assertIn('&lt;script&gt;',page);self.assertNotIn('<script>',page);self.assertIn('尚未回答',page)
        markdown=self.client.get('/api/export?format=markdown').text
        self.assertIn('````text',markdown);self.assertIn('确切问题',markdown)
        plain=self.client.get('/api/export?format=html&include_questions=false').text
        self.assertNotIn('确切问题',plain)
        csv_rows=list(csv.reader(io.StringIO(self.client.get('/api/export?format=csv').text.lstrip('\ufeff'))))
        formula=next(row for row in csv_rows if 'HYPERLINK' in str(row))
        self.assertTrue(formula[4].startswith("'="));self.assertTrue(formula[5].startswith("'="))
        stats=self.client.get('/api/record-metrics').json()
        self.assertEqual(stats['metrics']['event_content_days']['count'],1)
        self.assertEqual(stats['metrics']['diary_content_days']['count'],1)
        self.assertEqual(stats['reward_policy'],'unconfigured')
        from app.services.achievement_service import _metrics
        from app.models import User
        with self.Session() as db:
            old=_metrics(db,db.query(User).filter_by(username='friend').one());self.assertEqual(old['journal_total'],0);self.assertEqual(old['events_total'],2)
            user=db.query(User).filter_by(username='friend').one();user.timezone='Pacific/Honolulu';db.commit()
        self.assertEqual(self.client.get('/api/record-metrics').json()['metrics']['event_saved_days']['dates'],['2026-10-16'])

    def login_owner(self):
        result=self.client.post('/api/auth/login',json={'username':'owner','password':'test-password-owner'})
        self.assertEqual(result.status_code,200,result.text)
        self.client.headers['X-CSRF-Token']=result.json()['csrf_token']

    def test_admin_permissions_registration_switch_disable_and_audit(self):
        friend=self.register();self.diary(content='朋友隐私原文')
        self.assertEqual(self.client.get('/api/admin/users').status_code,403)
        self.login_owner()
        listed=self.client.get('/api/admin/users').json()
        self.assertNotIn('朋友隐私',str(listed));self.assertNotIn('password_hash',str(listed))
        self.assertEqual(self.client.get('/api/diaries/2026-10-16').json()['diary'],None)
        policy={'site_name':'合成站点','description':'测试','registration':'open','email_required':False,'password_sessions':'all','reason':'隔离测试确认策略'}
        response=self.write('/admin/site',policy,0,'PUT')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/api/auth/options').json()['registration'],'open')
        disabled=self.write('/admin/users/'+str(friend['id'])+'/status',{'status':'disabled','reason':'隔离测试停用'},1)
        self.assertEqual(disabled.status_code,200,disabled.text)
        self.assertEqual(self.write('/admin/users/'+str(self.owner_id)+'/status',{'status':'disabled','reason':'禁止唯一管理停用'},1).status_code,409)
        self.assertGreaterEqual(len(self.client.get('/api/admin/audit').json()['items']),2)
        result=self.client.post('/api/auth/register',json={'username':'direct_friend','password':'direct-test-password'})
        self.assertEqual(result.status_code,201,result.text)
        self.client.headers['X-CSRF-Token']=result.json()['csrf_token']
        self.assertEqual(self.client.get('/api/admin/audit').status_code,403)

    def test_email_unavailable_single_use_bind_recovery_and_password_revocation(self):
        from app.services import mail_service
        registered=self.register()
        with patch.object(mail_service,'mailer',return_value=mail_service.DisabledMailer()):
            response=self.client.post('/api/auth/email/bind-request',json={'email':'friend@example.test'})
            self.assertEqual(response.status_code,503)
        outbox=mail_service.TestMailer()
        with patch.object(mail_service,'mailer',return_value=outbox):
            self.assertEqual(self.client.post('/api/auth/email/bind-request',json={'email':'friend@example.test'}).status_code,200)
            token=outbox.outbox[-1]['token']
            self.assertEqual(self.client.post('/api/auth/email/verify',json={'token':token}).status_code,200)
            self.assertEqual(self.client.post('/api/auth/email/verify',json={'token':token}).status_code,400)
            me=self.client.get('/api/auth/me').json();self.assertTrue(me['email_verified'])
            from fastapi import HTTPException
            with patch.object(outbox,'send',side_effect=HTTPException(503,'synthetic SMTP failure')):
                known=self.client.post('/api/auth/email/recover-request',json={'email':'friend@example.test'})
                unknown=self.client.post('/api/auth/email/recover-request',json={'email':'missing@example.test'})
                self.assertEqual(known.status_code,200);self.assertEqual(known.json(),unknown.json())
                self.assertIn('受理不代表投递成功',known.json()['message'])
            self.assertEqual(self.client.post('/api/auth/email/recover-request',json={'email':'friend@example.test'}).status_code,200)
            from app.services.mail_queue import deliver_one
            while deliver_one(self.Session):pass
            reset=outbox.outbox[-1]['token']
            result=self.client.post('/api/auth/email/reset-password',json={'token':reset,'new_password':'new-email-test-password'})
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(self.client.get('/api/events').status_code,401)
            self.assertEqual(self.client.post('/api/auth/email/reset-password',json={'token':reset,'new_password':'second-test-password'}).status_code,400)
        login=self.client.post('/api/auth/login',json={'username':'friend','password':'new-email-test-password'})
        self.client.headers['X-CSRF-Token']=login.json()['csrf_token']
        me=self.client.get('/api/auth/me').json()
        changed=self.client.post('/api/auth/password',json={'current_password':'new-email-test-password','new_password':'changed-test-password','expected_version':me['credentials_version']})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertTrue(changed.json()['reauthenticate']);self.assertEqual(self.client.get('/api/events').status_code,401)
        self.assertEqual(self.client.post('/api/auth/recover',json={'recovery_code':registered['recovery_code'],'new_password':'old-code-test-password'}).status_code,400)

    def friend_login(self):
        response=self.client.post('/api/auth/login',json={'username':'friend','password':'friend-test-password'})
        self.assertEqual(response.status_code,200,response.text)
        self.client.headers['X-CSRF-Token']=response.json()['csrf_token']

    def test_mainline_synthetic_rule_preview_original_atomic_confirmation(self):
        from app.models import Goal,AIJudgment
        self.register();self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        event=self.client.post('/api/events',json={'content':'阅读并整理笔记','record_kind':'event','ai_permission':'allowed','client_request_id':str(uuid4())}).json()
        with self.Session() as db:
            user_id=db.query(Event).first().user_id;goal=Goal(user_id=user_id,description='合成阅读目标');db.add(goal);db.flush();goal_id=goal.id
            judgment=AIJudgment(user_id=user_id,event_id=event['id'],status='pending',confidence=1,source_snapshot=[{'id':event['id'],'version':1,'permission_version':event['ai_permission_version']}],suggested_changes=[{'name':'体能','delta':1,'reason':'合成','evidence':''}],analysis=[]);db.add(judgment);db.commit();judgment_id=judgment.id
        mainline=self.write('/mainlines',{'goal_id':goal_id,'active':True}).json()
        body={'mainline_id':mainline['id'],'mainline_version':1,'event_id':event['id'],'event_version':1,'judgment_id':judgment_id,'minutes':15,'result':False,'evidence':'合成测试事实'}
        self.assertEqual(self.write('/reward-previews',body).status_code,409)
        self.login_owner()
        rule={'enabled':True,'approved':True,'effective_from':'2026-01-01','tiers':[{'code':'synthetic_effort','min_minutes':10,'result_required':False,'amount':7}],
            'daily_cap':20,'per_fact_cap':10,'max_active':2,'stacking':'replace_legacy','cap_basis':'confirmation','reason':'仅隔离测试规则，不是正式金额'}
        configured=self.write('/admin/rules/mainline',rule,0,'PUT');self.assertEqual(configured.status_code,200,configured.text)
        self.friend_login()
        preview=self.write('/reward-previews',body)
        self.assertEqual(preview.status_code,200,preview.text);preview=preview.json();self.assertEqual(preview['amount'],7)
        payload={'request_key':str(uuid4()),'expected_version':preview['snapshot']['judgment_version'],'reward_preview_id':preview['id']}
        confirmed=self.client.post(f'/api/judgments/{judgment_id}/confirm',json=payload)
        self.assertEqual(confirmed.status_code,200,confirmed.text);self.assertEqual(confirmed.json()['coins_gained'],7)
        self.assertEqual(confirmed.json()['balance'],87)
        self.assertEqual(self.client.post(f'/api/judgments/{judgment_id}/confirm',json=payload).json(),confirmed.json())
        self.assertEqual(len(self.client.get('/api/mainlines').json()['previews']),1)
        # A fault after attribute writes cannot leave money, fact claims or preview state committed.
        with self.Session() as db:
            second=Event(user_id=user_id,event_type='positive',record_kind='event',source='form',content='第二件合成事实',ai_permission='allowed');db.add(second);db.flush()
            second_judgment=AIJudgment(user_id=user_id,event_id=second.id,status='pending',confidence=1,source_snapshot=[{'id':second.id,'version':second.content_version,'permission_version':second.ai_permission_version}],suggested_changes=[{'name':'体能','delta':1,'reason':'合成','evidence':''}],analysis=[]);db.add(second_judgment);db.commit();second_id=second.id;second_jid=second_judgment.id
        second_preview=self.write('/reward-previews',{**body,'event_id':second_id,'judgment_id':second_jid}).json()
        second_payload={'request_key':str(uuid4()),'expected_version':second_preview['snapshot']['judgment_version'],'reward_preview_id':second_preview['id']}
        with patch('app.services.coin_service.grant',side_effect=RuntimeError('synthetic injected money failure')),self.assertRaises(RuntimeError):self.client.post(f'/api/judgments/{second_jid}/confirm',json=second_payload)
        from app.models.policies import MainlineAward,RewardPreview
        from app.models.workflow import FactSettlement
        with self.Session() as db:
            self.assertEqual(db.query(MainlineAward).count(),1);self.assertEqual(db.query(FactSettlement).count(),1)
            self.assertEqual(db.get(AIJudgment,second_jid).status,'pending');self.assertEqual(db.get(RewardPreview,second_preview['id']).state,'pending')
        self.assertEqual(self.client.get('/api/coins').json()['balance'],87)

    def test_dynamic_semantic_dedupe_unconfigured_reward_and_claim_once(self):
        self.register();self.client.post('/api/onboarding/neutral',json={'acknowledge':True});self.diary()
        criteria={'name':'合成一天候选','metric':'diary_content_days','shape':'total_days','target':1}
        first=self.write('/dynamic-candidates',criteria);self.assertEqual(first.status_code,200,first.text);first=first.json()
        renamed=self.write('/dynamic-candidates',{**criteria,'name':'重命名同一指标'}).json();self.assertEqual(first['id'],renamed['id'])
        self.assertEqual(self.write(f"/dynamic-candidates/{first['id']}/decision",{'action':'claim'},1).status_code,409)
        self.login_owner()
        rule={'enabled':True,'approved':True,'effective_from':'2026-01-01','rewards':{first['semantic_key']:11},'user_total_cap':11,'allow_fixed_stack':False,'reason':'隔离测试金额'}
        result=self.write('/admin/rules/dynamic',rule,0,'PUT');self.assertEqual(result.status_code,200,result.text)
        self.friend_login();key=str(uuid4());path=f"/dynamic-candidates/{first['id']}/decision"
        claimed=self.write(path,{'action':'claim'},1,key=key)
        self.assertEqual(claimed.status_code,200,claimed.text)
        self.assertEqual(self.write(path,{'action':'claim'},1,key=key).json(),claimed.json())
        self.assertEqual(self.client.get('/api/coins').json()['balance'],91)
        self.assertEqual(self.write(path,{'action':'claim'},2).status_code,409)

    def test_hosted_separate_secret_selection_budget_unknown_charge_and_stale_version(self):
        import json
        from pathlib import Path
        from types import SimpleNamespace
        from app.config import settings
        from app.services import llm_config,hosted_ai
        from app.services.llm_service import llm_service,USAGE_FACTORY,LLMError
        from app.models.policies import HostedUsage,AIPreference
        self.register();self.login_owner()
        secret=Path(self.temp.name)/'hosted-synthetic.json';secret.write_text(json.dumps({'TEST_HOSTED':'synthetic-site-key-only'}))
        rule={'enabled':True,'approved':True,'provider':'deepseek','model':'synthetic-chat','secret_ref':'TEST_HOSTED','user_daily_calls':2,'global_daily_calls':3,
            'global_daily_tokens':20000,'daily_cost_cap':10000,'input_tokens':4096,'output_tokens':64,'input_rate':1000000,'output_rate':1000000,'currency_unit':'synthetic-unit','price_checked_on':'2026-10-16','reason':'仅测试，不是真实价格'}
        with patch.object(settings,'hosted_secret_file',str(secret)):
            self.assertEqual(self.write('/admin/hosted-ai',{**rule,'input_rate':True},0,'PUT').status_code,422)
            result=self.write('/admin/hosted-ai',rule,0,'PUT');self.assertEqual(result.status_code,200,result.text)
            self.friend_login();user_id=self.client.get('/api/auth/me').json()['id']
            public=self.client.get('/api/ai/preferences').json();self.assertNotIn('synthetic-site-key',str(public));self.assertNotIn('secret_ref',str(public))
            self.assertEqual(self.write('/ai/preferences',{'mode':'off'},0,'PUT').status_code,200)
            with self.Session() as db,self.assertRaises(LLMError):llm_config.resolve_llm_config(db,user_id,'judge')
            self.assertEqual(self.write('/ai/preferences',{'mode':'hosted','acknowledge':True,'hosted_version':1},1,'PUT').status_code,200)
            with self.Session() as db:config=llm_config.resolve_llm_config(db,user_id,'judge')
            self.assertEqual(config.api_key,'synthetic-site-key-only');self.assertEqual(config.scope,'hosted')
            response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='OK'))],usage=SimpleNamespace(prompt_tokens=10,completion_tokens=5))
            fake=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:response)),close=lambda:None)
            factory_token=USAGE_FACTORY.set(self.Session)
            try:
                with patch.object(llm_service,'_get_client',side_effect=RuntimeError('synthetic init failure')),self.assertRaises(RuntimeError):llm_service.chat([{'role':'user','content':'合成内容'}],config=config)
                with patch.object(llm_service,'_get_client',return_value=fake):self.assertEqual(llm_service.chat([{'role':'user','content':'合成内容'}],config=config),'OK')
                secret.write_text(json.dumps({'TEST_HOSTED':'rotated-synthetic-key'}))
                with self.Session() as db:
                    with self.assertRaisesRegex(ValueError,'轮换'):llm_config.assert_current(db,config)
                    config=llm_config.resolve_llm_config(db,user_id,'judge')
                fake.chat.completions.create=lambda **kw:(_ for _ in ()).throw(TimeoutError())
                with patch.object(llm_service,'_get_client',return_value=fake),self.assertRaisesRegex(LLMError,'MODEL_TIMEOUT'):llm_service.chat([{'role':'user','content':'合成内容'}],config=config)
                with self.assertRaisesRegex(LLMError,'MODEL_DAILY_LIMIT'):llm_service.chat([{'role':'user','content':'合成内容'}],config=config)
                with self.Session() as db:
                    owner_pref=AIPreference(user_id=self.owner_id,mode='hosted',version=1);db.add(owner_pref);db.commit();owner_config=hosted_ai.resolve(db,self.owner_id,owner_pref)
                response.usage.prompt_tokens=5000
                fake.chat.completions.create=lambda **kw:response
                with patch.object(llm_service,'_get_client',return_value=fake),self.assertRaisesRegex(LLMError,'MODEL_DAILY_LIMIT'):llm_service.chat([{'role':'user','content':'合成内容'}],config=owner_config)
            finally:USAGE_FACTORY.reset(factory_token)
            with self.Session() as db:
                usage=db.query(HostedUsage).order_by(HostedUsage.id).all()
                self.assertEqual([(r.state,r.charged_cost) for r in usage],[('released',0),('settled',15),('unknown',4160),('overrun',5005)])
                pref=db.query(AIPreference).filter_by(user_id=user_id).one();pref.mode='off';pref.version+=1;db.commit()
                with self.assertRaises(ValueError):llm_config.assert_current(db,config)

    def test_new_resource_ownership_and_schedule_timezone_snapshot(self):
        from datetime import datetime,timezone
        from app.models import User
        registered=self.register();session=self.session()
        with self.Session() as db:
            user=db.get(User,registered['id']);user.timezone='America/Los_Angeles';db.commit()
        schedule=self.schedule(frequency='weekdays',weekdays=[3])
        with self.Session() as db:
            user=db.get(User,registered['id']);user.timezone='Asia/Shanghai';db.commit()
        with patch('app.routers.plans.utc_now',return_value=datetime(2026,10,16,0,30,tzinfo=timezone.utc)):
            agenda=self.client.get('/api/plan-occurrences?today=true').json()
            self.assertEqual(agenda['items'][0]['local_date'],'2026-10-15')
        self.login_owner();invite=self.client.post('/api/auth/invitations').json()['invite_token']
        other=self.client.post('/api/auth/register',json={'username':'other','password':'other-test-password','invite_token':invite})
        self.client.headers['X-CSRF-Token']=other.json()['csrf_token']
        self.assertEqual(self.client.get('/api/review-sessions/'+str(session['id'])).status_code,404)
        self.assertEqual(self.write(f"/plan-schedules/{schedule['id']}/occurrences/2026-10-15",{'outcome':'missed','schedule_version':1},0,'PUT').status_code,404)
        self.assertEqual(self.client.get('/api/admin/hosted-monitor').status_code,403)
        self.assertEqual(self.client.get('/api/diaries/2026-10-16').json()['diary'],None)
        self.assertNotIn('今天部署了项目',str(self.client.get('/api/export').json()))

    def test_legacy_importer_rejects_new_entities_without_touching_source(self):
        import importlib.util,hashlib
        from pathlib import Path
        from sqlalchemy import create_engine
        from app.database import Base
        from app.models import User
        from app.models.workflow import LifeChecklist
        spec=importlib.util.spec_from_file_location('continuation_importer','ops/import-sqlite.py');importer=importlib.util.module_from_spec(spec);spec.loader.exec_module(importer)
        source=Path(self.temp.name)/'synthetic-new-source.db';engine=create_engine('sqlite:///'+str(source));Base.metadata.create_all(engine)
        from sqlalchemy.orm import Session
        with Session(engine) as db:
            user=User(username='synthetic_importer_only');db.add(user);db.flush()
            db.add(LifeChecklist(user_id=user.id,local_date='2026-10-16',version=1,payload={'enabled':False}));db.commit()
        engine.dispose();before=hashlib.sha256(source.read_bytes()).hexdigest()
        _,report=importer.preflight(source)
        self.assertTrue(report['blocked']);self.assertTrue(any(item['reason']=='UNSUPPORTED_CONTINUATION_DATA' for item in report['issues']))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)

    def test_disabled_identity_cannot_pass_late_business_lock(self):
        from app.models import User
        from app.services.transactions import lock_profile
        from fastapi import HTTPException
        registered=self.register()
        with self.Session() as db:
            user=db.get(User,registered['id']);user.status='disabled';db.commit()
            with self.assertRaises(HTTPException) as failure:lock_profile(db,user.id)
            self.assertEqual(failure.exception.status_code,401)
            db.rollback()

    def test_explicit_local_worker_schema_and_utc_review_lease(self):
        from app.config import settings
        from app.models import Setting
        from app.models.analysis import AnalysisJob
        from app.worker import validate_local_schema
        from sqlalchemy import create_engine,inspect
        self.register();session=self.session()
        with self.Session() as db:
            user_id=db.query(Event).first().user_id
            db.add(Setting(user_id=user_id,key='llm_primary',value={'enabled':True,'api_key':'synthetic-local-key','base_url':'https://api.deepseek.com','model':'local-fixture','config_version':1}));db.commit()
        with patch.object(settings,'run_mode','local'):
            validate_local_schema(self.engine)
            empty=create_engine('sqlite://')
            with self.assertRaises(RuntimeError):validate_local_schema(empty)
            self.assertEqual(inspect(empty).get_table_names(),[]);empty.dispose()
            with self.Session() as db:
                job=AnalysisJob(user_id=user_id,event_id=session['diary_id'],event_version=1,operation='review',review_session_id=session['id'],session_version=1,permission_version=db.get(Event,session['diary_id']).ai_permission_version,
                    request_key=str(uuid4()),payload_hash='synthetic',config_version=analysis_jobs.configuration(db,user_id),state='queued')
                db.add(job);db.commit();job_id=job.id
            with patch('app.services.diary_review.llm_service.chat_json',return_value={'questions':[],'summary':'本地回顾成功','analysis':[]}):
                analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
            with self.Session() as db:
                self.assertEqual(db.get(AnalysisJob,job_id).state,'ready')
                self.assertEqual(db.query(ReviewAnalysis).one().payload['summary'],'本地回顾成功')
            # Local lightweight upgrades must enforce the new identity in the DB as well.
            from app.database import migrate_schema
            from sqlalchemy import text
            from sqlalchemy.exc import IntegrityError
            legacy=create_engine('sqlite://')
            with legacy.begin() as connection:connection.execute(text('CREATE TABLE events (id INTEGER PRIMARY KEY)'))
            migrate_schema(legacy)
            with legacy.begin() as connection:connection.execute(text("INSERT INTO events(id,diary_key) VALUES(1,'synthetic-day')"))
            with self.assertRaises(IntegrityError):
                with legacy.begin() as connection:connection.execute(text("INSERT INTO events(id,diary_key) VALUES(2,'synthetic-day')"))
            legacy.dispose()


if __name__=='__main__':unittest.main()
