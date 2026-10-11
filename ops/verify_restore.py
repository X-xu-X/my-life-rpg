"""只读校验独立恢复库、迁移头和另存密钥。"""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ops.db_manifest import manifest


def verify(url, expected, key_file):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.config import settings
    from app.models.access import LLMCredential
    from app.services.credentials import decrypt
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    if manifest(url)!=expected: raise RuntimeError('恢复库计数或内容哈希不一致。')
    settings.credential_key_file=key_file
    engine=create_engine(url)
    with Session(engine) as db:
        heads=set(db.execute(text('SELECT version_num FROM alembic_version')).scalars())
        expected_heads=set(ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))).get_heads())
        if heads!=expected_heads: raise RuntimeError('迁移版本不一致。')
        checked=0
        for row in db.query(LLMCredential).all():
            if row.encrypted_key:
                if not decrypt(row): raise RuntimeError('密钥恢复失败。')
                checked+=1
    engine.dispose()
    return {'tables_verified':len(expected),'credentials_decrypted':checked,'migration_heads':sorted(heads)}


if __name__=='__main__':
    if len(sys.argv)!=2 or not os.environ.get('DB_URL') or not os.environ.get('CREDENTIAL_KEY_FILE'):
        raise SystemExit('用法：DB_URL=... CREDENTIAL_KEY_FILE=... python ops/verify_restore.py manifest.json')
    print(json.dumps(verify(os.environ['DB_URL'],json.loads(Path(sys.argv[1]).read_text()),os.environ['CREDENTIAL_KEY_FILE'])))
