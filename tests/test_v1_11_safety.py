"""v1.11 regression: isolated databases only, without real-data lifespan."""
from contextlib import closing
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event, func, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db, migrate_schema
from app import models as m
from app.constants import ATTRIBUTE_DIMENSIONS_SET
from app.main import app
from app.routers import export, events, judgments, report, settings
from app.schemas import EventUpdate, GoalCreate
from app.services import (achievement_service, backup_service, challenge_service, coin_service,
    exemption_service, goal_service, item_service, judge_service, memory_service,
    onboarding_service, stagnation_service, subdimension_service)
from app.services.llm_service import LLMError, LLMService
from app.services.user_service import get_or_create_default_user, ensure_dimensions

CONFIG = SimpleNamespace(quality_note='')
RESULT = {'realistic': True, 'affected_attributes': [{'name': '体能', 'delta': 2}],
          'confidence': 1.0, 'summary': '真实测试', 'outcome': 'done'}


def seed(db):
    user = get_or_create_default_user(db)
    ensure_dimensions(db, user)
    return user


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        @sa_event.listens_for(self.engine, 'connect')
        def enable_fk(connection, record): connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.Session()
        self.user = seed(self.db)
        def dependency(): yield self.db
        app.dependency_overrides[get_db] = dependency
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def attr(self, name='体能'):
        return self.db.query(m.Attribute).filter_by(user_id=self.user.id, name=name).one()

    def event(self, **kw):
        data = dict(user_id=self.user.id, event_type='positive', title='唯一删除标记',
                    content='真实运动', category='运动', source='journal', occurred_at=datetime.now())
        data.update(kw)
        row = m.Event(**data)
        self.db.add(row); self.db.commit()
        return row

    def judgment(self, event=None, confidence=1, changes=None):
        event = event or self.event()
        row = m.AIJudgment(event_id=event.id, user_id=self.user.id, confidence=confidence,
            suggested_changes=changes if changes is not None else RESULT['affected_attributes'], status='pending')
        self.db.add(row); self.db.commit()
        return row

    def counts(self):
        return {t.name: self.db.execute(text('SELECT COUNT(*) FROM "'+t.name+'"')).scalar()
                for t in Base.metadata.sorted_tables}

    def run_llm(self, fn, result=None, callback=None):
        with patch.object(judge_service.llm_config, 'resolve_llm_config', return_value=CONFIG), \
             patch.object(judge_service.llm_service, 'chat_json', side_effect=callback, return_value=result or RESULT), \
             patch.object(memory_service, 'maybe_update_memory', return_value={}):
            return fn()

    def test_reset_denied_without_changing_any_table(self):
        profile = coin_service._profile(self.db, self.user)
        profile.initial_attributes_snapshot = {'attributes': [{'name':'体能','value':50}]}
        self.db.commit()
        before = self.counts()
        for route in ('reset','reset-all'):
            self.assertEqual(self.client.post('/api/onboarding/'+route).status_code, 409)
            self.assertEqual(before, self.counts())
        with self.assertRaises(ValueError): onboarding_service._generate_panel(self.db, profile, [])
        self.assertEqual(before, self.counts())
        self.assertEqual(self.attr().current_value,50)
        self.assertEqual(profile.initial_attributes_snapshot['attributes'][0]['value'],50)

    def test_blank_reset_allowed_but_history_blocks_generation(self):
        profile=coin_service._profile(self.db,self.user)
        profile.onboarding_state={'questions':['x']}; self.db.commit()
        self.assertEqual(self.client.post('/api/onboarding/reset').status_code,200)
        self.assertEqual(profile.onboarding_state,{})
        self.db.add(m.AttributeHistory(user_id=self.user.id, attribute_id=self.attr().id, delta=0,value_after=50))
        self.db.commit()
        with self.assertRaises(ValueError): onboarding_service._generate_panel(self.db,profile,[])
        self.assertEqual(self.client.post('/api/onboarding/reset').status_code,409)

    def test_settings_and_export_never_reveal_internal_key(self):
        key='sk-test-secret-that-must-not-leak-12345'
        self.db.add(m.Setting(user_id=self.user.id,key=settings.SETTING_KEY_PRIMARY,value={'api_key':key,'enabled':True}))
        self.db.commit()
        res=self.client.get('/api/settings')
        self.assertEqual(set(res.json()), settings.PUBLIC_SETTING_KEYS)
        self.assertNotIn(key,res.text)
        masked=self.client.get('/api/llm-config')
        self.assertNotIn(key,masked.text)
        self.assertTrue(masked.json()['primary']['configured'])
        self.assertNotEqual(masked.json()['primary']['api_key'],key)
        self.assertNotIn(key,json.dumps(export._collect(self.db,self.user.id)))
        for internal in (settings.SETTING_KEY_PRIMARY,settings.SETTING_KEY_AUX,'llm_config_primary','stagnation_checks','unreal_count'):
            self.assertEqual(self.client.post('/api/settings',json={'key':internal,'value':'bad'}).status_code,400)
        self.assertEqual(self.db.query(m.Setting).filter_by(key=settings.SETTING_KEY_PRIMARY).one().value['api_key'],key)
        for value in ({'achievements':1},{'unknown':True},'bad'):
            self.assertEqual(self.client.post('/api/settings',json={'key':'gamification_modules','value':value}).status_code,400)
        for value in (['unknown'],[1],'体能'):
            self.assertEqual(self.client.post('/api/settings',json={'key':'hidden_attributes','value':value}).status_code,400)
        for name,value in [('hidden_attributes',['体能','体能']),('disabled_attributes',['健康']),('gamification_modules',{'tasks':True})]:
            self.assertEqual(self.client.post('/api/settings',json={'key':name,'value':value}).status_code,200)
        self.assertEqual(self.client.get('/api/settings').json()['hidden_attributes'],['体能'])

    def test_confirm_and_coin_failure_roll_back_everything(self):
        j=self.judgment(); before=self.counts()
        with patch.object(coin_service,'reward_event_confirm',side_effect=RuntimeError('coin failed')):
            with self.assertRaises(RuntimeError): judgments.confirm(j.id,self.db)
        self.assertEqual(self.attr().current_value,50)
        self.assertEqual(j.status,'pending')
        self.assertEqual(before,self.counts())
        result=judgments.confirm(j.id,self.db)
        self.assertEqual(result['coins_gained'],2)
        self.assertEqual(self.attr().current_value,52)
        self.assertEqual(coin_service.balance(self.db,self.user),2)
        self.assertEqual(self.db.query(func.sum(m.CoinLedger.delta)).scalar(),2)
        frozen=self.counts()
        for action in (lambda:judge_service.confirm(self.db,j),lambda:judge_service.supplement(self.db,j,'extra'),lambda:judge_service.dispute(self.db,j,'wrong')):
            with self.assertRaises(ValueError): action()
            self.assertEqual(frozen,self.counts())
        for action in ('supplement','dispute'):
            self.assertEqual(self.client.post(f'/api/judgments/{j.id}/{action}',json={'detail':'extra'}).status_code,409)
        self.assertEqual(self.client.put(f'/api/events/{j.event_id}',json={'content':'changed'}).status_code,409)

    def test_confidence_invalid_or_low_never_books(self):
        for confidence in (None,0.5,2,-1):
            j=self.judgment(confidence=confidence)
            with self.assertRaises(ValueError): judge_service.confirm(self.db,j)
            self.assertEqual(j.status,'pending')
        self.assertEqual(self.db.query(m.AttributeHistory).count(),0)

    def test_numeric_and_json_validation(self):
        for raw in ('{"x":NaN}','{"x":Infinity}','{"x":-Infinity}','{"x":1e309}','{"coin_reward":9223372036854775808}','[]'):
            with self.assertRaises(LLMError): LLMService._parse_json(raw)
        self.assertEqual(LLMService._parse_json('```json\n{"x":1}\n```'),{'x':1})
        for raw in (None, True, 2, -1, 'nan', float('inf')):
            self.assertEqual(judge_service._parse_confidence(raw),0)
        for raw in (float('nan'),float('inf'),True,'bad','1e309'):
            self.assertEqual(judge_service._parse_changes([{'name':'体能','delta':raw}])[0]['delta'],0)
        for raw in ('bad', {}, None): self.assertEqual(judge_service._parse_changes(raw),[])
        self.assertEqual(judge_service._parse_changes([None,'x']),[])
        out=judge_service._parse_changes([{'name':'体能','delta':5,'reason':'r'},{'name':'体能','delta':5,'reason':'r'}])
        self.assertEqual(out[0]['delta'],5); self.assertEqual(out[0]['reason'],'r')

    def test_target_aggregation_cap_and_full_main_declines(self):
        parent=self.attr()
        kids=[m.Attribute(user_id=self.user.id,name=n,parent_id=parent.id,current_value=0) for n in ('耐力细分','力量细分')]
        self.db.add_all(kids); self.db.commit()
        j=self.judgment(changes=[{'name':k.name,'delta':5} for k in kids])
        judge_service.confirm(self.db,j)
        self.assertEqual(parent.current_value,55)
        self.assertEqual(self.db.query(m.AttributeHistory).count(),1)
        parent.current_value=100; self.db.commit()
        j=self.judgment(changes=[{'name':'体能','delta':-2}])
        judge_service.confirm(self.db,j)
        self.assertEqual(parent.current_value,98)
        self.assertEqual([k.current_value for k in kids],[0,0])

    def test_cap_records_actual_delta_and_disabled_parent_blocks_children(self):
        self.attr().current_value=99; self.db.commit()
        j=self.judgment(changes=[{'name':'体能','delta':5}]); judge_service.confirm(self.db,j)
        self.assertEqual(j.final_changes[0]['delta'],1)
        kid=m.Attribute(user_id=self.user.id,name='耐力细分',parent_id=self.attr().id,current_value=0)
        self.db.add(kid); self.db.add(m.Setting(user_id=self.user.id,key='disabled_attributes',value=['体能'])); self.db.commit()
        j=self.judgment(changes=[{'name':'耐力细分','delta':5},{'name':'体能','delta':-5},{'name':'unknown','delta':5}])
        judge_service.confirm(self.db,j)
        self.assertEqual(j.final_changes,[]); self.assertEqual(kid.current_value,0)

    def test_delete_uses_actual_history_not_suggestions(self):
        self.attr().current_value=100; self.db.commit()
        j=self.judgment(changes=[{'name':'体能','delta':5}]); judge_service.confirm(self.db,j)
        before=self.counts(); e=self.db.get(m.Event,j.event_id)
        judge_service.delete_event(self.db,e)
        self.assertEqual(self.attr().current_value,100)
        self.assertEqual(j.status,'deleted')
        self.assertEqual(self.counts()['judgment_logs'],before['judgment_logs']+1)
        self.assertEqual(self.counts()['ai_judgments'],before['ai_judgments'])
        with self.assertRaises(ValueError): judge_service.delete_event(self.db,e)
        self.assertEqual(self.attr().current_value,100)

    def test_delete_reverses_points_retains_coins_and_all_consumers_hide_event(self):
        item=m.CheckinItem(user_id=self.user.id,name='运动',frequency_type='daily',category='运动')
        self.db.add(item); self.db.commit()
        e=self.event(item_id=item.id); eid=e.id; j=self.judgment(event=e)
        judgments.confirm(j.id,self.db)
        before=self.counts()
        probe=self.event(title='对照事件',category='运动',source='form',is_pure=True)
        probes={
          'event list':lambda:[r.id for r in events.list_events(db=self.db,pure=None,q='',date=None)],
          'heatmap':lambda:events.get_heatmap(self.db),
          'judgment list':lambda:judgments.list_judgments(self.db),
          'achievement metrics':lambda:achievement_service._metrics(self.db,self.user),
          'journal streak':lambda:coin_service._journal_days(self.db,self.user),
          'exemption context':lambda:exemption_service._recent_events(self.db,self.user),
          'item count':lambda:item_service.count_in_period(self.db,self.user.id,item),
          'period counts':lambda:item_service.period_count_map(self.db,self.user.id,[item]),
          'item stats':lambda:item_service.build_stats(self.db,self.user.id,[item]),
          'same category':lambda:judge_service._recent_same_category_count(self.db,self.user.id,probe),
          'recent context':lambda:judge_service._recent_events_context(self.db,self.user.id,probe.id),
          '24h context':lambda:judge_service._recent_24h_context(self.db,self.user.id,probe.id),
          'today context':lambda:judge_service._today_events_context(self.db,self.user.id,probe.id),
          'memory context':lambda:memory_service._events_summary(self.db,self.user.id),
          'subdimension context':lambda:subdimension_service._related_events(self.db,self.user,'体能'),
        }
        original={k:f() for k,f in probes.items()}
        judge_service.delete_event(self.db,e)
        after={k:f() for k,f in probes.items()}
        self.assertNotIn(eid,after['event list'])
        self.assertEqual(after['judgment list'],[])
        self.assertEqual(sum(r['count'] for r in after['heatmap']),sum(r['count'] for r in original['heatmap'])-1)
        self.assertEqual(after['achievement metrics']['journal_total'],0)
        self.assertEqual(after['achievement metrics']['events_total'],1)
        self.assertEqual(after['journal streak'],0)
        self.assertEqual(after['item count'],0)
        self.assertEqual(after['period counts'][item.id],0)
        self.assertEqual(after['item stats'][0]['samples'],[])
        self.assertEqual(after['same category'],original['same category']-1)
        for k in ('exemption context','recent context','24h context','today context','memory context','subdimension context'):
            self.assertNotIn('唯一删除标记',after[k],k)
        with patch.object(report.prompts,'build_report_messages',return_value=[]) as build, \
             patch.object(report.llm_config,'resolve_llm_config',return_value=CONFIG), \
             patch.object(report.llm_service,'chat_json',return_value={}):
            report.generate_report(self.db)
            self.assertEqual(build.call_args.kwargs['stats']['events_count'],1)
        self.assertEqual(self.attr().current_value,50)
        self.assertEqual(coin_service.balance(self.db,self.user),2)
        self.assertGreater(self.counts()['attribute_history'],before['attribute_history'])
        log=self.db.query(m.JudgmentLog).filter_by(action='delete').one()
        self.assertFalse(log.payload['coins_rolled_back'])
        data=export._collect(self.db,self.user.id)
        self.assertEqual(len(data['tables']),17)
        self.assertTrue(next(row for row in data['tables']['events'] if row['id']==eid)['is_deleted'])
        self.assertEqual(self.client.get(f'/api/events/{eid}').status_code,404)
        self.assertEqual(self.client.post(f'/api/events/{eid}/judge',json={}).status_code,404)
        self.assertEqual(self.client.get('/api/export?format=csv').status_code,200)
        Path('docs/review/V1_11_CONSUMER_EVIDENCE.json').write_text(json.dumps({'before':original,'after':after},ensure_ascii=False,indent=2,default=str),encoding='utf-8')

    def test_unrealistic_event_retains_history_and_rejects_pending(self):
        e=self.event(); j=self.judgment(event=e)
        self.db.add(m.Setting(user_id=self.user.id,key='unreal_count',value=2)); self.db.commit()
        with self.assertRaises(ValueError): self.run_llm(lambda:judge_service.judge_event(self.db,e),{'realistic':False,'realistic_reason':'不科学'})
        self.assertTrue(e.is_deleted); self.assertEqual(j.status,'deleted')
        self.assertEqual(self.db.query(m.Event).count(),1)
        self.assertEqual(self.db.query(m.AttributeHistory).count(),1)
        self.assertEqual(self.db.query(m.JudgmentLog).filter_by(action='reject').count(),1)
        with self.assertRaises(ValueError):judge_service.confirm(self.db,j)

    def test_edit_rejudge_keeps_id_and_stale_response_is_rejected(self):
        e=self.event(); j=self.judgment(event=e); jid=j.id
        events.update_event(e.id,EventUpdate(content='edited'),self.db)
        self.assertEqual(j.status,'invalidated')
        self.run_llm(lambda:judge_service.judge_event(self.db,e))
        self.assertEqual(j.id,jid); self.assertEqual(self.db.query(m.AIJudgment).count(),1)
        def edit_during_call(*args,**kw):
            events.update_event(e.id,EventUpdate(content='edited-again'),self.db)
            return RESULT
        with self.assertRaises(ValueError):self.run_llm(lambda:judge_service.judge_event(self.db,e),callback=edit_during_call)
        self.assertEqual(j.status,'invalidated')
        self.assertEqual(self.db.query(m.AIJudgment).count(),1)

    def test_challenge_low_confidence_and_injected_coin_failure_rollback(self):
        e=self.event(origin='challenge'); j=self.judgment(event=e,confidence=.5)
        ch=m.Challenge(user_id=self.user.id,title='运动',status='accepted',event_id=e.id,judgment_id=j.id,outcome='done',deposit=12,coin_reward=20)
        self.db.add(ch); self.db.commit(); before=self.counts()
        with self.assertRaises(ValueError):challenge_service.settle(self.db,self.user,ch)
        self.assertEqual(ch.status,'accepted'); self.assertEqual(j.status,'pending'); self.assertEqual(before,self.counts())
        j.confidence=1; self.db.commit()
        with patch.object(coin_service,'grant',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):challenge_service.settle(self.db,self.user,ch)
        self.assertEqual(self.attr().current_value,50); self.assertEqual(ch.status,'accepted'); self.assertEqual(j.status,'pending')
        self.assertEqual(before,self.counts())

    def test_challenge_complete_prompt_realistic_and_original_id_retry(self):
        ch=m.Challenge(user_id=self.user.id,title='运动',status='accepted',related_attributes=['体能'],deposit=12,coin_reward=20)
        self.db.add(ch); self.db.commit()
        captured=[]
        def llm(messages,**kw):captured.append(messages); return RESULT
        first=self.run_llm(lambda:challenge_service.complete(self.db,self.user,ch,'真实运动'),callback=llm)
        second=self.run_llm(lambda:challenge_service.complete(self.db,self.user,ch,'更多真实细节'),callback=llm)
        self.assertEqual(first['judgment_id'],second['judgment_id'])
        self.assertEqual(self.db.query(m.Event).count(),1);self.assertEqual(self.db.query(m.AIJudgment).count(),1)
        self.assertEqual(self.db.query(m.JudgmentLog).count(),2)
        self.assertIn('realistic',captured[0][0]['content'])
        for segment in ('科学锚点','主维现状','子维度','禁用维度'): self.assertIn(segment,captured[0][1]['content'])
        self.assertEqual(self.client.post(f"/api/judgments/{first['judgment_id']}/confirm").status_code,409)
        with self.assertRaises(ValueError):self.run_llm(lambda:challenge_service.complete(self.db,self.user,ch,'500俯卧撑'),{'realistic':False})
        self.assertEqual(self.db.get(m.Event,ch.event_id).content,'更多真实细节')
        self.assertEqual(ch.status,'accepted')
        with patch.object(achievement_service,'check_and_grant',return_value=[]):
            settled=challenge_service.settle(self.db,self.user,ch)
        self.assertEqual(settled['coins_delta'],32); self.assertEqual(ch.status,'settled')
        self.assertEqual(self.attr().current_value,52)

    def test_expired_exemption_protects_historical_event_in_both_read_orders(self):
        yesterday=datetime.now()-timedelta(days=1)
        at=yesterday.replace(hour=15,minute=0)
        row=m.Exemption(user_id=self.user.id,target_date=at.date().isoformat(),period='afternoon',start_time='12:00',end_time='18:00',status='active')
        self.db.add(row); self.db.commit()
        changes=[{'name':'体能','delta':-2},{'name':'智力','delta':2}]
        first,_=exemption_service.apply_to_changes(changes,at,self.db,self.user)
        row.status='active'; self.db.commit(); exemption_service.expire_stale(self.db,self.user);self.db.commit()
        self.assertEqual(row.status,'expired')
        second,_=exemption_service.apply_to_changes(changes,at,self.db,self.user)
        self.assertEqual(first,second);self.assertEqual(second[0]['delta'],0);self.assertEqual(second[1]['delta'],2)
        self.assertEqual(row.status,'used')
        j=self.judgment(event=self.event(origin='challenge',occurred_at=at),changes=changes)
        judge_service.confirm(self.db,j)
        self.assertEqual(self.attr().current_value,50)
        self.assertEqual(self.attr('智力').current_value,52)

    def test_retreat_exemption_and_expiry_settlement(self):
        today=datetime.now().date().isoformat()
        self.db.add(m.Exemption(user_id=self.user.id,target_date=today,period='allday',start_time='00:00',end_time='23:59',status='active')); self.db.commit()
        ch=m.Challenge(user_id=self.user.id,title='运动',status='accepted',related_attributes=['体能'],difficulty=2,deposit=12)
        self.db.add(ch); self.db.commit()
        with patch.object(achievement_service,'check_and_grant',return_value=[]):result=challenge_service.abandon(self.db,self.user,ch)
        self.assertEqual(self.attr().current_value,50);self.assertEqual(result['coins_delta'],0)
        self.assertEqual(ch.status,'abandoned')
        self.assertEqual(self.db.query(m.JudgmentLog).count(),2)

    def test_stagnation_failure_rolls_back_and_children_count_as_activity(self):
        with patch.object(stagnation_service,'_set_checks',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):stagnation_service.answer(self.db,self.user,'体能',True)
        self.assertEqual(self.attr().current_value,50);self.assertEqual(self.db.query(m.AttributeHistory).count(),0)
        self.assertEqual(self.db.query(m.Challenge).count(),0)
        result=stagnation_service.answer(self.db,self.user,'体能',True)
        self.assertEqual(result['deducted'],-.3)
        self.assertEqual(result['challenge']['coin_reward'],35);self.assertEqual(result['challenge']['deposit'],21)
        self.assertTrue(stagnation_service.answer(self.db,self.user,'体能',True)['already_asked'])
        self.assertEqual(self.attr().current_value,49.7)
        self.assertEqual(self.client.post('/api/stagnation/unknown/answer',json={'stopped':True}).status_code,400)
        self.assertEqual(self.db.query(m.Attribute).count(),13)
        self.assertEqual(stagnation_service.answer(self.db,self.user,'智力',False)['deducted'],0)
        kid=m.Attribute(user_id=self.user.id,name='耐力细分',parent_id=self.attr().id,current_value=1)
        self.db.add(kid);self.db.flush()
        now=datetime.now();self.db.add(m.AttributeHistory(user_id=self.user.id,attribute_id=kid.id,delta=1,value_after=1,created_at=now));self.db.commit()
        self.assertEqual(stagnation_service._last_activity(self.db,self.user.id,self.attr().id),now)

    def test_stagnation_optional_challenge_failure_preserves_penalty(self):
        def fail(db,*args):db.add(m.Challenge(user_id=self.user.id,title='失败'));db.flush();raise RuntimeError()
        with patch.object(stagnation_service,'_build_restart_challenge',side_effect=fail):
            result=stagnation_service.answer(self.db,self.user,'体能',True)
        self.assertIsNone(result['challenge']);self.assertEqual(self.db.query(m.Challenge).count(),0)
        self.assertEqual(self.attr().current_value,49.7)
        self.assertTrue(stagnation_service.answer(self.db,self.user,'体能',True)['already_asked'])

    def test_goal_terminal_state_bounds_and_single_planning_reward(self):
        goal=m.Goal(user_id=self.user.id,metric='完成',related_attribute='规划力',reward=2,penalty=-1)
        self.db.add(goal);self.db.commit()
        _,applied=goal_service.achieve_goal(self.db,goal)
        self.assertEqual(len(applied),1);self.assertEqual(self.attr('规划力').current_value,52)
        before=self.counts()
        with self.assertRaises(ValueError):goal_service.fail_goal(self.db,goal)
        self.assertEqual(goal_service.achieve_goal(self.db,goal)[1],[])
        with self.assertRaises(ValueError):goal_service.update_goal(self.db,goal,{'reward':3})
        self.assertEqual(before,self.counts())
        for values in ({'reward':100},{'reward':float('inf')},{'reward':-1},{'penalty':1},{'related_attribute':'unknown'}):
            goal=m.Goal(user_id=self.user.id,metric='完成',reward=2,penalty=-1,related_attribute='')
            for key,val in values.items():setattr(goal,key,val)
            self.db.add(goal);self.db.commit()
            action=goal_service.fail_goal if 'penalty' in values else goal_service.achieve_goal
            with self.assertRaises(ValueError):action(self.db,goal)
        for data in ({'reward':100},{'reward':float('inf')},{'penalty':1}):
            with self.assertRaises(ValueError):GoalCreate(metric='完成',**data)
        goal=m.Goal(user_id=self.user.id,metric='取消');self.db.add(goal);self.db.commit()
        before=self.db.query(m.AttributeHistory).count();goal_service.cancel_goal(self.db,goal)
        self.assertEqual(before,self.db.query(m.AttributeHistory).count())
        self.assertEqual(self.client.post('/api/goals',json={'metric':'x','related_attribute':'unknown'}).status_code,409)

    def test_initial_panel_complete_finite_and_snapshot_matches_actual_values(self):
        panel=[{'name':n,'value':60} for n in ATTRIBUTE_DIMENSIONS_SET]
        for bad in (panel[:-1],panel+[panel[0]],[{'name':'unknown','value':50}], [{'name':n,'value':True} for n in ATTRIBUTE_DIMENSIONS_SET]):
            with self.assertRaises(ValueError):onboarding_service._parse_initial_panel(bad)
        profile=coin_service._profile(self.db,self.user)
        result={'attributes':panel,'initial_coins':123,'summary':'测试'}
        self.run_llm(lambda:onboarding_service._generate_panel(self.db,profile,[]),result)
        self.assertEqual(self.attr('诚信').current_value,50)
        for item in profile.initial_attributes_snapshot['attributes']:
            self.assertEqual(self.attr(item['name']).current_value,item['value'])
        self.assertEqual(coin_service.balance(self.db,self.user),123)
        self.assertEqual(onboarding_service._clamp_initial_coins(float('inf')),80)
        data=export._collect(self.db,self.user.id)
        self.assertIsInstance(data['tables']['user_profiles'][0]['initial_attributes_snapshot']['attributes'],list)

    def test_achievement_wall_retroactive_and_unique_route(self):
        for i in range(23): self.db.add(m.Event(user_id=self.user.id,event_type='positive',source='journal',content='日记',created_at=datetime.now()-timedelta(days=i)))
        self.db.commit()
        first=self.client.get('/api/achievements');self.assertEqual(first.status_code,200)
        count=self.db.query(m.Achievement).count();self.assertGreater(count,0)
        balance=coin_service.balance(self.db,self.user)
        self.assertEqual(balance,self.db.query(func.sum(m.CoinLedger.delta)).scalar())
        self.assertEqual(self.client.get('/api/achievements').json()['balance'],balance)
        self.assertEqual(self.db.query(m.Achievement).count(),count)
        paths=app.openapi()['paths']
        self.assertIn('/api/judgments/{judgment_id}/achievement',paths)
        # FastAPI may keep included routers as dynamic entries; inspect the source routers.
        self.assertEqual(len([r for r in judgments.router.routes if r.path=='/judgments/{judgment_id}/achievement']),1)

    def test_insufficient_coins_do_not_change_balance_or_ledger(self):
        coin_service.grant(self.db,self.user,10,'event_confirm');self.db.commit()
        before=self.counts()
        with self.assertRaises(coin_service.InsufficientCoins):coin_service.grant(self.db,self.user,-1000,'shop_redeem')
        self.assertEqual(coin_service.balance(self.db,self.user),10)
        self.assertEqual(before,self.counts())


    def test_retreat_after_review_reuses_event_and_judgment_ids(self):
        ch=m.Challenge(user_id=self.user.id,title='运动',status='accepted',related_attributes=['体能'])
        self.db.add(ch);self.db.commit()
        self.run_llm(lambda:challenge_service.complete(self.db,self.user,ch,'运动完成'))
        eid,jid=ch.event_id,ch.judgment_id
        with patch.object(achievement_service,'check_and_grant',return_value=[]):
            challenge_service.abandon(self.db,self.user,ch)
        self.assertEqual((ch.event_id,ch.judgment_id),(eid,jid))
        self.assertEqual(self.db.query(m.Event).count(),1)
        self.assertEqual(self.db.query(m.AIJudgment).count(),1)
        self.assertEqual(self.db.query(m.JudgmentLog).count(),3)

    def test_challenge_accept_and_expiration_full_chain(self):
        coin_service.grant(self.db,self.user,100,'onboarding_bonus');self.db.commit()
        ch=m.Challenge(user_id=self.user.id,title='运动',deposit=12,coin_reward=20,related_attributes=['体能'],scope='daily',status='candidate')
        self.db.add(ch);self.db.commit()
        challenge_service.accept(self.db,self.user,ch)
        self.assertEqual(coin_service.balance(self.db,self.user),88)
        with self.assertRaises(ValueError):challenge_service.accept(self.db,self.user,ch)
        self.run_llm(lambda:challenge_service.complete(self.db,self.user,ch,'运动完成'))
        with patch.object(achievement_service,'check_and_grant',return_value=[]):
            challenge_service.settle(self.db,self.user,ch)
        self.assertEqual(coin_service.balance(self.db,self.user),120)
        self.assertEqual(self.attr().current_value,52)
        old=m.Challenge(user_id=self.user.id,title='到期',status='accepted',related_attributes=['体能'],expires_at=datetime.now()-timedelta(days=1))
        self.db.add(old);self.db.commit()
        with patch.object(achievement_service,'check_and_grant',return_value=[]):
            challenge_service.expire_stale(self.db,self.user)
        self.assertEqual(old.status,'expired')
        histories=self.db.query(m.AttributeHistory).count()
        challenge_service.expire_stale(self.db,self.user)
        self.assertEqual(histories,self.db.query(m.AttributeHistory).count())

    def test_legacy_invalidated_judgment_does_not_replace_active_judgment(self):
        e=self.event();old=self.judgment(event=e)
        old.status='invalidated';self.db.commit()
        current=self.judgment(event=e)
        result=self.run_llm(lambda:judge_service.judge_event(self.db,e))
        self.assertEqual(result.id,current.id)
        self.assertEqual(old.status,'invalidated')

    def test_model_reward_storage_bound_and_boolean_fallback(self):
        with self.assertRaises(ValueError):challenge_service._parse_reward(2**63,'daily',1)
        self.assertEqual(challenge_service._parse_reward(True,'daily',1)[1],True)
        self.assertEqual(challenge_service._parse_reward(1000000,'daily',1),(1000000,False))


