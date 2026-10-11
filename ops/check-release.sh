#!/bin/sh
set -eu
: "${PRODUCTION_ENV_FILE:?set protected compose env file}"
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml config --quiet
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml ps
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml exec -T api python entrypoint.py python -c 'from app.main import init_db; init_db(); print("配置、密钥、迁移版本已就绪")'
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml exec -T api python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/api/ready",timeout=3).status)'
docker volume inspect game_of_life_pg18 game_of_life_caddy_data > /dev/null
df -h
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml exec -T worker python -c 'from pathlib import Path; import time; p=Path("/tmp/gol-worker-heartbeat"); assert p.exists() and time.time()-p.stat().st_mtime<300'
: "${PUBLIC_HTTPS_URL:?set authorized HTTPS address}"
case "$PUBLIC_HTTPS_URL" in https://*) ;; *) exit 2;; esac
python3 ops/monitor.py --public-url "$PUBLIC_HTTPS_URL"
public_base=${PUBLIC_HTTPS_URL%/}
test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$public_base/api/events")" = 401
test "$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$public_base/api/health")" = 404
# PASS requires current, explicit acceptance evidence; infrastructure checks alone never authorize invitations.
: "${RELEASE_GATE_EVIDENCE:?set verified release gate JSON}"
python3 ops/release_gates.py "$RELEASE_GATE_EVIDENCE"
