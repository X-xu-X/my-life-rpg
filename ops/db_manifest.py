"""整库恢复对照；只输出计数/哈希/迁移版本，不输出正文、密钥或哈希口令。"""
import hashlib
import json
import os
from datetime import date, datetime, timezone
from sqlalchemy import create_engine, MetaData, select


def encode(value):
    if isinstance(value,datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value,date): return value.isoformat()
    raise TypeError(type(value).__name__)


def collect(connection):
    metadata=MetaData()
    metadata.reflect(connection)
    result={}
    for name,table in sorted(metadata.tables.items()):
        rows=[dict(row) for row in connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
        data=json.dumps(rows,sort_keys=True,ensure_ascii=False,default=encode,separators=(',',':')).encode()
        result[name]={'count':len(rows),'sha256':hashlib.sha256(data).hexdigest()}
    return result


def manifest(url):
    engine=create_engine(url)
    with engine.connect() as connection:
        result=collect(connection)
    engine.dispose()
    return result


if __name__=='__main__':
    if not os.environ.get('DB_URL'): raise SystemExit('必须显式提供 DB_URL。')
    print(json.dumps(manifest(os.environ['DB_URL']),ensure_ascii=False,indent=2))
