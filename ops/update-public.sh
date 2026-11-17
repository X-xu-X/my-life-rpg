#!/usr/bin/env bash
# 同 schema 更新：本脚本**不迁移**、不恢复、不清理、不补发奖励。
#
# 带迁移的发布怎么写（v1.13.1 起固定下来，不靠口头）：
#   1. 迁移是**独立的前置步骤**：在停写窗口内、最终备份之后、起新镜像之前执行
#      （`alembic upgrade head`），不进本脚本的自动流程；
#   2. 迁移失败 → 全部停止，用备份恢复，**不起新镜像、不切流量**；
#   3. 迁移成功但新镜像起不来 → 允许回起旧镜像（旧代码不读新列，多一列无害），
#      但必须显式打出 `SCHEMA_AHEAD_OF_CODE`：回滚的是代码，库已经是新 schema，
#      别让人误以为库也退回去了。
#   库 head 与本包 head 不一致时，本脚本会在预检阶段（新镜像的 init_db）就停下，
#   不会带着未迁移的库去切流量。
set -euo pipefail
umask 077
if (( $# != 4 )); then
  printf 'Usage: bash ops/update-public.sh SOURCE_DIR EXPECTED_COMMIT ACTIVE_ENV_FILE REHEARSAL_RESULT_JSON\n' >&2
  exit 2
fi
source_dir=$(realpath -e -- "$1")
expected_sha=$2
old_env=$(sudo -n realpath -e -- "$3")
rehearsal=$(realpath -e -- "$4")
[[ "$expected_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$source_dir" = /home/admin/lifexp-*/* && "$old_env" = /etc/game-of-life/*.env ]]
dkr() { sudo -n docker "$@"; }
old_file=$(dkr inspect game-of-life-api-1 --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}')
[[ "$old_file" = /opt/game-of-life-public-*/deploy/compose.prod.yml ]]
old_source=${old_file%/deploy/compose.prod.yml}
old_release=$(dkr inspect game-of-life-api-1 --format '{{.Config.Image}}')
[[ "$old_release" = game-of-life-api:* ]]
old_release=${old_release#game-of-life-api:}
short=${expected_sha:0:8}
target="/opt/game-of-life-public-$short"
new_env="/etc/game-of-life/public-$short.env"
work=$(mktemp -d "$HOME/lifexp-cutover-$short.XXXXXX")
stage=preflight
stopped=0
backup_file=''
old_compose() { dkr compose --project-name game-of-life --env-file "$old_env" -f "$old_file" "$@"; }
new_compose() { dkr compose --project-name game-of-life --env-file "$new_env" -f "$target/deploy/compose.prod.yml" "$@"; }
# 期望 head 由发布包内的 alembic/versions 现算，**不写死常量**
# （写死的话每加一个迁移都要手改一遍，忘了就把一次正确的部署判成失败）。
expected_head=$(python3 -B "$source_dir/ops/expected_head.py" "$source_dir")
# 发布前的库 head：回滚时用它区分「库没动过」和「库已经迁到新版本」。
database_head=$(dkr exec game-of-life-db-1 psql -X -U gol_admin -d game_of_life -At -v ON_ERROR_STOP=1 \
  -c 'SELECT version_num FROM alembic_version' 2>/dev/null || true)
if [[ -z "$database_head" ]]; then
  printf 'DATABASE_HEAD_UNREADABLE: 先确认 game-of-life-db-1 正在运行。\n' >&2
  exit 2
fi
failed() {
  code=$?; trap - EXIT
  if (( code != 0 )); then
    printf '\nUPDATE_STOPPED stage=%s\nEVIDENCE_DIR=%s\nFINAL_BACKUP=%s\n' "$stage" "$work" "$backup_file"
    if (( stopped == 1 )); then
      head=$(dkr exec game-of-life-db-1 psql -X -U gol_admin -d game_of_life -At -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM alembic_version' 2>/dev/null || true)
      if [[ "$head" = "$database_head" ]]; then
        # 库还是发布前的版本：与旧镜像完全匹配，正常回滚。
        new_compose stop --timeout 210 api worker > "$work/stop-new.log" 2>&1 || true
        if old_compose up -d --no-deps --no-build --pull never --wait --wait-timeout 240 api worker caddy > "$work/recovery.log" 2>&1; then
          printf 'OLD_SERVICES_RECOVERED: existing database and volume preserved.\n'
        else printf 'SERVICE_RECOVERY_FAILED: inspect private recovery log.\n'; fi
      elif [[ "$head" = "$expected_head" ]]; then
        # 库已迁到本包 head：旧代码不读新列，可以回起，但库不是旧库了，必须说清楚。
        new_compose stop --timeout 210 api worker > "$work/stop-new.log" 2>&1 || true
        if old_compose up -d --no-deps --no-build --pull never --wait --wait-timeout 240 api worker caddy > "$work/recovery.log" 2>&1; then
          printf 'SCHEMA_AHEAD_OF_CODE: 代码已回滚到旧镜像，数据库仍是 %s。\n' "$head"
          printf 'OLD_SERVICES_RECOVERED_UNDER_NEW_SCHEMA: 不要以此状态继续发布，请重新走流程或从备份隔离恢复。\n'
        else printf 'SERVICE_RECOVERY_FAILED: inspect private recovery log.\n'; fi
      else printf 'DATABASE_HEAD_CHANGED: automatic rollback refused.\n'; fi
    fi
  fi
  exit "$code"
}
trap failed EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 -B "$source_dir/ops/verify_package.py" "$source_dir/RELEASE_MANIFEST.json"
release=$(python3 - "$source_dir/RELEASE_MANIFEST.json" "$expected_sha" <<'PY'
import json,re,sys
from pathlib import Path
m=json.loads(Path(sys.argv[1]).read_text())
assert m['git_head']==sys.argv[2], 'COMMIT_MISMATCH'
assert re.fullmatch(r'rr-[a-zA-Z0-9._-]+',m['release_id'])
assert {p.name for p in Path(sys.argv[1]).parent.joinpath('alembic/versions').glob('*.py')} and 'ops/cloud_update_snapshot.py' in m['files']
print(m['release_id'])
PY
)
[[ "$release" != "$old_release" ]]
python3 - "$rehearsal" "$release" "$database_head" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]);assert p.parent.parent==Path('/home/admin') and p.parent.name.startswith('lifexp-rehearsal.')
r=json.loads(p.read_text());assert r['status']=='ISOLATED_PG_REHEARSAL_PASS' and r['release_id']==sys.argv[2]
# 彩排还原的是「发布前」的备份，所以比对的是当前库 head，而不是本包 head。
assert r['production_containers_unchanged'] and r['head']==[sys.argv[3]]
backup=Path(r['backup_file']);assert backup.parent==Path('/home/admin') and backup.is_file()
assert hashlib.sha256(backup.read_bytes()).hexdigest()==r['backup_sha256']
print('RESTORE_REHEARSAL_VERIFIED')
PY
image_manifest="$source_dir/images-$release.manifest.jsonl"
sudo -n python3 -B "$source_dir/ops/image_identity.py" verify --manifest "$image_manifest" --release-id "$release" --platform linux/amd64
test "$(dkr inspect game-of-life-worker-1 --format '{{.Config.Image}}')" = "game-of-life-api:$old_release"
test "$(dkr inspect game-of-life-caddy-1 --format '{{.Config.Image}}')" = "game-of-life-web:$old_release"
db_id=$(dkr inspect game-of-life-db-1 --format '{{.Id}}')
test "$(dkr inspect game-of-life-db-1 --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql"}}{{.Name}}{{end}}{{end}}')" = game_of_life_pg18
sudo -n test ! -L "$target"
if ! sudo -n test -e "$target"; then sudo -n cp -a -- "$source_dir" "$target"; fi
sudo -n cmp -- "$source_dir/RELEASE_MANIFEST.json" "$target/RELEASE_MANIFEST.json"
sudo -n python3 -B "$source_dir/ops/verify_package.py" "$target/RELEASE_MANIFEST.json"
sudo -n python3 - "$old_env" "$new_env" "$old_release" "$release" <<'PY'
import os,re,sys
from pathlib import Path
source,target=map(Path,sys.argv[1:3]);content=source.read_text();fields={}
assert source.is_file() and not source.is_symlink()
for line in content.splitlines():
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        k,v=line.split('=',1);k=k.strip();assert k not in fields;fields[k]=v.strip().strip('"\'')
assert fields['RELEASE_ID']==sys.argv[3] and fields['DOMAIN']=='lifexp.cn'
assert not fields.get('DB_URL') and fields.get('ACME_EMAIL')
for key,value in {'SECRETS_DIR':'/etc/game-of-life/secrets','OPS_CONFIG_DIR':'/etc/game-of-life/ops','OPS_WORK_DIR':'/var/lib/game-of-life'}.items():assert fields[key]==value
assert fields.get('BACKUP_ID')
updated,n=re.subn(r'(?m)^RELEASE_ID=[^\n]*$','RELEASE_ID='+sys.argv[4],content);assert n==1
assert not target.is_symlink()
if target.exists():assert target.read_text()==updated and target.stat().st_mode&0o777==0o600
else:
    with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        stream.write(updated);stream.flush();os.fsync(stream.fileno())
