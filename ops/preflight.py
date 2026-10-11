"""Read-only Linux deployment checks. Print categories only, never expanded config/secrets."""
import argparse
import base64
import configparser
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=45)
    if result.returncode:raise RuntimeError('COMMAND_FAILED:'+args[0])
    return result.stdout.strip()


def private(path, owner=None, modes=(0o600,0o400)):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('SECRET_FILE_MISSING_OR_LINK')
    info=path.stat()
    if stat.S_IMODE(info.st_mode) not in modes or (owner is not None and info.st_uid!=owner):
        raise ValueError('SECRET_FILE_PERMISSIONS')
    return path


def environment(path):
    path=private(path)
    values={}
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        key,sep,value=line.partition('=')
        if not sep or any(char in value for char in '$`\r\n'):raise ValueError('ENV_FORMAT')
        values[key]=value.strip().strip('"\'')
    required=('RELEASE_ID','BACKUP_ID','DOMAIN','ACME_EMAIL','SECRETS_DIR','OPS_CONFIG_DIR','OPS_WORK_DIR')
    if any(not values.get(key) for key in required):raise ValueError('ENV_INCOMPLETE')
    if any('replace-' in values[key] or 'example' in values[key] or '<' in values[key] for key in required):
        raise ValueError('ENV_PLACEHOLDER')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{5,100}',values['RELEASE_ID']):raise ValueError('RELEASE_ID_INVALID')
    from ops.backup_run import backup_host
    backup_host(values['BACKUP_ID'])
    if values['BACKUP_ID']==values['RELEASE_ID']:raise ValueError('BACKUP_ID_MUST_BE_DEPLOYMENT_STABLE')
    if not re.fullmatch(r'[a-zA-Z0-9.-]+',values['DOMAIN']):raise ValueError('DOMAIN_INVALID')
    for key in ('SECRETS_DIR','OPS_CONFIG_DIR','OPS_WORK_DIR'):
        root=Path(values[key])
        if not root.is_absolute() or root.is_symlink() or root.resolve()!=root:raise ValueError('DIRECTORY_INVALID')
    return values


def check(env_file, allow_existing=False, core_only=False):
    if platform.system()!='Linux':raise ValueError('LINUX_REQUIRED')
    values=environment(env_file)
    from ops.verify_package import verify
    package=verify('RELEASE_MANIFEST.json')
    if package['release_id']!=values['RELEASE_ID']:raise ValueError('SOURCE_RELEASE_MISMATCH')
    if 'DB_URL' in values:raise ValueError('DATABASE_TARGET_OVERRIDE_FORBIDDEN')
    compose=['docker','compose','--env-file',str(env_file),'-f','deploy/compose.prod.yml']
    run(compose+['config','--quiet'])
    arch={'x86_64':'amd64','aarch64':'arm64'}.get(platform.machine())
    if not arch:raise ValueError('ARCH_UNSUPPORTED')
    if shutil.disk_usage(values['OPS_WORK_DIR']).free<5*1024**3:raise ValueError('DISK_FREE_BELOW_5_GIB')
    from ops.image_identity import verify_installed
    images=verify_installed(f'images-{values["RELEASE_ID"]}.manifest.jsonl',values['RELEASE_ID'],'linux/'+arch,core_only)
    pg_uid=int(run(['docker','run','--rm','--network','none','--entrypoint','id','postgres:18.6-bookworm','-u','postgres']))
    pg_gid=int(run(['docker','run','--rm','--network','none','--entrypoint','id','postgres:18.6-bookworm','-g','postgres']))
    root=Path(values['SECRETS_DIR'])
    admin=private(root/'admin-password',pg_uid)
    app=private(root/'app-password',10001,(0o440,))
    if app.stat().st_gid!=pg_gid:raise ValueError('APP_SECRET_POSTGRES_GROUP')
    if min(len(admin.read_text().strip()),len(app.read_text().strip()))<24 or admin.read_bytes()==app.read_bytes():
        raise ValueError('DATABASE_PASSWORD_POLICY')
    key=private(root/'credential-keys.json',10001)
    ring=json.loads(key.read_text())
    if ring.get('active') not in ring.get('keys',{}):raise ValueError('KEYRING_INVALID')
    if any(len(base64.urlsafe_b64decode(value))!=32 for value in ring['keys'].values()):raise ValueError('KEYRING_INVALID')
    ops=Path(values['OPS_CONFIG_DIR'])
    if not core_only:check_backup(ops)
    output=run(compose+['ps','--all','--format','json'])
    try:containers=json.loads(output or '[]')
    except ValueError:containers=[json.loads(line) for line in output.splitlines() if line.strip()]
    if isinstance(containers,dict):containers=[containers]
    check_database_ports(containers)
    volume=subprocess.run(['docker','volume','inspect','game_of_life_pg18'],capture_output=True).returncode==0
    if volume and not allow_existing:raise ValueError('EXISTING_DATABASE_VOLUME_REQUIRES_REVIEW')
    if not any(row.get('Service')=='caddy' and row.get('State')=='running' for row in containers):
        import socket
        for port in (80,443):
            with socket.socket() as probe:
                try:probe.bind(('0.0.0.0',port))
                except OSError:raise ValueError('PUBLIC_PORT_IN_USE') from None
    return {'status':'PASS','scope':'empty-private-staging' if core_only else 'configured-deployment',
        'backup_gate':'NOT_RUN' if core_only else 'configuration-only',
        'architecture':arch,'application_uid':10001,'postgres_uid':pg_uid,'image_identity':images,
        'database_target':'db:5432/game_of_life','database_volume':'game_of_life_pg18',
        'volume_exists':volume,'migration':'checked after explicit migrate by check-release.sh'}


