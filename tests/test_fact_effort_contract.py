"""Regression for the observed event36 effort-field rejection; fake suppliers only."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from app.models import AIJudgment, AttributeHistory, CoinLedger
from app.models.full_system import ActionAward, FactBundle
from app.services import fact_analysis, trial_rules, analysis_jobs
from app.services.llm_service import LLMError
from tests import test_full_system as fixture


class EffortParsingTests(unittest.TestCase):
    def response(self, **extra):
        return {'facts':[{'excerpt':'合成阅读','summary':'阅读笔记','confidence':.95,'changes':[],**extra}]}

    def test_effort_metadata_never_changes_the_model_price(self):
        for value in ('学习二十分钟',None,{'minutes':20},[],0,1,'true','false'):
            original=self.response(effort=value,coins=9);snapshot=copy.deepcopy(original)
            proposals,questions,warnings=fact_analysis.parse_response(original)
            self.assertFalse(proposals[0].effort)
            self.assertEqual(warnings,[{'fact_index':0,'code':'EFFORT_UNVERIFIED'}])
            self.assertEqual(proposals[0].coins,9)
            self.assertEqual(original,snapshot)
        for value in (True,False):
            proposals,_,warnings=fact_analysis.parse_response(self.response(effort=value))
            self.assertIs(proposals[0].effort,value);self.assertEqual(warnings,[])
        self.assertFalse(fact_analysis.parse_response(self.response())[0][0].effort)

    def test_coins_reject_strings_and_clamp_negatives(self):
        self.assertEqual(fact_analysis.parse_response(self.response(coins=0))[0][0].coins,0)
        self.assertEqual(fact_analysis.parse_response(self.response(coins=-3))[0][0].coins,0)
        with self.assertRaisesRegex(LLMError,'MODEL_FACT_FORMAT_INVALID'):
            fact_analysis.parse_response(self.response(coins='12'))

    def test_bad_confidence_and_grade_remain_blocking(self):
        for extra in ({'confidence':'0.95'},{'confidence':95},{'confidence':True},{'grade':'excellent'},{'mainline':True}):
            with self.assertRaisesRegex(LLMError,'MODEL_FACT_FORMAT_INVALID'):
                fact_analysis.parse_response(self.response(effort='错误类型',**extra))
        with self.assertRaisesRegex(LLMError,'MODEL_ATTRIBUTE_INVALID'):
            fact_analysis.parse_response(self.response(changes=[{'name':'智力','delta':True}]))


class EffortFlowTests(unittest.TestCase):
    setUp=fixture.FullSystemTests.setUp
    tearDown=fixture.FullSystemTests.tearDown
    register=fixture.FullSystemTests.register
    configure_model=fixture.FullSystemTests.configure_model
    write=fixture.FullSystemTests.write
    event=fixture.FullSystemTests.event
    facts=fixture.FullSystemTests.facts
    suggestion=fixture.FullSystemTests.suggestion
    preview=fixture.FullSystemTests.preview
    settle=fixture.FullSystemTests.settle

    def ready(self):
        self.register();self.configure_model()
        self.client.post('/api/onboarding/neutral',json={'acknowledge':True})

    def test_three_bad_effort_fields_do_not_discard_actions_or_grant_holiday_bonus(self):
        self.ready();event=self.event('整理笔记。完成练习。写下总结。','allowed')
        group=self.facts(event,[self.suggestion(excerpt,effort=effort) for excerpt,effort in
            [('整理笔记','二十分钟'),('完成练习',None),('写下总结',{'minutes':20})]])
        self.assertEqual(len(group['payload']['items']),3)
        self.assertEqual(len(group['payload']['warnings']),3)
        self.assertTrue(all(not i['effort'] and fact_analysis.EFFORT_NOTE in i['reason'] for i in group['payload']['items']))
        with self.Session() as db:
            self.assertEqual(db.query(ActionAward).count(),0)
            self.assertEqual(db.query(AttributeHistory).count(),0)
            self.assertEqual(db.query(AIJudgment).count(),0)
        with patch('app.routers.phase.holiday_rows',return_value=[SimpleNamespace(id=100,version=1)]):
            group=self.preview(group)
            self.assertEqual(group['preview']['total'],18)
            # 节日不再加成：effort 非法时金额只由模型给价决定，三项各 6 币不变
            self.assertTrue(all(i['breakdown']['coins']==6 and i['breakdown']['amount']==6 for i in group['preview']['items']))
            result=self.settle(group);self.assertEqual(result.status_code,200,result.text)
        with self.Session() as db:
            self.assertEqual(sum(a.amount for a in db.query(ActionAward)),18)
            self.assertEqual(db.query(AttributeHistory).count(),3)
            self.assertEqual(sum(c.delta for c in db.query(CoinLedger).filter_by(source='trial_action')),18)

    def test_prompt_declares_effort_boolean_and_confidence_range(self):
        self.ready();event=self.event('合成阅读记录','allowed');sent=[]
        def fake(messages,**kwargs):
            sent.extend(messages);return {'facts':[self.suggestion(event['content'],effort=True)]}
        with patch('app.services.llm_service.llm_service.chat_json',side_effect=fake):
            # The helper normally supplies its own mock, so dispatch directly here.
            job=self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1,'operation':'facts'}).json()
            analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
        prompt=' '.join(m['content'] for m in sent if m['role']=='system')
        self.assertIn('effort必须是JSON布尔值true或false',prompt)
        self.assertIn('confidence必须是0到1的数值',prompt)
        self.assertEqual(self.client.get('/api/analysis-jobs/'+str(job['id'])).json()['state'],'ready')

    def test_bad_source_and_relation_have_specific_safe_errors_and_no_bundle(self):
        self.ready()
        for content,proposal,code in [
            ('精确原文',self.suggestion('模型改写后的原文'),'MODEL_FACT_SOURCE_INVALID'),
            ('另一条原文',self.suggestion('另一条原文',related_event_id=999999),'MODEL_FACT_RELATION_INVALID'),
            ('有格式错误',self.suggestion('有格式错误',confidence='0.95'),'MODEL_FACT_FORMAT_INVALID')]:
            event=self.event(content,'allowed')
            job=self.client.post(f"/api/events/{event['id']}/analysis-jobs",json={'request_key':str(uuid4()),'event_version':1,'operation':'facts'}).json()
            with patch('app.services.llm_service.llm_service.chat_json',return_value={'facts':[proposal]}):
                analysis_jobs.process(self.Session,analysis_jobs.claim(self.Session))
            saved=self.client.get('/api/analysis-jobs/'+str(job['id'])).json()
            self.assertEqual(saved['state'],'failed');self.assertEqual(saved['safe_error_code'],code)
            self.assertIn('本次未入账',saved['safe_error_message'])
        with self.Session() as db:
            self.assertEqual(db.query(FactBundle).count(),0);self.assertEqual(db.query(ActionAward).count(),0)
