"""v1.13 批次 F：取消的目标可以恢复，且不重算点数。"""
import unittest
from uuid import uuid4

from tests import test_full_system as fixture


class GoalRestoreTests(unittest.TestCase):
    setUp = fixture.FullSystemTests.setUp
    tearDown = fixture.FullSystemTests.tearDown
    register = fixture.FullSystemTests.register
    write = fixture.FullSystemTests.write
    adopt = fixture.FullSystemTests.adopt

    def test_cancelled_goal_can_be_restored_with_audit(self):
        self.register(); self.adopt()
        goal = self.client.post('/api/goals', json={'description': '恢复测试目标', 'metric': '十章'}).json()
        cancelled = self.client.post(f"/api/goals/{goal['id']}/cancel", json={'request_key': str(uuid4()), 'expected_version': goal['updated_at']})
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()['status'], 'cancelled')
        restored = self.client.post(f"/api/goals/{goal['id']}/restore", json={'request_key': str(uuid4()), 'expected_version': cancelled.json()['updated_at']})
        self.assertEqual(restored.status_code, 200, restored.text)
        body = restored.json()
        self.assertEqual(body['status'], 'active')
        self.assertEqual(body['audit'][-1]['action'], 'restore')
        self.assertEqual([g['status'] for g in self.client.get('/api/goals').json()], ['active'])

    def test_only_cancelled_goals_can_be_restored(self):
        self.register(); self.adopt()
        goal = self.client.post('/api/goals', json={'description': '进行中的目标', 'metric': '五章'}).json()
        response = self.client.post(f"/api/goals/{goal['id']}/restore", json={'request_key': str(uuid4()), 'expected_version': goal['updated_at']})
        self.assertEqual(response.status_code, 409, response.text)
