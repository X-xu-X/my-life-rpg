import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


def check(path):
    evidence=json.loads(Path(path).read_text())
    now=datetime.now(timezone.utc)
    if evidence.get('release_id')!=os.environ.get('RELEASE_ID') or not evidence.get('release_id'):
        raise ValueError('release identity mismatch')
    age=now-datetime.fromisoformat(evidence['verified_at'])
    if age>timedelta(days=1) or age<timedelta(minutes=-5):raise ValueError('evidence stale or future')
    required=[f'RR{i:02}' for i in range(1,13)]
    if any(evidence.get('gates',{}).get(key)!='PASS' for key in required):raise ValueError('release gates incomplete')
    return {'status':'PASS','release_id':evidence['release_id']}


if __name__=='__main__':
    try:print(json.dumps(check(sys.argv[1])))
    except Exception:print('FAIL: current release acceptance evidence incomplete');raise SystemExit(2)
