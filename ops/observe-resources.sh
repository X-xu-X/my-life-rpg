#!/bin/sh
set -eu
: "${PRODUCTION_ENV_FILE:?set protected compose env file}" "${OBSERVATION_FILE:?set new evidence file}"
test ! -e "$OBSERVATION_FILE"
umask 077
compose() { docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml "$@"; }
compose config --quiet
# 31 samples, 30 minutes apart from startup overhead. Operator records workload windows separately.
i=0
while [ "$i" -le 30 ]; do
  {
    date -u '+%Y-%m-%dT%H:%M:%SZ'
    free -b
    vmstat 1 2
    docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}} {{.BlockIO}} {{.PIDs}}'
    for id in $(compose ps -q); do docker inspect --format '{{.Name}} OOM={{.State.OOMKilled}} restarts={{.RestartCount}} status={{.State.Status}}' "$id"; done
    df -B1
    docker system df
  } >> "$OBSERVATION_FILE"
  i=$((i+1))
  if [ "$i" -le 30 ]; then sleep 60; fi
done
