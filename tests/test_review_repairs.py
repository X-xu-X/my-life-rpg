"""N01-N05 regressions: synthetic accounts, actual endpoints and captured payloads."""
import json
import unittest
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
import tests.test_full_system as full
from app.models import Event,User
from app.services.time_service import utc_now,local_day


class ReviewRepairTests(unittest.TestCase):
    setUp=full.FullSystemTests.setUp
    tearDown=full.FullSystemTests.tearDown
    register=full.FullSystemTests.register
    configure_model=full.FullSystemTests.configure_model
    write=full.FullSystemTests.write
    event=full.FullSystemTests.event
    adopt=full.FullSystemTests.adopt
    facts=full.FullSystemTests.facts
    suggestion=full.FullSystemTests.suggestion
    preview=full.FullSystemTests.preview
    settle=full.FullSystemTests.settle
    user_id=full.FullSystemTests.user_id
    reward=full.FullSystemTests.reward

    def test_N01_legacy_names_never_bypass_permission_in_review_or_fact_analysis(self):
        from app.services import analysis_jobs
        self.register();self.configure_model();day=str(local_day(utc_now(),'Asia/Shanghai'))
        diary=self.write('/diaries/'+day,{'content':'只分析本次文字','ai_permission':'allowed'},0,'PUT').json()['diary']
        session=self.write('/diaries/'+day+'/review-sessions',version=1).json();legacy_version=0
        for config_state in ('absent','off','allowed'):
            if config_state!='absent':
                state=self.client.get('/api/care').json()
                self.write('/care/config',{'enabled':True,'ai_allowed':config_state=='allowed'},state['config']['version'] if state['config'] else 0,'PUT')
            for enabled in (False,True):
                with self.subTest(config=config_state,legacy_enabled=enabled):
                    result=self.write('/life-checklists/'+day,{'enabled':enabled,'entries':{'PRIVATE_FOCUS_SENTINEL':'skipped'}},legacy_version,'PUT')
                    self.assertEqual(result.status_code,200,result.text);legacy_version+=1
                    for operation in ('review','facts'):
                        sent=[]
                        if operation=='review':
                            state=self.client.get('/api/review-sessions/'+str(session['id'])).json()
                            queued=self.write('/review-sessions/'+str(session['id'])+'/analyze',version=state['version'])
                        else:queued=self.client.post(f"/api/events/{diary['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1,'operation':'facts'})
                        self.assertIn(queued.status_code,(200,202),queued.text)
                        def fake(messages,**kw):
                            sent.append(messages);return {'facts':[],'questions':[],'summary':'普通回顾','analysis':[]}
                        with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
                        self.assertEqual(len(sent),1);self.assertNotIn('PRIVATE_FOCUS_SENTINEL',json.dumps(sent))
                        data=json.loads(sent[0][-1]['content']);context=data if operation=='review' else data['context']
                        self.assertEqual(context['checklist']['counts']['skipped'],1)
                        self.assertEqual(context['checklist']['enabled'],enabled)
        # Ownership/export retains the exact old JSON; permission filtering is not deletion.
        self.assertIn('PRIVATE_FOCUS_SENTINEL',self.client.get('/api/export').text)

    def test_N02_no_history_applies_to_entire_export_and_all_attachments(self):
        from app.models.workflow import ReviewSession,ReviewTurn,ReviewAnalysis,FactIdentity
        from app.models.full_system import FactBundle,FactFragment,FactNote
        from app.models.access import EventDerivation
        from app.models import AIJudgment
        self.register();day=str(local_day(utc_now(),'Asia/Shanghai'))
        diary=self.write('/diaries/'+day,{'content':'OLD_DIARY_HISTORY_SENTINEL'},0,'PUT').json()['diary'];uid=self.user_id()
        with self.Session() as db:
            session=ReviewSession(user_id=uid,diary_id=diary['id'],source_version=1,sources=[{'id':diary['id'],'version':1,'content':'OLD_DIARY_HISTORY_SENTINEL'}]);db.add(session);db.flush()
            db.add(ReviewTurn(user_id=uid,session_id=session.id,ordinal=1,question='OLD_QUESTION_SENTINEL',answer='OLD_ANSWER_SENTINEL',state='answered'))
            db.add(ReviewAnalysis(user_id=uid,session_id=session.id,session_version=1,payload={'summary':'OLD_ANALYSIS_SENTINEL','sources_snapshot':{'sources':session.sources}},provenance={}))
            db.add(EventDerivation(user_id=uid,event_id=diary['id'],event_version=1,kind='original_version',payload={'content':'OLD_DIARY_HISTORY_SENTINEL'},provenance={}))
            db.add(AIJudgment(user_id=uid,event_id=diary['id'],summary='OLD_JUDGMENT_SENTINEL',source_snapshot=[{'id':diary['id'],'version':1}]))
            db.add(FactNote(user_id=uid,event_id=diary['id'],event_version=1,permission_version=1,content='OLD_NOTE_SENTINEL'))
            identity=FactIdentity(user_id=uid,identity_key='synthetic-old-fragment');db.add(identity);db.flush()
            db.add(FactFragment(user_id=uid,event_id=diary['id'],event_version=1,fact_id=identity.id,fingerprint='a'*64,excerpt='OLD_FRAGMENT_SENTINEL'))
            db.add(FactBundle(user_id=uid,event_id=diary['id'],event_version=1,permission_version=1,payload={'items':[],'summary':'OLD_BUNDLE_SENTINEL'},sources=[],provenance={}))
            db.commit()
        diary=self.write('/diaries/'+day,{'content':'CURRENT_DIARY'},1,'PUT').json()['diary']
        with self.Session() as db:
            session=ReviewSession(user_id=uid,diary_id=diary['id'],source_version=2,sources=[{'id':diary['id'],'version':2,'content':'CURRENT_DIARY'}]);db.add(session);db.flush()
            for summary in ('OLD_ROUND_SENTINEL','CURRENT_REVIEW'):
                db.add(ReviewAnalysis(user_id=uid,session_id=session.id,session_version=1,payload={'summary':summary},provenance={}))
            db.commit()
        for game in ('true','false'):
            for format in ('json','markdown','html','csv'):
                if game=='true' and format=='csv':continue
                with self.subTest(game=game,format=format):
                    response=self.client.get(f'/api/export?format={format}&kind=diary&include_history=false&include_game={game}')
                    self.assertEqual(response.status_code,200,response.text[:100]);self.assertNotIn('OLD_',response.text)
                    self.assertIn('CURRENT_DIARY',response.text);self.assertIn('CURRENT_REVIEW',response.text)
                    if format=='json':
                        result=response.json();self.assertEqual(result['tables']['diary_revisions'],[])
                        self.assertEqual(len(result['tables']['review_sessions']),1);self.assertEqual(len(result['tables']['review_analyses']),1)
        for format in ('json','markdown','html','csv'):
            response=self.client.get(f'/api/export?format={format}&kind=diary&include_history=true&include_game=false')
            self.assertEqual(response.status_code,200);self.assertIn('OLD_DIARY_HISTORY_SENTINEL',response.text)

    def test_N03_plan_minutes_versions_future_schedule_and_session_snapshot(self):
        self.register();self.adopt();now=utc_now();today=local_day(now,'Asia/Shanghai')
        def schedule(minutes):
            response=self.write('/plan-schedules',{'name':f'学习{minutes}分钟','frequency':'daily','start':str(today),'planned_minutes':minutes})
            self.assertEqual(response.status_code,200,response.text);return response.json()
        plan=schedule(20);other=schedule(45)
        for row,minutes in ((plan,20),(other,45)):
            self.assertEqual(row['rule']['planned_minutes'],minutes);self.assertEqual(row['history'][0]['rule']['planned_minutes'],minutes)
        self.assertEqual(self.write('/timers',{'kind':'plan','source_id':plan['id']}).status_code,422)
        self.assertEqual(self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':999}).status_code,409)
        first=self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':1,'planned_minutes':20}).json()
        self.assertEqual(first['limit_seconds'],1200)
        updated=self.write('/plan-schedules/'+str(plan['id']),{'name':'未来45分钟','frequency':'daily','start':str(today+timedelta(days=1)),'planned_minutes':45},1,'PUT').json()
        self.assertEqual(updated['version'],2)
        active=self.client.get('/api/timers').json()['active'];self.assertEqual(active['limit_seconds'],1200);self.assertEqual(active['contract']['plan_snapshot']['source_version'],1)
        preview=self.write(f"/timers/{first['id']}/end-preview",{'actual_seconds':0},first['version']).json()
        self.assertEqual(self.write(f"/timers/{first['id']}/confirm",version=preview['version']).status_code,200)
        current=next(r for r in self.client.get('/api/plan-schedules').json() if r['id']==plan['id'])
        self.assertEqual(current['timing']['planned_minutes'],20)
        self.assertEqual(self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':2,'planned_minutes':45}).status_code,409)
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(days=1)):
            second=self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':2,'planned_minutes':45})
        self.assertEqual(second.status_code,200,second.text);self.assertEqual(second.json()['limit_seconds'],2700)
        self.assertEqual(self.client.get('/api/timers').json()['active']['limit_seconds'],2700)
        self.client.post('/api/auth/logout')
        with self.Session() as db:
            from app.services.auth_service import issue_invitation
            self.invite=issue_invitation(db,db.get(User,self.owner_id));db.commit()
        self.register('third')
        self.assertEqual(self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':2}).status_code,404)

    def test_N03_legacy_default_duration_validation_and_old_receipt_replay(self):
        from app.models.workflow import PlanSchedule
        from app.models.access import RequestReceipt
        from app.routers.timers import StartIn
        import hashlib
        self.register();self.adopt();today=str(local_day(utc_now(),'Asia/Shanghai'))
        body={'name':'旧默认日程','frequency':'daily','start':today}
        for value in (0,1441,True,1.5):
            self.assertEqual(self.write('/plan-schedules',{**body,'planned_minutes':value}).status_code,422)
        plan=self.write('/plan-schedules',body).json()
        with self.Session() as db:
            row=db.get(PlanSchedule,plan['id']);row.rule={k:v for k,v in row.rule.items() if k!='planned_minutes'};row.history=[];db.commit()
        listed=self.client.get('/api/plan-schedules').json()[0];self.assertEqual(listed['timing']['planned_minutes'],30)
        response=self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':1})
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['limit_seconds'],1800)
        # A lost accepted pre-upgrade request still returns its original receipt.
        key=str(uuid4());payload=StartIn(request_key=key,expected_version=0,kind='plan',source_id=plan['id']).model_dump(mode='json');payload.pop('source_version')
        fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        with self.Session() as db:
            db.add(RequestReceipt(user_id=self.user_id(),operation='timer-start',request_key=key,payload_hash=fingerprint,resource_id=987,response_snapshot={'id':987,'limit_seconds':1800}));db.commit()
        replay=self.write('/timers',{'kind':'plan','source_id':plan['id']},key=key)
        self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json()['id'],987)

    def test_R01_legacy_empty_history_future_edit_preserves_today_and_receipt(self):
        from app.models.workflow import PlanSchedule
        self.register();self.adopt();now=utc_now();today=local_day(now,'Asia/Shanghai')
        goal=self.client.post('/api/goals',json={'description':'旧学习目标','metric':'十次'}).json()
        body={'name':'旧阅读计划','frequency':'daily','start':str(today-timedelta(days=7)),'goal_id':goal['id']}
        plan=self.write('/plan-schedules',body).json()
        with self.Session() as db:
            row=db.get(PlanSchedule,plan['id']);row.rule={k:v for k,v in row.rule.items() if k!='planned_minutes'}
            row.history=[];row.version=7;old_rule=dict(row.rule);db.commit()
        listed=next(r for r in self.client.get('/api/plan-schedules').json() if r['id']==plan['id'])
        self.assertEqual(listed['timing']['planned_minutes'],30)
        first=self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':7}).json()
        self.assertEqual(first['limit_seconds'],1800)
        key=str(uuid4());future={**body,'name':'明天阅读45分钟','start':str(today+timedelta(days=1)),'planned_minutes':45,'goal_id':None}
        response=self.write('/plan-schedules/'+str(plan['id']),future,7,'PUT',key)
        self.assertEqual(response.status_code,200,response.text);updated=response.json()
        replay=self.write('/plan-schedules/'+str(plan['id']),future,7,'PUT',key)
        self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json(),updated)
        listed=next(r for r in self.client.get('/api/plan-schedules').json() if r['id']==plan['id'])
        self.assertIsNotNone(listed['timing'],'future edit must preserve the legacy plan effective today')
        self.assertEqual(listed['timing'],{'name':'旧阅读计划','planned_minutes':30,'version':7,'enabled':True})
        self.assertEqual(listed['version'],8);self.assertEqual(len(listed['history']),2)
        old,new=listed['history'];self.assertEqual(old['rule'],old_rule);self.assertEqual(old['version'],7)
        self.assertEqual(old['name'],'旧阅读计划');self.assertTrue(old['enabled']);self.assertEqual(old['goal']['id'],goal['id'])
        self.assertIsNone(new['goal']);self.assertEqual(new['rule']['planned_minutes'],45)
        occurrences=self.client.get('/api/plan-occurrences?day='+str(today)).json()['items']
        self.assertEqual(next(r for r in occurrences if r['schedule']['id']==plan['id'])['schedule_snapshot']['rule'],old_rule)
        active=self.client.get('/api/timers').json()['active']
        self.assertEqual(active['limit_seconds'],1800);self.assertEqual(active['contract']['plan_snapshot'],first['contract']['plan_snapshot'])
        def end(timer):
            preview=self.write(f"/timers/{timer['id']}/end-preview",{'actual_seconds':0},timer['version']).json()
            result=self.write(f"/timers/{timer['id']}/confirm",version=preview['version'])
            self.assertEqual(result.status_code,200,result.text)
        end(active)
        self.assertEqual(self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':7}).status_code,409)
        current=self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':8,'planned_minutes':30})
        self.assertEqual(current.status_code,200,current.text);self.assertEqual(current.json()['limit_seconds'],1800)
        self.assertEqual(current.json()['contract']['plan_snapshot']['effective_version'],7);end(current.json())
        with patch('app.routers.plans.utc_now',return_value=now+timedelta(days=1)),patch('app.routers.timers.utc_now',return_value=now+timedelta(days=1)):
            tomorrow=next(r for r in self.client.get('/api/plan-schedules').json() if r['id']==plan['id'])
            self.assertEqual(tomorrow['timing']['planned_minutes'],45)
            started=self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':8,'planned_minutes':45})
        self.assertEqual(started.status_code,200,started.text);self.assertEqual(started.json()['limit_seconds'],2700)
        self.assertEqual(self.client.get('/api/timers').json()['active']['limit_seconds'],2700)
        with self.Session() as db:self.assertEqual(len(db.get(PlanSchedule,plan['id']).history),2)

    def test_R01_legacy_disabled_and_explicit_duration_are_preserved(self):
        from app.models.workflow import PlanSchedule
        self.register();self.adopt();today=local_day(utc_now(),'Asia/Shanghai')
        body={'name':'旧停用20分钟','frequency':'daily','start':str(today-timedelta(days=1)),'planned_minutes':20,'enabled':False}
        plan=self.write('/plan-schedules',body).json()
        with self.Session() as db:row=db.get(PlanSchedule,plan['id']);row.history=[];db.commit()
        response=self.write('/plan-schedules/'+str(plan['id']),{**body,'name':'明天启用45分钟','start':str(today+timedelta(days=1)),'planned_minutes':45,'enabled':True},1,'PUT')
        self.assertEqual(response.status_code,200,response.text)
        listed=next(r for r in self.client.get('/api/plan-schedules').json() if r['id']==plan['id'])
        self.assertIsNotNone(listed['timing']);self.assertFalse(listed['timing']['enabled'])
        self.assertEqual(listed['timing']['planned_minutes'],20)
        self.assertEqual(self.write('/timers',{'kind':'plan','source_id':plan['id'],'source_version':2}).status_code,409)
        self.assertEqual(self.client.get('/api/plan-occurrences?day='+str(today)).json()['items'],[])
        self.assertEqual([r['version'] for r in listed['history']],[1,2])

    def test_N04_unbuilt_awards_return_409_and_preserve_eligibility_until_baseline(self):
        from app.models.full_system import Holiday,DailyEntitlement,HolidayClaim,TimeSession
        self.register();self.configure_model();day=str(local_day(utc_now(),'Asia/Shanghai'))
        self.write('/trial',{'acknowledge':True,'base_minutes':30,'region':'fixture'},0,'PUT');self.event('先记后建档')
        state=self.client.get('/api/trial').json();self.assertTrue(state['baseline_required']);daily=state['daily'];key=str(uuid4())
        for _ in range(2):self.assertEqual(self.write('/trial/first-record/claim',version=daily['version'],key=key).status_code,409)
        candidate=self.write('/dynamic-candidates',{'name':'已核实首日','metric':'event_saved_days','shape':'total_days','target':1}).json()
        self.assertEqual(self.write(f"/dynamic-candidates/{candidate['id']}/decision",{'action':'claim'},candidate['version']).status_code,409)
        with self.Session() as db:db.add(Holiday(local_date=day,region='fixture',name='合成节日'));db.commit()
        self.assertEqual(self.write('/holidays/claim').status_code,409)
        action=self.event('尚未建档时只提出建议','allowed');group=self.facts(action,[self.suggestion(action['content'])]);group=self.preview(group)
        self.assertEqual(self.settle(group).status_code,409)
        with self.Session() as db:
            from app.models.workflow import FactSettlement
            from app.models import AttributeHistory
            self.assertEqual(db.query(FactSettlement).count(),0);self.assertEqual(db.query(AttributeHistory).count(),0)
        now=utc_now();timer=self.write('/timers',{'kind':'base','source_id':daily['id']}).json()
        with patch('app.routers.timers.utc_now',return_value=now+timedelta(minutes=6)),patch('app.services.timers.utc_now',return_value=now+timedelta(minutes=6)):
            preview=self.write(f"/timers/{timer['id']}/end-preview",version=1).json()
            self.assertEqual(self.write(f"/timers/{timer['id']}/confirm",version=preview['version']).status_code,409)
        with self.Session() as db:
            row=db.get(DailyEntitlement,daily['id']);self.assertFalse(row.claimed);self.assertEqual(row.version,1);self.assertEqual(row.used_seconds,0)
            self.assertEqual(db.query(HolidayClaim).count(),0);self.assertEqual(db.get(TimeSession,timer['id']).state,'review')
        self.assertEqual(self.client.get('/api/coins').json()['balance'],0)
        self.assertEqual(self.client.post('/api/onboarding/neutral',json={'acknowledge':True}).status_code,200)
        response=self.write('/trial/first-record/claim',version=1,key=key);self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['balance'],83)
        self.assertEqual(self.write('/trial/first-record/claim',version=1,key=key).json(),response.json())
        self.assertEqual(self.write('/trial/first-record/claim',version=2).status_code,409)
        self.assertFalse(self.client.get('/api/trial').json()['baseline_required'])

    def test_N05_pricing_payload_uses_latest_confirmed_entertainment_not_plan_or_purchases(self):
        from app.models.full_system import TimeSession
        from app.services import trial_rules
        self.register();self.configure_model();self.adopt();item=self.reward();now=utc_now();uid=self.user_id()
        for _ in range(2):self.client.post(f"/api/shop/items/{item['id']}/redeem",json={'request_key':str(uuid4()),'expected_version':item['updated_at']})
        def row(kind,day,seconds):
            return TimeSession(user_id=uid,kind=kind,source_id=1,state='ended',started_at=now,last_sync_at=now,timezone='Asia/Shanghai',local_date=day,limit_seconds=1800,contract={'mode':'gentle'},intervals=[],settlement={'day':day,'actual_seconds':seconds,'penalty_charged':0,'ontime_awarded':0,'consumed_seconds':0},history=[])
        sent=[]
        def price():
            def fake(messages,**kw):sent.append(messages);return {'coin_price':20,'pricing_reason':'合成依据','worth_note':''}
            with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):response=self.write('/reward-quotes',{'name':'额外娱乐','reward_kind':'entertainment','minutes':30})
            self.assertEqual(response.status_code,200,response.text)
            messages=sent[-1];label='【近30天购买与实际娱乐用量】\n'
            text=next(m['content'] for m in messages if label in m['content']).split(label)[1].split('\n【')[0]
            return json.loads(text)
        before=price();self.assertEqual(before['purchases']['vouchers'],2);self.assertEqual(before['entertainment']['actual_seconds'],0)
        today=local_day(now,'Asia/Shanghai')
        with self.Session() as db:
            usage=row('voucher',str(today),3600);db.add(usage);db.commit();usage_id=usage.id
        first=price();self.assertEqual(first['entertainment']['actual_seconds'],3600)
        with self.Session() as db:
            usage=db.get(TimeSession,usage_id);usage.settlement={**usage.settlement,'actual_seconds':10800};usage.version+=1;db.commit()
        second=price();self.assertEqual(second['entertainment']['actual_seconds'],10800);self.assertNotEqual(sent[-1],sent[-2])
        with self.Session() as db:
            db.add(row('plan',str(today),999999));db.add(row('voucher',str(today-timedelta(days=40)),999999));db.commit()
        same=price();self.assertEqual(same,second);self.assertEqual(sent[-1],sent[-2])
        with self.Session() as db:
            usage=db.get(TimeSession,usage_id);usage.settlement={**usage.settlement,'actual_seconds':600};usage.version+=1
            db.add(row('base',str(today-timedelta(days=8)),10800));db.commit()
        fallen=price();self.assertEqual(fallen['entertainment']['recent_7_days']['actual_seconds'],600)
        self.assertEqual(fallen['entertainment']['previous_7_days']['actual_seconds'],10800)
        self.assertEqual(len(fallen['entertainment']['daily']),2)
        self.assertNotIn('若他近期已多次兑换同类物品，应当提高价格',sent[-1][0]['content'])

