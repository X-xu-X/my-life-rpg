"""Isolated full-system contracts; fake suppliers and no application lifespan."""
import unittest
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
import tests.test_next_iteration as fixtures
from app.models import User,Event
from app.models.accounts import MailDelivery,EmailToken
from app.services import mail_service,mail_queue
from app.services.time_service import utc_now,local_day


class FullSystemTests(unittest.TestCase):
    setUp=fixtures.CloudTests.setUp
    tearDown=fixtures.CloudTests.tearDown
    register=fixtures.CloudTests.register
    configure_model=fixtures.CloudTests.configure_model

    def write(self,path,body=None,version=0,method='POST',key=None):
        return self.client.request(method,'/api'+path,json={'request_key':key or str(uuid4()),'expected_version':version,**(body or {})})

    def owner(self):
        response=self.client.post('/api/auth/login',json={'username':'owner','password':'test-password-owner'})
        self.assertEqual(response.status_code,200,response.text)
        self.client.headers['X-CSRF-Token']=response.json()['csrf_token']

    def test_recovery_durable_acceptance_no_smtp_and_retry_same_token(self):
        self.register()
        with self.Session() as db:
            user=db.query(User).filter_by(username='friend').one();user.email='friend@example.test';user.email_verified_at=utc_now();db.commit()
        fake=mail_service.TestMailer()
        with patch('app.services.mail_service.mailer',return_value=fake):
            known=self.client.post('/api/auth/email/recover-request',json={'email':'friend@example.test'})
            unknown=self.client.post('/api/auth/email/recover-request',json={'email':'unknown@example.test'})
            self.assertEqual(known.json(),unknown.json());self.assertEqual(fake.outbox,[])
            with self.Session() as db:self.assertEqual(db.query(MailDelivery).count(),2)
            with patch.object(fake,'send',side_effect=RuntimeError('synthetic failure')):self.assertTrue(mail_queue.deliver_one(self.Session))
            with self.Session() as db:
                delivery=db.query(MailDelivery).filter_by(email='friend@example.test').one()
                self.assertEqual(delivery.state,'retry');self.assertEqual(delivery.error_code,'DELIVERY_UNCONFIRMED')
                delivery.next_attempt=utc_now()-timedelta(seconds=1);token_id=delivery.token_id;db.commit()
            # A new invocation represents a restarted worker; persisted encrypted token is reused.
            self.assertTrue(mail_queue.deliver_one(self.Session));self.assertEqual(len(fake.outbox),1)
            self.assertTrue(mail_queue.deliver_one(self.Session));self.assertEqual(len(fake.outbox),1)
        with self.Session() as db:
            self.assertEqual(db.query(EmailToken).count(),1);self.assertEqual(db.query(EmailToken).one().id,token_id)
            self.assertEqual(db.query(MailDelivery).filter_by(email='unknown@example.test').one().state,'discarded')
        reset=self.client.post('/api/auth/email/reset-password',json={'token':fake.outbox[0]['token'],'new_password':'test-recovered-password'})
        self.assertEqual(reset.status_code,200,reset.text)
        self.assertEqual(self.client.post('/api/auth/email/reset-password',json={'token':fake.outbox[0]['token'],'new_password':'test-recovered-password'}).status_code,400)

    def test_admin_group_statistics_and_literal_search_filters(self):
        self.register();self.owner()
        result=self.client.get('/api/admin/overview').json()
        self.assertEqual(result['groups']['ordinary']['total'],1)
        self.assertEqual(result['groups']['administrators']['total'],1)
        self.assertEqual(result['groups']['ordinary']['logged_in_7_days'],1)
        for query in ('q=nobody','role=user&status=disabled','q=%25'):
            self.assertEqual(self.client.get('/api/admin/users?'+query).json()['items'],[])
        selected=self.client.get('/api/admin/users?role=user&q=friend').json()['items']
        self.assertEqual(len(selected),1);self.assertTrue(selected[0]['last_login_at'])

    def test_plan_goal_snapshot_full_frequencies_and_owned_selection(self):
        self.register();self.client.post('/api/onboarding/neutral',json={'acknowledge':True})
        goal=self.client.post('/api/goals',json={'description':'我的训练目标','metric':'十次'}).json()
        response=self.write('/plan-schedules',{'name':'训练','frequency':'workdays','start':'2026-10-01','goal_id':goal['id']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['history'][0]['goal']['title'],'我的训练目标')
        self.assertEqual(len(self.client.get('/api/plan-occurrences?day=2026-10-12').json()['items']),1)
        self.assertEqual(self.client.get('/api/plan-occurrences?day=2026-10-11').json()['items'],[])
        self.assertEqual(self.write('/plan-schedules',{'name':'非法目标','frequency':'daily','start':'2026-10-01','goal_id':99999}).status_code,404)
        from app.routers.plans import due
        from datetime import date
        for freq,expected in [('once',True),('manual',False),('weekends',True)]:self.assertEqual(due({'frequency':freq,'start':'2026-10-18'},date(2026,10,18)),expected)

    def test_current_streak_yesterday_and_separate_kinds(self):
        self.register();today=local_day(utc_now(),'Asia/Shanghai')
        with self.Session() as db:
            uid=db.query(User).filter_by(username='friend').one().id
            for n in (1,2,3):db.add(Event(user_id=uid,event_type='positive',content='合成保存日',record_kind='event',saved_on=str(today-timedelta(days=n))))
            db.add(Event(user_id=uid,event_type='positive',content='合成日记',record_kind='diary',saved_on=str(today)))
            db.commit()
        result=self.client.get('/api/record-metrics').json()['metrics']
        self.assertEqual(result['event_saved_days']['current_contiguous_days'],3)
        self.assertEqual(result['diary_saved_days']['current_contiguous_days'],1)

    def event(self,content,permission='private'):
        response=self.client.post('/api/events',json={'content':content,'record_kind':'event','ai_permission':permission,
            'client_request_id':str(uuid4()),'occurred_on':str(local_day(utc_now(),'Asia/Shanghai')),'time_precision':'date'})
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def test_private_default_owner_export_and_no_active_pending(self):
        self.register();self.configure_model();private=self.event('PRIVATE_SENTINEL')
        self.assertEqual(private['ai_permission'],'private')
        self.assertEqual(self.client.get('/api/pending').json()['items'],[])
        response=self.client.post(f"/api/events/{private['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1})
        self.assertEqual(response.status_code,409,response.text)
        self.assertIn('PRIVATE_SENTINEL',self.client.get('/api/export').text)
        permission=self.write(f"/events/{private['id']}/ai-permission",{'permission':'allowed','content_version':1,'acknowledge':True},1,'PUT')
        self.assertEqual(permission.status_code,200,permission.text)
        self.assertEqual(self.client.get('/api/events/'+str(private['id'])).json()['ai_permission_version'],2)

    def test_actual_judge_payload_excludes_private_and_unknown_memory(self):
        import json
        from app.services import analysis_jobs
        from app.models import UserProfile
        self.register();self.configure_model();private=self.event('PRIVATE_RAW_SENTINEL');allowed=self.event('允许分析的散步','allowed')
        with self.Session() as db:
            profile=db.query(UserProfile).filter_by(user_id=allowed['id']+1).first()
            profile=db.query(UserProfile).filter_by(user_id=db.query(User).filter_by(username='friend').one().id).one()
            profile.long_term_memory=json.dumps({'preferences':['PRIVATE_DERIVED_SENTINEL']});db.commit()
        sent=[]
        def fake(messages,**kwargs):sent.append(messages);return {'confidence':0.9,'affected_attributes':[],'summary':'已分析','analysis':[]}
        response=self.client.post(f"/api/events/{allowed['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1})
        self.assertEqual(response.status_code,202,response.text)
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        self.assertNotIn('PRIVATE_',json.dumps(sent,ensure_ascii=False));self.assertIn('允许分析的散步',json.dumps(sent,ensure_ascii=False))
        self.assertEqual(self.client.get('/api/analysis-jobs/'+str(response.json()['id'])).json()['state'],'ready')

    def test_revoke_running_permission_rejects_late_result_and_queue(self):
        from app.services import analysis_jobs
        self.register();self.configure_model();event=self.event('允许后撤回','allowed')
        response=self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1})
        def revoke(*args,**kwargs):
            with self.Session() as db:
                from app.services.ai_context import change
                change(db,db.get(Event,event['id']),'private');db.commit()
            return {'confidence':1,'affected_attributes':[{'name':'体能','delta':1}],'summary':'禁止写入'}
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=revoke):analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        self.assertEqual(self.client.get('/api/analysis-jobs/'+str(response.json()['id'])).json()['state'],'superseded')
        self.assertEqual(self.client.get('/api/judgments').json(),[])

    def test_review_each_round_refreshes_authorized_sources_and_metadata(self):
        import json
        from app.services import analysis_jobs
        self.register();self.configure_model();day=str(local_day(utc_now(),'Asia/Shanghai'))
        diary=self.write('/diaries/'+day,{'content':'今天有些低落','ai_permission':'allowed'},0,'PUT').json()['diary']
        session=self.write('/diaries/'+day+'/review-sessions',version=diary['content_version']).json()
        self.event('PRIVATE_NEW_AFTER_SESSION');new=self.event('新写的支持经历','allowed')
        self.write('/life-checklists/'+day,{'entries':{'活动':'skipped'}},0,'PUT')
        schedule=self.write('/plan-schedules',{'name':'训练','frequency':'daily','start':day}).json()
        self.write(f"/plan-schedules/{schedule['id']}/occurrences/{day}",{'outcome':'missed','schedule_version':1},0,'PUT')
        sent=[]
        def fake(messages,**kwargs):sent.append(messages);return {'questions':[],'summary':'允许没有积极片段','analysis':[]}
        response=self.write(f"/review-sessions/{session['id']}/analyze",version=session['version'])
        self.assertEqual(response.status_code,200,response.text)
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        payload=json.loads(sent[0][-1]['content']);self.assertIn(new['id'],[r['id'] for r in payload['sources']])
        self.assertEqual(payload['plans'][0]['outcome'],'missed');self.assertEqual(payload['checklist']['counts']['skipped'],1)
        self.assertNotIn('PRIVATE_NEW_AFTER_SESSION',json.dumps(sent));state=self.client.get(f"/api/review-sessions/{session['id']}").json()
        self.assertEqual(state['analyses'][0]['payload']['sources_snapshot']['sources'],payload['sources'])

    def adopt(self,minutes=30):
        response=self.client.post('/api/onboarding/neutral',json={'acknowledge':True});self.assertEqual(response.status_code,200,response.text)
        response=self.write('/trial',{'acknowledge':True,'base_minutes':minutes},0,'PUT');self.assertEqual(response.status_code,200,response.text)

    def facts(self,event,items):
        from app.services import analysis_jobs
        response=self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':event['content_version'],'operation':'facts'})
        self.assertEqual(response.status_code,202,response.text)
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'facts':items}):analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        job=self.client.get('/api/analysis-jobs/'+str(response.json()['id'])).json();self.assertEqual(job['state'],'ready',job)
        return self.client.get(f"/api/events/{event['id']}/fact-bundles").json()['items'][0]

    def suggestion(self,text,**extra):
        coins=extra.pop('coins',6);reason=extra.pop('coins_reason','合成定价依据')
        return {'excerpt':text,'summary':'根据实际行为提出建议','coins':coins,'coins_reason':reason,'changes':[{'name':'体能','delta':1,'reason':'合成事实','evidence':'用户所述'}],'confidence':1,**extra}

    def preview(self,bundle):
        response=self.write(f"/fact-bundles/{bundle['id']}/preview",version=bundle['version']);self.assertEqual(response.status_code,200,response.text);return response.json()

    def settle(self,bundle,key=None):return self.write(f"/fact-bundles/{bundle['id']}/confirm",version=bundle['version'],key=key)

    def test_diary_multifacts_preserves_originals_and_only_new_action_awarded(self):
        from app.models.full_system import ActionAward
        self.register();self.configure_model();self.adopt()
        english=self.event('背英语二十分钟','allowed');running=self.event('跑步两公里','allowed')
        for record in (english,running):
            group=self.facts(record,[self.suggestion(record['content'])]);self.assertEqual(self.settle(self.preview(group)).status_code,200)
        day=str(local_day(utc_now(),'Asia/Shanghai'))
        diary=self.write('/diaries/'+day,{'content':'背英语二十分钟。跑步两公里。画了人物速写。','ai_permission':'allowed'},0,'PUT').json()['diary']
        group=self.facts(diary,[self.suggestion('背英语二十分钟',relation='same',related_event_id=english['id']),self.suggestion('跑步两公里',relation='same',related_event_id=running['id']),self.suggestion('画了人物速写')])
        for item in list(group['payload']['items']):
            if item['candidate_fact_id']:
                group=self.write(f"/fact-bundles/{group['id']}/decision",{'fragment_id':item['fragment_id'],'decision':'same'},group['version']).json()
        group=self.preview(group);self.assertEqual(group['preview']['total'],6)
        self.assertEqual(sum(i['booked'] for i in group['preview']['items']),2)
        key=str(uuid4());result=self.settle(group,key);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.settle(group,key).json(),result.json())
        self.assertEqual(len(self.client.get('/api/events').json()),3)
        with self.Session() as db:self.assertEqual(db.query(ActionAward).count(),3)

    def test_diary_first_booking_does_not_authorize_private_daytime_original(self):
        self.register();self.configure_model();self.adopt();private=self.event('读完一章数学')
        day=str(local_day(utc_now(),'Asia/Shanghai'))
        diary=self.write('/diaries/'+day,{'content':'读完一章数学','ai_permission':'allowed'},0,'PUT').json()['diary']
        group=self.facts(diary,[self.suggestion('读完一章数学')]);self.assertEqual(self.settle(self.preview(group)).status_code,200)
        self.assertEqual(self.client.get('/api/events/'+str(private['id'])).json()['ai_permission'],'private')
        self.write(f"/events/{private['id']}/ai-permission",{'permission':'allowed','acknowledge':True,'content_version':1},1,'PUT')
        group=self.facts(private,[self.suggestion('读完一章数学')])
        item=group['payload']['items'][0]
        self.assertEqual(item['decision'],'keep')
        group=self.write(f"/fact-bundles/{group['id']}/decision",{'fragment_id':item['fragment_id'],'decision':'same'},group['version']).json()
        group=self.preview(group)
        self.assertEqual(group['preview']['total'],0);self.assertTrue(group['preview']['items'][0]['booked'])

    def test_group_stale_preview_and_injected_failure_leave_no_half_booking(self):
        from app.models.full_system import ActionAward
        from app.models.workflow import FactSettlement
        from app.models import AttributeHistory
        self.register();self.configure_model();self.adopt()
        event=self.event('运动五分钟。整理了书桌。','allowed')
        first=self.preview(self.facts(event,[self.suggestion('运动五分钟'),self.suggestion('整理了书桌')]))
        second=self.preview(self.facts(event,[self.suggestion('运动五分钟')]))
        self.assertEqual(self.settle(second).status_code,200)
        self.assertEqual(self.settle(first).status_code,409)
        first=self.preview(first);self.assertEqual(first['preview']['total'],6)
        with patch('app.services.trial_rules.award',side_effect=ValueError('injected transaction failure')):
            with self.assertRaises(ValueError):self.settle(first)
        with self.Session() as db:
            self.assertEqual(db.query(FactSettlement).count(),1);self.assertEqual(db.query(ActionAward).count(),1);self.assertEqual(db.query(AttributeHistory).count(),1)

    def test_first_record_backfill_and_delete_do_not_reset_entitlement(self):
        self.register();self.adopt();record=self.event('负面也可以只保存')
        state=self.client.get('/api/trial').json();self.assertEqual(state['daily']['base_seconds'],1800)
        key=str(uuid4());body={'expected_version':state['daily']['version']}
        first=self.write('/trial/first-record/claim',body,key=key);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.write('/trial/first-record/claim',body,key=key).json(),first.json())
        self.assertEqual(self.write('/trial/first-record/claim',version=2).status_code,409)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],83)

    def test_care_eight_items_zero_persists_and_record_skip_identity(self):
        self.register();self.adopt();day=str(local_day(utc_now(),'Asia/Shanghai'));items=[]
        for n in range(8):
            response=self.write('/care/items',{'name':'项目'+str(n),'frequency':'daily','position':n})
            self.assertEqual(response.status_code,200,response.text);items.append(response.json())
        self.assertEqual(len(self.client.get('/api/care').json()['today']),8)
        item=items[0];path=f"/care/items/{item['id']}/entries/{day}"
        record=self.write(path,{'item_version':1,'state':'recorded','content':'安静吃了午饭'},0,'PUT').json()
        self.assertEqual(record['event']['ai_permission'],'private')
        skipped=self.write(path,{'item_version':1,'state':'skipped'},1,'PUT').json()
        self.assertEqual(skipped['event']['content'],'安静吃了午饭')
        again=self.write(path,{'item_version':1,'state':'recorded','content':'安静吃了午饭'},2,'PUT').json()
        self.assertEqual(again['event']['id'],record['event']['id'])
        for item in items:self.assertEqual(self.write('/care/items/'+str(item['id']),{'name':item['name'],'frequency':'daily','removed':True},1,'PUT').status_code,200)
        self.assertEqual(self.client.get('/api/care').json()['today'],[])
        self.assertEqual(self.client.get('/api/care').json()['items'],[])
        self.assertEqual(len(self.client.get('/api/events').json()),1)

    def test_feedback_owner_reply_and_third_account_denied(self):
        self.register();response=self.write('/feedback',{'kind':'problem','title':'私密问题','content':'PRIVATE_FEEDBACK'})
        self.assertEqual(response.status_code,200,response.text);feedback=response.json()
        self.owner();rows=self.client.get('/api/admin/feedback').json()['items'];self.assertEqual(rows[0]['content'],'PRIVATE_FEEDBACK')
        reply=self.write(f"/admin/feedback/{feedback['id']}/reply",{'content':'站内回复'},1)
        self.assertEqual(reply.status_code,200,reply.text)
        self.assertEqual(len(reply.json()['replies']),1)
        self.client.post('/api/auth/logout')
        with self.Session() as db:
            from app.services.auth_service import issue_invitation
            self.invite=issue_invitation(db,db.get(User,self.owner_id));db.commit()
        self.register('third')
        self.assertEqual(self.client.get('/api/feedback').json()['items'],[])
        self.assertEqual(self.write(f"/feedback/{feedback['id']}/reply",{'content':'偷看'},2).status_code,404)
        self.assertEqual(self.client.get('/api/admin/feedback').status_code,403)

    def reward(self,kind='entertainment'):
        timed=kind=='entertainment'
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'coin_price':20,'pricing_reason':'合成模型按期望频率建议','worth_note':'可自行决定','is_timed':timed,'minutes_estimate':30 if timed else None}):
            quote=self.write('/reward-quotes',{'name':'额外娱乐半小时'})
        self.assertEqual(quote.status_code,200,quote.text)
        result=self.write('/reward-quotes/'+str(quote.json()['id'])+'/accept',version=1)
        self.assertEqual(result.status_code,200,result.text);return result.json()['item']

    def test_reward_auto_quote_invalid_no_fallback_and_compatible_accept_reprice_bounds(self):
        self.register();self.configure_model();self.adopt()
        before=len(self.client.get('/api/shop/items').json()['items'])
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'coin_price':0,'pricing_reason':'无效'}):
            response=self.write('/reward-quotes',{'name':'想要的奖励'})
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual(len(self.client.get('/api/shop/items').json()['items']),before)
        item=self.reward();self.assertEqual(item['duration_seconds'],1800)
        # An existing price from a previous day can be checked; today's initial price is not checked twice.
        from app.models import ShopItem
        with self.Session() as db:
            stored=db.get(ShopItem,item['id']);stored.repriced_on=None;db.commit()
        item=next(i for i in self.client.get('/api/shop/items').json()['items'] if i['id']==item['id'])
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'coin_price':1000,'pricing_reason':'合成升价','worth_note':''}):
            response=self.write('/reward-quotes',{'name':item['name'],'item_id':item['id'],'item_version':item['updated_at']})
        self.assertEqual(response.status_code,200,response.text);quote=response.json();self.assertEqual(quote['result']['coin_price'],1000)
        key=str(uuid4());first=self.write(f"/reward-quotes/{quote['id']}/accept",version=1,key=key)
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(self.write(f"/reward-quotes/{quote['id']}/accept",version=1,key=key).json(),first.json())
        accepted=self.write(f"/reward-quotes/{quote['id']}/accept",version=quote['version'])
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(accepted.json()['item']['coin_price'],1000)
        with patch('app.services.llm_service.llm_service.chat_json') as model:
            self.assertEqual(self.write('/reward-quotes',{'name':item['name'],'item_id':item['id'],'item_version':accepted.json()['item']['updated_at']}).status_code,409)
            model.assert_not_called()

    def test_two_vouchers_independent_five_minutes_then_full_new_thirty(self):
        self.register();self.configure_model();self.adopt();item=self.reward();vouchers=[]
        for _ in range(2):
            response=self.client.post(f"/api/shop/items/{item['id']}/redeem",json={'request_key':str(uuid4()),'expected_version':item['updated_at']})
            self.assertEqual(response.status_code,200,response.text);vouchers.append(response.json()['redemption'])
        now=utc_now()
        with patch('app.routers.timers.utc_now',return_value=now):
            first=self.write('/timers',{'kind':'voucher','source_id':vouchers[0]['id']}).json()
        self.assertEqual(first['limit_seconds'],1800)
        self.assertEqual(self.write('/timers',{'kind':'voucher','source_id':vouchers[1]['id']}).status_code,409)
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(minutes=5)),patch('app.services.timers.utc_now',return_value=now+timedelta(minutes=5)):
            end=self.write(f"/timers/{first['id']}/end-preview",version=first['version']).json()
            self.assertEqual(end['preview']['actual_seconds'],300)
            self.assertEqual(self.write(f"/timers/{first['id']}/confirm",version=end['version']).status_code,200)
            second=self.write('/timers',{'kind':'voucher','source_id':vouchers[1]['id']}).json()
            self.assertEqual(second['limit_seconds'],1800)
            end=self.write(f"/timers/{second['id']}/end-preview",version=1).json()
            self.write(f"/timers/{second['id']}/confirm",version=end['version'])
            old=self.write('/timers',{'kind':'voucher','source_id':vouchers[0]['id']}).json()
            self.assertEqual(old['limit_seconds'],1500)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],41)

    def test_questionnaire_all_skipped_preview_only_confirm_once_and_existing_unchanged(self):
        from app.models import UserProfile
        self.register();catalog=self.client.get('/api/questionnaire').json();self.assertEqual(len(catalog['questions']),30)
        answers={q['id']:{'state':'skipped','value':''} for q in catalog['questions']}
        saved=self.write('/questionnaire',{'answers':answers,'send_groups':[]},0,'PUT').json()
        with patch('app.services.llm_service.llm_service.chat_json') as fake:
            proposed=self.write('/questionnaire/preview',{'use_ai':False},saved['version']).json();fake.assert_not_called()
        self.assertEqual(proposed['preview']['initial_coins'],80)
        self.assertFalse(self.client.get('/api/auth/me').json()['onboarding_completed'])
        key=str(uuid4());result=self.write('/questionnaire/confirm',version=proposed['version'],key=key)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(self.write('/questionnaire/confirm',version=proposed['version'],key=key).json(),result.json())
        self.assertEqual(self.client.get('/api/coins').json()['balance'],80)
        again=self.write('/questionnaire',{'answers':{'rewards_1':{'state':'answered','value':'不能改写旧答卷'}},'send_groups':['rewards']},result.json()['version'],'PUT')
        self.assertEqual(again.status_code,409)
        info=self.write('/personal-information',{'entries':[{'id':str(uuid4()),'text':'希望换一杯茶','uses':['pricing']}]},0,'PUT')
        self.assertEqual(info.status_code,200,info.text)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],80)
        history=self.client.get('/api/questionnaire').json()['history']
        self.assertEqual(len(history),1);self.assertEqual(history[0]['answers'],answers)
        self.assertNotIn('希望换一杯茶',self.client.get('/api/export').text)
        self.assertIn('希望换一杯茶',self.client.get('/api/export?include_questionnaire=true').text)

    def test_identical_text_can_be_distinct_and_correction_survives_reanalysis(self):
        self.register();self.configure_model();self.adopt()
        first=self.event('学习英语二十分钟','allowed');first_group=self.preview(self.facts(first,[self.suggestion(first['content'])]));self.assertEqual(self.settle(first_group).status_code,200)
        second=self.event('学习英语二十分钟','allowed');group=self.facts(second,[self.suggestion(second['content'])])
        item=group['payload']['items'][0];self.assertEqual(item['decision'],'keep')
        group=self.write(f"/fact-bundles/{group['id']}/decision",{'fragment_id':item['fragment_id'],'decision':'distinct'},group['version']).json()
        # A later model proposes same; explicit user correction still wins at confirmation.
        group=self.facts(second,[self.suggestion(second['content'],relation='same',related_event_id=first['id'])])
        self.assertEqual(group['payload']['items'][0]['decision'],'keep')
        group=self.preview(group);self.assertEqual(group['preview']['total'],6);self.assertEqual(self.settle(group).status_code,200)

    def test_strict_timer_preview_grace_offline_and_correction_net_only(self):
        self.register();self.adopt();self.event('首记');daily=self.client.get('/api/trial').json()['daily'];now=utc_now()
        self.assertEqual(self.write('/timers',{'kind':'base','source_id':daily['id'],'mode':'strict'}).status_code,422)
        with patch('app.routers.timers.utc_now',return_value=now):row=self.write('/timers',{'kind':'base','source_id':daily['id'],'mode':'strict','acknowledge_penalty':True}).json()
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(minutes=38)),patch('app.services.timers.utc_now',return_value=now+timedelta(minutes=38)):
            preview=self.write(f"/timers/{row['id']}/end-preview",version=1).json()
            self.assertEqual(preview['preview']['penalty_charged'],2);self.assertTrue(preview['preview']['offline_interval'])
            self.assertEqual(self.client.get('/api/coins').json()['balance'],80)
            end=self.write(f"/timers/{row['id']}/confirm",version=preview['version']).json();self.assertEqual(self.client.get('/api/coins').json()['balance'],78)
            correction=self.write(f"/timers/{row['id']}/end-preview",{'actual_seconds':1800,'explanation':'接电话时已经停止'},end['version']).json()
            self.assertEqual(correction['preview']['coin_delta'],3)
            end=self.write(f"/timers/{row['id']}/confirm",version=correction['version']).json();self.assertEqual(self.client.get('/api/coins').json()['balance'],81)
            again=self.write(f"/timers/{row['id']}/end-preview",{'actual_seconds':1800,'explanation':'重复核对'},end['version']).json()
            self.assertEqual(again['preview']['coin_delta'],0)

    def test_custom_endpoint_dns_private_redirect_and_rebinding_boundary(self):
        from fastapi import HTTPException
        from app.services.credentials import validate_endpoint,public_addresses,PinnedTransport
        self.register();self.configure_model()
        for url in ('http://api.example.com/v1','https://127.0.0.1/v1','https://169.254.169.254/','https://api.example.com:80/v1','https://user:pw@api.example.com/v1','https://api.example.com:notaport','https://api.example.com/v1?redirect=bad'):
            with self.assertRaises(HTTPException):validate_endpoint(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):public_addresses('public.example.com')
        endpoint='https://public.example.com/v1'
        rejected=self.client.put('/api/llm-config',json={'group':'primary','provider_id':'custom','base_url':endpoint,'model':'custom-chat','enabled':True})
        self.assertEqual(rejected.status_code,422)
        saved=self.client.put('/api/llm-config',json={'group':'primary','provider_id':'custom','base_url':endpoint,'model':'custom-chat','api_key':'fake-custom-key','enabled':True})
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(self.client.get('/api/llm-config').json()['primary']['base_url'],endpoint)
        self.assertEqual(self.client.put('/api/llm-config',json={'group':'primary','provider_id':'custom','base_url':'https://other.example.com/v1','enabled':True}).status_code,422)
        import httpx
        transport=PinnedTransport(allowed_hosts=['public.example.com'])
        try:
            with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.8',443))]),patch('httpx.HTTPTransport.handle_request') as upstream:
                with self.assertRaises(ValueError):transport.handle_request(httpx.Request('POST',endpoint+'/chat/completions'))
                upstream.assert_not_called()
        finally:transport.close()

    def test_report_preview_no_record_day_and_permission_change_prevents_save(self):
        self.register();self.configure_model();event=self.event('允许的运动','allowed');self.event('PRIVATE_REPORT')
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'summary':'合成回顾'}) as fake:response=self.client.post('/api/reports?period=week',json={'request_key':str(uuid4())})
        self.assertEqual(response.status_code,200,response.text);report=response.json()
        self.assertEqual(self.client.get('/api/reports').json()['items'],[])
        self.assertEqual(len(self.client.get('/api/reports/previews').json()['items']),1)
        self.write(f"/events/{event['id']}/ai-permission",{'permission':'private','content_version':1},1,'PUT')
        self.assertEqual(self.write(f"/reports/{report['id']}/save",version=report['version']).status_code,409)
        self.assertEqual(len(self.client.get('/api/events').json()),2)

    def test_migrations_upgrade_old_sample_preserves_money_coupons_and_unknown_permission(self):
        from pathlib import Path
        from sqlalchemy import create_engine,MetaData,Table,Boolean,Integer,Float,DateTime,JSON,select,text
        from alembic import command
        from alembic.config import Config
        url='sqlite:///'+str(Path(self.temp.name)/'synthetic-upgrade.sqlite3');config=Config('alembic.ini');config.attributes['database_url']=url
        command.upgrade(config,'b009_policies');engine=create_engine(url);meta=MetaData();meta.reflect(engine)
        def values(table_name,**extra):
            payload={}
            for c in meta.tables[table_name].columns:
                if c.nullable:continue
                payload[c.name]=({} if isinstance(c.type,JSON) else False if isinstance(c.type,Boolean) else 0 if isinstance(c.type,(Integer,Float)) else utc_now() if isinstance(c.type,DateTime) else '')
            payload.update(extra);return payload
        with engine.begin() as db:
            db.execute(meta.tables['users'].insert().values(**values('users',id=1,username='synthetic_upgrade',status='active',role='user',timezone='Asia/Shanghai',credentials_version=1)))
            db.execute(meta.tables['user_profiles'].insert().values(**values('user_profiles',id=1,user_id=1,coins=40,onboarding_completed=True,initial_attributes_snapshot={'retain':'old evaluation'})))
            db.execute(meta.tables['events'].insert().values(**values('events',id=1,user_id=1,content='历史不明许可',source='journal',event_type='positive',content_version=1,timezone_at_capture='Asia/Shanghai')))
            db.execute(meta.tables['shop_items'].insert().values(**values('shop_items',id=1,user_id=1,name='旧时间券',coin_price=12)))
            db.execute(meta.tables['redemptions'].insert().values(**values('redemptions',id=1,user_id=1,shop_item_id=1,coin_spent=12,status='pending')))
        engine.dispose();command.upgrade(config,'head');command.upgrade(config,'head');engine=create_engine(url)
        with engine.connect() as db:
            self.assertEqual(db.execute(text('select coins from user_profiles')).scalar(),40)
            self.assertEqual(db.execute(text('select ai_permission from events')).scalar(),'private')
            self.assertIsNone(db.execute(text('select record_kind from events')).scalar())
            self.assertIsNone(db.execute(text('select duration_seconds from redemptions')).scalar())
            self.assertEqual(db.execute(text('select count(*) from analysis_jobs')).scalar(),0)
            self.assertEqual(db.execute(text('select auto_pricing from shop_items')).scalar(),False)
            self.assertIsNone(db.execute(text('select priced_at from shop_items')).scalar())
            for table in ('personal_information','return_checkins','important_days','experience_preferences','official_calendars','pricing_checks','model_dispatches'):
                self.assertEqual(db.execute(text('select count(*) from '+table)).scalar(),0)
            self.assertEqual(db.execute(text('pragma foreign_key_check')).all(),[])
            from alembic.script import ScriptDirectory
            self.assertEqual(db.execute(text('select version_num from alembic_version')).scalar(),ScriptDirectory.from_config(config).get_current_head())
        engine.dispose()

    def test_review_answers_and_related_supplements_are_fact_sources_not_fake_events(self):
        from app.models.workflow import ReviewTurn,ReviewSession
        self.register();self.configure_model();self.adopt()
        day=str(local_day(utc_now(),'Asia/Shanghai'))
        diary=self.write('/diaries/'+day,{'content':'今天心情低落','ai_permission':'allowed'},0,'PUT').json()['diary']
        session=self.write('/diaries/'+day+'/review-sessions',version=1).json()
        with self.Session() as db:
            event=db.get(Event,diary['id'])
            turn=ReviewTurn(user_id=event.user_id,session_id=session['id'],ordinal=1,question='后来做了什么？')
            db.add(turn);db.commit();turn_id=turn.id
        response=self.write(f"/review-sessions/{session['id']}/turns/{turn_id}",{'session_version':session['version'],'answer':'散步十分钟'},1,'PUT')
        self.assertEqual(response.status_code,200,response.text)
        group=self.facts(diary,[self.suggestion('散步十分钟',source_kind='review_answer',source_id=turn_id)])
        self.assertEqual(self.settle(self.preview(group)).json()['coins_gained'],6)
        key=str(uuid4());note=self.write(f"/events/{diary['id']}/fact-notes",{'content':'完成一幅速写'},1,key=key)
        self.assertEqual(note.status_code,200,note.text)
        self.assertEqual(self.write(f"/events/{diary['id']}/fact-notes",{'content':'完成一幅速写'},1,key=key).json(),note.json())
        group=self.facts(diary,[self.suggestion('散步十分钟',source_kind='review_answer',source_id=turn_id),self.suggestion('完成一幅速写',source_kind='note',source_id=note.json()['id'])])
        new_item=next(i for i in group['payload']['items'] if i['source_kind']=='note')
        self.assertEqual(new_item['decision'],'keep')
        group=self.write(f"/fact-bundles/{group['id']}/decision",{'fragment_id':new_item['fragment_id'],'decision':'distinct'},group['version']).json()
        self.assertEqual(self.settle(self.preview(group)).json()['coins_gained'],6)
        self.assertEqual(self.client.get('/api/events').json()[0]['content'],'今天心情低落')
        self.assertEqual(len(self.client.get('/api/events').json()),1)
        self.write(f"/events/{diary['id']}/fact-notes",{'content':'补充新的细节'},1)
        self.assertEqual(self.write(f"/fact-bundles/{group['id']}/preview",version=group['version']).status_code,409)

    def test_shared_fact_withdrawal_retains_attributes_until_last_live_source(self):
        from app.models import Attribute
        self.register();self.configure_model();self.adopt()
        a=self.event('完成跑步','allowed');b=self.event('晚间重述跑步','allowed')
        def value():
            with self.Session() as db:return db.query(Attribute).filter_by(user_id=self.user_id(),name='体能',parent_id=None).one().current_value
        initial=value();group=self.facts(a,[self.suggestion('完成跑步')]);self.settle(self.preview(group))
        group=self.facts(b,[self.suggestion('晚间重述跑步',related_event_id=a['id'],relation='same')]);item=group['payload']['items'][0]
        group=self.write(f"/fact-bundles/{group['id']}/decision",{'fragment_id':item['fragment_id'],'decision':'same'},group['version']).json()
        self.settle(self.preview(group));balance=self.client.get('/api/coins').json()['balance']
        self.assertEqual(value(),initial+1)
        for event,expected in ((a,initial+1),(b,initial)):
            response=self.client.request('DELETE',f"/api/events/{event['id']}",json={'request_key':str(uuid4()),'expected_version':1})
            self.assertEqual(response.status_code,200,response.text);self.assertEqual(value(),expected)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],balance)

    def user_id(self):
        with self.Session() as db:return db.query(User).filter_by(username='friend').one().id

    def test_model_priced_coins_are_awarded_without_caps(self):
        from app.services import trial_rules
        self.assertEqual(trial_rules.validate(0),0)
        self.assertEqual(trial_rules.validate(25),25)
        self.register();self.configure_model();self.adopt()
        for index in range(5):
            event=self.event('阶段成果'+str(index),'allowed');group=self.facts(event,[self.suggestion(event['content'],coins=25)])
            result=self.settle(self.preview(group));self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['coins_gained'],25)
        # 5 × 25 = 125：没有每日 100 上限，也不做单次 40 截断
        self.assertEqual(self.client.get('/api/trial').json()['action_used'],125)

    def test_care_legacy_mapping_is_explicit_repeatable_and_never_creates_events(self):
        self.register();day=str(local_day(utc_now(),'Asia/Shanghai'))
        self.write('/life-checklists/'+day,{'enabled':True,'entries':{'睡眠':'recorded','散步':'skipped'}},0,'PUT')
        state=self.client.get('/api/care').json();self.assertEqual(state['items'],[])
        old=state['legacy'];response=self.write('/care/legacy-import',{'legacy_id':old['id'],'legacy_version':old['version']},0)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.write('/care/legacy-import',{'legacy_id':old['id'],'legacy_version':old['version']},1).status_code,200)
        state=self.client.get('/api/care').json();self.assertEqual(len(state['items']),2);self.assertEqual(len(state['today']),2)
        self.assertEqual([r['entry']['state'] for r in state['today']],['recorded','skipped'])
        self.assertEqual(self.client.get('/api/events').json(),[])

    def test_discovery_month_ignore_equivalence_and_dynamic_cap_preserves_candidate(self):
        from app.services import discoveries
        from app.models.policies import DynamicCandidate
        self.register();self.adopt()
        user_id=self.user_id()
        with self.Session() as db:
            user=db.get(User,user_id)
            for n in range(1,32):db.add(Event(user_id=user_id,event_type='positive',source='form',record_kind='event',content='合成记录',saved_on=f'2026-08-{n:02}',saved_timezone=user.timezone))
            db.flush();discoveries.discover(db,user);db.commit()
            month=db.query(DynamicCandidate).filter(DynamicCandidate.user_id==user_id).all()
            self.assertTrue(any(r.criteria['shape']=='calendar_month' for r in month))
            ignored=next(r for r in month if r.criteria['shape']=='consecutive_days' and r.criteria['target']==3);ignored.state='ignored';db.commit()
            duplicate=discoveries.propose(db,user,'换个名称',dict(ignored.criteria,start='2026-08-01',end='2026-08-31'))
            self.assertEqual(duplicate.id,ignored.id)
            for target,expected in ((1,10),(2,10),(3,10),(4,10)):
                criteria={'metric':'event_saved_days','shape':'total_days','target':target,'start':None,'end':None}
                row=discoveries.propose(db,user,str(target),criteria);discoveries.claim(db,user,row);db.commit()
            row=discoveries.propose(db,user,'第五项',{'metric':'event_saved_days','shape':'total_days','target':5,'start':None,'end':None});db.commit()
            from fastapi import HTTPException
            with self.assertRaises(HTTPException):discoveries.claim(db,user,row)
            self.assertEqual(row.state,'candidate')

    def test_game_attachment_respects_unchecked_question_and_analysis_exports(self):
        from app.models.workflow import ReviewSession,ReviewTurn,ReviewAnalysis
        self.register();event=self.event('原文可读','allowed');user_id=self.user_id()
        self.write(f"/events/{event['id']}/fact-notes",{'content':'SUPPLEMENT_SENTINEL'},1)
        with self.Session() as db:
            session=ReviewSession(user_id=user_id,diary_id=event['id'],source_version=1);db.add(session);db.flush()
            db.add(ReviewTurn(user_id=user_id,session_id=session.id,ordinal=1,question='QUESTION_SENTINEL',answer='ANSWER_SENTINEL',state='answered'))
            db.add(ReviewAnalysis(user_id=user_id,session_id=session.id,session_version=1,payload={'summary':'ANALYSIS_SENTINEL','turns_snapshot':[{'question':'QUESTION_SENTINEL','answer':'ANSWER_SENTINEL'}]},provenance={}))
            db.commit()
        for format in ('json','markdown','html','csv'):
            game='false' if format=='csv' else 'true'
            response=self.client.get(f'/api/export?format={format}&include_game={game}&include_questions=false&include_analysis=false')
            self.assertEqual(response.status_code,200,response.text[:100])
            for secret in ('QUESTION_SENTINEL','ANSWER_SENTINEL','ANALYSIS_SENTINEL','SUPPLEMENT_SENTINEL'):self.assertNotIn(secret,response.text)
            self.assertIn('原文可读',response.text)
            from pathlib import Path
            artifacts=Path(__import__('os').environ.get('FULL_SYSTEM_EVIDENCE_DIR','docs/review/full_system_2026-10-18'))/'export-fixtures';artifacts.mkdir(parents=True,exist_ok=True)
            (artifacts/('lifexp-records.'+{'json':'json','markdown':'md','html':'html','csv':'csv'}[format])).write_bytes(response.content)
        response=self.client.get('/api/export?include_questions=true&include_analysis=true')
        for text in ('QUESTION_SENTINEL','ANSWER_SENTINEL','ANALYSIS_SENTINEL','SUPPLEMENT_SENTINEL'):self.assertIn(text,response.text)

    def test_timezone_change_only_changes_future_rule_days(self):
        from datetime import datetime,timezone
        from app.services import trial_rules
        from app.models.full_system import TrialAccount
        self.register();self.adopt();user_id=self.user_id()
        now=datetime(2026,10,18,12,tzinfo=timezone.utc)
        with patch('app.services.time_service.utc_now',return_value=now):
            result=self.write('/trial',{'acknowledge':True,'timezone':'America/Los_Angeles','base_minutes':30},1,'PUT')
        self.assertEqual(result.status_code,200,result.text)
        with self.Session() as db:
            user=db.get(User,user_id);config=db.query(TrialAccount).filter_by(user_id=user_id).one()
            self.assertEqual(config.timezone_effective_at,datetime(2026,10,18,16,tzinfo=timezone.utc))
            with patch('app.services.trial_rules.utc_now',return_value=now):self.assertEqual(trial_rules.zone_for(db,user),'Asia/Shanghai')
            with patch('app.services.trial_rules.utc_now',return_value=now+timedelta(hours=5)):self.assertEqual(trial_rules.zone_for(db,user),'America/Los_Angeles')

    def test_rewriting_booked_diary_defaults_no_second_award_without_blocking(self):
        self.register();self.configure_model();self.adopt();day=str(local_day(utc_now(),'Asia/Shanghai'))
        diary=self.write('/diaries/'+day,{'content':'跑步两公里','ai_permission':'allowed'},0,'PUT').json()['diary']
        group=self.facts(diary,[self.suggestion('跑步两公里')]);self.settle(self.preview(group));balance=self.client.get('/api/coins').json()['balance']
        diary=self.write('/diaries/'+day,{'content':'晚上进行了两公里慢跑','ai_permission':'allowed','correction_reason':'重写表达，原事实未变'},1,'PUT').json()['diary']
        group=self.facts(diary,[self.suggestion('晚上进行了两公里慢跑')]);self.assertEqual(group['payload']['items'][0]['decision'],'keep')
        preview=self.preview(group);self.assertEqual(preview['preview']['total'],0);self.assertEqual(self.settle(preview).status_code,200)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],balance)
        diary=self.write('/diaries/'+day,{'content':'夜里完成两公里慢跑','ai_permission':'allowed','correction_reason':'再次重写表达'},2,'PUT').json()['diary']
        group=self.facts(diary,[self.suggestion('夜里完成两公里慢跑')]);item=group['payload']['items'][0]
        group=self.write(f"/fact-bundles/{group['id']}/decision",{'fragment_id':item['fragment_id'],'decision':'same','related_fact_id':item['candidate_options'][0]['fact_id']},group['version']).json()
        self.assertEqual(self.settle(self.preview(group)).json()['coins_gained'],0)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],balance)

    def test_all_model_uses_exclude_private_and_untraced_derived_fragments(self):
        import json
        from app.models import UserProfile,Attribute,AttributeHistory,Challenge
        from app.services import memory_service,shop_service,challenge_service,exemption_service,subdimension_service,onboarding_service
        self.register();self.configure_model();self.adopt();private=self.event('PRIVATE_RAW_ALL');allowed=self.event('允许的散步','allowed');user_id=self.user_id()
        with self.Session() as db:
            profile=db.query(UserProfile).filter_by(user_id=user_id).one();profile.long_term_memory=json.dumps({'preferences':['PRIVATE_DERIVED_ALL']});profile.memory_sources=None
            attr=db.query(Attribute).filter_by(user_id=user_id,name='体能').one();attr.current_value=95
            db.add(AttributeHistory(user_id=user_id,attribute_id=attr.id,event_id=private['id'],delta=1,value_after=95,reason='PRIVATE_HISTORY_ALL',evidence='PRIVATE_EVIDENCE_ALL'))
            db.add(Challenge(user_id=user_id,title='PRIVATE_CHALLENGE_ALL',description='PRIVATE_CHALLENGE_DESCRIPTION',scope='daily',status='abandoned',period_key=challenge_service.period_key('daily')));db.commit()
        replies={
            'memory':{'preferences':['仅采用允许的散步']},
            'shop':{'coin_price':20,'pricing_reason':'合成依据','worth_note':''},
            'challenge':{'challenges':[]},
            'exemption':{'coin_cost':1,'motive':'legitimate'},
            'subdimension':{'items':[{'name':'耐力练习','description':'方向一'},{'name':'灵活练习','description':'方向二'}]},
            'supplement':{'adjustments':[],'explanation':'只更新明确提交的背景'},
        }
        for purpose in replies:
            with self.subTest(purpose=purpose),self.Session() as db:
                db.info['user_id']=user_id;user=db.get(User,user_id);sent=[]
                def fake(messages,**kwargs):sent.append(messages);return replies[purpose]
                with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):
                    if purpose=='memory':memory_service.update_long_term_memory(db,user)
                    elif purpose=='shop':shop_service.price_item(db,user,'想要的体验',None)
                    elif purpose=='challenge':challenge_service.generate(db,user)
                    elif purpose=='exemption':exemption_service.buy(db,user,str(local_day(utc_now(),user.timezone)),'morning',reason='本次明确说明')
                    elif purpose=='subdimension':subdimension_service.propose(db,user,db.query(Attribute).filter_by(user_id=user_id,name='体能').one())
                    else:onboarding_service.supplement_profile(db,'本次明确提供的长期信息')
                self.assertEqual(len(sent),1)
                self.assertNotIn('PRIVATE_',json.dumps(sent,ensure_ascii=False))

    def test_trial_streak_and_legacy_auto_routes_share_lifetime_reward_identity(self):
        from app.services import discoveries,coin_service,achievement_service
        from app.models.full_system import TrialAccount
        from app.models.policies import DynamicCandidate
        from app.models import Achievement
        self.register();self.adopt();user_id=self.user_id();today=local_day(utc_now(),'Asia/Shanghai')
        with self.Session() as db:
            user=db.get(User,user_id)
            for n in range(7):db.add(Event(user_id=user_id,event_type='positive',source='journal',record_kind='diary',content='合成日记',saved_on=str(today-timedelta(days=n)),saved_timezone=user.timezone,occurred_at=utc_now()-timedelta(days=n)))
            db.flush();discoveries.discover(db,user)
            for target in (3,7):
                row=next(r for r in db.query(DynamicCandidate).filter_by(user_id=user_id).all() if r.criteria['metric']=='diary_saved_days' and r.criteria['shape']=='consecutive_days' and r.criteria['target']==target)
                discoveries.claim(db,user,row)
            db.commit();balance=coin_service.balance(db,user)
            self.assertEqual(coin_service.check_journal_streak(db,user),[]);self.assertEqual(achievement_service.check_and_grant(db,user),[])
            config=db.query(TrialAccount).filter_by(user_id=user_id).one();config.enabled=False;db.commit()
            self.assertEqual(coin_service.check_journal_streak(db,user),[])
            achievement_service.check_and_grant(db,user)
            self.assertFalse(db.query(Achievement).filter_by(user_id=user_id,code='journal_streak_7').filter(Achievement.unlocked_at.is_not(None)).first())

    def test_return_policy_new_account_sparse_usage_and_skip_cooldown(self):
        self.register();self.assertFalse(self.client.get('/api/phase').json()['return_prompt'])
        event=self.event('仅有的一条记录');user_id=self.user_id()
        with self.Session() as db:
            user=db.get(User,user_id);user.created_at=utc_now()-timedelta(days=60);db.commit()
        state=self.client.get('/api/phase').json();self.assertTrue(state['return_prompt']);self.assertEqual(state['return_policy']['sparse_max_records'],2)
        response=self.write('/phase',{'skip_return':True},0,'PUT');self.assertEqual(response.status_code,200,response.text)
        self.assertIn('return_policy',response.json()['history'][0]);self.assertFalse(self.client.get('/api/phase').json()['return_prompt'])

    def test_strong_contract_requires_acceptance_locks_old_contract_and_daily_cap(self):
        self.register();self.configure_model();self.adopt();self.event('当天首记')
        daily=self.client.get('/api/trial').json()['daily'];now=utc_now().replace(hour=1,minute=0,second=0,microsecond=0)
        self.assertEqual(self.write('/timers',{'kind':'base','source_id':daily['id'],'mode':'strong','acknowledge_penalty':True}).status_code,409)
        item=self.reward();vouchers=[]
        for _ in range(2):
            response=self.client.post(f"/api/shop/items/{item['id']}/redeem",json={'request_key':str(uuid4()),'expected_version':item['updated_at']})
            self.assertEqual(response.status_code,200,response.text);vouchers.append(response.json()['redemption'])
        phase=self.write('/phase',{'title':'考试阶段','preferences':'自愿接受严格娱乐约定','ai_allowed':True},0,'PUT').json()
        def accept(mode,phase):
            with patch('app.services.llm_service.llm_service.chat_json',return_value={'mode':mode,'reason':'仅对未来自愿开始的娱乐采用'}):suggestion=self.write('/phase/analyze',version=phase['version'])
            self.assertEqual(suggestion.status_code,200,suggestion.text)
            self.assertEqual(self.write('/phase/accept-constraint',{'acknowledge':False},suggestion.json()['version']).status_code,422)
            result=self.write('/phase/accept-constraint',{'acknowledge':True},suggestion.json()['version'])
            self.assertEqual(result.status_code,200,result.text);return result.json()
        phase=accept('strong',phase)
        with patch('app.routers.timers.utc_now',return_value=now):first=self.write('/timers',{'kind':'voucher','source_id':vouchers[0]['id'],'mode':'strong','acknowledge_penalty':True}).json()
        phase=accept('gentle',phase)
        self.assertEqual(self.client.get('/api/timers').json()['active']['contract']['mode'],'strong')
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(minutes=80)),patch('app.services.timers.utc_now',return_value=now+timedelta(minutes=80)):
            preview=self.write(f"/timers/{first['id']}/end-preview",version=1).json();self.assertEqual(preview['preview']['penalty_charged'],20)
            settled=self.write(f"/timers/{first['id']}/confirm",version=preview['version']);self.assertEqual(settled.status_code,200,settled.text)
        phase=accept('strong',phase)
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(minutes=80)):second=self.write('/timers',{'kind':'voucher','source_id':vouchers[1]['id'],'mode':'strong','acknowledge_penalty':True}).json()
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(minutes=160)),patch('app.services.timers.utc_now',return_value=now+timedelta(minutes=160)):
            preview=self.write(f"/timers/{second['id']}/end-preview",version=1).json();self.assertEqual(preview['preview']['penalty_charged'],10)
            self.assertEqual(self.write(f"/timers/{second['id']}/confirm",version=preview['version']).status_code,200)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],10)
        plan=self.write('/plan-schedules',{'name':'计划不套娱乐罚款','frequency':'manual','start':str(local_day(utc_now(),'Asia/Shanghai'))}).json()
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(minutes=160)):row=self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':plan['version'],'mode':'strong'}).json()
        self.assertEqual(row['contract']['mode'],'gentle')
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(minutes=240)),patch('app.services.timers.utc_now',return_value=now+timedelta(minutes=240)):
            preview=self.write(f"/timers/{row['id']}/end-preview",version=1).json();self.assertEqual(preview['preview']['penalty_charged'],0);self.assertEqual(preview['preview']['ontime_awarded'],0)
            self.assertEqual(self.write(f"/timers/{row['id']}/confirm",version=preview['version']).status_code,200)
        self.assertEqual(self.client.get('/api/plan-occurrences').json()['history'],[])

    def test_holiday_and_mainline_real_preview_breakdown_and_single_day_gift(self):
        from app.models.full_system import Holiday
        self.register();self.configure_model();self.adopt();user_id=self.user_id();day=str(local_day(utc_now(),'Asia/Shanghai'))
        self.write('/trial',{'acknowledge':True,'region':'fixture-region','base_minutes':30},1,'PUT')
        with self.Session() as db:
            db.add_all([Holiday(local_date=day,region='fixture-region',name='合成节日一'),Holiday(local_date=day,region='fixture-region',name='合成节日二')]);db.commit()
        goal=self.client.post('/api/goals',json={'description':'当前学习目标','metric':'十章'}).json()
        main=self.write('/mainlines',{'goal_id':goal['id'],'active':True});self.assertEqual(main.status_code,200,main.text)
        event=self.event('完成一段有效学习','allowed');group=self.facts(event,[self.suggestion(event['content'],coins=30,goal_id=goal['id'],effort=True)])
        item=group['payload']['items'][0];group=self.write(f"/fact-bundles/{group['id']}/decision",{'fragment_id':item['fragment_id'],'decision':'keep','mainline':True},group['version']).json()
        group=self.preview(group);split=group['preview']['items'][0]['breakdown'];self.assertEqual((split['coins'],split['amount'],split['mainline'],split['holiday']),(30,30,True,True))
        self.assertEqual(self.settle(group).json()['coins_gained'],30)
        key=str(uuid4());response=self.write('/holidays/claim',key=key);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.write('/holidays/claim',key=key).json(),response.json());self.assertEqual(self.write('/holidays/claim').status_code,409)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],120)

    def test_care_model_candidates_require_acceptance_and_exclude_unlicensed_names(self):
        import json
        self.register();self.configure_model();self.write('/care/items',{'name':'PRIVATE_CARE_NAME','frequency':'daily'})
        state=self.client.get('/api/care').json();sent=[]
        def fake(messages,**kwargs):sent.append(messages);return {'items':['散步','散步','喝水']}
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):response=self.write('/care/suggestions',{'topic':'本次主动提供的方向'},state['config']['version'])
        self.assertEqual(response.status_code,200,response.text);self.assertNotIn('PRIVATE_CARE_NAME',json.dumps(sent,ensure_ascii=False))
        self.assertEqual(len(self.client.get('/api/care').json()['items']),1)
        version=response.json()['version'];key=str(uuid4());accepted=self.write('/care/suggestions/0/accept',version=version,key=key)
        self.assertEqual(accepted.status_code,200,accepted.text);self.assertEqual(self.write('/care/suggestions/0/accept',version=version,key=key).json(),accepted.json())
        self.assertEqual(len(self.client.get('/api/care').json()['items']),2)
        self.assertEqual(self.write('/care/suggestions/0/accept',version=accepted.json()['config']['version']).status_code,409)
