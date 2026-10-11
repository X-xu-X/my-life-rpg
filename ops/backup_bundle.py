"""pg_dump 与对照清单共享只读快照，不依赖停写或暴露 DSN 到命令行。"""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from sqlalchemy import create_engine, text
from db_manifest import collect


def bundle(url, base, service, pg_dump='pg_dump'):
    engine=create_engine(url, isolation_level='REPEATABLE READ')
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        snapshot=connection.execute(text('SELECT pg_export_snapshot()')).scalar_one()
        dump=Path(str(base)+'.dump')
        if any(Path(str(base)+suffix).exists() or Path(str(base)+suffix).is_symlink()
               for suffix in ('.dump','.manifest.json','.sha256')): raise RuntimeError('拒绝覆盖已有备份。')
        subprocess.run([pg_dump,'--dbname='+service,'--format=custom','--no-owner','--no-acl',
            '--snapshot='+snapshot,'--file='+str(dump)],check=True,capture_output=True)
        data=collect(connection)
        with Path(str(base)+'.manifest.json').open('x',encoding='utf-8') as output:output.write(json.dumps(data,indent=2))
        digest=hashlib.sha256(dump.read_bytes()).hexdigest()
        with Path(str(base)+'.sha256').open('x',encoding='ascii') as output:output.write(digest+'  '+dump.name+'\n')
    engine.dispose()
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('--service',required=True)
    parser.add_argument('--pg-dump',default='pg_dump')
    args=parser.parse_args()
    if not os.environ.get('DB_URL'): parser.error('必须显式提供 DB_URL')
    bundle(os.environ['DB_URL'],args.base,'service='+args.service,args.pg_dump)
    print('只读快照备份与哈希清单完成。')