print('PUBLIC_ENV_READY: original settings and secrets preserved')
PY
new_compose config --quiet
new_compose run --rm --no-deps --pull never --interactive=false -T api python -c 'from app.main import init_db; init_db(); print("SCHEMA_AND_KEYS_READY")'
new_compose run --rm --no-deps --pull never --interactive=false -T --entrypoint caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile > "$work/caddy-validate.log" 2>&1
printf 'PREFLIGHT_PASS: starting brief write pause for verified backup and comparison.\n'
stage=stop-writers;stopped=1
old_compose stop --timeout 210 api worker
test "$(dkr inspect game-of-life-api-1 --format '{{.State.Running}}')" = false
test "$(dkr inspect game-of-life-worker-1 --format '{{.State.Running}}')" = false
stage=before-snapshot
new_compose run --rm --no-deps --pull never --interactive=false -T api python ops/cloud_update_snapshot.py > "$work/before.json"
python3 - "$work/before.json" "$expected_head" <<'PY'
import json,sys
# 新镜像只能跑在本包 head 上；库没迁到位时在这里停下，不要带着旧 schema 去切流量。
r=json.load(open(sys.argv[1]));assert r['head']==[sys.argv[2]] and r['tables']
PY
chmod 644 "$work/before.json"
stage=final-backup
backup_file=$(mktemp "$HOME/gol-before-$short-$(date -u +%Y%m%dT%H%M%SZ).XXXXXX.dump")
dkr exec game-of-life-db-1 pg_dump -U gol_admin -d game_of_life --format=custom > "$backup_file"
test -s "$backup_file"
dkr exec -i game-of-life-db-1 pg_restore --list < "$backup_file" > /dev/null
sha256sum "$backup_file" | tee "$work/final-backup.sha256"
printf 'FINAL_BACKUP=%s\n' "$backup_file"
stage=after-snapshot
new_compose run --rm --no-deps --pull never --interactive=false -T --volume "$work/before.json:/proof/before.json:ro" api python ops/cloud_update_snapshot.py /proof/before.json > "$work/after.json"
python3 - "$work/after.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='DATA_UNCHANGED';print(json.dumps(r))
PY
stage=start-new-services
new_compose up -d --no-deps --no-build --pull never --wait --wait-timeout 240 api worker
new_compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 caddy
for service in api worker; do
  test "$(dkr inspect "game-of-life-$service-1" --format '{{.Image}}')" = "$(dkr image inspect "game-of-life-api:$release" --format '{{.Id}}')"
