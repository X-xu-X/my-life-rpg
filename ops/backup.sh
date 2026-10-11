#!/bin/sh
set -eu
umask 077
: "${PGSERVICE:?set PGSERVICE}" "${PGSERVICEFILE:?set PGSERVICEFILE}" "${PGPASSFILE:?set PGPASSFILE}"
: "${DB_URL:?set private DB_URL for manifest}" "${BACKUP_DIR:?set private backup directory}"
: "${RESTIC_REPOSITORY:?set independent private repository}" "${RESTIC_PASSWORD_FILE:?set restic password file}"
mkdir -p "$BACKUP_DIR"
exec python ops/backup_run.py
