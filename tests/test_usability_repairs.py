"""State, ownership and money regressions for October 24 usability repairs."""
import unittest
from uuid import uuid4
from copy import deepcopy
import tests.test_daily_use_redesign as daily
import tests.test_full_system as full
from app.models import ShopItem
from app.services.time_service import utc_now, local_day


class UsabilityRepairsTests(unittest.TestCase):
    setUp = daily.DailyUseTests.setUp
    tearDown = daily.DailyUseTests.tearDown
    register = daily.DailyUseTests.register
    configure_model = daily.DailyUseTests.configure_model
    adopt = daily.DailyUseTests.adopt
    write = daily.DailyUseTests.write
    user_id = daily.DailyUseTests.user_id
    event = daily.DailyUseTests.event
    facts = daily.DailyUseTests.facts
    suggestion = daily.DailyUseTests.suggestion
    preview = daily.DailyUseTests.preview
    settle = daily.DailyUseTests.settle
    reward = full.FullSystemTests.reward

    def test_confirmed_zero_and_nonzero_bundles_leave_pending_new_analysis_returns(self):
        self.register(); self.configure_model(); self.adopt()
        for changes, grade, coins in (([], 'none', 0), ([{'name':'体能','delta':1,'reason':'实际练习','evidence':'练习'}], 'small', 6)):
            event = self.event('实际练习'+grade, 'allowed')
            bundle = self.facts(event, [self.suggestion(event['content'], changes=changes, coins=coins)])
            self.assertIn(event['id'], [r['event_id'] for r in self.client.get('/api/pending').json()['items']])
            bundle = self.preview(bundle)
            self.assertEqual(self.settle(bundle).status_code, 200)
            self.assertNotIn(event['id'], [r['event_id'] for r in self.client.get('/api/pending').json()['items']])
            retry = self.write(f"/events/{event['id']}/analysis-jobs", {'event_version':event['content_version'], 'operation':'facts'})
            self.assertEqual(retry.status_code, 202, retry.text)
            self.assertIn(event['id'], [r['event_id'] for r in self.client.get('/api/pending').json()['items']])
            self.client.post('/api/analysis-jobs/'+str(retry.json()['id'])+'/cancel')

    def test_atomic_order_replay_conflict_and_preserved_schedule_history(self):
        self.register(); today = str(local_day(utc_now(), 'Asia/Shanghai'))
        for name, category in [('读书','plan'), ('午睡','care'), ('练习','plan')]:
            response=self.write('/projects', {'name':name,'category':category,'frequency':'daily','start':today,'note':'饭后慢慢做' if category=='care' else ''})
            self.assertEqual(response.status_code,200,response.text)
        before=self.client.get('/api/projects').json()['items']
        history={r['key']:deepcopy(r['history']) for r in before}
        reordered=list(reversed(before)); body={'items':[{'key':r['key'],'version':r['version']} for r in reordered]};key=str(uuid4())
        result=self.write('/projects/reorder',body,key=key)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.write('/projects/reorder',body,key=key).json(),result.json())
        self.assertEqual(self.write('/projects/reorder',body).status_code,409)
        after=self.client.get('/api/projects').json()['items']
        self.assertEqual([r['key'] for r in after],[r['key'] for r in reordered])
        self.assertEqual({r['key']:r['history'] for r in after},history)
        self.assertEqual(next(r for r in after if r['category']=='care')['rule']['note'],'饭后慢慢做')
        bad={'items':[{'key':'care:999999','version':1}]}
        self.assertEqual(self.write('/projects/reorder',bad).status_code,409)
        self.assertEqual([r['key'] for r in self.client.get('/api/projects').json()['items']],[r['key'] for r in after])

    def test_confirmed_display_uses_actual_weighted_changes_and_failure_has_safe_message(self):
        self.register(); self.configure_model(); self.adopt()
        event=self.event('有明确投入的练习', 'allowed')
        bundle=self.facts(event,[self.suggestion(event['content'],confidence=.9)])
        self.assertEqual(self.settle(self.preview(bundle)).status_code,200)
        result=self.client.get(f"/api/events/{event['id']}/fact-bundles").json()['items'][0]
        self.assertEqual(result['applied_changes'][0]['changes'][0]['delta'],.9)
        before=self.client.get('/api/coins').json()['balance']
        self.client.get(f"/api/events/{event['id']}/fact-bundles")
        self.assertEqual(self.client.get('/api/coins').json()['balance'],before)
        from app.models.analysis import AnalysisJob
        from app.services.analysis_jobs import output
        job=AnalysisJob(safe_error_code='MODEL_TIMEOUT')
        self.assertIn('超时',output(job)['safe_error_message'])
        job.safe_error_code='SECRET_SUPPLIER_PAYLOAD'
        self.assertNotIn('SECRET_SUPPLIER_PAYLOAD',output(job)['safe_error_message'])

    def test_reward_archive_preserves_purchase_and_balance_replays_once(self):
        self.register(); self.configure_model(); self.adopt(); item=self.reward()
        with self.Session() as db:
            row=db.get(ShopItem,item['id']); row.auto_pricing=True; db.commit()
        item=next(i for i in self.client.get('/api/shop/items').json()['items'] if i['id']==item['id'])
        purchased=self.write(f"/shop/items/{item['id']}/redeem",{'expected_version':item['updated_at']})
        self.assertEqual(purchased.status_code,200,purchased.text)
        balance=self.client.get('/api/coins').json()['balance'];vouchers=self.client.get('/api/redemptions').json()
        key=str(uuid4());body={'expected_version':item['updated_at']}
        archived=self.write(f"/shop/items/{item['id']}",body,method='DELETE',key=key)
        self.assertEqual(archived.status_code,200,archived.text)
        self.assertEqual(self.write(f"/shop/items/{item['id']}",body,method='DELETE',key=key).json(),archived.json())
        saved=next(i for i in self.client.get('/api/shop/items').json()['items'] if i['id']==item['id'])
        self.assertFalse(saved['enabled']); self.assertFalse(saved['auto_pricing'])
        self.assertEqual(self.client.get('/api/coins').json()['balance'],balance)
        self.assertEqual(self.client.get('/api/redemptions').json(),vouchers)


if __name__ == '__main__': unittest.main()
