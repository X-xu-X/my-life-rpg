#!/usr/bin/env bash
# Restore a backup into a private PG copy; never attach production networks/volume.
# Generic read-only release rehearsal; no event-specific repair assertions.
set -euo pipefail
umask 077
if (( $# != 2 )); then printf 'Usage: bash ops/rehearse-public-update.sh SOURCE_DIR BACKUP_FILE\n' >&2; exit 2; fi
source_dir=$(realpath -e -- "$1");backup_file=$(realpath -e -- "$2")
[[ "$source_dir" = /home/admin/lifexp-*/* && "$backup_file" = /home/admin/gol-*.dump ]]
test -s "$backup_file"
available_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
if (( available_kb < 720896 )); then printf 'INSUFFICIENT_FREE_MEMORY: available=%s_KiB\n' "$available_kb"; exit 2; fi
dkr() { sudo -n docker "$@"; }
python3 -B "$source_dir/ops/verify_package.py" "$source_dir/RELEASE_MANIFEST.json"
release=$(python3 - "$source_dir/RELEASE_MANIFEST.json" <<'PY'
import json,re,sys
r=json.load(open(sys.argv[1]));assert re.fullmatch(r'rr-[A-Za-z0-9._-]+',r['release_id']);print(r['release_id'])
PY
)
sudo -n python3 -B "$source_dir/ops/image_identity.py" verify --manifest "$source_dir/images-$release.manifest.jsonl" --release-id "$release" --platform linux/amd64
work=$(mktemp -d "$HOME/lifexp-rehearsal.XXXXXX")
name="lifexp-proof-${work##*.}"
network="$name-net";volume="$name-pg";db="$name-db";probe="$name-probe"
stage=prepare
live_before=$(dkr inspect game-of-life-api-1 game-of-life-worker-1 game-of-life-db-1 game-of-life-caddy-1 --format '{{.Id}} {{.Image}} {{.State.StartedAt}}')
cleanup() {
  code=$?;trap - EXIT
  if (( code != 0 )); then
    # Retain private diagnostics before removing the disposable containers.
    dkr logs "$db" > "$work/postgres.log" 2>&1 || true
    dkr inspect "$db" --format '{{json .State}}' > "$work/postgres-state.json" 2>/dev/null || true
    printf 'REHEARSAL_STOPPED stage=%s exit=%s\n' "$stage" "$code"
  fi
  dkr rm -f "$probe" "$db" > /dev/null 2>&1 || true
  dkr network rm "$network" > /dev/null 2>&1 || true
  printf 'EVIDENCE_DIR=%s\nPRIVATE_TEST_VOLUME=%s\n' "$work" "$volume"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 - "$work" <<'PY'
import os,secrets,sys
from pathlib import Path
root=Path(sys.argv[1])
for name in ('app-password','admin-password'):
    p=root/name;p.write_text(secrets.token_hex(32));os.chmod(p,0o444)
PY
# Receive/extract uses umask 077. PostgreSQL's non-root user cannot read a
# directly mounted 0600 source file. Only this non-secret staging copy is public
# readable; source files and production secrets retain their permissions.
cp -- "$source_dir/deploy/init-app-role.sql" "$work/init-app-role.sql"
chmod 644 "$work/init-app-role.sql"
dkr network create --internal --label lifexp.scope=isolated-rehearsal "$network" > /dev/null
dkr volume create --label lifexp.scope=isolated-rehearsal "$volume" > /dev/null
stage=database-start
dkr run -d --pull never --name "$db" --network "$network" --network-alias db --memory 256m --cpus 0.5 --pids-limit 100 \
  --env POSTGRES_USER=gol_admin --env POSTGRES_DB=game_of_life --env POSTGRES_PASSWORD_FILE=/run/secrets/admin_password \
  --volume "$volume:/var/lib/postgresql" --volume "$work/admin-password:/run/secrets/admin_password:ro" \
  --volume "$work/app-password:/run/secrets/app_password:ro" --volume "$work/init-app-role.sql:/docker-entrypoint-initdb.d/01-app-role.sql:ro" \
  postgres:18.6-bookworm -c shared_buffers=32MB -c max_connections=15 -c work_mem=2MB -c maintenance_work_mem=32MB > /dev/null
ready=0
for attempt in $(seq 1 60); do
  if dkr exec "$db" pg_isready -h 127.0.0.1 -U gol_admin -d game_of_life > /dev/null 2>&1; then ready=1;break;fi
  sleep 1
done
test "$ready" = 1
stage=restore-copy
dkr exec -i "$db" pg_restore -U gol_admin -d game_of_life --no-owner --no-privileges --role=gol_app --exit-on-error < "$backup_file" > "$work/restore.log" 2>&1
stage=restore-health-proof
dkr run --rm --pull never --name "$probe" --network "$network" --memory 320m --cpus 0.5 --pids-limit 100 --read-only --tmpfs /tmp:rw,nosuid,size=64m \
  --env RUN_MODE=cloud --env PUBLIC_ORIGIN=https://lifexp.cn --env DB_PASSWORD_FILE=/run/secrets/app_password \
  --env CREDENTIAL_KEY_FILE=/run/secrets/credential_keys --env LIFEXP_ISOLATED_REHEARSAL=public-update-copy-only \
  --volume "$work/app-password:/run/secrets/app_password:ro" --volume /etc/game-of-life/secrets/credential-keys.json:/run/secrets/credential_keys:ro \
  "game-of-life-api:$release" python ops/rehearse_public_update.py > "$work/result.json"
python3 - "$work/result.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]));assert r['status']=='ISOLATED_PG_REHEARSAL_PASS'
PY
stage=verify-production-containers
test "$(dkr inspect game-of-life-api-1 game-of-life-worker-1 game-of-life-db-1 game-of-life-caddy-1 --format '{{.Id}} {{.Image}} {{.State.StartedAt}}')" = "$live_before"
python3 - "$work/result.json" "$release" "$backup_file" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]);r=json.loads(p.read_text())
r.update(release_id=sys.argv[2],backup_file=sys.argv[3],backup_sha256=hashlib.sha256(Path(sys.argv[3]).read_bytes()).hexdigest(),production_containers_unchanged=True)
p.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
PY
stage=complete
printf 'PRODUCTION_CONTAINERS_UNCHANGED\n'