class ConcurrencyAndBackupTests(unittest.TestCase):
    def setUp(self):
        Path('backups').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='v1_11_test_',dir='backups')
        self.engine=create_engine('sqlite:///'+str(Path(self.tmp.name,'isolated.db').resolve()),connect_args={'check_same_thread':False,'timeout':30})
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(bind=self.engine,autoflush=False)
        with self.Session() as db:
            user=seed(db);self.uid=user.id
            e=m.Event(user_id=self.uid,event_type='positive',content='测试')
            db.add(e);db.flush();j=m.AIJudgment(user_id=self.uid,event_id=e.id,status='pending',confidence=1,suggested_changes=[{'name':'体能','delta':2}])
            g=m.Goal(user_id=self.uid,metric='完成',reward=2,penalty=-1)
            db.add_all([j,g]);db.commit();self.jid=j.id;self.gid=g.id

    def tearDown(self):self.engine.dispose();self.tmp.cleanup()

    def parallel(self,n,action):
        barrier=threading.Barrier(n)
        def worker(_):
            with self.Session() as db:
                user=db.get(m.User,self.uid);j=db.get(m.AIJudgment,self.jid);g=db.get(m.Goal,self.gid)
                barrier.wait()
                try:
                    result=action(db,user,j,g);db.commit();return result
                except ValueError:db.rollback();return 'rejected'
        with ThreadPoolExecutor(max_workers=n) as pool:return list(pool.map(worker,range(n)))

    def test_parallel_ten_grants_and_startup_bonus_once(self):
        self.parallel(10,lambda db,u,j,g:coin_service.grant(db,u,10,'event_confirm'))
        with self.Session() as db:
            rows=db.query(m.CoinLedger).order_by(m.CoinLedger.id).all()
            self.assertEqual([r.balance_after for r in rows],list(range(10,101,10)))
            self.assertEqual(db.get(m.UserProfile,1).coins,100)
        result=self.parallel(2,lambda db,u,j,g:coin_service.grant_startup_bonus_if_needed(db,u))
        self.assertEqual(result.count(True),1)
        with self.Session() as db:
            self.assertEqual(db.query(m.CoinLedger).filter_by(source='onboarding_bonus').count(),1)
            self.assertEqual(db.get(m.UserProfile,1).coins,db.query(func.sum(m.CoinLedger.delta)).scalar())

    def test_parallel_confirm_books_once(self):
        result=self.parallel(2,lambda db,u,j,g:judge_service.confirm(db,j))
        self.assertEqual(result.count('rejected'),1)
        with self.Session() as db:
            self.assertEqual(db.query(m.AttributeHistory).count(),1)
            self.assertEqual(db.query(m.Attribute).filter_by(name='体能').one().current_value,52)

    def test_parallel_goal_achieve_books_once(self):
        self.parallel(2,lambda db,u,j,g:goal_service.achieve_goal(db,g))
        with self.Session() as db:self.assertEqual(db.query(m.AttributeHistory).count(),1)

    def test_parallel_first_judgment_leaves_one_current_row(self):
        with self.Session() as db:
            e=m.Event(user_id=self.uid,event_type='positive',content='并发首判')
            db.add(e);db.commit();eid=e.id
        barrier=threading.Barrier(2)
        def llm(*args,**kwargs):
            barrier.wait(timeout=10)
            return RESULT
        with patch.object(judge_service.llm_config,'resolve_llm_config',return_value=CONFIG), \
             patch.object(judge_service.llm_service,'chat_json',side_effect=llm), \
             patch.object(memory_service,'maybe_update_memory',return_value={}):
            results=self.parallel(2,lambda db,u,j,g:judge_service.judge_event(db,db.get(m.Event,eid)))
        self.assertEqual(results.count('rejected'),1)
        with self.Session() as db:
            self.assertEqual(db.query(m.AIJudgment).filter_by(event_id=eid).count(),1)

    def test_parallel_accept_deducts_one_deposit(self):
        with self.Session() as db:
            user=db.get(m.User,self.uid)
            coin_service.grant(db,user,100,'onboarding_bonus')
            ch=m.Challenge(user_id=self.uid,title='并发接受',status='candidate',deposit=12,coin_reward=20)
            db.add(ch);db.commit();cid=ch.id
        results=self.parallel(2,lambda db,u,j,g:challenge_service.accept(db,u,db.get(m.Challenge,cid)))
        self.assertEqual(results.count('rejected'),1)
        with self.Session() as db:
            self.assertEqual(db.get(m.UserProfile,1).coins,88)
            self.assertEqual(db.query(m.CoinLedger).filter_by(source='challenge_deposit').count(),1)

    def test_backup_keeps_old_schema_before_migration(self):
        old=create_engine('sqlite:///'+str(Path(self.tmp.name,'old.db').resolve()))
        with old.begin() as conn:
            conn.execute(text('CREATE TABLE events (id INTEGER PRIMARY KEY, user_id INTEGER, event_type VARCHAR(20))'))
            conn.execute(text("INSERT INTO events VALUES (77,1,'positive')"))
        with patch.object(backup_service,'engine',old),patch.object(backup_service,'BACKUP_DIR',Path(self.tmp.name,'old_copies')):
            backup=backup_service.backup_now()
        migrate_schema(old)
        import sqlite3
        with closing(sqlite3.connect(str(backup))) as conn:
            self.assertEqual([r[1] for r in conn.execute('PRAGMA table_info(events)')],['id','user_id','event_type'])
            self.assertEqual(conn.execute('SELECT id FROM events').fetchall(),[(77,)])
        old.dispose()

    def test_backup_actual_path_distinct_names_and_failures(self):
        target=Path(self.tmp.name,'copies')
        with patch.object(backup_service,'engine',self.engine),patch.object(backup_service,'BACKUP_DIR',target):
            a=backup_service.backup_now();b=backup_service.backup_now()
            self.assertNotEqual(a,b)
            import sqlite3
            with closing(sqlite3.connect(a)) as conn:self.assertEqual(conn.execute('select count(*) from users').fetchone()[0],1)
            with patch.object(Path,'mkdir',side_effect=OSError('denied')):self.assertIsNone(backup_service.backup_now())
            with patch.object(backup_service.sqlite3,'connect',side_effect=OSError('denied')):self.assertIsNone(backup_service.backup_now())
            with patch.object(backup_service,'_cleanup',side_effect=OSError('denied')):self.assertIsNotNone(backup_service.backup_now())
            with patch.object(backup_service.sqlite3,'connect',side_effect=OSError('denied')),patch.object(Path,'unlink',side_effect=OSError('denied')):
                self.assertIsNone(backup_service.backup_now())

    def test_schema_adds_delete_flag_without_rebuilding_old_table(self):
        old=create_engine('sqlite://')
        with old.begin() as conn:
            conn.execute(text('CREATE TABLE events (id INTEGER PRIMARY KEY, user_id INTEGER, event_type VARCHAR(20))'))
            conn.execute(text("INSERT INTO events VALUES (77,1,'positive')"))
        migrate_schema(old)
        with old.connect() as conn:self.assertEqual(conn.execute(text('SELECT id,is_deleted FROM events')).all(),[(77,0)])
        old.dispose()


if __name__=='__main__':unittest.main(verbosity=2)
