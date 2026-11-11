"""「是否同一次行动」只在同一内容日范围内判断：每天重复的阅读不跨天合并。"""
import unittest
from datetime import timedelta

from app.models import Event
from app.models.full_system import FactFragment
from app.services import fact_analysis
from app.services.time_service import local_day, utc_now
from tests import test_full_system as fixture
from tests.test_reward_incident import RewardIncidentTests


class SameDayScopeTests(RewardIncidentTests):
    def make_yesterday(self, event_id):
        """Turn a record into yesterday's without leaving today's fingerprint behind."""
        day = str(local_day(utc_now(), 'Asia/Shanghai') - timedelta(days=1))
        with self.Session() as db:
            row = db.get(Event, event_id)
            row.occurred_on = day
            for fragment in db.query(FactFragment).filter_by(event_id=event_id).all():
                fragment.fingerprint = fact_analysis.digest(db, row.user_id, day, fragment.excerpt)
            db.commit()

    def test_identical_text_on_another_day_is_a_new_action_and_never_asks(self):
        self.ready()
        yesterday = self.event('阅读30分钟', 'allowed')
        self.assertEqual(self.settle(self.preview(self.facts(yesterday, [self.suggestion('阅读30分钟')]))).status_code, 200)
        self.make_yesterday(yesterday['id'])

        today = self.event('阅读30分钟', 'allowed')
        item = self.facts(today, [self.suggestion('阅读30分钟', relation='same', related_event_id=yesterday['id'])])['payload']['items'][0]
        self.assertIsNone(item['candidate_fact_id'])
        self.assertEqual(item['decision'], 'keep')
        self.assertEqual(item['candidate_options'], [])

    def test_identical_text_on_the_same_day_still_asks_before_double_booking(self):
        self.ready()
        first = self.event('阅读30分钟', 'allowed')
        self.settle(self.preview(self.facts(first, [self.suggestion('阅读30分钟')])))

        second = self.event('阅读30分钟', 'allowed')
        item = self.facts(second, [self.suggestion('阅读30分钟', relation='same', related_event_id=first['id'])])['payload']['items'][0]
        self.assertIsNotNone(item['candidate_fact_id'])
        self.assertEqual(item['decision'], 'unresolved')


class EventOptionScopeTests(unittest.TestCase):
    """选择已有事件的列表默认只给当天，更早的必须显式搜索。"""

    setUp = fixture.FullSystemTests.setUp
    tearDown = fixture.FullSystemTests.tearDown
    register = fixture.FullSystemTests.register
    configure_model = fixture.FullSystemTests.configure_model
    event = fixture.FullSystemTests.event

    def test_default_list_is_today_only_and_search_reaches_older_records(self):
        self.register(); self.configure_model()
        self.client.post('/api/onboarding/neutral', json={'acknowledge': True})
        old = self.event('上个月的阅读记录', 'allowed')
        with self.Session() as db:
            db.get(Event, old['id']).occurred_on = '2026-10-01'
            db.commit()
        today = self.event('今天的阅读记录', 'allowed')

        listed = [row['id'] for row in self.client.get('/api/event-options').json()['items']]
        self.assertIn(today['id'], listed)
        self.assertNotIn(old['id'], listed, '默认列表不应铺出很早的历史')

        searched = [row['id'] for row in self.client.get('/api/event-options?q=上个月的阅读').json()['items']]
        self.assertIn(old['id'], searched, '关键词搜索应能取回更早的记录')


if __name__ == '__main__':
    unittest.main(verbosity=2)
