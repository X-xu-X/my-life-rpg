"""Final real-data smoke: back up before startup, read-only business requests."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.database import engine, SessionLocal
from app.main import app
from app.services.backup_service import backup_now
from app.routers.export import _collect


def counts():
    with engine.connect() as conn:
        names=[r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))]
        return {name:conn.execute(text('SELECT count(*) FROM "'+name+'"')).scalar() for name in names}


before=counts()
backup=backup_now()
assert backup is not None, 'An existing database must be backed up before smoke startup'
with closing(sqlite3.connect(str(backup))) as copy:
    old_columns=[r[1] for r in copy.execute('PRAGMA table_info(events)')]
    old_foreign_keys=copy.execute('PRAGMA foreign_key_check').fetchall()
with TestClient(app) as client:
    endpoints={}
    for route in ('health','attributes','onboarding/status','events','judgments','settings','llm-config','items/stats'):
        response=client.get('/api/'+route)
        assert response.status_code==200,(route,response.status_code)
        endpoints[route]=response.status_code
after=counts()
assert before==after, 'Read-only smoke must not alter table counts'
with SessionLocal() as db:
    uid=db.execute(text('SELECT id FROM users WHERE username=:name'),{'name':'default'}).scalar()
    data=_collect(db,uid)
    tables=data['tables']
    profile=tables['user_profiles'][0]
    baseline={a['name']:a['value'] for a in profile['initial_attributes_snapshot']['attributes']}
    totals={}
    for row in tables['attribute_history']:
        totals[row['attribute_id']]=totals.get(row['attribute_id'],0)+row['delta']
    checks=[]
    for attr in tables['attributes']:
        if attr['parent_id'] is not None:continue
        # Historical honesty starts at 50; v1.11 must not rewrite its old snapshot.
        initial=50 if attr['name']=='诚信' else baseline.get(attr['name'],50)
        expected=round(initial+totals.get(attr['id'],0),2)
        checks.append({'name':attr['name'],'baseline':initial,'delta_sum':round(totals.get(attr['id'],0),2),
                       'expected':expected,'actual':attr['current_value'],'matches':abs(expected-attr['current_value'])<.011})
    assert len(checks)==13 and all(c['matches'] for c in checks)
    ledger=sum(row['delta'] for row in tables['coin_ledger'])
    assert ledger==profile['coins']==40, 'Historical startup funds must remain unchanged'
    assert len(tables)==17
    raw=json.dumps(data,ensure_ascii=False)
    settings=db.execute(text('SELECT key,value FROM settings WHERE user_id=:uid'),{'uid':uid}).all()
    for key,value in settings:
        if key.startswith('llm_'):
            config=json.loads(value) if isinstance(value,str) else value
            secret=config.get('api_key') if isinstance(config,dict) else None
            if secret:assert secret not in raw
    foreign_keys=[tuple(row) for row in db.execute(text('PRAGMA foreign_key_check')).all()]
    assert foreign_keys==old_foreign_keys, 'Smoke must not introduce or repair old dangling references'
    assert db.execute(text('PRAGMA integrity_check')).scalar()=='ok'
result={'backup':str(backup),'backup_event_columns':old_columns,'endpoints':endpoints,
        'before_counts':before,'after_counts':after,'coins':profile['coins'],'ledger_sum':ledger,
        'attribute_checks':checks,'export_tables':len(tables),'export_contains_key':False,
        'foreign_key_check':{'unchanged':True,'preexisting_findings':foreign_keys},'integrity_check':'ok'}
Path('docs/review/V1_11_REAL_SMOKE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'tables_unchanged':before==after,'coins':profile['coins'],'attribute_matches':sum(c['matches'] for c in checks),'export_tables':len(tables),'endpoints':endpoints}))
