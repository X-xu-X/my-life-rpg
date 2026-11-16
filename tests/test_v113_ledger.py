"""v1.13 批次 B：流水按天归组所需字段（kind/day）与行动摘要。"""
import unittest

from app.services.time_service import local_day, utc_now
from tests import test_full_system as fixture


class LedgerDetailTests(unittest.TestCase):
    setUp = fixture.FullSystemTests.setUp
    tearDown = fixture.FullSystemTests.tearDown
    register = fixture.FullSystemTests.register
    configure_model = fixture.FullSystemTests.configure_model
    write = fixture.FullSystemTests.write
    adopt = fixture.FullSystemTests.adopt
    event = fixture.FullSystemTests.event
    facts = fixture.FullSystemTests.facts
    suggestion = fixture.FullSystemTests.suggestion
    preview = fixture.FullSystemTests.preview
    settle = fixture.FullSystemTests.settle

    def test_event_award_carries_kind_day_and_action_summary(self):
        self.register(); self.configure_model(); self.adopt()
        record = self.event('整理读书笔记', 'allowed')
        group = self.facts(record, [self.suggestion(record['content'], coins=12)])
        self.assertEqual(self.settle(self.preview(group)).status_code, 200)
        ledger = self.client.get('/api/coins').json()['ledger']
        row = next(r for r in ledger if r['source'] == 'trial_action')
        self.assertEqual(row['kind'], 'event')
        self.assertEqual(row['day'], str(local_day(utc_now(), 'Asia/Shanghai')))
        # 人读的一行是行动摘要，不再拼接规则版本号
        self.assertEqual(row['reason'], '根据实际行为提出建议')
        self.assertEqual(row['delta'], 12)

    def test_diary_award_grouped_as_diary_and_zero_award_writes_no_ledger(self):
        self.register(); self.configure_model(); self.adopt()
        day = str(local_day(utc_now(), 'Asia/Shanghai'))
        diary = self.write('/diaries/' + day, {'content': '读完一章并做了笔记', 'ai_permission': 'allowed'}, 0, 'PUT').json()['diary']
        group = self.facts(diary, [self.suggestion('读完一章并做了笔记', coins=9)])
        self.assertEqual(self.settle(self.preview(group)).status_code, 200)
        zero = self.event('只是记录心情', 'allowed')
        group = self.facts(zero, [self.suggestion(zero['content'], coins=0, changes=[])])
        self.assertEqual(self.settle(self.preview(group)).status_code, 200)
        ledger = self.client.get('/api/coins').json()['ledger']
        trial = [r for r in ledger if r['source'] == 'trial_action']
        self.assertEqual(len(trial), 1)
        self.assertEqual(trial[0]['kind'], 'diary')
        self.assertEqual(trial[0]['day'], day)
