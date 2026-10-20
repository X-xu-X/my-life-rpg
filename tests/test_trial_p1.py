"""P1 contracts use synthetic accounts/DB and supplier doubles only."""
import unittest
from unittest.mock import patch
from uuid import uuid4
import tests.test_next_iteration as fixtures
from app.models import Setting
from app.models.access import LLMCredential
from app.services.llm_service import LLMError


class TrialP1Tests(unittest.TestCase):
    setUp = fixtures.CloudTests.setUp
    tearDown = fixtures.CloudTests.tearDown
    register = fixtures.CloudTests.register
    configure_model = fixtures.CloudTests.configure_model
    save = fixtures.CloudTests.save

    def version(self):
        return self.client.get('/api/llm-config').json()['primary']['config_version']

    def test_save_never_tests_and_validation_is_versioned_and_private(self):
        self.register()
        with patch('app.services.llm_service.llm_service.chat', return_value='OK') as supplier:
            self.configure_model(); supplier.assert_not_called()
            version = self.version()
            result = self.client.post('/api/llm-config/test', json={'group':'primary','expected_config_version':version})
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['status'],'passed')
            self.assertEqual(supplier.call_args.kwargs['max_tokens'],8)
            summary = self.client.get('/api/llm-config').json()['primary']
            self.assertEqual(summary['validation']['config_version'],version)
            self.assertNotIn('sk-fake-test-only-key',str(summary))
            self.client.put('/api/llm-config',json={'group':'primary','model':'another-model'})
            self.assertEqual(self.client.get('/api/llm-config').json()['primary']['validation']['status'],'stale')
            stale = self.client.post('/api/llm-config/test',json={'group':'primary','expected_config_version':version})
            self.assertEqual(stale.status_code,409)
            self.assertEqual(supplier.call_count,1)

    def test_old_client_and_unsaved_body_are_explicitly_rejected(self):
        self.register(); self.configure_model()
        with patch('app.services.llm_service.llm_service.chat') as supplier:
            for body in ({'group':'primary'}, {'group':'primary','expected_config_version':self.version(),'model':'unsaved'}, {'group':'primary','expected_config_version':False}):
                self.assertEqual(self.client.post('/api/llm-config/test',json=body).status_code,422)
            supplier.assert_not_called()

    def test_supplier_failures_are_persisted_and_sanitized(self):
        self.register();self.configure_model()
        for error, expected in [(LLMError('MODEL_AUTH_FAILED：secret-provider-body'),'MODEL_AUTH_FAILED'),
                                (LLMError('MODEL_TIMEOUT'),'MODEL_TIMEOUT'),(RuntimeError('sk-secret-not-for-user'),'MODEL_UNAVAILABLE')]:
            with patch('app.services.llm_service.llm_service.chat',side_effect=error):
                response=self.client.post('/api/llm-config/test',json={'group':'primary','expected_config_version':self.version()})
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['status'],'failed')
                self.assertEqual(response.json()['error_code'],expected)
                self.assertNotIn('secret',response.text)
                self.assertEqual(self.client.get('/api/llm-config').json()['primary']['validation']['error_code'],expected)

    def test_configuration_changed_during_test_cannot_publish_success(self):
        self.register();self.configure_model();version=self.version()
        def change(*args,**kwargs):
            with self.Session() as db:
                row=db.query(LLMCredential).one();row.model='new-model';row.config_version+=1;db.commit()
            return 'OK'
        with patch('app.services.llm_service.llm_service.chat',side_effect=change):
            response=self.client.post('/api/llm-config/test',json={'group':'primary','expected_config_version':version})
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.client.get('/api/llm-config').json()['primary']['validation']['status'],'untested')

    def test_date_precision_save_replay_and_inconsistent_time_rejected(self):
        self.register();key=str(uuid4())
        first=self.save(key=key,source='form',occurred_on='2026-10-15',time_precision='date')
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['occurred_on'],'2026-10-15')
        self.assertEqual(first.json()['time_precision'],'date')
        replay=self.save(key=key,source='form',occurred_on='2026-10-15',time_precision='date')
        self.assertEqual(replay.json()['id'],first.json()['id'])
        self.assertEqual(self.save(key=key,source='form',occurred_on='2026-10-14',time_precision='date').status_code,409)
        self.assertEqual(self.save(occurred_on='2026-10-15',time_precision='date',occurred_at='2026-10-15T10:00:00+08:00').status_code,422)
        self.assertEqual(self.save(occurred_on='2026-10-15',time_precision='minute',occurred_at='2026-10-14T10:00:00+08:00').status_code,422)
        minute=self.save(time_precision='minute',occurred_at='2026-10-15T23:30:00Z')
        self.assertEqual(minute.json()['occurred_on'],'2026-10-16')
        edited=self.client.put('/api/events/'+str(minute.json()['id']),json={'expected_version':1,'occurred_at':'2026-10-16T12:00:00+08:00'})
        self.assertEqual(edited.status_code,200,edited.text)
        self.assertIsNone(edited.json()['time_precision'])

    def test_legacy_creation_keeps_receipt_fingerprint_and_unknown_precision(self):
        from app.schemas import EventCreate
        from app.models.access import RequestReceipt
        import hashlib,json
        self.register();key=str(uuid4());body={'content':'legacy text','source':'journal','client_request_id':key}
        result=self.client.post('/api/events',json=body)
        self.assertEqual(result.status_code,200,result.text)
        original=EventCreate(**body).model_dump(mode='json')
        original.pop('occurred_on');original.pop('time_precision');original.pop('record_kind');original.pop('ai_permission')
        expected=hashlib.sha256(json.dumps(original,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with self.Session() as db:
            self.assertEqual(db.query(RequestReceipt).filter_by(operation='create_event',request_key=key).one().payload_hash,expected)
        self.assertIsNone(result.json()['time_precision'])

    def test_model_name_format_and_get_have_no_supplier_side_effects(self):
        self.register();self.configure_model()
        with patch('app.services.llm_service.llm_service.chat') as supplier:
            self.assertEqual(self.client.put('/api/llm-config',json={'group':'primary','model':'bad model'}).status_code,422)
            for path in ('/api/llm-config','/api/events','/api/pending'):
                self.assertEqual(self.client.get(path).status_code,200)
            supplier.assert_not_called()

    def test_actual_analysis_source_is_saved_and_old_audit_keeps_snapshot(self):
        from app.models import Event, JudgmentLog
        from app.services import judge_service
        from tests.test_v1_11_safety import RESULT
        self.register();self.configure_model();self.save(source='form')
        def analyze():
            with self.Session() as db:
                event=db.query(Event).one();db.info['user_id']=event.user_id
                with patch.object(judge_service.llm_service,'chat_json',return_value=RESULT),patch('app.services.memory_service.maybe_update_memory',return_value={}):
                    result=judge_service.judge_event(db,event)
                    return dict(result.model_provenance)
        first=analyze()
        self.client.put('/api/llm-config',json={'group':'primary','model':'later-model'})
        second=analyze()
        self.assertNotEqual(first['model'],second['model'])
        self.assertLess(first['config_version'],second['config_version'])
        with self.Session() as db:
            logs=db.query(JudgmentLog).order_by(JudgmentLog.id).all()
            self.assertEqual(logs[0].payload['model_provenance'],first)
            self.assertEqual(logs[-1].payload['model_provenance'],second)

    def test_safe_error_categories_do_not_include_provider_text(self):
        from app.services.model_errors import category
        for status,code,expected in [(401,None,'MODEL_AUTH_FAILED'),(403,None,'MODEL_NOT_FOUND'),
                                     (404,None,'MODEL_NOT_FOUND'),(429,None,'MODEL_RATE_LIMITED'),
                                     (429,'insufficient_quota','MODEL_BALANCE_INSUFFICIENT'),
                                     (504,None,'MODEL_TIMEOUT'),(500,None,'MODEL_SERVICE_ERROR'),(400,None,'MODEL_INVALID_RESPONSE')]:
            error=RuntimeError('private-provider-body');error.status_code=status;error.body={'error':{'code':code}}
            self.assertEqual(category(error),expected)

    def test_local_saved_version_and_validation_are_compatible(self):
        from app.config import settings
        from app.routers import settings as routes
        from app.services.model_validation import snapshot,summary
        from app.schemas import LLMConfigIn
        with self.Session() as db,patch.object(settings,'run_mode','local'):
            from app.models import User
            user=db.get(User,self.owner_id)
            db.add(Setting(user_id=user.id,key='llm_primary',value={'api_key':'synthetic-local-key','enabled':True,'base_url':'https://api.deepseek.com','model':'local-old','config_version':3}))
            db.add(Setting(user_id=user.id,key='llm_validation_primary',value={'status':'passed','config_version':3}))
            db.commit()
            with patch.object(routes,'get_or_create_default_user',return_value=user),patch('app.services.llm_service.llm_service.chat') as supplier:
                routes.put_llm_config(LLMConfigIn(group='primary',model='local-new'),db)
                supplier.assert_not_called()
            meta=snapshot(db,user.id,'primary')
            self.assertEqual(meta['config_version'],4)
            self.assertEqual(summary(db,user.id,'primary',4)['status'],'stale')


if __name__=='__main__':unittest.main()
