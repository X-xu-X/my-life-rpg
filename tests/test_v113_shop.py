"""v1.13 批次 D：心愿表单不再让用户选形式/填分钟；时长估值可改且不影响价格。"""
import unittest
from unittest.mock import patch

from tests import test_full_system as fixture


class ShopFormTests(unittest.TestCase):
    setUp = fixture.FullSystemTests.setUp
    tearDown = fixture.FullSystemTests.tearDown
    register = fixture.FullSystemTests.register
    configure_model = fixture.FullSystemTests.configure_model
    write = fixture.FullSystemTests.write
    adopt = fixture.FullSystemTests.adopt

    def test_quote_without_form_kind_or_minutes_is_timed_by_model(self):
        self.register(); self.configure_model(); self.adopt()
        priced = {'coin_price': 48, 'pricing_reason': '按投入与稀缺度', 'worth_note': '可以换',
                  'is_timed': True, 'minutes_estimate': 200}
        with patch('app.services.llm_service.llm_service.chat_json', return_value=priced):
            response = self.write('/reward-quotes', {'name': '连着玩三小时左右', 'description': '想连着玩三小时左右', 'auto_check': True})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['item']['duration_seconds'], 200 * 60)
        self.assertEqual(body['item']['coin_price'], 48)

    def test_estimate_can_be_edited_without_touching_price(self):
        self.register(); self.configure_model(); self.adopt()
        priced = {'coin_price': 30, 'pricing_reason': '合成依据', 'worth_note': '可以换',
                  'is_timed': True, 'minutes_estimate': 60}
        with patch('app.services.llm_service.llm_service.chat_json', return_value=priced):
            item = self.write('/reward-quotes', {'name': '一小时游戏', 'auto_check': True}).json()['item']
        response = self.client.put('/api/shop/items/' + str(item['id']), json={'duration_minutes': 120})
        self.assertEqual(response.status_code, 200, response.text)
        changed = next(i for i in self.client.get('/api/shop/items').json()['items'] if i['id'] == item['id'])
        self.assertEqual(changed['duration_seconds'], 7200)
        self.assertEqual(changed['coin_price'], 30)
        self.assertEqual(changed['pricing_reason'], '合成依据')

    def test_invalid_estimate_does_not_make_item_timed(self):
        self.register(); self.configure_model(); self.adopt()
        priced = {'coin_price': 12, 'pricing_reason': '合成依据', 'worth_note': '',
                  'is_timed': True, 'minutes_estimate': 9999}
        with patch('app.services.llm_service.llm_service.chat_json', return_value=priced):
            item = self.write('/reward-quotes', {'name': '不确定时长', 'auto_check': True}).json()['item']
        self.assertIsNone(item['duration_seconds'])