done
test "$(dkr inspect game-of-life-caddy-1 --format '{{.Image}}')" = "$(dkr image inspect "game-of-life-web:$release" --format '{{.Id}}')"
test "$(dkr inspect game-of-life-db-1 --format '{{.Id}}')" = "$db_id"
stage=https-origin
curl --fail --silent --show-error --compressed --connect-timeout 10 --max-time 30 --resolve lifexp.cn:443:127.0.0.1 https://lifexp.cn/ -o "$work/live-index.html"
dkr exec game-of-life-caddy-1 cat /srv/index.html > "$work/image-index.html"
cmp "$work/live-index.html" "$work/image-index.html"
curl --fail --silent --show-error --connect-timeout 10 --max-time 30 --resolve lifexp.cn:443:127.0.0.1 https://lifexp.cn/service-status -o "$work/service-status.json"
python3 - "$work/service-status.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))['status']=='ready'
PY
new_compose ps
python3 - "$work" "$release" "$expected_sha" "$target" "$new_env" "$backup_file" "$expected_head" <<'PY'
import hashlib,json,sys
from pathlib import Path
work,release,sha,source,env,backup,head=sys.argv[1:]
r={'status':'PUBLIC_UPDATE_READY','release_id':release,'git_head':sha,'database_head':head,
   'schema_migration':'NONE','source_dir':source,'env_file':env,'evidence_dir':work,
   'final_backup':backup,'backup_sha256':hashlib.sha256(Path(backup).read_bytes()).hexdigest(),
   'backup_check':'archive listing only; full restore rehearsal separate',
   'database_container_preserved':True,'reward_repair':'NOT_RUN','real_supplier':'NOT_RUN',
   'remaining':'External access, ordinary/admin login, real model and reward repair acceptance'}
Path(work,'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
PY
stage=complete;stopped=0
