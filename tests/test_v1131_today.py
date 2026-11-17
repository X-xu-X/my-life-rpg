"""v1.13.1 批次 K：把「今日已得」改成当日全口径。

上限取消后这个数只用于显示，必须把手账、首记、挑战、成就都算进来；
启动资金不算「今天赚的」，不能把 80 币算进第一天的已得。
"""
import unittest

from app.models import User
from app.services import coin_service
from app.services.time_service import local_day, utc_now
from tests import test_full_system as fixture


class DayTotalTests(unittest.TestCase):
    setUp = fixture.FullSystemTests.setUp
    tearDown = fixture.FullSystemTests.tearDown
    register = fixture.FullSystemTests.register

    def test_day_total_sums_every_earning_and_skips_startup_capital(self):
        uid = self.register()['id']
        self.client.post('/api/onboarding/neutral', json={'acknowledge': True})
        with self.Session() as db:
            user = db.get(User, uid)
            coin_service.grant(db, user, 80, 'onboarding_bonus', '启动资金')
            coin_service.grant(db, user, 25, 'trial_action', '经本人确认的有效行动')
            coin_service.grant(db, user, 3, 'daily_first_record', '首记')
            coin_service.grant(db, user, 40, 'challenge_reward', '挑战完成')
            coin_service.grant(db, user, -10, 'shop_redeem', '兑换奖励')
            db.commit()
            day = str(local_day(utc_now(), user.timezone))
            self.assertEqual(coin_service.day_total(db, user, day), 68)

    def test_trial_endpoint_uses_the_new_total(self):
        uid = self.register()['id']
        self.client.post('/api/onboarding/neutral', json={'acknowledge': True})
        with self.Session() as db:
            user = db.get(User, uid)
            coin_service.grant(db, user, 25, 'trial_action', '经本人确认的有效行动')
            coin_service.grant(db, user, 3, 'daily_first_record', '首记')
            db.commit()
            day = str(local_day(utc_now(), user.timezone))
        body = self.client.get('/api/trial').json()
        self.assertEqual(body['today'], day)
        self.assertEqual(body['action_used'], 28)


if __name__ == '__main__':
    unittest.main()
