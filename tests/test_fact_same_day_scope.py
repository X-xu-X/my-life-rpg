"""「是否同一次行动」只在同一内容日范围内判断：每天重复的阅读不跨天合并。"""
import unittest
from datetime import timedelta

from app.models import Event
from app.models.full_system import FactFragment
from app.services import fact_analysis
from app.services.time_service import local_day, utc_now
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
