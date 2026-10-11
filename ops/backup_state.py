"""Explicit backup classification and confined staging cleanup. No remote access here."""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

NAME=re.compile(r'gol-\d{8}T\d{6}Z-[0-9a-f]{12}')
SUFFIXES=('.dump','.manifest.json','.sha256','.state.json')


def root_path(root):
    root=Path(root).absolute()
    if not root.is_dir() or root.is_symlink() or root.resolve()!=root:raise ValueError('BACKUP_ROOT_INVALID')
    return root


def confined(root,name,suffix):
    if not NAME.fullmatch(name) or suffix not in SUFFIXES:raise ValueError('BACKUP_NAME_INVALID')
    path=root/(name+suffix)
    if path.is_symlink() or path.resolve().parent!=root:raise ValueError('BACKUP_PATH_ESCAPE')
    return path


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_bundle(root,name):
    paths=[confined(root,name,suffix) for suffix in SUFFIXES[:3]]
    if any(not path.is_file() for path in paths):raise ValueError('BACKUP_INCOMPLETE')
    expected,filename=paths[2].read_text().strip().split(maxsplit=1)
    if filename!=paths[0].name or expected!=digest(paths[0]):raise ValueError('BACKUP_CHECKSUM')
    json.loads(paths[1].read_text())
    return {'dump_sha256':expected,'manifest_sha256':digest(paths[1])}


def write_state(root,name,value):
    target=confined(root,name,'.state.json')
    temp=root/(name+'.state.tmp')
    # O_EXCL and O_NOFOLLOW prevent replacing links or following stale temp paths.
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        with os.fdopen(fd,'w') as output:
            json.dump(value,output);output.flush();os.fsync(output.fileno())
        os.replace(temp,target)
    finally:
        if temp.exists() and not temp.is_symlink():temp.unlink()


def remote(root,name,snapshot):
    root=root_path(root)
    if not re.fullmatch('[0-9a-f]{64}',snapshot):raise ValueError('SNAPSHOT_ID_INVALID')
    value={**verified_bundle(root,name),'snapshot_id':snapshot,'remote_verified_at':datetime.now(timezone.utc).isoformat(),
        'restore_verified_at':None}
    write_state(root,name,value)
    return value


def restored(root,name,evidence):
    root=root_path(root);state=json.loads(confined(root,name,'.state.json').read_text())
    current=verified_bundle(root,name)
    if any(current[key]!=state[key] for key in current):raise ValueError('BACKUP_CHANGED')
    if (evidence.get('status')!='PASS' or evidence.get('snapshot_id')!=state['snapshot_id']
        or evidence.get('dump_sha256')!=state['dump_sha256'] or evidence.get('tables_verified',0)<17
        or not evidence.get('migration_heads')):raise ValueError('RESTORE_EVIDENCE_MISMATCH')
    state['restore_verified_at']=datetime.now(timezone.utc).isoformat()
    write_state(root,name,state)


def cleanup(root,*,apply=False,keep=2):
    root=root_path(root)
    if keep<1:raise ValueError('KEEP_MUST_BE_POSITIVE')
    eligible=[]
    for path in root.glob('gol-*.state.json'):
        name=path.name.removesuffix('.state.json')
        if not NAME.fullmatch(name):continue
        # Abort the whole plan before deleting anything if a candidate escapes the root.
        state=json.loads(confined(root,name,'.state.json').read_text())
        if not state.get('remote_verified_at') or not state.get('restore_verified_at'):continue
        actual=verified_bundle(root,name)
        if any(actual[key]!=state.get(key) for key in actual):raise ValueError('BACKUP_CHANGED')
        eligible.append((state['restore_verified_at'],name))
    eligible.sort(reverse=True)
    names=[name for _,name in eligible[keep:]]
    targets=[confined(root,name,suffix) for name in names for suffix in SUFFIXES]
    if apply:
        for path in targets:path.unlink()
    return {'mode':'apply' if apply else 'dry-run','delete_bundles':names,
        'retained_verified':len(eligible)-len(names),'unknown_or_failed':'retained'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    sub=parser.add_subparsers(dest='action',required=True)
    clean=sub.add_parser('cleanup');clean.add_argument('--apply',action='store_true');clean.add_argument('--keep',type=int,default=2)
    restore=sub.add_parser('mark-restored');restore.add_argument('--name',required=True);restore.add_argument('--evidence',required=True)
    args=parser.parse_args()
    try:
        if args.action=='cleanup':print(json.dumps(cleanup(args.root,apply=args.apply,keep=args.keep)))
        else:restored(args.root,args.name,json.loads(Path(args.evidence).read_text()));print('Restore classification recorded')
    except Exception:print('FAIL: backup classification or path validation');raise SystemExit(2)