def check_database_ports(containers):
    for row in containers:
        if row.get('Service')!='db':continue
        for publisher in row.get('Publishers') or []:
            # Compose also lists EXPOSE-only ports: PublishedPort=0 is not a host binding.
            port=publisher.get('PublishedPort')
            if type(port) is not int or not 0<=port<=65535:raise ValueError('DATABASE_PORT_DATA_INVALID')
            if port>0:raise ValueError('DATABASE_PORT_PUBLISHED')


def check_backup(ops):
    for name in ('pg_service.conf','pgpass','restic-password','backup.env'):private(ops/name,10001)
    services=configparser.ConfigParser();services.read(ops/'pg_service.conf')
    for service,user,database in (('gol_backup','gol_app','game_of_life'),('gol_restore','gol_admin','postgres')):
        expected={'host':'db','port':'5432','user':user,'dbname':database}
        if not services.has_section(service) or any(services[service].get(k)!=v for k,v in expected.items()):
            raise ValueError('LIBPQ_DATABASE_TARGET_MISMATCH')
    private_env=(ops/'backup.env').read_text()
    if re.search(r'^\s*DB_URL\s*=',private_env,re.M):raise ValueError('BACKUP_DATABASE_OVERRIDE_FORBIDDEN')
    if not re.search(r'^\s*RESTIC_REPOSITORY=(s3:|sftp:|rest:|b2:|azure:|gs:)',private_env,re.M):
        raise ValueError('INDEPENDENT_REMOTE_REPOSITORY_REQUIRED')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--env-file',required=True)
    parser.add_argument('--reviewed-existing-volume',action='store_true')
    parser.add_argument('--core-only',action='store_true',help='empty private staging only; does not satisfy backup/release gates')
    args=parser.parse_args()
    try:print(json.dumps(check(args.env_file,args.reviewed_existing_volume,args.core_only)))
    except Exception as exc:
        # Exception messages from external tools may contain secrets; emit only controlled categories.
        category=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z0-9_]+',str(exc)) else type(exc).__name__
        print(json.dumps({'status':'FAIL','category':category}));raise SystemExit(2)
