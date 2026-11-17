"""v1.13 批次 E：不参照商店价位、不截断幅度、常用券/一次性两种定价方式。"""
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from app.models import ShopItem, User
from app.services import economy_service, pricing_checks
from app.services.time_service import local_day, utc_now
from tests import test_full_system as fixture


class PricingModeTests(unittest.TestCase):
    setUp = fixture.FullSystemTests.setUp
    tearDown = fixture.FullSystemTests.tearDown
    register = fixture.FullSystemTests.register
    configure_model = fixture.FullSystemTests.configure_model
    write = fixture.FullSystemTests.write
    adopt = fixture.FullSystemTests.adopt
    user_id = fixture.FullSystemTests.user_id

    def priced(self, name='奖励', coin=48):
        priced = {'coin_price': coin, 'pricing_reason': '合成依据', 'worth_note': '',
                  'is_timed': False, 'minutes_estimate': None}
        with patch('app.services.llm_service.llm_service.chat_json', return_value=priced):
            response = self.write('/reward-quotes', {'name': name, 'auto_check': True})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['item'], response.json()

    def test_snapshot_drops_shop_price_range_and_old_tiers(self):
        self.register()
        with self.Session() as db:
            text = economy_service.snapshot(db, db.query(User).first())
        self.assertNotIn('商店价位', text)
        self.assertNotIn('6/15/25', text)
        self.assertIn('【金币余额】', text)

    def test_model_price_is_kept_without_truncation(self):
        self.register(); self.configure_model(); self.adopt()
        item, _ = self.priced('画纸', coin=23)
        with self.Session() as db:
            row = db.get(ShopItem, item['id']); row.repriced_on = None; db.commit()
        item = next(i for i in self.client.get('/api/shop/items').json()['items'] if i['id'] == item['id'])
        priced = {'coin_price': 48, 'pricing_reason': '合成升价', 'worth_note': '', 'is_timed': False, 'minutes_estimate': None}
        with patch('app.services.llm_service.llm_service.chat_json', return_value=priced):
            response = self.write('/reward-quotes', {'name': item['name'], 'item_id': item['id'], 'item_version': item['updated_at']})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['result']['coin_price'], 48)
        self.assertEqual(body['result']['previous_price'], 23)
        self.assertEqual(body['result']['change_pct'], round((48 - 23) * 100 / 23))

    def test_only_recurring_items_enter_the_daily_queue(self):
        self.register(); self.configure_model(); self.adopt()
        once, _ = self.priced('一次性', coin=20)
        recurring, _ = self.priced('常用券', coin=20)
        response = self.client.patch('/api/shop/items/' + str(recurring['id']) + '/pricing-mode',
                                     json={'mode': 'recurring', 'expected_version': recurring['updated_at'], 'acknowledge': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['pricing_mode'], 'recurring')
        tomorrow = str(local_day(utc_now(), 'Asia/Shanghai') + timedelta(days=1))
        with patch('app.services.trial_rules.day', return_value=tomorrow):
            queued = self.write('/pricing-checks', {}).json()
        self.assertEqual(queued['queued'], 1)
        with self.Session() as db:
            rows = db.query(ShopItem).filter_by(user_id=self.user_id()).all()
            self.assertEqual([r.pricing_mode for r in rows if r.id == recurring['id']], ['recurring'])
            self.assertEqual([r.pricing_mode for r in rows if r.id == once['id']], ['once'])

    def test_daily_limit_is_ten_not_three(self):
        self.register(); self.configure_model(); uid = self.user_id()
        with self.Session() as db:
            db.add_all([ShopItem(user_id=uid, name='券' + str(n), coin_price=20, enabled=True, pricing_mode='recurring') for n in range(12)]); db.commit()
        queued = self.write('/pricing-checks', {}).json()
        self.assertEqual(queued['queued'], 10)
        self.assertEqual(queued['remaining'], 2)
        self.assertEqual(queued['reason'], 'daily_limit')

    def test_new_wish_keeps_both_switches_consistent(self):
        """v1.13.1 P1-1：新建一律 once，旧列 auto_pricing 不能因为前端传了 auto_check 就变成 True。"""
        self.register(); self.configure_model(); self.adopt()
        item, _ = self.priced('画纸', coin=23)
        self.assertEqual(item['pricing_mode'], 'once')
        self.assertFalse(item['auto_pricing'])
        with self.Session() as db:
            row = db.get(ShopItem, item['id'])
            self.assertEqual(row.pricing_mode, 'once')
            self.assertFalse(row.auto_pricing)

    def test_pricing_mode_is_the_only_switch(self):
        """v1.13.1 P1-1：切到 recurring / 切回 once 时两个字段一起变。"""
        self.register(); self.configure_model(); self.adopt()
        item, _ = self.priced('画纸', coin=23)
        path = '/api/shop/items/' + str(item['id']) + '/pricing-mode'
        to_recurring = self.client.patch(path, json={'mode': 'recurring', 'expected_version': item['updated_at'], 'acknowledge': True})
        self.assertEqual(to_recurring.status_code, 200, to_recurring.text)
        self.assertEqual((to_recurring.json()['pricing_mode'], to_recurring.json()['auto_pricing']), ('recurring', True))
        to_once = self.client.patch(path, json={'mode': 'once', 'expected_version': to_recurring.json()['updated_at'], 'acknowledge': True})
        self.assertEqual(to_once.status_code, 200, to_once.text)
        self.assertEqual((to_once.json()['pricing_mode'], to_once.json()['auto_pricing']), ('once', False))

    def test_old_automatic_pricing_endpoint_is_gone(self):
        """v1.13.1 P1-1：旧入口整个删掉，不留「点了没反应」的别名。"""
        self.register(); self.configure_model(); self.adopt()
        item, _ = self.priced('画纸', coin=23)
        gone = self.client.post('/api/shop/items/' + str(item['id']) + '/automatic-pricing',
                                json={'expected_version': item['updated_at'], 'enabled': True, 'acknowledge': True})
        self.assertEqual(gone.status_code, 404, gone.text)

    def test_archiving_stops_future_repricing(self):
        """停用/移除后恢复，也不能因为旧的 auto_pricing 残留而重新进入重估队列。"""
        self.register(); self.configure_model(); self.adopt()
        item, _ = self.priced('画纸', coin=23)
        recurring = self.client.patch('/api/shop/items/' + str(item['id']) + '/pricing-mode',
                                      json={'mode': 'recurring', 'expected_version': item['updated_at'], 'acknowledge': True})
        self.assertEqual(recurring.status_code, 200, recurring.text)
        removed = self.client.request('DELETE', '/api/shop/items/' + str(item['id']), json={'request_key': str(uuid4()), 'expected_version': recurring.json()['updated_at']})
        self.assertEqual(removed.status_code, 200, removed.text)
        with self.Session() as db:
            row = db.get(ShopItem, item['id'])
            self.assertEqual((row.enabled, row.pricing_mode, row.auto_pricing), (False, 'once', False))
        back = self.client.put('/api/shop/items/' + str(item['id']), json={'enabled': True})
        self.assertEqual(back.status_code, 200, back.text)
        tomorrow = str(local_day(utc_now(), 'Asia/Shanghai') + timedelta(days=1))
        with patch('app.services.trial_rules.day', return_value=tomorrow):
            self.assertEqual(self.write('/pricing-checks', {}).json()['queued'], 0)

    def test_rollback_restores_previous_price_and_freezes(self):
        self.register(); self.configure_model(); self.adopt()
        item, _ = self.priced('常用券', coin=20)
        self.client.patch('/api/shop/items/' + str(item['id']) + '/pricing-mode',
                          json={'mode': 'recurring', 'expected_version': item['updated_at'], 'acknowledge': True})
        with self.Session() as db:
            row = db.get(ShopItem, item['id']); row.repriced_on = None; db.commit()
        fresh = next(i for i in self.client.get('/api/shop/items').json()['items'] if i['id'] == item['id'])
        priced = {'coin_price': 60, 'pricing_reason': '合成升价', 'worth_note': '', 'is_timed': False, 'minutes_estimate': None}
        with patch('app.services.llm_service.llm_service.chat_json', return_value=priced):
            self.write('/reward-quotes', {'name': fresh['name'], 'item_id': fresh['id'], 'item_version': fresh['updated_at']})
        current = next(i for i in self.client.get('/api/shop/items').json()['items'] if i['id'] == item['id'])
        self.assertEqual(current['coin_price'], 60)
        rolled = self.client.post('/api/shop/items/' + str(item['id']) + '/price-rollback', json={'expected_version': current['updated_at']})
        self.assertEqual(rolled.status_code, 200, rolled.text)
        self.assertEqual(rolled.json()['coin_price'], 20)
        self.assertEqual(rolled.json()['pricing_mode'], 'once')
        self.assertEqual(rolled.json()['auto_pricing'], False)
