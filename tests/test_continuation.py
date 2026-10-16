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
        response=self.write('/diaries/'+day,{'content':content},version,'PUT')
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


if __name__=='__main__':unittest.main()
