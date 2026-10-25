"""No real model/server; reproduce metadata diagnosis and the pre-write hard stop."""
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from app.models import User, Event
from app.models.analysis import AnalysisJob
from app.models.full_system import FactBundle, FactFragment, ActionAward
from app.models.workflow import FactIdentity, FactSettlement
from app.services import fact_analysis
from ops.diagnose_fact_response import validate_response, Captured
from tests import test_full_system as fixture


class MetadataTests(unittest.TestCase):
    def report(self, facts, questions=None, **inputs):
        value = {'facts': facts}
        if questions is not None:value['questions'] = questions
        return validate_response(value, {'original':'合成阅读记录 原文私密标识', 'event_id':36,
            'related_sources':[], **inputs}, fact_analysis.Suggestion,
            event_valid=lambda identifier:False, fact_valid=lambda identifier:False)

    def suggestion(self, **extra):
        return {'excerpt':'合成阅读记录', 'summary':'示例', 'confidence':.95, 'changes':[], **extra}

    def test_valid_response_has_no_issues(self):
        self.assertEqual(self.report([self.suggestion()])['issues'], [])

    def test_percentage_string_extra_field_and_questions_are_distinguished(self):
        for changes, expected in [({'confidence':95},'less_than_equal'),
                ({'confidence':'0.95'},'float_type'), ({'mainline':False},'extra_forbidden')]:
            issues=self.report([self.suggestion(**changes)])['issues']
            self.assertTrue(any(i['code']==expected and i['stage']=='schema' for i in issues))
        self.assertEqual(self.report([self.suggestion()], questions=[''] )['issues'][0]['code'],'QUESTIONS_INVALID')

    def test_excerpt_and_duplicate_and_pointer_are_distinguished(self):
        issues=self.report([self.suggestion(excerpt='合成 阅读记录')])['issues']
        self.assertEqual(issues[0]['code'],'EXCERPT_NOT_EXACT')
        self.assertTrue(issues[0]['matches_after_removing_whitespace'])
        self.assertEqual(self.report([self.suggestion(),self.suggestion()])['issues'][0]['code'],'DUPLICATE_SOURCE_EXCERPT')
        self.assertEqual(self.report([self.suggestion(related_event_id=99)])['issues'][0]['code'],'RELATED_EVENT_INVALID')
        self.assertEqual(self.report([self.suggestion(related_fact_id=99)])['issues'][0]['code'],'RELATED_FACT_INVALID')
        self.assertEqual(self.report([self.suggestion(source_kind='note',source_id=99)])['issues'][0]['code'],'SOURCE_NOT_FOUND')

    def test_no_original_or_model_values_or_unknown_private_keys_in_report(self):
        record=self.suggestion(summary='MODEL_PRIVATE_SENTINEL',reason='MODEL_PRIVATE_SENTINEL')
        record['SENSITIVE_PRIVATE_KEY']= 'MODEL_PRIVATE_SENTINEL'
        serialized=json.dumps(self.report([record]),ensure_ascii=False)
        for private in ('原文私密标识','MODEL_PRIVATE_SENTINEL','SENSITIVE_PRIVATE_KEY','合成阅读记录'):
            self.assertNotIn(private, serialized)
        self.assertIn('unknown_field',serialized)


class DiagnosticStopTests(unittest.TestCase):
    setUp=fixture.FullSystemTests.setUp
    tearDown=fixture.FullSystemTests.tearDown
    register=fixture.FullSystemTests.register
    configure_model=fixture.FullSystemTests.configure_model
    event=fixture.FullSystemTests.event

    def test_capture_always_stops_generate_before_any_fact_or_award_write(self):
        self.register();self.configure_model();record=self.event('合成阅读记录','allowed')
        for raw in ({'facts':[{'excerpt':'合成阅读记录','summary':'示例','confidence':.95}]},
                    {'facts':[{'excerpt':'合成阅读记录','summary':'示例','confidence':'0.95'}]}):
            with self.Session() as db:
                user=db.query(User).filter_by(username='friend').one();db.info['user_id']=user.id
                def capture(messages,**kwargs):
                    inputs=json.loads(messages[-1]['content']);inputs['event_id']=record['id']
                    raise Captured(validate_response(raw,inputs,fact_analysis.Suggestion,
                            event_valid=lambda _:False,fact_valid=lambda _:False))
                with patch('app.services.llm_service.llm_service.chat_json',side_effect=capture), self.assertRaises(Captured):
                    fact_analysis.generate(db,SimpleNamespace(user_id=user.id,event_id=record['id']),lambda db:None)
                db.rollback()
                for model in (FactBundle,FactFragment,FactIdentity,FactSettlement,ActionAward):
                    self.assertEqual(db.query(model).count(),0)
                self.assertEqual(db.get(Event,record['id']).content,'合成阅读记录')
                self.assertEqual(db.query(AnalysisJob).count(),0)
