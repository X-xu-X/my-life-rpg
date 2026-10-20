"""Split an imported owner's personal identity without moving any business rows.

Default is a read-only preview. Apply requires a reviewed source ID and fingerprint,
an interactive terminal, and a separate password for the personal account. Run during
maintenance with the API and worker stopped, through the production entrypoint.
"""
import argparse
import getpass
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text
from app.database import Base
from app.models import User, UserProfile
import app.models.accounts
import app.models.analysis
import app.models.full_system
import app.models.workflow
from app.models.access import AuthSession, RecoveryToken, Invitation
from app.models.accounts import AdminAudit, EmailToken
from app.services import auth_service as auth
from app.services.time_service import utc_now


class SplitError(ValueError):
    pass


def _validate_username(username):
    # Reuse exactly the HTTP login/registration contract, including Chinese names.
    from app.routers.auth import LoginIn
    try:
        LoginIn(username=username, password='validation-only-placeholder')
    except ValueError:
        raise SplitError('INVALID_PERSONAL_USERNAME') from None


def personal_state(db, user_id):
    """Fingerprint all modeled personal rows; never return their private contents."""
    ignored = {'auth_sessions', 'recovery_tokens', 'email_tokens'}
    counts = {}
    fingerprint = hashlib.sha256()
    for name, table in sorted(Base.metadata.tables.items()):
        if name in ignored or 'user_id' not in table.c:
            continue
        rows = [dict(row) for row in db.execute(select(table).where(
            table.c.user_id == user_id).order_by(*table.primary_key.columns)).mappings()]
        counts[name] = len(rows)
        fingerprint.update(json.dumps([name, rows], ensure_ascii=False, sort_keys=True,
            separators=(',', ':'), default=str).encode('utf-8'))
    return {'sha256': fingerprint.hexdigest(), 'counts': counts}


def preview(db, source_username, personal_username, expected_source_id, *, lock=False):
    _validate_username(personal_username)
    if personal_username == source_username:
        raise SplitError('DISTINCT_USERNAMES_REQUIRED')
    query = select(User).where(User.username == source_username)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    source = db.execute(query).scalar_one_or_none()
    if not source or source.id != expected_source_id or source.role != 'owner' or source.status != 'active':
        raise SplitError('SOURCE_IDENTITY_MISMATCH')
    if db.execute(select(User.id).where(User.username == personal_username)).first():
        raise SplitError('PERSONAL_USERNAME_ALREADY_EXISTS')
    profile_query = select(UserProfile).where(UserProfile.user_id == source.id)
    if lock:
        profile_query = profile_query.with_for_update()
    if db.execute(profile_query).scalar_one_or_none() is None:
        raise SplitError('SOURCE_PROFILE_MISSING')
    if not source.password_hash:
        raise SplitError('SOURCE_ADMIN_PASSWORD_MISSING')
    state = personal_state(db, source.id)
    return {'mode': 'READ_ONLY_PREVIEW', 'source_user_id': source.id,
        'personal_username': personal_username, 'admin_username': source_username,
        'personal_state_sha256': state['sha256'],
        'preserved_counts': {name: count for name, count in state['counts'].items() if count},
        'plan': 'Keep source ID and all personal data; rename it and remove admin role. Create a distinct admin ID with the original admin login/password. Revoke old sessions, recovery codes and pending invitations; generate new recovery codes for both accounts.'}


