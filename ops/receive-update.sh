#!/usr/bin/env bash
# Download one successful private Actions build, verify, and load images only.
set -euo pipefail
umask 077
if (( $# != 2 )); then
  printf 'Usage: bash ops/receive-update.sh RUN_ID EXPECTED_COMMIT\n' >&2
  exit 2
fi
run_id=$1; expected_sha=$2
[[ "$run_id" =~ ^[0-9]+$ && "$expected_sha" =~ ^[0-9a-f]{40}$ ]]
delivery=$(mktemp -d "$HOME/lifexp-${expected_sha:0:8}.XXXXXX")
gh api "repos/X-xu-X/my-life-rpg/actions/runs/$run_id" > "$delivery/workflow-run.json"
python3 - "$delivery/workflow-run.json" "$expected_sha" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r['head_sha']==sys.argv[2] and r['status']=='completed' and r['conclusion']=='success'
assert r['head_repository']['full_name']=='X-xu-X/my-life-rpg'
print('BUILD_COMMIT_VERIFIED')
PY
gh run download "$run_id" --repo X-xu-X/my-life-rpg --name "lifexp-linux-amd64-$expected_sha" --dir "$delivery"
cd "$delivery"
sha256sum -c SHA256SUMS
release=$(python3 - "$expected_sha" <<'PY'
import json,re,sys
from pathlib import Path
r=json.loads(Path('BUILD_RECEIPT.json').read_text())
assert r['git_head']==sys.argv[1] and r['target_platform']=='linux/amd64' and r['image_status']=='BUILT'
assert re.fullmatch(r'rr-[A-Za-z0-9._-]+',r['release_id'])
print(r['release_id'])
PY
)
source_dir="$delivery/source"
mkdir "$source_dir"
python3 - "$release.zip" "$source_dir" "$expected_sha" "$release" <<'PY'
import json,sys,zipfile
from pathlib import Path,PurePosixPath
with zipfile.ZipFile(sys.argv[1]) as z:
    m=json.loads(z.read('RELEASE_MANIFEST.json'))
    assert m['git_head']==sys.argv[3] and m['release_id']==sys.argv[4]
    assert len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(m['files'])|{'RELEASE_MANIFEST.json'}
    for name in z.namelist():
        p=PurePosixPath(name)
        assert not p.is_absolute() and '..' not in p.parts and '\\' not in name
    z.extractall(Path(sys.argv[2]))
PY
python3 -B "$source_dir/ops/verify_package.py" "$source_dir/RELEASE_MANIFEST.json"
gzip -dc "images-$release.tar.gz" > "images-$release.tar"
sha256sum -c "images-$release.tar.sha256"
python3 -B "$source_dir/ops/image_identity.py" verify-archive --archive "images-$release.tar" --manifest "images-$release.manifest.jsonl" --release-id "$release" --platform linux/amd64
sudo -n docker load -i "images-$release.tar"
sudo -n python3 -B "$source_dir/ops/image_identity.py" verify --manifest "images-$release.manifest.jsonl" --release-id "$release" --platform linux/amd64
cp "images-$release.manifest.jsonl" "$source_dir/"
printf '\nIMAGES_READY\nSOURCE_DIR=%s\nRELEASE_ID=%s\n' "$source_dir" "$release"
