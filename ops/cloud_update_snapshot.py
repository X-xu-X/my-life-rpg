"""Read-only b025 update proof; output counts/hashes only, never row content."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def compare(before, after):
    if before != after:
        raise ValueError('DATABASE_SNAPSHOT_CHANGED')
    return {'status': 'DATA_UNCHANGED', 'head': after['head'],
            'tables_checked': len(after['tables']), 'sequences_unchanged': True,
            'credential_rows_checked': after['credential_rows_checked']}


def capture():
    from sqlalchemy import text
    from app.config import settings
    from app.database import engine
    from app.models.access import LLMCredential
    from app.services.credentials import keyring, decrypt
    from ops.db_manifest import collect
    from sqlalchemy.orm import Session
    if not settings.cloud or engine.dialect.name != 'postgresql':
        raise ValueError('CLOUD_POSTGRESQL_REQUIRED')
    if (engine.url.host, engine.url.database, engine.url.username) != ('db', 'game_of_life', 'gol_app'):
        raise ValueError('DATABASE_TARGET_CHANGED')
    keyring()
    with engine.connect() as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
            heads = sorted(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
            if heads != ['b025_daily_use']:
                raise ValueError('DATABASE_NOT_B025')
            tables = collect(connection)
            sequences = [dict(row) for row in connection.execute(text(
                'SELECT sequencename,last_value FROM pg_sequences WHERE schemaname=current_schema() ORDER BY sequencename')).mappings()]
            with Session(bind=connection) as db:
                rows = db.query(LLMCredential).all()
                for row in rows:
                    if row.encrypted_key:
                        decrypt(row)
                credential_count = len(rows)
    return {'head': heads, 'tables': tables, 'sequences': sequences,
            'credential_rows_checked': credential_count}


if __name__ == '__main__':
    try:
        result = capture()
        if len(sys.argv) == 2:
            result = compare(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')), result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        code = str(exc) if type(exc) is ValueError and str(exc).replace('_', '').isupper() else type(exc).__name__
        print(json.dumps({'status': 'UPDATE_PROOF_FAILED', 'code': code}))
        raise SystemExit(2)
