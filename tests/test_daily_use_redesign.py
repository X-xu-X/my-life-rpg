"""October 21 contracts: isolated SQLite, captured requests, no real suppliers."""
import json,unittest
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4
import tests.test_full_system as full
from app.models import User,UserProfile,ShopItem
from app.services.time_service import utc_now,local_day


class DailyUseTests(unittest.TestCase):
    setUp=full.FullSystemTests.setUp
    tearDown=full.FullSystemTests.tearDown
    register=full.FullSystemTests.register
    configure_model=full.FullSystemTests.configure_model
    write=full.FullSystemTests.write
    event=full.FullSystemTests.event
    adopt=full.FullSystemTests.adopt
    user_id=full.FullSystemTests.user_id
    facts=full.FullSystemTests.facts
    suggestion=full.FullSystemTests.suggestion
    preview=full.FullSystemTests.preview
    settle=full.FullSystemTests.settle
    owner=full.FullSystemTests.owner

    def basics(self,answered=None):
        catalog=self.client.get('/api/questionnaire').json()
        answers={q['id']:{'state':'skipped','value':''} for q in catalog['questions']}
        for key,value in (answered or {}).items():answers[key]={'state':'answered','value':value}
        response=self.write('/questionnaire',{'answers':answers,'send_groups':['work','rewards']},0,'PUT')
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_A01_controlled_diagnostics_and_provider_specific_request(self):
        from app.services.llm_service import llm_service
        from app.services.model_errors import category
        from app.services.model_diagnostics import response_summary,test_options
        self.register();self.configure_model();version=self.client.get('/api/llm-config').json()['primary']['config_version']
        for content,reason,other,expected in [('','stop','HIDDEN_REASONING','MODEL_EMPTY_RESPONSE'),('partial','length','HIDDEN_REASONING','MODEL_OUTPUT_TRUNCATED'),('OK','stop','',None)]:
            response=NS(choices=[NS(message=NS(content=content,reasoning_content=other),finish_reason=reason)],usage=NS(prompt_tokens=3,completion_tokens=9,total_tokens=12))
            client=NS(chat=NS(completions=NS(create=lambda **kw:response)),close=lambda:None)
            with patch.object(llm_service,'_get_client',return_value=client),patch('app.services.llm_service.reserve_usage'):
                result=self.client.post('/api/llm-config/test',json={'group':'primary','expected_config_version':version})
            self.assertEqual(result.status_code,200,result.text);value=result.json()
            self.assertEqual(value['error_code'],expected);self.assertEqual(value['diagnostic']['finish_reason'],reason)
            self.assertEqual(value['diagnostic']['has_other_output'],bool(other));self.assertNotIn('HIDDEN_REASONING',result.text)
            self.assertEqual(value['diagnostic']['usage']['total_tokens'],12)
        self.assertIn('extra_body',test_options(NS(base_url='https://api.deepseek.com')))
        self.assertEqual(test_options(NS(base_url='https://proxy.example/v1')),{})
        self.assertEqual(category(NS(status_code=400,body={'error':{'message':'SECRET'}})),'MODEL_REQUEST_INCOMPATIBLE')

    def test_A06_A08_A09_questionnaire_once_readonly_history_and_neutral_exit(self):
        self.register();draft=self.basics()
        with patch('app.services.llm_service.llm_service.chat_json') as model:
            preview=self.write('/questionnaire/analyze',{'use_ai':False},draft['version'])
        self.assertEqual(preview.status_code,200,preview.text);model.assert_not_called()
        key=str(uuid4());confirmed=self.write('/questionnaire/confirm',version=preview.json()['version'],key=key)
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        self.assertEqual(self.write('/questionnaire/confirm',version=preview.json()['version'],key=key).json(),confirmed.json())
        history=self.client.get('/api/questionnaire').json();self.assertEqual(len(history['history']),1)
        self.assertEqual(len(history['history'][0]['questions']),30)
        self.assertEqual(self.write('/questionnaire',{'answers':{}},confirmed.json()['version'],'PUT').status_code,409)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],80)

    def test_A07_personalized_followups_are_bounded_and_skips_not_resent(self):
        self.register();self.configure_model();draft=self.basics({'work_1':'学习水彩','rewards_1':'每周一张画纸'})
        sent=[]
        def fake(messages,**kw):sent.append(messages);return {'questions':[{'text':'学水彩时想练哪一种画法？','based_on':['work_1']}]}
        key=str(uuid4())
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake) as model:
            result=self.write('/questionnaire/analyze',{'use_ai':True,'acknowledge_scope':True},draft['version'],key=key)
            replay=self.write('/questionnaire/analyze',{'use_ai':True,'acknowledge_scope':True},draft['version'],key=key)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(replay.json(),result.json());self.assertEqual(model.call_count,1)
        self.assertEqual(result.json()['stage'],'followups')
        self.assertIn('学习水彩',json.dumps(sent,ensure_ascii=False))
        question=result.json()['followups'][0]['questions'][0]
        answers={**draft['answers'],question['id']:{'state':'skipped','value':''}}
        saved=self.write('/questionnaire',{'answers':answers,'send_groups':['work','rewards']},result.json()['version'],'PUT')
        self.assertEqual(saved.status_code,200,saved.text)
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'questions':[{'text':'不该问跳过的生活题','based_on':['life_1']}]}):
            bad=self.write('/questionnaire/analyze',{'use_ai':True,'acknowledge_scope':True},saved.json()['version'])
        self.assertEqual(bad.status_code,422,bad.text)

    def test_A04_A09_personal_background_permissions_delete_and_no_financial_writes(self):
        from app.services.personal_context import background
        self.register();self.adopt();uid=self.user_id();entry={'id':str(uuid4()),'text':'SELF_PRIVATE_SENTINEL INFP','uses':['pricing']}
        response=self.write('/personal-information',{'entries':[entry]},0,'PUT');self.assertEqual(response.status_code,200,response.text)
        with self.Session() as db:
            self.assertNotIn('SELF_PRIVATE_SENTINEL',json.dumps(background(db,uid,'judge')))
            self.assertIn('SELF_PRIVATE_SENTINEL',json.dumps(background(db,uid,'pricing')))
        removed=self.write('/personal-information',{'entries':[]},response.json()['version'],'PUT')
        self.assertEqual(removed.status_code,200,removed.text)
        with self.Session() as db:self.assertNotIn('SELF_PRIVATE_SENTINEL',json.dumps(background(db,uid,'pricing')))
        self.assertEqual(self.client.get('/api/coins').json()['balance'],80)
        self.assertEqual(self.client.post('/api/onboarding/supplement',json={'detail':'不能重评'}).status_code,409)

    def test_A12_A13_optional_minutes_project_reclassification_preserves_identity(self):
        from app.models import Event
        self.register();self.adopt();today=local_day(utc_now(),'Asia/Shanghai')
        body={'name':'照看窗边植物','category':'care','frequency':'daily','start':str(today),'planned_minutes':None}
        response=self.write('/projects',body);self.assertEqual(response.status_code,200,response.text);project=response.json()['project']
        saved=self.write(f"/care/items/{project['id']}/entries/{today}",{'item_version':project['version'],'state':'skipped'},0,'PUT')
        self.assertEqual(saved.status_code,200,saved.text)
        changed=self.write(f"/projects/care/{project['id']}",{**body,'category':'plan','start':str(today+timedelta(days=1))},project['version'],'PUT')
        self.assertEqual(changed.status_code,200,changed.text)
        listed=self.client.get('/api/projects?day='+str(today)).json()['items'][0]
        self.assertEqual(listed['origin'],'care');self.assertEqual(listed['entry']['state'],'skipped');self.assertEqual(listed['result_category'],'care')
        self.assertEqual(self.write('/timers',{'kind':'plan','source_type':'care','source_id':project['id'],'source_version':2}).status_code,422)
        timer=self.write('/timers',{'kind':'plan','source_type':'care','source_id':project['id'],'source_version':2,'planned_minutes':25})
        self.assertEqual(timer.status_code,200,timer.text);self.assertEqual(timer.json()['limit_seconds'],1500)
        with self.Session() as db:self.assertEqual(db.query(Event).count(),0)

    def test_A19_A21_auto_price_initial_integer_bounds_no_default_goods(self):
        from app.routers.reward_quotes import bounded_price
        self.register();self.configure_model();self.adopt()
        self.assertEqual(self.client.get('/api/shop/items').json()['items'],[])
        key=str(uuid4())
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'coin_price':23,'pricing_reason':'本人每周一次的画纸参考','worth_note':'自主决定'}) as model:
            response=self.write('/reward-quotes',{'name':'画纸','auto_check':True},key=key)
            replay=self.write('/reward-quotes',{'name':'画纸','auto_check':True},key=key)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['state'],'accepted')
        self.assertEqual(replay.json(),response.json());self.assertEqual(model.call_count,1)
        items=self.client.get('/api/shop/items').json()['items'];self.assertEqual(len(items),1);self.assertEqual(items[0]['coin_price'],23)
        self.assertEqual(bounded_price(23,99),(27,[19,27]));self.assertEqual(bounded_price(31,1),(25,[25,37]));self.assertEqual(bounded_price(1,9),(1,[1,1]))
        self.assertEqual(self.client.put(f"/api/shop/items/{items[0]['id']}",json={'coin_price':1}).status_code,409)
        with patch('app.services.llm_service.llm_service.chat_json') as model:
            check=self.write('/pricing-checks',{});self.assertEqual(check.status_code,200,check.text);self.assertEqual(check.json()['queued'],0);model.assert_not_called()

    def test_A26_preferences_are_server_owned_and_new_sessions_distinct(self):
        self.register();first=self.client.get('/api/auth/me').json()['login_session']
        saved=self.write('/experience-preferences',{'suppressed':['plans-help'],'return_disabled':True},0,'PUT')
        self.assertEqual(saved.status_code,200,saved.text)
        self.client.post('/api/auth/logout')
        result=self.client.post('/api/auth/login',json={'username':'friend','password':'friend-test-password'});self.client.headers['X-CSRF-Token']=result.json()['csrf_token']
        self.assertNotEqual(self.client.get('/api/auth/me').json()['login_session'],first)
        self.assertEqual(self.client.get('/api/experience-preferences').json()['suppressed'],['plans-help'])

    def test_A28_important_days_cross_year_leap_day_and_invalid_date(self):
        from app.routers.daily_use import upcoming
        from datetime import date
        self.register();uid=self.user_id()
        for body in ({'name':'跨年生日','month':1,'day':2,'annual':True,'remind_days':7},{'name':'闰日','month':2,'day':29,'annual':True}):
            self.assertEqual(self.write('/important-days',body).status_code,200)
        self.assertEqual(self.write('/important-days',{'name':'无效','month':2,'day':31}).status_code,422)
        self.assertEqual(self.write('/important-days',{'name':'一次','month':1,'day':2,'annual':False}).status_code,422)
        with self.Session() as db:
            user=db.get(User,uid);self.assertEqual(upcoming(db,user,date(2026,12,29))[0]['date'],'2027-01-02')
            self.assertEqual(upcoming(db,user,date(2027,2,27)),[])

    def test_A15_A16_A17_A18_per_fact_threshold_supplement_and_first_record_independent(self):
        from app.models import AttributeHistory,Event
        from app.models.workflow import FactSettlement
        self.register();self.configure_model();self.adopt()
        event=self.event('伸展了三分钟。完成十个深蹲。','allowed')
        group=self.facts(event,[self.suggestion('伸展了三分钟。',confidence=.799),self.suggestion('完成十个深蹲。',confidence=.8)])
        group=self.preview(group);self.assertEqual([i['eligible'] for i in group['preview']['items']],[False,True]);self.assertEqual(group['preview']['total'],6)
        self.assertEqual(self.settle(group).status_code,200)
        with self.Session() as db:self.assertEqual(db.query(FactSettlement).count(),1)
        note=self.write(f"/events/{event['id']}/fact-notes",{'content':'补充：伸展过程和身体活动的实际投入。'},1)
        self.assertEqual(note.status_code,200,note.text)
        next_group=self.preview(self.facts(event,[self.suggestion('伸展了三分钟。',confidence=.9)]))
        self.assertEqual(self.settle(next_group).status_code,200)
        with self.Session() as db:self.assertEqual(db.query(Event).count(),1);self.assertEqual(db.query(FactSettlement).count(),2)
        daily=self.client.get('/api/trial').json()['daily'];key=str(uuid4())
        claimed=self.write('/trial/first-record/claim',version=daily['version'],key=key)
        self.assertEqual(claimed.status_code,200,claimed.text)
        self.assertEqual(self.write('/trial/first-record/claim',version=daily['version'],key=key).json(),claimed.json())
        self.assertEqual(claimed.json()['coins_gained'],3)

    def test_A15_invalid_confidence_never_becomes_a_fact_or_legacy_confirm(self):
        from app.services.fact_analysis import Suggestion
        from pydantic import ValidationError
        from app.models import AIJudgment,AttributeHistory
        self.register();self.configure_model();self.adopt();event=self.event('可核对的低信息行动','allowed')
        for value in (True,None,float('nan'),float('inf'),-.1,1.01,'0.9'):
            with self.assertRaises(ValidationError):Suggestion.model_validate(self.suggestion(event['content'],confidence=value))
        from app.services import analysis_jobs
        response=self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1,'operation':'judge'})
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'realistic':True,'confidence':True,'affected_attributes':[]}):analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        self.assertEqual(self.client.get('/api/analysis-jobs/'+str(response.json()['id'])).json()['state'],'failed')
        with self.Session() as db:
            judgment=AIJudgment(user_id=self.user_id(),event_id=event['id'],confidence=.799,status='pending',suggested_changes=[])
            db.add(judgment);db.commit();jid=judgment.id;stamp=judgment.updated_at.isoformat()
        denied=self.client.post(f'/api/judgments/{jid}/confirm',json={'request_key':str(uuid4()),'expected_version':stamp})
        self.assertIn(denied.status_code,(400,409),denied.text)
        with self.Session() as db:self.assertEqual(db.query(AttributeHistory).count(),0)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],80)

    def test_A08_ai_assessment_keeps_personal_coin_range_and_replays_without_second_call(self):
        from app.constants import ATTRIBUTE_DIMENSIONS
        self.register();self.configure_model();draft=self.basics({'work_1':'修复了一套可核对的部署流程','rewards_1':'希望每周一次阅读新书'})
        panel={'attributes':[{'name':n,'value':53,'reason':'合成初始依据，不是能力测量'} for n in ATTRIBUTE_DIMENSIONS],'initial_coins':150,'summary':'合成充分资料','economic_reference':{'basis':'每周一次本人心愿，不设统一汇率'}}
        sent=[]
        def model(messages,**kw):sent.append(messages);return {'questions':[]} if '整体阅读本人明确授权' in messages[0]['content'] else panel
        key=str(uuid4());body={'use_ai':True,'acknowledge_scope':True}
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=model):
            preview=self.write('/questionnaire/analyze',body,draft['version'],key=key)
            replay=self.write('/questionnaire/analyze',body,draft['version'],key=key)
        self.assertEqual(preview.status_code,200,preview.text);self.assertEqual(replay.json(),preview.json());self.assertEqual(len(sent),2)
        self.assertEqual(preview.json()['preview']['initial_coins'],150)
        confirmed=self.write('/questionnaire/confirm',version=preview.json()['version']);self.assertEqual(confirmed.status_code,200,confirmed.text)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],150)
        self.assertEqual(self.client.post('/api/onboarding/neutral',json={'acknowledge':True}).status_code,409)
        history=self.client.get('/api/questionnaire').json()['history'][0]
        self.assertEqual(history['assessment']['initial_coins'],150)

    def test_A10_A11_return_cooldown_excludes_deleted_and_never_deducts_for_absence(self):
        from app.models import Event,AttributeHistory
        self.register();self.adopt();uid=self.user_id();now=utc_now()
        with self.Session() as db:
            db.get(User,uid).created_at=now-timedelta(days=90)
            db.add(Event(user_id=uid,event_type='positive',record_kind='diary',content='已撤销的合成记录',is_deleted=True,created_at=now))
            db.commit()
        self.assertTrue(self.client.get('/api/return-checkin').json()['eligible'])
        data=self.client.get('/api/return-checkin').json();answers={q['id']:{'state':'skipped','value':''} for q in data['questions']}
        saved=self.write('/return-checkin',{'answers':answers,'uses':[]},0,'PUT')
        self.assertEqual(saved.status_code,200,saved.text)
        completed=self.write('/return-checkin/complete',{},saved.json()['version'])
        self.assertEqual(completed.status_code,200,completed.text);self.assertFalse(self.client.get('/api/return-checkin').json()['eligible'])
        self.assertEqual(self.client.get('/api/stagnation').json()['items'],[])
        self.assertEqual(self.client.get('/api/coins').json()['balance'],80)
        with self.Session() as db:self.assertEqual(db.query(Event).count(),1);self.assertEqual(db.query(AttributeHistory).count(),0)

    def test_A20_A21_A23_auto_check_coalesces_bounds_and_old_purchase_preview_conflicts(self):
        from app.services import pricing_checks,trial_rules
        from app.models import Redemption
        self.register();self.configure_model();self.adopt()
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'coin_price':23,'pricing_reason':'本人期望频率','worth_note':''}):q=self.write('/reward-quotes',{'name':'周末娱乐','reward_kind':'entertainment','minutes':30,'auto_check':True}).json()
        item=q['item'];first=self.client.post(f"/api/shop/items/{item['id']}/redeem",json={'request_key':str(uuid4()),'expected_version':item['updated_at']})
        self.assertEqual(first.status_code,200,first.text)
        tomorrow=str(local_day(utc_now(),'Asia/Shanghai')+timedelta(days=1))
        with patch('app.services.trial_rules.day',return_value=tomorrow):
            a=self.write('/pricing-checks',{});b=self.write('/pricing-checks',{})
            self.assertEqual(a.json()['queued'],1);self.assertEqual(b.json()['queued'],0)
            with patch('app.services.llm_service.llm_service.chat_json',return_value={'coin_price':99,'pricing_reason':'合成调整','worth_note':''}) as model:pricing_checks.process(self.Session,pricing_checks.claim(self.Session))
            self.assertEqual(model.call_count,1)
        checks=self.client.get('/api/pricing-checks').json()['items'];self.assertEqual(checks[0]['state'],'completed',checks)
        changed=self.client.get('/api/shop/items').json()['items'][0];self.assertEqual(changed['coin_price'],27)
        stale=self.client.post(f"/api/shop/items/{item['id']}/redeem",json={'request_key':str(uuid4()),'expected_version':item['updated_at']})
        self.assertEqual(stale.status_code,409,stale.text)
        with self.Session() as db:
            red=db.query(Redemption).one();self.assertEqual(red.coin_spent,23);self.assertEqual(red.duration_seconds,1800)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],57)

    def test_A20_failed_daily_check_preserves_price_and_has_only_one_explicit_retry(self):
        from app.services import pricing_checks
        from app.services.llm_service import LLMError
        self.register();self.configure_model();self.adopt()
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'coin_price':31,'pricing_reason':'个人依据','worth_note':''}):self.write('/reward-quotes',{'name':'绘画材料','auto_check':True})
        tomorrow=str(local_day(utc_now(),'Asia/Shanghai')+timedelta(days=1))
        with patch('app.services.trial_rules.day',return_value=tomorrow),patch('app.services.llm_service.llm_service.chat_json',side_effect=LLMError('MODEL_TIMEOUT')) as model:
            self.write('/pricing-checks',{});pricing_checks.process(self.Session,pricing_checks.claim(self.Session))
            first=self.client.get('/api/pricing-checks').json()['items'][0]
            self.assertEqual(first['state'],'failed');self.assertEqual(self.write('/pricing-checks',{}).json()['queued'],0)
            retried=self.write('/pricing-checks/'+str(first['id'])+'/retry',version=first['version']);self.assertEqual(retried.status_code,200,retried.text)
            pricing_checks.process(self.Session,pricing_checks.claim(self.Session))
            last=self.client.get('/api/pricing-checks').json()['items'][0]
            self.assertEqual(self.write('/pricing-checks/'+str(last['id'])+'/retry',version=last['version']).status_code,409)
            self.assertEqual(model.call_count,2)
        self.assertEqual(self.client.get('/api/shop/items').json()['items'][0]['coin_price'],31)

    def test_A22_price_late_background_revocation_cannot_create_item(self):
        from app.models.daily_use import PersonalInformation
        self.register();self.configure_model();self.adopt();uid=self.user_id()
        self.write('/personal-information',{'entries':[{'id':str(uuid4()),'text':'PRICING_ALLOWED_BACKGROUND','uses':['pricing']}]},0,'PUT')
        def revoke(messages,**kw):
            self.assertIn('PRICING_ALLOWED_BACKGROUND',json.dumps(messages))
            with self.Session() as db:row=db.query(PersonalInformation).filter_by(user_id=uid).one();row.entries=[];row.version+=1;db.commit()
            return {'coin_price':17,'pricing_reason':'晚回的合成结果','worth_note':''}
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=revoke):result=self.write('/reward-quotes',{'name':'不能接受晚回'})
        self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(self.client.get('/api/shop/items').json()['items'],[])
        self.assertEqual(self.client.get('/api/reward-quotes').json()['items'][0]['state'],'failed')

    def test_A27_official_calendar_and_import_do_not_add_gift_days(self):
        from app.models.full_system import Holiday
        self.register();self.adopt();calendar=self.client.get('/api/calendar?year=2026').json()
        self.assertEqual(len(calendar['data']['statutory']),13);self.assertIn('2026-01-04',calendar['data']['working_days'])
        self.assertEqual(self.client.get('/api/calendar?year=2027').json()['status'],'missing')
        self.assertEqual(self.write('/admin/calendars/2026',{'source_url':calendar['source_url'],'data':calendar['data'],'reason':'合成未授权检查'},0).status_code,403)
        self.owner()
        imported=self.write('/admin/calendars/2026',{'source_url':calendar['source_url'],'data':calendar['data'],'reason':'隔离官方数据导入检查'},0)
        self.assertEqual(imported.status_code,200,imported.text)
        with self.Session() as db:self.assertEqual(db.query(Holiday).count(),0)

    def test_A30_optional_archives_and_no_lease_token_export(self):
        from app.models.daily_use import PricingCheck
        self.register();self.configure_model();self.adopt();uid=self.user_id()
        self.write('/personal-information',{'entries':[{'id':str(uuid4()),'text':'PRIVATE_PERSONAL_ARCHIVE','uses':[]}]},0,'PUT')
        self.write('/important-days',{'name':'PRIVATE_IMPORTANT_DATE','month':2,'day':29})
        with self.Session() as db:
            item=ShopItem(user_id=uid,name='已有商品',coin_price=23);db.add(item);db.flush()
            db.add(PricingCheck(user_id=uid,item_id=item.id,local_date=str(local_day(utc_now(),'Asia/Shanghai')),request_key=str(uuid4()),state='running',lease_token='EXPORT_LEASE_SECRET'));db.commit()
        default=self.client.get('/api/export');self.assertNotIn('PRIVATE_PERSONAL_ARCHIVE',default.text);self.assertNotIn('PRIVATE_IMPORTANT_DATE',default.text);self.assertNotIn('EXPORT_LEASE_SECRET',default.text)
        selected=self.client.get('/api/export?include_questionnaire=true&include_personal=true&include_game=false')
        self.assertIn('PRIVATE_PERSONAL_ARCHIVE',selected.text);self.assertIn('PRIVATE_IMPORTANT_DATE',selected.text);self.assertNotIn('EXPORT_LEASE_SECRET',selected.text)
        self.assertEqual(self.client.get('/api/export?start=2026-02-31').status_code,422)

    def test_A03_synchronous_unknown_dispatch_never_pays_again_on_same_key(self):
        from app.services.llm_service import LLMError
        self.register();self.configure_model()
        phase=self.write('/phase',{'title':'当前阶段','preferences':'温和提醒','ai_allowed':True},0,'PUT').json()
        key=str(uuid4())
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=LLMError('MODEL_TIMEOUT')) as model:
            first=self.write('/phase/analyze',version=phase['version'],key=key)
            retry=self.write('/phase/analyze',version=phase['version'],key=key)
        self.assertEqual(first.status_code,503,first.text);self.assertEqual(retry.status_code,409,retry.text);self.assertEqual(model.call_count,1)
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'mode':'gentle','reason':'本次主动重新分析'}) as model:
            new_key=str(uuid4());second=self.write('/phase/analyze',version=phase['version'],key=new_key)
            replay=self.write('/phase/analyze',version=phase['version'],key=new_key)
        self.assertEqual(second.status_code,200,second.text);self.assertEqual(replay.json(),second.json());self.assertEqual(model.call_count,1)

    def test_A04_A14_A22_phase_uses_only_current_goal_and_invalidates_late_mainline(self):
        from app.models.policies import Mainline
        self.register();self.configure_model();self.adopt();uid=self.user_id()
        created=self.client.post('/api/goals',json={'description':'CURRENT_UNIQUE_MAINLINE','metric':'十章'})
        self.assertEqual(created.status_code,200,created.text);goal=created.json()
        self.assertEqual(self.write('/mainlines',{'goal_id':goal['id'],'active':True}).status_code,200)
        phase=self.write('/phase',{'title':'现阶段','goal':'OBSOLETE_DUPLICATE_GOAL','ai_allowed':True},0,'PUT').json();sent=[]
        def late(messages,**kw):
            sent.append(messages)
            with self.Session() as db:
                line=db.query(Mainline).filter_by(user_id=uid).one();line.version+=1;line.active=False;db.commit()
            return {'mode':'strong','reason':'已过期的合成建议'}
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=late):result=self.write('/phase/analyze',version=phase['version'])
        self.assertEqual(result.status_code,409,result.text);payload=json.dumps(sent,ensure_ascii=False)
        self.assertIn('CURRENT_UNIQUE_MAINLINE',payload);self.assertNotIn('OBSOLETE_DUPLICATE_GOAL',payload)
        self.assertIsNone(self.client.get('/api/phase').json()['phase']['pending'])

    def test_A22_old_unproven_constraint_cannot_be_newly_accepted(self):
        from app.models.full_system import PersonalPhase
        self.register();uid=self.user_id()
        with self.Session() as db:
            db.add(PersonalPhase(user_id=uid,version=1,payload={'accepted_mode':'gentle'},pending={'mode':'strong','reason':'旧建议，无来源版本'}));db.commit()
        self.assertEqual(self.write('/phase/accept-constraint',{'acknowledge':True},1).status_code,409)
        self.assertEqual(self.client.get('/api/phase').json()['phase']['payload']['accepted_mode'],'gentle')

    def test_A03_A04_report_key_replay_purpose_permissions_and_late_revoke(self):
        self.register();self.configure_model();self.adopt();entry=str(uuid4());uid=self.user_id()
        with patch('app.services.llm_service.llm_service.chat_json') as model:
            self.assertEqual(self.client.post('/api/report?period=week').status_code,422);model.assert_not_called()
        self.write('/personal-information',{'entries':[{'id':entry,'text':'ONLY_REPORT_BACKGROUND','uses':['report']},{'id':str(uuid4()),'text':'PRIVATE_INFO_NOT_AUTHORIZED','uses':[]}]},0,'PUT')
        private=self.event('PRIVATE_ORIGINAL_SENTINEL');self.event('ALLOWED_FACT_SENTINEL','allowed');sent=[]
        def fake(messages,**kw):sent.append(messages);return {'summary':'合成报告'}
        key=str(uuid4())
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake) as model:
            result=self.write('/report?period=week',key=key);again=self.write('/report?period=week',key=key)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(again.json(),result.json());self.assertEqual(model.call_count,1)
        payload=json.dumps(sent,ensure_ascii=False);self.assertIn('ONLY_REPORT_BACKGROUND',payload);self.assertNotIn('PRIVATE_ORIGINAL_SENTINEL',payload);self.assertNotIn('PRIVATE_INFO_NOT_AUTHORIZED',payload)
        def revoke(messages,**kw):
            from app.models.daily_use import PersonalInformation
            with self.Session() as db:
                row=db.query(PersonalInformation).filter_by(user_id=uid).one();row.entries=[];row.version+=1;db.commit()
            return {'summary':'已过期报告'}
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=revoke):late=self.write('/report?period=month')
        self.assertEqual(late.status_code,409,late.text)

    def test_A04_captured_outbound_payloads_for_all_four_background_purposes(self):
        from app.services import analysis_jobs
        from pathlib import Path
        import os
        self.register();self.configure_model();self.adopt();uid=self.user_id()
        uses=('judge','review','report','pricing')
        entries=[{'id':str(uuid4()),'text':'BACKGROUND_FOR_'+purpose.upper(),'uses':[purpose]} for purpose in uses]
        entries.append({'id':str(uuid4()),'text':'PRIVATE_VOLUNTARY_SENTINEL','uses':[]})
        self.write('/personal-information',{'entries':entries},0,'PUT')
        self.event('PRIVATE_ORIGINAL_SENTINEL');allowed=self.event('ALLOWED_ORIGINAL_SENTINEL','allowed')
        with self.Session() as db:
            profile=db.query(UserProfile).filter_by(user_id=uid).one();profile.long_term_memory=json.dumps({'preferences':['PRIVATE_DERIVED_SENTINEL']});profile.memory_sources=None;db.commit()
        captured={};active=['judge']
        def fake(messages,**kw):
            captured.setdefault(active[0],[]).append(messages)
            return {'facts':[],'questions':[],'summary':'合成模型输出','analysis':[],'coin_price':23,'pricing_reason':'本人真实背景参考','worth_note':'必要休息免费'}
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):
            queued=self.client.post(f"/api/events/{allowed['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1,'operation':'facts'})
            self.assertEqual(queued.status_code,202,queued.text);analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
            self.assertEqual(self.client.get('/api/analysis-jobs/'+str(queued.json()['id'])).json()['state'],'ready')
            active[0]='review';day=str(local_day(utc_now(),'Asia/Shanghai'))
            diary=self.write('/diaries/'+day,{'content':'ALLOWED_DIARY_SENTINEL','ai_permission':'allowed'},0,'PUT').json()['diary']
            session=self.write('/diaries/'+day+'/review-sessions',version=1).json()
            queued=self.write('/review-sessions/'+str(session['id'])+'/analyze',version=session['version']);self.assertEqual(queued.status_code,200,queued.text)
            analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
            active[0]='report';result=self.write('/report?period=week');self.assertEqual(result.status_code,200,result.text)
            active[0]='pricing';result=self.write('/reward-quotes',{'name':'同类心愿的个人价格'});self.assertEqual(result.status_code,200,result.text)
        for purpose in uses:
            payload=json.dumps(captured[purpose],ensure_ascii=False)
            self.assertIn('BACKGROUND_FOR_'+purpose.upper(),payload)
            for other in set(uses)-{purpose}:self.assertNotIn('BACKGROUND_FOR_'+other.upper(),payload)
            self.assertNotIn('PRIVATE_',payload)
        if os.environ.get('FULL_SYSTEM_EVIDENCE_DIR'):
            Path(os.environ['FULL_SYSTEM_EVIDENCE_DIR'],'captured-model-payloads.json').write_text(json.dumps(captured,ensure_ascii=False,indent=2),encoding='utf-8')

    def test_A27_tipline_suppressed_lines_roundtrip_and_backward_compat(self):
        """UI-IA F7：行级提示清单可写可读；不带字段的旧 PUT 不得清空。"""
        self.register()
        saved=self.write('/experience-preferences',{'suppressed':['plans-help'],'suppressed_lines':['journal.pure-flag','growth.ability-note'],'return_disabled':False},0,'PUT')
        self.assertEqual(saved.status_code,200,saved.text)
        got=self.client.get('/api/experience-preferences').json()
        self.assertEqual(got['suppressed_lines'],['journal.pure-flag','growth.ability-note'])
        # 旧客户端只发 suppressed → suppressed_lines 必须保持原值（核心防回归）
        again=self.write('/experience-preferences',{'suppressed':['growth-help'],'return_disabled':False},got['version'],'PUT')
        self.assertEqual(again.status_code,200,again.text)
        got2=self.client.get('/api/experience-preferences').json()
        self.assertEqual(got2['suppressed'],['growth-help'])
        self.assertEqual(got2['suppressed_lines'],['journal.pure-flag','growth.ability-note'])
        # 显式传 [] = 清空（偏好页「恢复一般提示」走这条）
        cleared=self.write('/experience-preferences',{'suppressed':[],'suppressed_lines':[],'return_disabled':False},got2['version'],'PUT')
        self.assertEqual(cleared.status_code,200,cleared.text)
        self.assertEqual(self.client.get('/api/experience-preferences').json()['suppressed_lines'],[])

    def test_A27b_tipline_rejects_bad_id_and_over_limit(self):
        """UI-IA F7：非法 id 与超 40 条均 422，不做静默截断。"""
        self.register()
        bad=self.write('/experience-preferences',{'suppressed':[],'suppressed_lines':['Bad_ID'],'return_disabled':False},0,'PUT')
        self.assertEqual(bad.status_code,422,bad.text)
        many=[f'page.item-{i}' for i in range(41)]
        over=self.write('/experience-preferences',{'suppressed':[],'suppressed_lines':many,'return_disabled':False},0,'PUT')
        self.assertEqual(over.status_code,422,over.text)
