#!/bin/sh
# Runner-only, synthetic images. Never run this privileged harness on production.
set -eu
: "${GITHUB_ACTIONS:?isolated GitHub runner required}" "${RUNNER_TEMP:?runner temp required}"
test "$GITHUB_ACTIONS" = true
test "$(uname -s)" = Linux
original_docker=$(command -v docker)
test_root=$(mktemp -d "$RUNNER_TEMP/image-store-compat.XXXXXX")
classic_id=; containerd_id=
cleanup() {
    # Only the two new --rm test containers; never prune or touch host daemon storage.
    test -z "$classic_id" || "$original_docker" rm -f "$classic_id" >/dev/null
    test -z "$containerd_id" || "$original_docker" rm -f "$containerd_id" >/dev/null
}
trap cleanup EXIT
trap 'exit 130' INT TERM
"$original_docker" pull docker:29-dind
"$original_docker" image inspect docker:29-dind --format '{{json .RepoDigests}}' > "$test_root/dind-image.json"
classic_id=$("$original_docker" run -d --rm --privileged --network none -e DOCKER_TLS_CERTDIR= docker:29-dind dockerd --host=unix:///var/run/docker.sock --feature=containerd-snapshotter=false --storage-driver=vfs --bridge=none --iptables=false --ip6tables=false)
containerd_id=$("$original_docker" run -d --rm --privileged --network none -e DOCKER_TLS_CERTDIR= docker:29-dind dockerd --host=unix:///var/run/docker.sock --feature=containerd-snapshotter=true --storage-driver=overlayfs --bridge=none --iptables=false --ip6tables=false)
for node in "$classic_id" "$containerd_id"; do
    ready=false
    for attempt in $(seq 1 60); do
        if "$original_docker" exec "$node" docker info >/dev/null 2>&1; then ready=true; break; fi
        sleep 1
    done
    if test "$ready" != true; then "$original_docker" logs --tail 80 "$node"; exit 2; fi
done
"$original_docker" exec "$classic_id" docker info --format '{{.Driver}}' > "$test_root/classic.driver"
"$original_docker" exec "$containerd_id" docker info --format '{{.Driver}} {{json .DriverStatus}}' > "$test_root/containerd.driver"
test "$(cat "$test_root/classic.driver")" = vfs
python3 - "$test_root/containerd.driver" <<'PY'
import sys
assert 'io.containerd.snapshotter.v1' in open(sys.argv[1]).read()
PY
mkdir "$test_root/bin" "$test_root/context"
cat > "$test_root/bin/docker" <<'SH'
#!/bin/sh
exec "$IMAGE_TEST_DOCKER" exec -i "$IMAGE_TEST_NODE" docker "$@"
SH
chmod 700 "$test_root/bin/docker"
cat > "$test_root/context/Dockerfile" <<'DOCKERFILE'
FROM scratch
COPY Dockerfile /fixture
USER 10001:10001
DOCKERFILE
"$original_docker" cp "$test_root/context" "$classic_id:/context"
release=rr-store-compat-fixture
"$original_docker" exec "$classic_id" docker build --network none --platform linux/amd64 -t "game-of-life-api:$release" /context
for role in web ops; do "$original_docker" exec "$classic_id" docker tag "game-of-life-api:$release" "game-of-life-$role:$release"; done
# This postgres-tagged scratch fixture tests the protocol only, never the real PG server.
cat > "$test_root/context/Dockerfile" <<'DOCKERFILE'
FROM scratch
COPY Dockerfile /fixture
USER 999:999
DOCKERFILE
"$original_docker" cp "$test_root/context/Dockerfile" "$classic_id:/context/Dockerfile"
"$original_docker" exec "$classic_id" docker build --network none --platform linux/amd64 -t postgres:18.6-bookworm /context
set -- "game-of-life-api:$release" "game-of-life-web:$release" "game-of-life-ops:$release" postgres:18.6-bookworm
"$original_docker" exec "$classic_id" docker image save --platform linux/amd64 "$@" > "$test_root/classic.tar"
export IMAGE_TEST_DOCKER="$original_docker" IMAGE_TEST_NODE="$classic_id"
export PATH="$test_root/bin:$PATH"
python3 -B ops/image_identity.py create --archive "$test_root/classic.tar" --manifest "$test_root/classic.jsonl" --release-id "$release" --platform linux/amd64
python3 -B ops/image_identity.py verify --manifest "$test_root/classic.jsonl" --release-id "$release" --platform linux/amd64 > "$test_root/classic-self.json"
"$original_docker" exec -i "$containerd_id" docker load < "$test_root/classic.tar"
export IMAGE_TEST_NODE="$containerd_id"
python3 -B ops/image_identity.py verify --manifest "$test_root/classic.jsonl" --release-id "$release" --platform linux/amd64 > "$test_root/classic-to-containerd.json"
python3 -B ops/image_identity.py verify --manifest "$test_root/classic.jsonl" --release-id "$release" --platform linux/amd64 --core-only > "$test_root/core-only.json"
docker image save --platform linux/amd64 "$@" > "$test_root/containerd.tar"
python3 -B ops/image_identity.py create --archive "$test_root/containerd.tar" --manifest "$test_root/containerd.jsonl" --release-id "$release" --platform linux/amd64
"$original_docker" exec -i "$classic_id" docker load < "$test_root/containerd.tar"
export IMAGE_TEST_NODE="$classic_id"
python3 -B ops/image_identity.py verify --manifest "$test_root/containerd.jsonl" --release-id "$release" --platform linux/amd64 > "$test_root/containerd-to-classic.json"
# A second real Docker build deliberately omits USER; retain the explicit sample above.
cat > "$test_root/context/Dockerfile" <<'DOCKERFILE'
FROM scratch
COPY Dockerfile /fixture-default-user
DOCKERFILE
"$original_docker" cp "$test_root/context/Dockerfile" "$classic_id:/context/Dockerfile"
"$original_docker" exec "$classic_id" docker build --network none --platform linux/amd64 -t postgres:18.6-bookworm /context
"$original_docker" exec "$classic_id" docker image save --platform linux/amd64 "$@" > "$test_root/default-classic.tar"
python3 -B ops/image_identity.py create --archive "$test_root/default-classic.tar" --manifest "$test_root/default-classic.jsonl" --release-id "$release" --platform linux/amd64
python3 -B ops/image_identity.py verify --manifest "$test_root/default-classic.jsonl" --release-id "$release" --platform linux/amd64 > "$test_root/default-classic-self.json"
"$original_docker" exec -i "$containerd_id" docker load < "$test_root/default-classic.tar"
export IMAGE_TEST_NODE="$containerd_id"
python3 -B ops/image_identity.py verify --manifest "$test_root/default-classic.jsonl" --release-id "$release" --platform linux/amd64 > "$test_root/default-classic-to-containerd.json"
python3 -B ops/image_identity.py verify --manifest "$test_root/default-classic.jsonl" --release-id "$release" --platform linux/amd64 --core-only > "$test_root/default-core-only.json"
docker image inspect postgres:18.6-bookworm --format '{{json (index .Config "User")}}' > "$test_root/default-user.json"
docker image save --platform linux/amd64 "$@" > "$test_root/default-containerd.tar"
python3 -B ops/image_identity.py create --archive "$test_root/default-containerd.tar" --manifest "$test_root/default-containerd.jsonl" --release-id "$release" --platform linux/amd64
"$original_docker" exec -i "$classic_id" docker load < "$test_root/default-containerd.tar"
export IMAGE_TEST_NODE="$classic_id"
python3 -B ops/image_identity.py verify --manifest "$test_root/default-containerd.jsonl" --release-id "$release" --platform linux/amd64 > "$test_root/default-containerd-to-classic.json"
"$original_docker" exec "$classic_id" docker version --format '{{.Server.Version}}' > "$test_root/docker-version.txt"
python3 - "$test_root" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
matrix = {name: json.loads((root / (name + '.json')).read_text()) for name in
          ('classic-self', 'classic-to-containerd', 'core-only', 'containerd-to-classic')}
assert all(row['status'] == 'PASS' for row in matrix.values())
assert set(matrix['classic-to-containerd']['outer_id_changed']) == {'api', 'web', 'ops', 'postgres'}
assert set(matrix['containerd-to-classic']['outer_id_changed']) == {'api', 'web', 'ops', 'postgres'}
default_matrix = {name: json.loads((root / ('default-' + name + '.json')).read_text()) for name in matrix}
assert all(row['status'] == 'PASS' for row in default_matrix.values())
assert json.loads((root / 'default-user.json').read_text()) in (None, '')
for direction in ('classic-to-containerd', 'containerd-to-classic'):
    assert set(default_matrix[direction]['outer_id_changed']) == {'api', 'web', 'ops', 'postgres'}
for name in ('default-classic', 'default-containerd'):
    rows = [json.loads(line) for line in (root / (name + '.jsonl')).read_text().splitlines()]
    assert next(row['user'] for row in rows if row['role'] == 'postgres') == ''
report = {'status': 'PASS', 'scope': 'synthetic-image-protocol-only',
          'docker_version': (root / 'docker-version.txt').read_text().strip(),
          'dind_image': json.loads((root / 'dind-image.json').read_text()),
          'classic_driver': (root / 'classic.driver').read_text().strip(),
          'containerd_driver': (root / 'containerd.driver').read_text().strip(), 'matrix': matrix,
          'default_user_matrix': default_matrix, 'default_user_template_value': json.loads((root / 'default-user.json').read_text())}
(root / 'IMAGE_STORE_COMPAT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
PY
cp "$test_root/IMAGE_STORE_COMPAT.json" "$RUNNER_TEMP/IMAGE_STORE_COMPAT.json"
