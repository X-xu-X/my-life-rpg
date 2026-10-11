#!/bin/sh
set -eu
: "${PRODUCTION_ENV_FILE:?set protected compose env file}"
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml run --rm --no-deps ops sh ops/backup.sh
