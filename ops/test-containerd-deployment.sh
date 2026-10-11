#!/bin/sh
# Import the actual newly built delivery, including official PostgreSQL, into Docker29.
# Only for an isolated Actions runner. No DB process, host socket mount or public port.
set -eu
: "${GITHUB_ACTIONS:?runner required}" "${RUNNER_TEMP:?runner temp required}" "${RELEASE_ID:?}" "${TARGET_PLATFORM:?}"
test "$GITHUB_ACTIONS" = true
test "$(uname -s)" = Linux
test "$TARGET_PLATFORM" = linux/amd64
test -f "images-$RELEASE_ID.tar"
original_docker=$(command -v docker)
test_root=$(mktemp -d "$RUNNER_TEMP/production-containerd.XXXXXX")
node_id=
cleanup() { test -z "$node_id" || "$original_docker" rm -f "$node_id" >/dev/null; }
trap cleanup EXIT
trap 'exit 130' INT TERM
"$original_docker" image inspect postgres:18.6-bookworm --format '{{json .RepoDigests}}' > "$test_root/official-postgres.json"
python3 - "$test_root/official-postgres.json" <<'PY'
import json, sys
refs = json.load(open(sys.argv[1]))
assert refs and any(ref.startswith('postgres@sha256:') or ref.startswith('docker.io/library/postgres@sha256:') for ref in refs)
PY
"$original_docker" image inspect docker:29-dind --format '{{json .RepoDigests}}' > "$test_root/dind-image.json"
node_id=$("$original_docker" run -d --rm --privileged --network none -e DOCKER_TLS_CERTDIR= docker:29-dind dockerd --host=unix:///var/run/docker.sock --feature=containerd-snapshotter=true --storage-driver=overlayfs --bridge=none --iptables=false --ip6tables=false)
ready=false
for attempt in $(seq 1 60); do
    if "$original_docker" exec "$node_id" docker info >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
done
if test "$ready" != true; then "$original_docker" logs --tail 80 "$node_id"; exit 2; fi
"$original_docker" exec "$node_id" docker info --format '{{.Driver}} {{json .DriverStatus}}' > "$test_root/driver.txt"
python3 - "$test_root/driver.txt" <<'PY'
import sys
assert 'io.containerd.snapshotter.v1' in open(sys.argv[1]).read()
PY
"$original_docker" exec -i "$node_id" docker load < "images-$RELEASE_ID.tar"
mkdir "$test_root/bin"
cat > "$test_root/bin/docker" <<'SH'
#!/bin/sh
exec "$IMAGE_TEST_DOCKER" exec -i "$IMAGE_TEST_NODE" docker "$@"
SH
chmod 700 "$test_root/bin/docker"
export IMAGE_TEST_DOCKER="$original_docker" IMAGE_TEST_NODE="$node_id"
export PATH="$test_root/bin:$PATH"
python3 -B ops/image_identity.py verify --manifest "images-$RELEASE_ID.manifest.jsonl" --release-id "$RELEASE_ID" --platform "$TARGET_PLATFORM" > "$test_root/full.json"
python3 -B ops/image_identity.py verify --manifest "images-$RELEASE_ID.manifest.jsonl" --release-id "$RELEASE_ID" --platform "$TARGET_PLATFORM" --core-only > "$test_root/core.json"
docker image inspect postgres:18.6-bookworm --format '{{json (index .Config "User")}}' > "$test_root/postgres-user.json"
# Only emit whether the key exists, never any other Config value (including Env).
docker image inspect postgres:18.6-bookworm --format '{{range $key, $value := .Config}}{{if eq $key "User"}}present{{end}}{{end}}' > "$test_root/postgres-user-key.txt"
docker version --format '{{.Server.Version}}' > "$test_root/docker-version.txt"
python3 - "$test_root" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(sys.argv[1]); release = os.environ['RELEASE_ID']
full, core = [json.loads((root / name).read_text()) for name in ('full.json', 'core.json')]
assert full['status'] == core['status'] == 'PASS'
assert full['roles'] == ['api', 'web', 'ops', 'postgres'] and core['roles'] == ['api', 'web', 'postgres']
rows = [json.loads(line) for line in Path('images-' + release + '.manifest.jsonl').read_text().splitlines()]
pg = next(row for row in rows if row['role'] == 'postgres')
assert pg['image'] == 'postgres:18.6-bookworm' and pg['platform'] == 'linux/amd64' and pg['user'] == ''
raw_user = json.loads((root / 'postgres-user.json').read_text())
assert raw_user is None or raw_user == ''
version = (root / 'docker-version.txt').read_text().strip(); assert version.startswith('29.')
report = {'status': 'PASS', 'scope': 'actual-deployment-images-containerd-import', 'release_id': release,
          'platform': os.environ['TARGET_PLATFORM'], 'docker_version': version,
          'driver': (root / 'driver.txt').read_text().strip(),
          'dind_image': json.loads((root / 'dind-image.json').read_text()),
          'official_postgres_repo_digests': json.loads((root / 'official-postgres.json').read_text()),
          'postgres_config_digest': pg['config_digest'], 'postgres_expected_user': pg['user'],
          'postgres_inspect_user': raw_user, 'postgres_inspect_user_key_present': (root / 'postgres-user-key.txt').read_text().strip() == 'present',
          'full': full, 'core_only': core, 'database_execution': 'NOT_RUN'}
(root / 'PRODUCTION_CONTAINERD_VERIFY.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
PY
cp "$test_root/PRODUCTION_CONTAINERD_VERIFY.json" "$RUNNER_TEMP/PRODUCTION_CONTAINERD_VERIFY.json"
