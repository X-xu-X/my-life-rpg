"""R1-R4 review regressions; synthetic databases and captured supplier calls only."""
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
import tests.test_daily_use_redesign as daily
from app.models import ShopItem,Event,CoinLedger
from app.models.daily_use import PricingCheck
from app.services.time_service import utc_now,local_day


class DailyReviewFixTests(unittest.TestCase):
    setUp=daily.DailyUseTests.setUp
    tearDown=daily.DailyUseTests.tearDown
    register=daily.DailyUseTests.register
    configure_model=daily.DailyUseTests.configure_model
    adopt=daily.DailyUseTests.adopt
    write=daily.DailyUseTests.write
    user_id=daily.DailyUseTests.user_id
    facts=daily.DailyUseTests.facts
    suggestion=daily.DailyUseTests.suggestion
    preview=daily.DailyUseTests.preview
    settle=daily.DailyUseTests.settle

    def test_R1_strict_inputs_and_two_origins_edit_replay(self):
        self.register();today=str(local_day(utc_now(),'Asia/Shanghai'))
        for category in ('plan','care'):
            body={'name':category+' original','category':category,'frequency':'once','start':today,'position':17}
            created=self.write('/projects',body).json();item=created['project'];path=f"/projects/{created['origin']}/{item['id']}"
            self.assertEqual(self.write(path,{**body,'timezone':'Asia/Shanghai'},item['version'],'PUT').status_code,422)
            key=str(uuid4());changed=self.write(path,{**body,'name':category+' renamed','enabled':False,'effective_from':today},item['version'],'PUT',key=key)
            self.assertEqual(changed.status_code,200,changed.text)
            self.assertEqual(self.write(path,{**body,'name':category+' renamed','enabled':False,'effective_from':today},item['version'],'PUT',key=key).json(),changed.json())
            row=next(p for p in self.client.get('/api/projects').json()['items'] if p['key']==f"{created['origin']}:{item['id']}")
            self.assertEqual((row['name'],row['position'],row['enabled']),(category+' renamed',17,False))

    def test_R2_future_once_and_interval_anchor_are_distinct_from_effective_day(self):
        self.register();today=local_day(utc_now(),'Asia/Shanghai');future=today+timedelta(days=7)
        for category in ('plan','care'):
            once={'name':'future '+category,'category':category,'frequency':'once','start':str(future)}
            created=self.write('/projects',once).json();p=created['project'];origin=created['origin'];identity=f"{origin}:{p['id']}"
            edited=self.write(f"/projects/{origin}/{p['id']}",{**once,'name':'renamed '+category,'effective_from':str(future)},p['version'],'PUT')
            self.assertEqual(edited.status_code,200,edited.text)
            self.assertEqual(edited.json()['project']['rule']['start'],str(future))
            self.assertIsNone(next(row for row in self.client.get('/api/projects').json()['items'] if row['key']==identity)['effective'])
            anchored={'name':'interval '+category,'category':category,'frequency':'interval','interval':3,'start':str(today-timedelta(days=7))}
            created=self.write('/projects',anchored).json();p=created['project'];origin=created['origin'];identity=f"{origin}:{p['id']}"
            edited=self.write(f"/projects/{origin}/{p['id']}",{**anchored,'name':'interval renamed','effective_from':str(today)},p['version'],'PUT')
            self.assertEqual(edited.status_code,200,edited.text)
            for offset,expected in ((-1,True),(0,False),(1,False),(2,True)):
                selected=today+timedelta(days=offset)
                item=next(r for r in self.client.get('/api/projects?day='+str(selected)).json()['items'] if r['key']==identity)
                self.assertEqual(item['scheduled_due'],expected,(category,selected,item))
                self.assertEqual(item['effective']['name'],anchored['name'] if offset<0 else 'interval renamed')
                self.assertEqual(item['effective']['rule']['start'],anchored['start'])

    def test_R2_historical_daily_result_and_legacy_empty_snapshot_remain_unchanged(self):
        from app.models.workflow import PlanSchedule
        self.register();today=local_day(utc_now(),'Asia/Shanghai');start=str(today-timedelta(days=10))
        body={'name':'旧每日计划','category':'plan','frequency':'daily','start':start,'planned_minutes':25}
        item=self.write('/projects',body).json()['project'];uid=self.user_id();day=str(today-timedelta(days=1))
        recorded=self.write(f"/plan-schedules/{item['id']}/occurrences/{day}",{'schedule_version':item['version'],'outcome':'missed'},0,'PUT')
        self.assertEqual(recorded.status_code,200,recorded.text)
        with self.Session() as db:row=db.get(PlanSchedule,item['id']);row.history=[];db.commit()
        changed=self.write(f"/projects/plan/{item['id']}",{**body,'name':'明天新名称','effective_from':str(today+timedelta(days=1))},item['version'],'PUT')
        self.assertEqual(changed.status_code,200,changed.text)
        current=self.client.get('/api/projects').json()['items'][0];self.assertEqual(current['effective']['name'],'旧每日计划')
        old=self.client.get('/api/projects?day='+day).json()['items'][0]
        self.assertEqual(old['entry'],recorded.json());self.assertEqual(old['entry']['outcome'],'missed')
        timer=self.write('/timers',{'kind':'plan','source_id':item['id'],'source_version':2,'planned_minutes':25})
        self.assertEqual(timer.status_code,200,timer.text);self.assertEqual(timer.json()['contract']['plan_snapshot']['name'],'旧每日计划')
        with self.Session() as db:self.assertEqual(db.query(Event).filter_by(user_id=uid).count(),0)

    def seed_rewards(self,count):
        self.register();self.configure_model();uid=self.user_id()
        with self.Session() as db:
            items=[ShopItem(user_id=uid,name='reward '+str(n+1),coin_price=23,enabled=True,auto_pricing=True,pricing_mode='recurring') for n in range(count)]
            db.add_all(items);db.commit();return [i.id for i in items]

    def test_R3_six_items_bounded_batches_dedup_failed_no_automatic_retry(self):
        from app.services import pricing_checks
        ids=self.seed_rewards(6);key=str(uuid4())
        # v1.13 F12：当天全部排队（不再每次只排 3 件），仍受每日 10 件上限
        first=self.write('/pricing-checks',key=key);self.assertEqual(first.json()['queued'],6);self.assertFalse(first.json()['has_more'])
        self.assertEqual(self.write('/pricing-checks',key=key).json(),first.json())
        self.assertEqual(self.write('/pricing-checks').json()['queued'],0)
        with patch('app.services.llm_service.llm_service.chat_json',return_value={'coin_price':23,'pricing_reason':'合成本人价格','worth_note':''}) as supplier:
            for n in range(6):pricing_checks.process(self.Session,pricing_checks.claim(self.Session))
        self.assertEqual(supplier.call_count,6)
        with self.Session() as db:
            rows=db.query(PricingCheck).all();self.assertEqual({r.item_id for r in rows},set(ids));self.assertTrue(all(r.state=='completed' for r in rows))
            rows[0].state='failed';db.commit()
        self.assertEqual(self.write('/pricing-checks').json()['queued'],0)

    def test_R3_daily_limit_and_next_day_fairness_include_failed_attempts(self):
        ids=self.seed_rewards(13);today=local_day(utc_now(),'Asia/Shanghai')
        # 13 件 → 当天先排满 10 件，再请求就撞 daily_limit；次日补剩下的 3 件
        self.assertEqual([self.write('/pricing-checks').json()['queued'] for n in range(2)],[10,0])
        capped=self.write('/pricing-checks').json();self.assertEqual((capped['queued'],capped['reason']),(0,'daily_limit'))
        with self.Session() as db:
            first=db.query(PricingCheck).order_by(PricingCheck.id).first();first.state='failed';db.commit()
        with patch('app.services.trial_rules.day',return_value=str(today+timedelta(days=1))):
            next_batch=self.write('/pricing-checks').json();self.assertEqual(next_batch['queued'],10)
        with self.Session() as db:
            tomorrow=db.query(PricingCheck).filter_by(local_date=str(today+timedelta(days=1))).all()
            # 最久没评估的（从未评估过的那 3 件）排在最前
            self.assertEqual([r.item_id for r in tomorrow][:3],ids[10:])
            self.assertEqual(db.query(PricingCheck).filter_by(local_date=str(today)).count(),10)

    def test_R3_empty_first_then_new_permission_gets_a_fresh_finite_batch(self):
        self.seed_rewards(0);empty=self.write('/pricing-checks').json();self.assertEqual((empty['queued'],empty['has_more']),(0,False));uid=self.user_id()
        with self.Session() as db:db.add(ShopItem(user_id=uid,name='later authorized',coin_price=23,enabled=True,auto_pricing=True,pricing_mode='recurring'));db.commit()
        self.assertEqual(self.write('/pricing-checks').json()['queued'],1)

    def test_R4_home_preference_order_and_removed_archives_keep_settled_identity(self):
        self.register();self.configure_model();self.adopt();today=str(local_day(utc_now(),'Asia/Shanghai'))
        body={'name':'较后项目','category':'care','frequency':'daily','start':today,'position':40}
        later=self.write('/projects',body).json()['project'];self.write('/projects',{**body,'name':'较前项目','position':2})
        state=self.client.get('/api/projects').json();self.assertEqual([p['name'] for p in state['items']],['较前项目','较后项目'])
        response=self.write('/care/config',{'enabled':False,'ai_allowed':False},state['care_config']['version'],'PUT');self.assertEqual(response.status_code,200,response.text)
        state=self.client.get('/api/projects').json();self.assertTrue(all(not p['due'] and not p['show_today'] and p['scheduled_due'] for p in state['items']))
        self.write('/care/config',{'enabled':True,'ai_allowed':False},state['care_config']['version'],'PUT')
        saved=self.write(f"/care/items/{later['id']}/entries/{today}",{'item_version':later['version'],'state':'recorded','content':'实际照顾了植物十分钟','ai_permission':'allowed'},0,'PUT')
        self.assertEqual(saved.status_code,200,saved.text);event=self.client.get('/api/events/'+str(saved.json()['entry']['event_id'])).json()
        group=self.preview(self.facts(event,[self.suggestion(event['content'])]));self.assertEqual(self.settle(group).status_code,200)
        before=self.client.get('/api/coins').json()['balance'];uid=self.user_id()
        with self.Session() as db:ledger_count=db.query(CoinLedger).filter_by(user_id=uid).count()
        removed=self.write(f"/projects/care/{later['id']}",{**body,'removed':True,'effective_from':today},later['version'],'PUT');self.assertEqual(removed.status_code,200,removed.text)
        self.assertNotIn(later['id'],[p['id'] for p in self.client.get('/api/projects').json()['items']])
        archive=next(p for p in self.client.get('/api/projects?include_removed=true').json()['items'] if p['key']=='care:'+str(later['id']))
        self.assertEqual(archive['entry'],saved.json()['entry']);self.assertFalse(archive['show_today']);self.assertEqual(archive['position'],40)
        self.assertEqual(self.client.get('/api/coins').json()['balance'],before)
        with self.Session() as db:self.assertEqual(db.query(CoinLedger).filter_by(user_id=uid).count(),ledger_count)

    def test_R4_reclassification_both_origins_keeps_original_result_semantics(self):
        self.register();today=local_day(utc_now(),'Asia/Shanghai');old=str(today-timedelta(days=3))
        for category,state in (('care','skipped'),('plan','partial')):
            body={'name':category,'category':category,'frequency':'daily','start':old,'position':12}
            created=self.write('/projects',body).json();p=created['project'];origin=created['origin']
            path=f"/care/items/{p['id']}/entries/{today}" if origin=='care' else f"/plan-schedules/{p['id']}/occurrences/{today}"
            record={'item_version':1,'state':state} if origin=='care' else {'schedule_version':1,'outcome':state,'content':'实际学习十分钟'}
            saved=self.write(path,record,0,'PUT');self.assertEqual(saved.status_code,200,saved.text)
            changed=self.write(f"/projects/{origin}/{p['id']}",{**body,'category':'plan' if category=='care' else 'care','effective_from':str(today+timedelta(days=1))},p['version'],'PUT')
            self.assertEqual(changed.status_code,200,changed.text)
            item=next(r for r in self.client.get('/api/projects').json()['items'] if r['key']==f"{origin}:{p['id']}")
            self.assertEqual(item['result_category'],category);self.assertEqual(item['entry'],saved.json()['entry'] if origin=='care' else saved.json())
