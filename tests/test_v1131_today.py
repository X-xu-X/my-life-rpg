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
    configure_model = fixture.FullSystemTests.configure_model
    adopt = fixture.FullSystemTests.adopt
    write = fixture.FullSystemTests.write
    event = fixture.FullSystemTests.event
    facts = fixture.FullSystemTests.facts
    suggestion = fixture.FullSystemTests.suggestion
    preview = fixture.FullSystemTests.preview

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

    def test_analysis_preview_uses_the_same_total_as_settings_page(self):
        """设置页读 /api/trial，分析页读 preview.used——两处必须是同一个数（B-84）。"""
        uid = self.register()['id']
        self.configure_model(); self.adopt()
        with self.Session() as db:
            user = db.get(User, uid)
            coin_service.grant(db, user, 25, 'trial_action', '经本人确认的有效行动')
            coin_service.grant(db, user, 3, 'daily_first_record', '首记')
            db.commit()
        record = self.event('整理读书笔记', 'allowed')
        group = self.facts(record, [self.suggestion(record['content'], coins=12)])
        # bundle 的 JSON 列 `preview` 里才是 used / items / total
        preview = self.preview(group)['preview']
        self.assertEqual(preview['used'], 28)
        self.assertEqual(self.client.get('/api/trial').json()['action_used'], preview['used'])


if __name__ == '__main__':
    unittest.main()
