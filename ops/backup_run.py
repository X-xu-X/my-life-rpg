"""Fail closed: no fresh success marker until dump, remote check and retention all succeed."""
import json
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ops.backup_state import root_path, remote
from ops.monitor import notify


def command(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=1800)
    if result.returncode:raise RuntimeError('BACKUP_STEP_FAILED')
    return result.stdout


def backup_host(value):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{5,80}',value or '') or 'replace-' in value:
        raise ValueError('BACKUP_ID_INVALID')
    return value


def snapshot_commands(host,base):
    host=backup_host(host)
    return (
        ['restic','backup','--json','--host',host,'--tag','game-of-life',str(base)+'.dump',str(base)+'.manifest.json',str(base)+'.sha256'],
        ['restic','forget','--host',host,'--tag','game-of-life','--group-by','host,tags','--keep-daily','7','--keep-weekly','4','--prune'],
    )


def main():
    required=('PGSERVICE','PGSERVICEFILE','PGPASSFILE','DB_URL','BACKUP_DIR','RESTIC_REPOSITORY','RESTIC_PASSWORD_FILE','RESTIC_HOST')
    if any(not os.environ.get(key) for key in required):raise ValueError('BACKUP_CONFIG_INCOMPLETE')
    host=backup_host(os.environ['RESTIC_HOST'])
    root=root_path(os.environ['BACKUP_DIR'])
    name='gol-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(6)
    base=root/name
    command([sys.executable,'ops/backup_bundle.py',str(base),'--service',os.environ['PGSERVICE']])
    backup,forget=snapshot_commands(host,base)
    output=command(backup)
    summaries=[json.loads(line) for line in output.splitlines() if line.strip()]
    snapshot=next(row['snapshot_id'] for row in reversed(summaries) if row.get('snapshot_id'))
    command(['restic','check'])
    command(forget)
    remote(root,name,snapshot)
    print(json.dumps({'status':'PASS','bundle':name,'backup_host':host,'remote_verified':True,'restore_verified':False}))


if __name__=='__main__':
    os.umask(0o077)
    try:main()
    except Exception:
        try:notify(['BACKUP_FAILED'],os.environ.get('ALERT_WEBHOOK_URL'))
        except Exception:print('ALERT_DELIVERY_FAILED',file=sys.stderr)
        print('BACKUP_FAILED: success state unchanged',file=sys.stderr);raise SystemExit(2)
