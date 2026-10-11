"""Versioned image config identities; never serialize inspect.Config as a digest.

docker save is streamed from the *installed* tags when verifying a deployment.
Only bounded JSON metadata is read into memory; layer bytes are skipped.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import tarfile
import threading

SCHEMA = 2
MAX_MANIFEST = 64 * 1024
MAX_JSON = 4 * 1024 * 1024
MAX_JSON_TOTAL = 32 * 1024 * 1024
MAX_MEMBERS = 4096
TIMEOUT = 300
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
INSPECT_FORMAT = ('{"observed_id":{{json .Id}},"os":{{json .Os}},'
                  '"architecture":{{json .Architecture}},"user":{{json (index .Config "User")}},'
                  '"tags":{{json .RepoTags}}}')
FIELDS = {'schema_version', 'release_id', 'role', 'image', 'config_digest',
          'observed_id', 'platform', 'user'}


class BoundedTarInfo(tarfile.TarInfo):
    """Bound hidden PAX/GNU headers before tarfile buffers them internally."""
    def _proc_member(self, archive):
        archive.identity_headers = getattr(archive, 'identity_headers', 0) + 1
        if archive.identity_headers > MAX_MEMBERS: fail('IMAGE_ARCHIVE_MEMBER_LIMIT')
        extended = self.type in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK)
        if not extended and self.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE): fail('IMAGE_ARCHIVE_MEMBER_INVALID')
        archive.identity_chain = getattr(archive, 'identity_chain', 0) + 1 if extended else 0
        if extended and (self.size > 64 * 1024 or archive.identity_chain > 16): fail('IMAGE_ARCHIVE_HEADER_LIMIT')
        if self.size < 0: fail('IMAGE_ARCHIVE_MEMBER_INVALID')
        return super()._proc_member(archive)

    def _proc_gnusparse_10(self, *args):
        fail('IMAGE_ARCHIVE_FORMAT_UNSUPPORTED')

    _proc_gnusparse_00 = _proc_gnusparse_10
    _proc_gnusparse_01 = _proc_gnusparse_10


def fail(category):
    raise ValueError(category)


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj: fail('IMAGE_JSON_DUPLICATE_KEY')
        obj[key] = value
    return obj


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError):
        fail('IMAGE_JSON_INVALID')


def image_names(release_id):
    if not isinstance(release_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{5,100}', release_id):
        fail('IMAGE_RELEASE_ID_INVALID')
    return {role: f'game-of-life-{role}:{release_id}' for role in ('api', 'web', 'ops')} | {'postgres': 'postgres:18.6-bookworm'}


def check_platform(platform):
    if platform not in ('linux/amd64', 'linux/arm64'): fail('IMAGE_PLATFORM_UNSUPPORTED')


def normalize_user(value, category):
    # OCI optional User: missing/null means the default, but 0/false are errors.
    if value is None: return ''
    if not isinstance(value, str): fail(category)
    return value


def read_manifest(path, release_id, platform):
    check_platform(platform)
    names = image_names(release_id)
    try:
        with Path(path).open('rb') as stream: raw = stream.read(MAX_MANIFEST + 1)
    except OSError:
        fail('IMAGE_MANIFEST_MISSING')
    if len(raw) > MAX_MANIFEST: fail('IMAGE_MANIFEST_TOO_LARGE')
    rows = []
    for line in raw.splitlines():
        if not line.strip(): continue
        row = decode(line)
        if not isinstance(row, dict): fail('IMAGE_MANIFEST_INVALID')
        if 'schema_version' not in row or 'id' in row: fail('IMAGE_MANIFEST_REBUILD_REQUIRED')
        if type(row['schema_version']) is not int or row['schema_version'] != SCHEMA: fail('IMAGE_MANIFEST_VERSION_UNSUPPORTED')
        if set(row) != FIELDS: fail('IMAGE_MANIFEST_INVALID')
        role = row['role']
        if not isinstance(role, str) or role not in names or any(r['role'] == role for r in rows): fail('IMAGE_MANIFEST_ROLE_INVALID')
        if row['release_id'] != release_id: fail('IMAGE_RELEASE_MISMATCH')
        if row['image'] != names[role]: fail('IMAGE_TAG_MISMATCH')
        if row['platform'] != platform: fail('IMAGE_ARCH_MISMATCH')
        if any(not isinstance(row[k], str) or not DIGEST.fullmatch(row[k]) for k in ('config_digest', 'observed_id')): fail('IMAGE_DIGEST_INVALID')
        if not isinstance(row['user'], str): fail('IMAGE_USER_INVALID')
        if role != 'postgres' and row['user'] != '10001:10001': fail('IMAGE_APPLICATION_UID_MISMATCH')
        rows.append(row)
    if len(rows) != 4 or {r['role'] for r in rows} != set(names): fail('IMAGE_MANIFEST_INCOMPLETE')
    return rows


def config_identity(raw, name):
    value = decode(raw)
    if not isinstance(value, dict) or not all(k in value for k in ('architecture', 'os', 'rootfs', 'config')):
        fail('IMAGE_ARCHIVE_CONFIG_INVALID')
    rootfs = value['rootfs']
    if not isinstance(rootfs, dict) or rootfs.get('type') != 'layers' or not isinstance(rootfs.get('diff_ids'), list): fail('IMAGE_ARCHIVE_CONFIG_INVALID')
    if any(not isinstance(d, str) or not DIGEST.fullmatch(d) for d in rootfs['diff_ids']): fail('IMAGE_ARCHIVE_CONFIG_INVALID')
    if not isinstance(value['config'], dict): fail('IMAGE_ARCHIVE_CONFIG_INVALID')
    user = normalize_user(value['config'].get('User'), 'IMAGE_ARCHIVE_CONFIG_INVALID')
    if not isinstance(value['os'], str) or not isinstance(value['architecture'], str): fail('IMAGE_ARCHIVE_CONFIG_INVALID')
    digest = hashlib.sha256(raw).hexdigest()
    # Both Docker legacy config names and OCI content-addressed paths bind raw bytes.
    if name not in (digest + '.json', 'blobs/sha256/' + digest): fail('IMAGE_ARCHIVE_CONFIG_HASH_MISMATCH')
    return {'config_digest': 'sha256:' + digest, 'platform': value['os'] + '/' + value['architecture'], 'user': user}


def archive_identities(stream, images):
    """No extraction and no layer buffering. Reject ambiguous tags/unknown formats."""
    configs, seen, manifest = {}, set(), None
    total_json = 0
    try:
        with tarfile.open(fileobj=stream, mode='r|', tarinfo=BoundedTarInfo) as archive:
            for number, member in enumerate(archive, 1):
                if number > MAX_MEMBERS: fail('IMAGE_ARCHIVE_MEMBER_LIMIT')
                name = member.name
                path = PurePosixPath(name)
                if len(name) > 512 or path.is_absolute() or '..' in path.parts or '\\' in name: fail('IMAGE_ARCHIVE_PATH_INVALID')
                if name in seen: fail('IMAGE_ARCHIVE_DUPLICATE_MEMBER')
                seen.add(name)
                if member.isdir(): continue
                if not member.isfile(): fail('IMAGE_ARCHIVE_MEMBER_INVALID')
                candidate = name == 'manifest.json' or bool(re.fullmatch(r'[0-9a-f]{64}\.json|blobs/sha256/[0-9a-f]{64}', name))
                if not candidate: continue
                src = archive.extractfile(member)
                first = src.read(min(256, member.size))
                if name != 'manifest.json' and not first.lstrip().startswith(b'{'): continue
                if member.size > MAX_JSON: fail('IMAGE_ARCHIVE_JSON_TOO_LARGE')
                total_json += member.size
                if total_json > MAX_JSON_TOTAL: fail('IMAGE_ARCHIVE_JSON_LIMIT')
                raw = first + src.read(member.size - len(first))
                if len(raw) != member.size: fail('IMAGE_ARCHIVE_TRUNCATED')
                value = decode(raw)
                if name == 'manifest.json': manifest = value
                elif isinstance(value, dict) and 'rootfs' in value:
                    configs[name] = config_identity(raw, name)
                # OCI manifest/index JSON is not a config, and is never used as one.
    except (tarfile.TarError, OSError, EOFError):
        fail('IMAGE_ARCHIVE_INVALID')
    if not isinstance(manifest, list) or not manifest: fail('IMAGE_ARCHIVE_FORMAT_UNSUPPORTED')
    result = {}
    for entry in manifest:
        if not isinstance(entry, dict) or not isinstance(entry.get('Config'), str) or not isinstance(entry.get('RepoTags'), list): fail('IMAGE_ARCHIVE_MANIFEST_INVALID')
        if any(not isinstance(t, str) for t in entry['RepoTags']): fail('IMAGE_ARCHIVE_MANIFEST_INVALID')
        for image in images:
            if image in entry['RepoTags']:
                if image in result: fail('IMAGE_ARCHIVE_TAG_AMBIGUOUS')
                if entry['Config'] not in configs: fail('IMAGE_ARCHIVE_CONFIG_MISSING')
                if not isinstance(entry.get('Layers'), list) or any(not isinstance(n, str) or n not in seen for n in entry['Layers']): fail('IMAGE_ARCHIVE_LAYER_MISSING')
                result[image] = configs[entry['Config']]
    if set(result) != set(images): fail('IMAGE_ARCHIVE_TAG_MISSING')
    return result


def inspect_images(images):
    # Bounded, selected non-secret fields only; never print full inspect or stderr.
    try:
        proc = subprocess.Popen(['docker', 'image', 'inspect', '--format', INSPECT_FORMAT, *images],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=(os.name == 'posix'))
    except OSError: fail('IMAGE_INSPECT_FAILED')
    timer = threading.Timer(45, stop_process, args=(proc,))
    timer.daemon = True; timer.start()
    try:
        raw = proc.stdout.read(MAX_MANIFEST + 1)
        if len(raw) > MAX_MANIFEST: fail('IMAGE_INSPECT_TOO_LARGE')
        if proc.wait(timeout=5): fail('IMAGE_INSPECT_FAILED')
    except (OSError, subprocess.TimeoutExpired): fail('IMAGE_INSPECT_FAILED')
    finally:
        stop_process(proc); proc.stdout.close()
        try: proc.wait(timeout=5)
        finally: timer.cancel(); timer.join()
    lines = raw.splitlines()
    if len(lines) != len(images): fail('IMAGE_INSPECT_INVALID')
    result = {}
    for image, line in zip(images, lines):
        meta = decode(line)
        if not isinstance(meta, dict) or set(meta) != {'observed_id', 'os', 'architecture', 'user', 'tags'}: fail('IMAGE_INSPECT_INVALID')
        meta['user'] = normalize_user(meta['user'], 'IMAGE_INSPECT_INVALID')
        if not isinstance(meta['observed_id'], str) or not DIGEST.fullmatch(meta['observed_id']): fail('IMAGE_INSPECT_INVALID')
        if not isinstance(meta['tags'], list) or any(not isinstance(t, str) for t in meta['tags']) or image not in meta['tags']: fail('IMAGE_TAG_MISMATCH')
        if any(not isinstance(meta[k], str) for k in ('os', 'architecture', 'user')): fail('IMAGE_INSPECT_INVALID')
        result[image] = meta
    return result


def stop_process(proc):
    if proc.poll() is None:
        try:
            if os.name == 'posix': os.killpg(proc.pid, signal.SIGKILL)
            else: proc.kill()
        except ProcessLookupError: pass


def installed_identities(images, platform, timeout=TIMEOUT):
    """Export the installed tags, not a user-supplied TAR beside the deployment."""
    check_platform(platform)
    if not 1 <= timeout <= 900: fail('IMAGE_TIMEOUT_INVALID')
    before = inspect_images(images)
    try:
        proc = subprocess.Popen(['docker', 'image', 'save', '--platform', platform, *images],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=(os.name == 'posix'))
    except OSError: fail('IMAGE_SAVE_FAILED')
    expired = threading.Event()
    def expire():
        expired.set(); stop_process(proc)
    timer = threading.Timer(timeout, expire)
    timer.daemon = True; timer.start()
    try:
        try:
            identities = archive_identities(proc.stdout, images)
            # Drain any bytes past TAR end without buffering the full stream.
            while proc.stdout.read(64 * 1024): pass
            status = proc.wait(timeout=5)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            if expired.is_set(): fail('IMAGE_SAVE_TIMEOUT')
            raise
        if expired.is_set(): fail('IMAGE_SAVE_TIMEOUT')
        if status: fail('IMAGE_SAVE_FAILED')
    finally:
        stop_process(proc); proc.stdout.close()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: fail('IMAGE_SAVE_REAP_FAILED')
        timer.cancel(); timer.join()
    after = inspect_images(images)
    for image in images:
        if before[image] != after[image]: fail('IMAGE_TAG_CHANGED_DURING_CHECK')
        meta, identity = before[image], identities[image]
        if meta['os'] + '/' + meta['architecture'] != identity['platform'] or identity['platform'] != platform: fail('IMAGE_ARCH_MISMATCH')
        if meta['user'] != identity['user']: fail('IMAGE_USER_MISMATCH')
    return identities, before


def compare(row, actual):
    if actual['platform'] != row['platform']: fail('IMAGE_ARCH_MISMATCH')
    if actual['user'] != row['user']: fail('IMAGE_APPLICATION_UID_MISMATCH' if row['role'] != 'postgres' else 'IMAGE_USER_MISMATCH')
    if actual['config_digest'] != row['config_digest']: fail('IMAGE_CONFIG_DIGEST_MISMATCH')


def verify_installed(path, release_id, platform, core_only=False):
    rows = read_manifest(path, release_id, platform)
    selected = [r for r in rows if not core_only or r['role'] != 'ops']
    identities, observed = installed_identities([r['image'] for r in selected], platform)
    for row in selected: compare(row, identities[row['image']])
    return {'status': 'PASS', 'schema_version': SCHEMA, 'identity_type': 'raw-image-config-sha256',
            'platform': platform, 'roles': [r['role'] for r in selected],
            'outer_id_changed': [r['role'] for r in selected if observed[r['image']]['observed_id'] != r['observed_id']]}


def create_manifest(archive, path, release_id, platform):
    names = image_names(release_id); check_platform(platform)
    if Path(path).exists(): fail('IMAGE_MANIFEST_EXISTS')
    with Path(archive).open('rb') as stream: saved = archive_identities(stream, list(names.values()))
    live, observed = installed_identities(list(names.values()), platform)
    rows = []
    for role, image in names.items():
        identity = saved[image]
        if identity != live[image]: fail('IMAGE_ARCHIVE_INSTALLED_MISMATCH')
        if identity['platform'] != platform: fail('IMAGE_ARCH_MISMATCH')
        if role != 'postgres' and identity['user'] != '10001:10001': fail('IMAGE_APPLICATION_UID_MISMATCH')
        rows.append({'schema_version': SCHEMA, 'release_id': release_id, 'role': role, 'image': image,
                     **identity, 'observed_id': observed[image]['observed_id']})
    with Path(path).open('x', encoding='utf-8', newline='\n') as output:
        for row in rows: output.write(json.dumps(row, sort_keys=True) + '\n')
    return {'status': 'PASS', 'schema_version': SCHEMA, 'roles': list(names), 'identity_type': 'raw-image-config-sha256'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('create', 'verify', 'verify-archive'))
    parser.add_argument('--manifest', required=True); parser.add_argument('--release-id', required=True)
    parser.add_argument('--platform', required=True); parser.add_argument('--archive')
    parser.add_argument('--core-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.operation == 'create':
            if not args.archive or args.core_only: fail('IMAGE_ARGUMENT_INVALID')
            result = create_manifest(args.archive, args.manifest, args.release_id, args.platform)
        elif args.operation == 'verify':
            if args.archive: fail('IMAGE_ARGUMENT_INVALID')
            result = verify_installed(args.manifest, args.release_id, args.platform, args.core_only)
        else:
            if not args.archive or args.core_only: fail('IMAGE_ARGUMENT_INVALID')
            rows = read_manifest(args.manifest, args.release_id, args.platform)
            with Path(args.archive).open('rb') as stream: identities = archive_identities(stream, [r['image'] for r in rows])
            for row in rows: compare(row, identities[row['image']])
            result = {'status': 'PASS', 'scope': 'archive-only', 'installed_images': 'NOT_CHECKED'}
        print(json.dumps(result))
    except Exception as exc:
        category = str(exc) if isinstance(exc, ValueError) and re.fullmatch('[A-Z0-9_]+', str(exc)) else 'IMAGE_IDENTITY_CHECK_FAILED'
        print(json.dumps({'status': 'FAIL', 'category': category})); return 2
    return 0


if __name__ == '__main__': raise SystemExit(main())
