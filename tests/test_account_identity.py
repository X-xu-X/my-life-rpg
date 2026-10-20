"""Isolated Chinese login and personal/admin identity separation contracts."""
import json
import os
import sys
import unittest
from unittest.mock import patch
from datetime import timedelta
from types import SimpleNamespace
from pydantic import ValidationError
import tests.test_next_iteration as fixtures
from app.models import User, UserProfile, Event, CoinLedger, Attribute, AttributeHistory
from app.models.access import AuthSession, RecoveryToken, Invitation, LLMCredential
from app.models.accounts import EmailToken, AdminAudit
from app.routers.auth import LoginIn
from app.services import auth_service as auth
from app.services.time_service import utc_now
from ops import split_personal_account as split


class AccountIdentityTests(unittest.TestCase):
    setUp = fixtures.CloudTests.setUp
    tearDown = fixtures.CloudTests.tearDown
    register = fixtures.CloudTests.register

    def seed_personal_history(self):
        response = self.client.post('/api/auth/login', json={
            'username': 'owner', 'password': 'test-password-owner'})
        self.assertEqual(response.status_code, 200)
        self.client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        with self.Session() as db:
            source = db.get(User, self.owner_id)
            source.email = 'synthetic-personal@example.test'
            source.email_verified_at = utc_now()
            profile = db.query(UserProfile).filter_by(user_id=source.id).one()
            profile.coins = 55
            profile.onboarding_completed = True
            profile.baseline_kind = 'legacy'
            profile.basic_profile = {'synthetic_private_field': 'SYNTHETIC_PRIVATE_PROFILE'}
            event = Event(user_id=source.id, event_type='other', content='SYNTHETIC_PRIVATE_EVENT', source='journal')
            db.add(event)
            db.flush()
            self.event_id = event.id
            attribute = db.query(Attribute).filter_by(user_id=source.id).first()
            attribute.current_value = 51.5
            db.add(AttributeHistory(user_id=source.id, attribute_id=attribute.id, event_id=event.id,
                delta=1.5, value_after=51.5, reason='synthetic evidence', evidence='synthetic evidence'))
            db.add(CoinLedger(user_id=source.id, delta=55, balance_after=55,
                source='synthetic', reason='synthetic imported balance'))
            db.add(LLMCredential(user_id=source.id, group='judge', provider_id='deepseek',
                model='synthetic-model', encrypted_key='SYNTHETIC_ENCRYPTED_SENTINEL'))
            auth.new_recovery(db, source)
            db.add(EmailToken(user_id=source.id, email=source.email, purpose='recover',
                token_hash=auth.digest('synthetic-mail-token'), credentials_version=source.credentials_version,
                expires_at=utc_now() + timedelta(minutes=30)))
            db.commit()

    def planned(self):
        with self.Session() as db:
            return split.preview(db, 'owner', '旭旭仔', self.owner_id)

    def apply(self, digest=None, password='personal-test-password'):
        digest = digest or self.planned()['personal_state_sha256']
        with self.Session() as db, db.begin():
            return split.apply_split(db, 'owner', '旭旭仔', self.owner_id, digest, password)

    def test_chinese_registration_login_logout_and_existing_ascii_login(self):
        self.register('旭旭仔')
        self.assertEqual(self.client.get('/api/auth/me').json()['username'], '旭旭仔')
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/login', json={
            'username': '旭旭仔', 'password': 'friend-test-password'}).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/login', json={
            'username': 'owner', 'password': 'test-password-owner'}).status_code, 200)

    def test_username_bounds_and_unsupported_characters_still_rejected(self):
        for username in ('xx', '旭旭', '汉' * 51, 'abc def', 'abc<script>', 'abc/def', 'abc😀'):
            with self.subTest(username=username), self.assertRaises(ValidationError):
                LoginIn(username=username, password='synthetic-password')
        for username in ('旭旭仔', 'owner', 'a_b-01', 'abc旭旭仔'):
            self.assertEqual(LoginIn(username=username, password='synthetic-password').username, username)

    def test_preview_is_read_only_and_does_not_expose_private_content(self):
        self.seed_personal_history()
        with self.Session() as db:
            before = split.personal_state(db, self.owner_id)
            users = db.query(User).count()
        plan = self.planned()
        self.assertEqual(plan['mode'], 'READ_ONLY_PREVIEW')
        self.assertEqual(plan['personal_state_sha256'], before['sha256'])
        self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps(plan))
        self.assertNotIn('SYNTHETIC_ENCRYPTED', json.dumps(plan))
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), users)
            self.assertEqual(db.get(User, self.owner_id).role, 'owner')
            self.assertEqual(split.personal_state(db, self.owner_id), before)

    def test_split_preserves_all_personal_rows_ids_points_coins_and_credentials(self):
        self.seed_personal_history()
        plan = self.planned()
        result = self.apply()
        self.assertEqual(result['personal_user_id'], self.owner_id)
        self.assertNotEqual(result['admin_user_id'], self.owner_id)
        self.assertEqual(result['personal_state_sha256'], plan['personal_state_sha256'])
        with self.Session() as db:
            personal = db.get(User, self.owner_id)
            admin = db.query(User).filter_by(username='owner').one()
            self.assertEqual((personal.username, personal.role), ('旭旭仔', 'user'))
            self.assertTrue(auth.verify_password(personal, 'personal-test-password'))
            self.assertTrue(auth.verify_password(admin, 'test-password-owner'))
            self.assertIsNone(admin.email)
            self.assertEqual(personal.email, 'synthetic-personal@example.test')
            self.assertEqual(db.get(Event, self.event_id).user_id, self.owner_id)
            self.assertEqual(db.query(UserProfile).filter_by(user_id=self.owner_id).one().coins, 55)
            self.assertEqual(db.query(Attribute).filter_by(user_id=admin.id).count(), 0)
            self.assertEqual(db.query(CoinLedger).filter_by(user_id=admin.id).count(), 0)
            self.assertEqual(db.query(AdminAudit).filter_by(action='split-personal-identity').count(), 1)

    def test_old_sessions_recovery_email_and_pending_invitation_revoked(self):
        self.seed_personal_history()
        with self.Session() as db:
            old_recovery = {r.id for r in db.query(RecoveryToken)}
        result = self.apply()
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)
        with self.Session() as db:
            self.assertTrue(all(r.revoked for r in db.query(AuthSession).filter_by(user_id=self.owner_id)))
            self.assertTrue(all(r.consumed_at for r in db.query(RecoveryToken).filter(RecoveryToken.id.in_(old_recovery))))
            self.assertTrue(all(r.consumed_at for r in db.query(EmailToken).filter_by(user_id=self.owner_id)))
            self.assertTrue(all(r.consumed_at for r in db.query(Invitation).filter_by(creator_id=self.owner_id)))
            for key, uid in [('personal_recovery_code', self.owner_id), ('admin_recovery_code', result['admin_user_id'])]:
                token = db.query(RecoveryToken).filter_by(token_hash=auth.digest(result[key]), user_id=uid).one()
                self.assertIsNone(token.consumed_at)

    def test_split_logins_use_distinct_roles_and_admin_cannot_read_personal_events(self):
        self.seed_personal_history()
        self.apply()
        response = self.client.post('/api/auth/login', json={'username': '旭旭仔', 'password': 'personal-test-password'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').json()['role'], 'user')
        self.assertEqual(self.client.get('/api/admin/overview').status_code, 403)
        self.assertIn(self.event_id, [row['id'] for row in self.client.get('/api/events').json()])
        response = self.client.post('/api/auth/login', json={'username': 'owner', 'password': 'test-password-owner'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').json()['role'], 'owner')
        self.assertEqual(self.client.get('/api/admin/overview').status_code, 200)
        self.assertEqual(self.client.get('/api/events').json(), [])

    def test_existing_target_account_refused_without_overwriting(self):
        self.seed_personal_history()
        with self.Session() as db:
            auth.initialize_account(db, '旭旭仔', 'existing-target-password')
            db.commit()
        with self.assertRaisesRegex(split.SplitError, 'PERSONAL_USERNAME_ALREADY_EXISTS'):
            self.apply('0' * 64)
        with self.Session() as db:
            self.assertEqual(db.get(User, self.owner_id).username, 'owner')
            self.assertTrue(auth.verify_password(db.query(User).filter_by(username='旭旭仔').one(), 'existing-target-password'))

    def test_changed_data_fingerprint_or_same_password_refused(self):
        self.seed_personal_history()
        for digest, password, category in [('0' * 64, 'personal-test-password', 'PERSONAL_DATA_CHANGED'),
                (self.planned()['personal_state_sha256'], 'test-password-owner', 'PERSONAL_PASSWORD_MUST_DIFFER')]:
            with self.subTest(category=category), self.assertRaisesRegex(split.SplitError, category):
                self.apply(digest, password)
        with self.Session() as db:
            self.assertEqual(db.get(User, self.owner_id).username, 'owner')
            self.assertEqual(db.query(User).count(), 1)

    def test_invariant_failure_rolls_back_identity_and_security_changes(self):
        self.seed_personal_history()
        planned = self.planned()
        original = split.personal_state
        calls = 0
        def unexpected_change(db, uid):
            nonlocal calls
            calls += 1
            value = original(db, uid)
            if calls == 2:
                value['sha256'] = '0' * 64
            return value
        with patch.object(split, 'personal_state', side_effect=unexpected_change):
            with self.assertRaisesRegex(split.SplitError, 'PERSONAL_DATA_INVARIANT_FAILED'):
                self.apply(planned['personal_state_sha256'])
        with self.Session() as db:
            self.assertEqual(db.query(User).count(), 1)
            self.assertEqual((db.get(User, self.owner_id).username, db.get(User, self.owner_id).role), ('owner', 'owner'))
            self.assertEqual(db.query(AdminAudit).count(), 0)
            self.assertTrue(all(not row.revoked for row in db.query(AuthSession)))
            self.assertEqual(split.personal_state(db, self.owner_id)['sha256'], planned['personal_state_sha256'])

    def test_wrong_source_id_refused_without_changes(self):
        self.seed_personal_history()
        with self.Session() as db, self.assertRaisesRegex(split.SplitError, 'SOURCE_IDENTITY_MISMATCH'):
            split.preview(db, 'owner', '旭旭仔', self.owner_id + 1)

    def test_cli_refuses_non_postgresql_before_opening_database(self):
        with patch.object(sys, 'argv', ['split', '--personal-username', '旭旭仔', '--expected-source-id', '1']):
            with self.assertRaisesRegex(split.SplitError, 'EXPLICIT_CLOUD_POSTGRESQL_REQUIRED'):
                split.main()

    def test_cli_apply_requires_reviewed_hash_and_interactive_terminal(self):
        base = ['split', '--personal-username', '旭旭仔', '--expected-source-id', '1', '--apply']
        with patch('app.database.engine', SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))), patch.dict(os.environ, {'DB_URL': 'synthetic-explicit-url'}):
            with patch.object(sys, 'argv', base), self.assertRaisesRegex(split.SplitError, 'REVIEWED_PERSONAL_SHA256_REQUIRED'):
                split.main()
            with patch.object(sys, 'argv', base + ['--approve-personal-sha256', '0' * 64]), patch.object(sys.stdin, 'isatty', return_value=False):
                with self.assertRaisesRegex(split.SplitError, 'INTERACTIVE_TERMINAL_REQUIRED'):
                    split.main()


if __name__ == '__main__':
    unittest.main()
