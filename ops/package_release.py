"""Allowlisted source bundle; excludes real DBs, env, keys, caches and images."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATTERNS=('app/**/*.py','alembic/**/*.py','alembic/script.py.mako','ops/*.py','ops/*.sh','ops/*.md','ops/*.example',
    'deploy/Dockerfile.*','deploy/Caddyfile*','deploy/*.yml','deploy/*.sql','deploy/*.service','deploy/*.timer',
    'deploy/entrypoint.py','deploy/.env.production.example','frontend/src/**/*.js','frontend/src/**/*.vue',
    'frontend/src/**/*.css','frontend/public/**/*','frontend/package.json','frontend/package-lock.json',
    'frontend/index.html','frontend/vite.config.*','tests/*.py','tests/*.mjs',
    'requirements.txt','requirements.lock','alembic.ini','.dockerignore','.gitattributes','.gitignore',
    '.env.example','README.md','docs/*.md','docs/review/RELEASE_READINESS_EVIDENCE_2026-10-10.json',
    'docs/review/RELEASE_ROUTE_INVENTORY_2026-10-10.json',
    'docs/review/RELEASE_BROWSER_EVIDENCE_2026-10-10.json',
    'docs/review/RELEASE_TEST_LOG_2026-10-10.txt',
    'docs/review/OPS_REVIEW_EVIDENCE_2026-10-10.json',
    'docs/review/OPS_REVIEW_TEST_LOG_2026-10-10.txt')


def files():
    selected={path for pattern in PATTERNS for path in ROOT.glob(pattern) if path.is_file()}
    for path in selected:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):raise ValueError('SOURCE_LINK_REJECTED')
        if path.suffix in ('.db','.sqlite3','.pem','.dump','.zip') or '.secret.' in path.name:raise ValueError('SECRET_ARTIFACT_REJECTED')
    return sorted(selected)


def identity():
    selected=files()
    hashes={path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in selected}
    # Runtime identity stays stable when delivery notes/evidence gain their own final checksums.
    runtime={key:value for key,value in hashes.items() if not key.startswith('docs/') and key!='ops/README.md'}
    digest=hashlib.sha256(json.dumps(runtime,sort_keys=True).encode()).hexdigest()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    return {'release_id':'rr-20261010-'+head[:8]+'-'+digest[:12],'runtime_sha256':digest,'git_head':head,
        'worktree':'includes uncommitted A/B baseline and release-readiness changes',
        'target_platforms':['linux/amd64','linux/arm64'],'image_status':'NOT_BUILT',
        'dependency_locks':['requirements.lock','frontend/package-lock.json'],'files':hashes}


def package(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    manifest=identity();name=manifest['release_id'];archive=output/(name+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as target:
        for relative in manifest['files']:target.write(ROOT/relative,relative)
        target.writestr('RELEASE_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    with (output/(name+'.sha256')).open('x',encoding='ascii') as file:file.write(digest+'  '+archive.name+'\n')
    with (output/(name+'.manifest.json')).open('x',encoding='utf-8') as file:json.dump(manifest,file,ensure_ascii=False,indent=2)
    return {'release_id':name,'archive':str(archive),'sha256':digest,'files':len(manifest['files']),'images':'NOT_BUILT'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');parser.add_argument('--identity',action='store_true');args=parser.parse_args()
    if args.identity:
        result=identity();result.pop('files');print(json.dumps(result,ensure_ascii=False,indent=2))
    elif args.output:print(json.dumps(package(args.output),ensure_ascii=False,indent=2))
    else:parser.error('--output or --identity required')
