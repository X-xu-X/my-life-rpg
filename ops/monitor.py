"""Lightweight probe; run public probe on an independent host. No notification by default."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path


def notify(codes, url=None):
    # Only category codes are transmitted. Configure a user-authorized endpoint in a private env.
    payload=json.dumps({'service':'game-of-life','alerts':sorted(set(codes))}).encode()
    if url:
        if not url.startswith('https://'):raise ValueError('HTTPS_ALERT_ENDPOINT_REQUIRED')
        request=urllib.request.Request(url,data=payload,headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(request,timeout=10) as response:
            if not 200<=response.status<300:raise ValueError('ALERT_DELIVERY_FAILED')
    else:print(payload.decode(),file=sys.stderr)


def public_probe(url):
    try:parsed=urlsplit(url)
    except ValueError:return ['PUBLIC_HTTPS_CONFIG_INVALID']
    if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password:
        return ['PUBLIC_HTTPS_CONFIG_INVALID']
    codes=[]
    try:
        with urllib.request.urlopen(url,timeout=10) as response:
            if response.status!=200:codes.append('PUBLIC_SERVICE_UNREACHABLE')
    except Exception:codes.append('PUBLIC_SERVICE_UNREACHABLE')
    status_url=urlunsplit((parsed.scheme,parsed.netloc,'/service-status','',''))
    try:
        request=urllib.request.Request(status_url,headers={'Cache-Control':'no-cache'})
        with urllib.request.urlopen(request,timeout=10) as response:
            body=response.read(4097)
            if (response.status!=200 or len(body)>4096
                    or json.loads(body)!={'status':'ready'}):
                codes.append('PUBLIC_APPLICATION_UNAVAILABLE')
    except Exception:codes.append('PUBLIC_APPLICATION_UNAVAILABLE')
    return codes


def local_probe(root, compose):
    codes=[]
    usage=shutil.disk_usage(root)
    if usage.free<5*1024**3 or usage.free/usage.total<.10:codes.append('DISK_LOW')
    states=[]
    for path in Path(root).glob('gol-*.state.json'):
        try:states.append(json.loads(path.read_text()))
        except Exception:codes.append('BACKUP_STATE_INVALID')
    from datetime import datetime, timezone
    dates=[datetime.fromisoformat(s['remote_verified_at']).timestamp() for s in states if s.get('remote_verified_at')]
    if not dates or time.time()-max(dates)>24*3600:codes.append('BACKUP_STALE')
    commands=[('API_UNAVAILABLE',['exec','-T','api','python','-c',
        'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/api/ready",timeout=3)']),
        ('WORKER_STALE',['exec','-T','worker','python','-c',
        'from pathlib import Path; import time; p=Path("/tmp/gol-worker-heartbeat"); assert p.exists() and time.time()-p.stat().st_mtime<300'])]
    for code,command in commands:
        try:
            if subprocess.run(compose+command,capture_output=True,timeout=15).returncode:codes.append(code)
        except Exception:codes.append(code)
    return codes


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--public-url');parser.add_argument('--backup-root')
    parser.add_argument('--alert-code');args=parser.parse_args()
    codes=[]
    if args.alert_code:
        if args.alert_code not in ('BACKUP_FAILED','ALERT_TEST'):raise SystemExit(2)
        codes.append(args.alert_code)
    if args.public_url:codes+=public_probe(args.public_url)
    if args.backup_root:
        env=os.environ.get('PRODUCTION_ENV_FILE')
        if not env:raise SystemExit('PRODUCTION_ENV_FILE required')
        codes+=local_probe(args.backup_root,['docker','compose','--env-file',env,'-f','deploy/compose.prod.yml'])
    if not (args.public_url or args.backup_root or args.alert_code):raise SystemExit(2)
    try:
        if codes:notify(codes,os.environ.get('ALERT_WEBHOOK_URL'))
    except Exception:print('ALERT_DELIVERY_FAILED',file=sys.stderr);raise SystemExit(3)
    raise SystemExit(2 if codes else 0)
