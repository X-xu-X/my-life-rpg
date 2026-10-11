#!/bin/sh
set -eu
umask 077
: "${RESTORE_DB:?set NEW gol_rehearsal_ database}" "${RESTORE_SERVICE:?set isolated libpq service}"
: "${RESTIC_SNAPSHOT:?set independent snapshot}" "${RESTIC_DUMP_PATH:?set archived absolute dump path}"
: "${CREDENTIAL_KEY_FILE:?supply independently kept encryption key file}"
: "${RESTIC_REPOSITORY:?set independent repository}" "${RESTIC_PASSWORD_FILE:?set private password file}"
: "${PGSERVICEFILE:?set private libpq service file}" "${PGPASSFILE:?set private libpq password file}"
case "$RESTORE_DB" in gol_rehearsal_*) ;; *) echo '目标名称不符合隔离约束' >&2; exit 2;; esac
case "$RESTORE_DB" in *[!a-zA-Z0-9_]*) exit 2;; esac
work=$(mktemp -d)
# 保留临时结果供审计；不删除任何现有库或目录。
prefix=${RESTIC_DUMP_PATH%.dump}
restic dump "$RESTIC_SNAPSHOT" "$RESTIC_DUMP_PATH" > "$work/source.dump"
restic dump "$RESTIC_SNAPSHOT" "$prefix.manifest.json" > "$work/manifest.json"
restic dump "$RESTIC_SNAPSHOT" "$prefix.sha256" > "$work/source.sha256"
expected=$(cut -d ' ' -f 1 "$work/source.sha256")
actual=$(sha256sum "$work/source.dump" | cut -d ' ' -f 1)
[ "$expected" = "$actual" ] || { echo '备份哈希不一致' >&2; exit 1; }
# createdb 在目标已存在时失败；不使用 --clean、不覆盖生产库。
createdb --maintenance-db="service=$RESTORE_SERVICE" "$RESTORE_DB"
pg_restore --exit-on-error --no-owner --no-acl --dbname="service=$RESTORE_SERVICE dbname=$RESTORE_DB" "$work/source.dump"
export DB_URL="postgresql+psycopg:///?service=$RESTORE_SERVICE&dbname=$RESTORE_DB"
python ops/verify_restore.py "$work/manifest.json" > "$work/result.json"
export RESTORE_DUMP_SHA256="$actual" RESTORE_RESULT_FILE="$work/result.json"
python -c 'import json,os,platform; from datetime import datetime,timezone; from pathlib import Path; p=Path(os.environ["RESTORE_RESULT_FILE"]); r=json.loads(p.read_text()); r.update(status="PASS",snapshot_id=os.environ["RESTIC_SNAPSHOT"],dump_sha256=os.environ["RESTORE_DUMP_SHA256"],restore_host=platform.node(),verified_at=datetime.now(timezone.utc).isoformat()); p.write_text(json.dumps(r)); print(json.dumps(r))'
echo "Restore evidence file: $work/result.json"
