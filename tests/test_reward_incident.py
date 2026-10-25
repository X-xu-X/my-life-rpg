"""Regress the observed missing-config + invented-attribute cloud incident."""
import copy
import json
import unittest
from unittest.mock import patch
from uuid import uuid4
from app.models import User, Attribute, AttributeHistory, CoinLedger, AIJudgment, Event
from app.models.full_system import TrialAccount, ActionAward, FactBundle, FactFragment
from app.models.workflow import FactSettlement
from app.models.access import RequestReceipt
from app.services import analysis_jobs, fact_analysis, trial_rules
from app.services.llm_service import LLMError
from ops import repair_confirmed_rewards as repair
from tests import test_full_system as fixture


class RewardIncidentTests(unittest.TestCase):
    setUp = fixture.FullSystemTests.setUp
    tearDown = fixture.FullSystemTests.tearDown
    register = fixture.FullSystemTests.register
    configure_model = fixture.FullSystemTests.configure_model
    write = fixture.FullSystemTests.write
    event = fixture.FullSystemTests.event
    facts = fixture.FullSystemTests.facts
    suggestion = fixture.FullSystemTests.suggestion
    preview = fixture.FullSystemTests.preview
    settle = fixture.FullSystemTests.settle

    def ready(self):
        self.register(); self.configure_model()
        self.client.post('/api/onboarding/neutral', json={'acknowledge': True})

    def test_without_trial_account_event_diary_and_same_plan_fact_earn_once(self):
        self.ready()
        with self.Session() as db:
            self.assertEqual(db.query(TrialAccount).count(), 0)
        event = self.event('完成英语计划的阅读练习', 'allowed')
        group = self.preview(self.facts(event, [self.suggestion(event['content'])]))
        self.assertEqual(group['preview']['total'], 6)
        self.assertEqual(self.settle(group).status_code, 200)
        from app.services.time_service import utc_now, local_day
        day = str(local_day(utc_now(), 'Asia/Shanghai'))
        diary = self.write('/diaries/' + day, {'content': event['content'] + '。练习画画', 'ai_permission': 'allowed'}, 0, 'PUT').json()['diary']
        group = self.facts(diary, [self.suggestion(event['content'], relation='same', related_event_id=event['id']), self.suggestion('练习画画')])
        item = group['payload']['items'][0]
        group = self.write(f"/fact-bundles/{group['id']}/decision", {'fragment_id': item['fragment_id'], 'decision': 'same'}, group['version']).json()
        group = self.preview(group)
        self.assertEqual(group['preview']['total'], 6)
        self.assertEqual(self.settle(group).status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.query(ActionAward).count(), 2)
            self.assertEqual(db.query(AttributeHistory).count(), 2)
            self.assertEqual(sum(r.delta for r in db.query(CoinLedger).filter_by(source='trial_action')), 12)

    def test_prompt_supplies_registered_names_and_invalid_name_fails_without_partial_booking(self):
        self.ready(); event = self.event('完成了一份问卷', 'allowed'); sent = []
        def fake(messages, **kwargs):
            sent.append(messages)
            return {'facts': [self.suggestion(event['content'], changes=[{'name': '任务产出', 'delta': 1}])]}
        job = self.client.post(f"/api/events/{event['id']}/analysis-jobs", json={'request_key': str(uuid4()), 'event_version': 1, 'operation': 'facts'}).json()
        with patch('app.services.llm_service.llm_service.chat_json', side_effect=fake):
            analysis_jobs.process(self.Session, analysis_jobs.claim(self.Session))
        result = self.client.get('/api/analysis-jobs/' + str(job['id'])).json()
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['safe_error_code'], 'MODEL_ATTRIBUTE_INVALID')
        names = {a['name'] for a in json.loads(sent[0][-1]['content'])['allowed_attributes']}
        self.assertIn('创造力', names); self.assertNotIn('任务产出', names)
        with self.Session() as db:
            for model in (FactBundle, FactFragment, FactSettlement, ActionAward, AttributeHistory):
                self.assertEqual(db.query(model).count(), 0)

    def test_normalizer_rejects_bad_points_and_accepts_registered_alias(self):
        self.ready()
        with self.Session() as db:
            user = db.query(User).filter_by(username='friend').one()
            for delta in (True, float('nan'), 6, '1'):
                with self.assertRaises(LLMError): fact_analysis.normalized_changes(db, user, [{'name': '智力', 'delta': delta}])
            self.assertEqual(fact_analysis.normalized_changes(db, user, [{'name': '智力', 'delta': .4}])[0]['delta'], .4)

    def test_historical_invalid_preview_has_clear_error_instead_of_silent_zero(self):
        self.ready(); event = self.event('完成问卷', 'allowed')
        with patch.object(fact_analysis, 'normalized_changes', side_effect=lambda db, user, raw: raw):
            group = self.facts(event, [self.suggestion('完成问卷', changes=[{'name': '任务产出', 'delta': 1}])])
        response = self.write(f"/fact-bundles/{group['id']}/preview", version=group['version'])
        self.assertEqual(response.status_code, 422)
        self.assertIn('未登记的属性名', response.json()['detail'])
        with self.Session() as db:
            self.assertEqual(db.query(FactSettlement).count(), 0)
            self.assertEqual(db.get(FactBundle, group['id']).state, 'draft')

    def test_optional_entertainment_disabled_does_not_disable_core_action_and_confidence_gate_remains(self):
        self.ready()
        config = self.write('/trial', {'acknowledge': True, 'base_minutes': 30}, 0, 'PUT').json()
        with self.Session() as db:
            db.query(TrialAccount).one().enabled = False; db.commit()
        event = self.event('做完练习。模糊的事情', 'allowed')
        group = self.preview(self.facts(event, [self.suggestion('做完练习'), self.suggestion('模糊的事情', confidence=.79)]))
        self.assertEqual(group['preview']['total'], 6)
        self.assertFalse(group['preview']['items'][1]['eligible'])
        self.assertEqual(self.settle(group).status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.query(FactSettlement).count(), 1)
            self.assertEqual(db.query(AttributeHistory).count(), 1)

    def broken_bundle(self):
        self.ready()
        record = self.event('完成问卷。构思方案。勇敢发布。搜集样品。心情记录。明天打算。', 'allowed')
        items = [self.suggestion(t, confidence=.95, changes=[{'name': '任务产出', 'delta': 1, 'reason': '旧错误', 'evidence': t}])
                 for t in ('完成问卷', '构思方案', '勇敢发布', '搜集样品')]
        items += [self.suggestion(t, grade='none', changes=[]) for t in ('心情记录', '明天打算')]
        zero = {k: 0 for k in ('base', 'mainline', 'holiday', 'before_cap', 'amount', 'cap_reduction')}
        with patch.object(fact_analysis, 'normalized_changes', side_effect=lambda db, user, raw: raw), patch.object(trial_rules, 'split', return_value=zero):
            bundle = self.preview(self.facts(record, items))
            self.assertEqual(self.settle(bundle).status_code, 200)
        self.assertEqual(bundle['preview']['total'], 0)
        return record['id'], bundle['id']

    def make_plan(self, db, event_id, bundle_id):
        def model(messages, **kwargs):
            data = json.loads(messages[-1]['content'])
            return {'facts': [{'fact_id': f['fact_id'], 'changes': [{'name': '智力', 'delta': .4,
                        'reason': '按实际小成果评估', 'evidence': f['excerpt']}]} for f in data['facts']]}
        return repair.assess(db, 'friend', bundle_id, event_id, 24, call=model)

    def test_repair_preserves_original_identity_preview_and_is_exactly_once(self):
        event_id, bundle_id = self.broken_bundle()
        with self.Session() as db:
            before_preview = copy.deepcopy(db.get(FactBundle, bundle_id).preview)
            settlements = [(r.id, r.fact_id, r.judgment_id) for r in db.query(FactSettlement)]
            plan = self.make_plan(db, event_id, bundle_id)
            self.assertEqual(db.query(AttributeHistory).count(), 0)
            uid = plan['user_id']; before = db.query(Attribute).filter_by(user_id=uid, name='智力').one().current_value
            result = repair.apply(db, plan, repair.digest(plan))
            self.assertEqual(result['coins_added'], 24)
            self.assertEqual(db.get(FactBundle, bundle_id).preview, before_preview)
            self.assertEqual([(r.id, r.fact_id, r.judgment_id) for r in db.query(FactSettlement)], settlements)
            self.assertEqual(db.query(ActionAward).count(), 6)
            self.assertEqual(sum(a.amount for a in db.query(ActionAward)), 24)
            self.assertEqual(db.query(AttributeHistory).count(), 4)
            self.assertAlmostEqual(db.query(Attribute).filter_by(user_id=uid, name='智力').one().current_value - before, 1.52)
            replay = repair.apply(db, json.loads(json.dumps(plan)), repair.digest(plan))
            self.assertTrue(replay['replayed'])
            self.assertEqual(db.query(CoinLedger).filter_by(ref_type='reward_repair').count(), 4)
            self.assertEqual(db.query(AttributeHistory).count(), 4)
            self.assertEqual(db.query(RequestReceipt).filter_by(operation=repair.OPERATION).count(), 1)
        groups = self.client.get(f'/api/events/{event_id}/fact-bundles').json()['items']
        repaired = next(g for g in groups if g['id'] == bundle_id)
        self.assertEqual(repaired['preview']['total'], 0)
        self.assertEqual(repaired['applied_total'], 24)
        self.assertEqual(sum(i['coins'] for i in repaired['applied_changes']), 24)
        self.assertEqual(sum(len(i['changes']) for i in repaired['applied_changes']), 4)

    def test_repair_rejects_stale_plan_and_rolls_back_partial_failure(self):
        event_id, bundle_id = self.broken_bundle()
        with self.Session() as db:
            plan = self.make_plan(db, event_id, bundle_id)
            real_grant = repair.coin_service.grant
            count = 0
            def fail(*args, **kwargs):
                nonlocal count
                count += 1
                if count == 2: raise RuntimeError('synthetic failure')
                return real_grant(*args, **kwargs)
            with patch.object(repair.coin_service, 'grant', side_effect=fail), self.assertRaises(RuntimeError):
                repair.apply(db, plan, repair.digest(plan))
            db.rollback()
            self.assertEqual(db.query(AttributeHistory).count(), 0)
            self.assertEqual(sum(a.amount for a in db.query(ActionAward)), 0)
            self.assertEqual(db.query(CoinLedger).filter_by(ref_type='reward_repair').count(), 0)
            db.get(Event, event_id).content_version += 1; db.commit()
            with self.assertRaises(ValueError): repair.apply(db, plan, repair.digest(plan))
            db.rollback()

    def test_repair_never_replays_skipped_private_or_already_awarded_facts(self):
        event_id, bundle_id = self.broken_bundle()
        with self.Session() as db:
            bundle = db.get(FactBundle, bundle_id)
            value = copy.deepcopy(bundle.payload); value['items'][0]['decision'] = 'skip'; bundle.payload = value; db.commit()
            with self.assertRaises(ValueError): repair.inspect_source(db, 'friend', bundle_id, event_id, 24)
            db.rollback()
            db.get(Event, event_id).ai_permission = 'private'; db.commit()
            with self.assertRaises(Exception): repair.inspect_source(db, 'friend', bundle_id, event_id, 24)
