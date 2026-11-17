"""Read-only release rehearsal on an isolated restored database.

Runs inside the release image against a private PostgreSQL copy. Proves that the
backup restores, the application role can read it, credentials still decrypt and
the restored revision is one this release knows. Never writes business data and
never calls a real model.

`capture(require_head=False)`: 彩排用的是**迁移前**的备份，库里还是旧 revision，
不能要求它等于本包的 head，否则每次带迁移的发布都会在彩排阶段被拒。
"""

The retired event-35 reward-repair assertions lived only in the 2026-10-25
one-off compensation release; retrieve them from git history if ever needed.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    if os.environ.get('LIFEXP_ISOLATED_REHEARSAL') != 'public-update-copy-only':
        raise ValueError('ISOLATED_REHEARSAL_REQUIRED')
    from app.services.llm_service import llm_service
    from ops.cloud_update_snapshot import capture

    def blocked(*args, **kwargs):
        raise ValueError('REAL_MODEL_FORBIDDEN_IN_REHEARSAL')

    llm_service.chat = llm_service.chat_json = blocked
    # capture() enforces cloud PostgreSQL, host=db, database=game_of_life,
    # username=gol_app and a revision this release knows. Its transaction is READ ONLY;
    # table/sequence counts and credential decryption emit no row content.
    snapshot = capture(require_head=False)
    if not snapshot['tables']:
        raise ValueError('RESTORED_TABLES_MISSING')
    return {'status': 'ISOLATED_PG_REHEARSAL_PASS', 'head': snapshot['head'],
            'restored_tables': len(snapshot['tables']),
            'sequences_checked': len(snapshot['sequences']),
            'credential_rows_checked': snapshot['credential_rows_checked'],
            'application_role': 'gol_app', 'database_access': 'READ_ONLY',
            'business_writes': 'NONE', 'real_supplier': 'NOT_CALLED',
            'production_database_connection': 'NONE'}


if __name__ == '__main__':
    try:
        print(json.dumps(run(), ensure_ascii=False))
    except Exception as exc:
        code = str(exc) if type(exc) is ValueError and str(exc).replace('_', '').isupper() else type(exc).__name__
        print(json.dumps({'status': 'REHEARSAL_STOPPED', 'code': code}))
        raise SystemExit(2)