def apply_split(db, source_username, personal_username, expected_source_id, approved_sha256, personal_password):
    """Caller owns the transaction; an invariant failure rolls everything back."""
    if not 12 <= len(personal_password) <= 256:
        raise SplitError('PERSONAL_PASSWORD_LENGTH')
    planned = preview(db, source_username, personal_username, expected_source_id, lock=True)
    if approved_sha256 != planned['personal_state_sha256']:
        raise SplitError('PERSONAL_DATA_CHANGED_SINCE_PREVIEW')
    source = db.get(User, expected_source_id)
    if auth.verify_password(source, personal_password):
        raise SplitError('PERSONAL_PASSWORD_MUST_DIFFER_FROM_ADMIN')
    admin_password_hash = source.password_hash
    source.username = personal_username
    source.role = 'user'
    source.password_hash = auth.PASSWORDS.hash(personal_password)
    source.credentials_version += 1
    db.flush()  # Release the original admin username inside the same transaction.
    admin = User(username=source_username, role='owner', status='active',
        password_hash=admin_password_hash, timezone=source.timezone)
    db.add(admin)
    db.flush()
    # A management identity gets no personal attributes, coins, or shop awards.
    db.add(UserProfile(user_id=admin.id, coins=0, onboarding_completed=False))
    now = utc_now()
    db.query(AuthSession).filter_by(user_id=source.id).update({AuthSession.revoked: True})
    for model in (RecoveryToken, EmailToken):
        db.query(model).filter_by(user_id=source.id, consumed_at=None).update({model.consumed_at: now})
    db.query(Invitation).filter_by(creator_id=source.id, consumed_at=None).update({Invitation.consumed_at: now})
    personal_recovery = auth.new_recovery(db, source)
    admin_recovery = auth.new_recovery(db, admin)
    db.add(AdminAudit(actor_id=admin.id, action='split-personal-identity',
        target=f'user:{source.id}', version=source.credentials_version,
        reason=f'Keep imported personal data on ID {source.id}; personal login {personal_username}; separate management login {source_username}.'))
    db.flush()
    after = personal_state(db, source.id)
    if after['sha256'] != approved_sha256:
        raise SplitError('PERSONAL_DATA_INVARIANT_FAILED')
    return {'status': 'PASS', 'personal_user_id': source.id, 'personal_username': personal_username,
        'admin_user_id': admin.id, 'admin_username': source_username,
        'personal_state_sha256': after['sha256'], 'preserved_counts': planned['preserved_counts'],
        'personal_recovery_code': personal_recovery, 'admin_recovery_code': admin_recovery}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-username', default='owner')
    parser.add_argument('--personal-username', required=True)
    parser.add_argument('--expected-source-id', type=int, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-personal-sha256')
    args = parser.parse_args()
    from app.config import settings
    from app.database import engine, SessionLocal
    if not os.environ.get('DB_URL') or not settings.cloud or engine.dialect.name != 'postgresql':
        raise SplitError('EXPLICIT_CLOUD_POSTGRESQL_REQUIRED')
    if not args.apply:
        with SessionLocal() as db:
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            result = preview(db, args.source_username, args.personal_username, args.expected_source_id)
            db.rollback()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not args.approve_personal_sha256:
        raise SplitError('REVIEWED_PERSONAL_SHA256_REQUIRED')
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SplitError('INTERACTIVE_TERMINAL_REQUIRED')
    password = getpass.getpass('日常账号的新密码（12–256字符，须与管理密码不同）：')
    if password != getpass.getpass('再次输入日常账号密码：'):
        raise SplitError('PASSWORD_CONFIRMATION_MISMATCH')
    with SessionLocal() as db, db.begin():
        result = apply_split(db, args.source_username, args.personal_username,
            args.expected_source_id, args.approve_personal_sha256, password)
    print('请私下保存以下两份恢复码；不要把它们发到聊天或截图中。')
    print('日常账号恢复码：' + result.pop('personal_recovery_code'))
    print('管理账号恢复码：' + result.pop('admin_recovery_code'))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except SplitError as exc:
        print('ACCOUNT_SPLIT_STOPPED: ' + str(exc), file=sys.stderr)
        raise SystemExit(2) from None
    except (Exception, KeyboardInterrupt):
        print('ACCOUNT_SPLIT_FAILED: transaction not confirmed; inspect safely before retrying.', file=sys.stderr)
        raise SystemExit(2) from None
