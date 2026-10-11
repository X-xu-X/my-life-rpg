"""Synthetic config archives and real subprocess streams; no Docker/DB required."""
import copy
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ops import image_identity as identity, preflight

RELEASE = 'rr-image-protocol-test'
PLATFORM = 'linux/amd64'
NAMES = identity.image_names(RELEASE)


def config(role, **changes):
    value = {'os': 'linux', 'architecture': 'amd64',
             'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + 'a' * 64]},
             'config': {'User': '' if role == 'postgres' else '10001:10001', 'Env': ['FIXTURE=yes']}}
    value.update(changes)
    # Deliberate whitespace proves the digest is over raw bytes, not JSON reserialization.
    return json.dumps(value, indent=2).encode() + b'\n'


def add(archive, name, raw):
    member = tarfile.TarInfo(name); member.size = len(raw)
    archive.addfile(member, io.BytesIO(raw))


def fixture(raws=None, oci=False, tags=None):
    raws = raws or {role: config(role) for role in NAMES}
    output = io.BytesIO(); rows = []; configs = set()
    with tarfile.open(fileobj=output, mode='w') as archive:
        layer = 'blobs/sha256/' + 'a' * 64 if oci else 'layer/layer.tar'
        add(archive, layer, b'not-a-real-layer-test-fixture')
        for role, name in NAMES.items():
            raw = raws[role]; digest = hashlib.sha256(raw).hexdigest()
            path = 'blobs/sha256/' + digest if oci else digest + '.json'
            if path not in configs: add(archive, path, raw); configs.add(path)
            rows.append({'Config': path, 'RepoTags': [(tags or {}).get(role, name)], 'Layers': [layer]})
        if oci:
            add(archive, 'index.json', b'{"schemaVersion":2,"manifests":[]}')
            add(archive, 'oci-layout', b'{"imageLayoutVersion":"1.0.0"}')
            add(archive, 'blobs/sha256/' + 'b' * 64, b'{"schemaVersion":2,"mediaType":"fixture"}')
        add(archive, 'manifest.json', json.dumps(rows).encode())
    return output.getvalue()


class ImageIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent, prefix='image-identity-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'images.manifest.jsonl'
        self.raws = {role: config(role) for role in NAMES}
        self.actual = identity.archive_identities(io.BytesIO(fixture(self.raws)), list(NAMES.values()))
        self.rows = [{'schema_version': 2, 'release_id': RELEASE, 'role': role, 'image': name,
                      **self.actual[name], 'observed_id': self.actual[name]['config_digest']}
                     for role, name in NAMES.items()]
        self.write()

    def write(self, rows=None):
        self.manifest.write_text(''.join(json.dumps(row) + '\n' for row in (self.rows if rows is None else rows)))

    def observed(self, outer='c'):
        return {name: {'observed_id': 'sha256:' + outer * 64, 'os': 'linux', 'architecture': 'amd64',
                       'user': self.actual[name]['user'], 'tags': [name]} for name in NAMES.values()}

    def live(self, raw=None, outer='c'):
        """Run an actual child writing a TAR to stdout, through the production parser."""
        path = self.root / 'installed.tar'; path.write_bytes(raw or fixture(self.raws, oci=True))
        original = subprocess.Popen
        processes = []
        def launch(args, **kwargs):
            self.assertEqual(args[:5], ['docker', 'image', 'save', '--platform', PLATFORM])
            proc = original([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(open(sys.argv[1],"rb").read())', str(path)], **kwargs)
            processes.append(proc); return proc
        with patch.object(identity, 'inspect_images', return_value=self.observed(outer)), patch.object(identity.subprocess, 'Popen', side_effect=launch):
            result = identity.verify_installed(self.manifest, RELEASE, PLATFORM)
        self.assertTrue(all(p.poll() is not None for p in processes))
        return result

    def test_classic_and_containerd_different_outer_ids_same_raw_config_pass(self):
        for outer in ('c', 'd'):
            with self.subTest(outer=outer):
                result = self.live(outer=outer)
                self.assertEqual(result['status'], 'PASS')
                self.assertEqual(result['outer_id_changed'], list(NAMES))

    def test_raw_bytes_digest_and_archive_layouts(self):
        for oci in (False, True):
            parsed = identity.archive_identities(io.BytesIO(fixture(self.raws, oci)), list(NAMES.values()))
            self.assertEqual(parsed, self.actual)
        raw = self.raws['api']
        self.assertEqual(self.actual[NAMES['api']]['config_digest'], 'sha256:' + hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(hashlib.sha256(raw).digest(), hashlib.sha256(json.dumps(json.loads(raw)).encode()).digest())

    def test_installed_config_change_with_same_layers_platform_user_fails(self):
        changed = copy.deepcopy(self.raws)
        # Only an environment setting changes. RootFS, platform and UID/GID are identical.
        changed['api'] = changed['api'].replace(b'FIXTURE=yes', b'FIXTURE=changed')
        with self.assertRaisesRegex(ValueError, '^IMAGE_CONFIG_DIGEST_MISMATCH$'):
            self.live(fixture(changed, oci=True))

    def test_postgres_config_change_is_checked(self):
        changed = dict(self.raws); changed['postgres'] = changed['postgres'].replace(b'FIXTURE=yes', b'FIXTURE=changed')
        with self.assertRaisesRegex(ValueError, 'IMAGE_CONFIG_DIGEST_MISMATCH'):
            self.live(fixture(changed, oci=True))

    def user_config(self, role, value, missing=False):
        data = json.loads(config(role))
        if missing: data['config'].pop('User')
        else: data['config']['User'] = value
        return json.dumps(data, indent=2).encode() + b'\n'

    def test_optional_user_raw_config_normalization_preserves_exact_digest(self):
        digests = set()
        for value, missing, expected in [(None, True, ''), ('', False, ''), (None, False, ''), ('999:999', False, '999:999')]:
            with self.subTest(value=value, missing=missing):
                raw = self.user_config('postgres', value, missing)
                digest = hashlib.sha256(raw).hexdigest(); digests.add(digest)
                result = identity.config_identity(raw, digest + '.json')
                self.assertEqual(result['user'], expected)
                self.assertEqual(result['config_digest'], 'sha256:' + digest)
        self.assertEqual(len(digests), 4)  # normalized user equality never changes raw identity

    def test_optional_user_wrong_types_rejected_in_raw_config(self):
        for value in (0, 1, False, True, [], {}, ['10001:10001']):
            with self.subTest(value=value):
                raw = self.user_config('postgres', value)
                with self.assertRaisesRegex(ValueError, 'IMAGE_ARCHIVE_CONFIG_INVALID'):
                    identity.config_identity(raw, hashlib.sha256(raw).hexdigest() + '.json')

    def test_postgres_missing_empty_null_and_explicit_users_verified(self):
        for value, missing, expected in [(None, True, ''), ('', False, ''), (None, False, ''), ('999:999', False, '999:999')]:
            with self.subTest(value=value, missing=missing):
                raws = dict(self.raws); raws['postgres'] = self.user_config('postgres', value, missing)
                actual = identity.archive_identities(io.BytesIO(fixture(raws)), list(NAMES.values()))
                self.rows[-1].update(actual[NAMES['postgres']]); self.write()
                self.actual[NAMES['postgres']] = actual[NAMES['postgres']]
                self.assertEqual(self.live(fixture(raws, oci=True))['status'], 'PASS')
                self.assertEqual(self.rows[-1]['user'], expected)

    def test_postgres_explicit_user_is_not_ignored(self):
        raws = dict(self.raws); raws['postgres'] = self.user_config('postgres', '999:999')
        self.actual[NAMES['postgres']]['user'] = '999:999'  # inspect agrees with exported raw config
        with self.assertRaisesRegex(ValueError, '^IMAGE_USER_MISMATCH$'):
            self.live(fixture(raws, oci=True))  # manifest still expects the default user

    def test_application_default_or_wrong_user_still_rejected(self):
        for role in ('api', 'web', 'ops'):
            for value, missing in ((None, True), ('', False), (None, False), ('0:0', False)):
                with self.subTest(role=role, value=value, missing=missing):
                    raws = dict(self.raws); raws[role] = self.user_config(role, value, missing)
                    old_identity = self.actual[NAMES[role]]
                    self.actual[NAMES[role]] = {**old_identity, 'user': '' if value is None else value}
                    try:
                        with self.assertRaisesRegex(ValueError, '^IMAGE_APPLICATION_UID_MISMATCH$'):
                            self.live(fixture(raws, oci=True))
                    finally: self.actual[NAMES[role]] = old_identity

    def test_postgres_default_user_config_digest_change_still_rejected(self):
        for value, missing in ((None, True), ('', False), (None, False)):
            with self.subTest(value=value, missing=missing):
                raws = dict(self.raws); raws['postgres'] = self.user_config('postgres', value, missing)
                actual = identity.archive_identities(io.BytesIO(fixture(raws)), list(NAMES.values()))
                self.rows[-1].update(actual[NAMES['postgres']]); self.write()
                raws['postgres'] = raws['postgres'].replace(b'FIXTURE=yes', b'FIXTURE=changed')
                with self.assertRaisesRegex(ValueError, '^IMAGE_CONFIG_DIGEST_MISMATCH$'):
                    self.live(fixture(raws, oci=True))

    def test_installed_wrong_platform_user_tag_and_missing_image_fail(self):
        cases = [('platform', 'api', 'IMAGE_ARCH_MISMATCH'), ('platform', 'postgres', 'IMAGE_ARCH_MISMATCH'),
                 ('user', 'api', 'IMAGE_USER_MISMATCH'), ('tag', 'api', 'IMAGE_ARCHIVE_TAG_MISSING')]
        for kind, role, error in cases:
            with self.subTest(kind=kind, role=role):
                raws = dict(self.raws); tags = None
                if kind == 'platform': raws[role] = config(role, architecture='arm64')
                if kind == 'user': raws[role] = raws[role].replace(b'10001:10001', b'0:0')
                if kind == 'tag': tags = {role: 'wrong:tag'}
                with self.assertRaisesRegex(ValueError, error): self.live(fixture(raws, True, tags))
        with patch.object(identity, 'inspect_images', side_effect=ValueError('IMAGE_INSPECT_FAILED')), patch.object(identity.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(ValueError, 'IMAGE_INSPECT_FAILED'):
                identity.verify_installed(self.manifest, RELEASE, PLATFORM)
            launch.assert_not_called()

    def test_bad_manifest_fails_closed(self):
        cases = [([], 'INCOMPLETE'), (self.rows[:3], 'INCOMPLETE'),
                 (self.rows + [self.rows[0]], 'ROLE_INVALID')]
        for key, value, error in [('schema_version', 3, 'VERSION_UNSUPPORTED'), ('schema_version', True, 'VERSION_UNSUPPORTED'),
                                  ('config_digest', 'sha256:no', 'DIGEST_INVALID'), ('platform', 'linux/arm64', 'ARCH_MISMATCH'),
                                  ('user', '10001', 'APPLICATION_UID_MISMATCH'), ('image', 'other:tag', 'TAG_MISMATCH'),
                                  ('release_id', 'rr-other', 'RELEASE_MISMATCH')]:
            rows = copy.deepcopy(self.rows); rows[0][key] = value; cases.append((rows, error))
        missing = copy.deepcopy(self.rows); del missing[0]['config_digest']; cases.append((missing, 'MANIFEST_INVALID'))
        for rows, error in cases:
            with self.subTest(error=error, rows=rows[:1]):
                self.write(rows)
                with self.assertRaisesRegex(ValueError, error): identity.read_manifest(self.manifest, RELEASE, PLATFORM)
        for text in ('{bad json}', '{"schema_version":2,"schema_version":2}', 'null'):
            self.manifest.write_text(text)
            with self.assertRaises(ValueError): identity.read_manifest(self.manifest, RELEASE, PLATFORM)

    def test_old_manifest_requires_new_build_and_is_never_rewritten(self):
        old = b'{"id":"sha256:' + b'a' * 64 + b'","platform":"linux/amd64","tags":["fixture:test"]}\n'
        self.manifest.write_bytes(old)
        with self.assertRaisesRegex(ValueError, 'IMAGE_MANIFEST_REBUILD_REQUIRED'):
            identity.verify_installed(self.manifest, RELEASE, PLATFORM)
        self.assertEqual(self.manifest.read_bytes(), old)

    def test_core_only_checks_postgres_and_still_requires_complete_manifest(self):
        with patch.object(identity, 'installed_identities', return_value=(self.actual, self.observed())) as live:
            result = identity.verify_installed(self.manifest, RELEASE, PLATFORM, core_only=True)
        self.assertEqual(result['roles'], ['api', 'web', 'postgres'])
        self.assertEqual(live.call_args.args[0], [NAMES[r] for r in ('api', 'web', 'postgres')])
        self.write(self.rows[:2])
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE'):
            identity.verify_installed(self.manifest, RELEASE, PLATFORM, core_only=True)

    def test_create_checks_saved_archive_against_installed_and_refuses_overwrite(self):
        archive = self.root / 'build.tar'; archive.write_bytes(fixture(self.raws))
        output = self.root / 'new.manifest.jsonl'
        with patch.object(identity, 'installed_identities', return_value=(self.actual, self.observed())):
            identity.create_manifest(archive, output, RELEASE, PLATFORM)
            self.assertEqual(len(identity.read_manifest(output, RELEASE, PLATFORM)), 4)
            with self.assertRaisesRegex(ValueError, 'MANIFEST_EXISTS'):
                identity.create_manifest(archive, output, RELEASE, PLATFORM)
        changed = copy.deepcopy(self.actual); changed[NAMES['api']]['config_digest'] = 'sha256:' + 'f' * 64
        with patch.object(identity, 'installed_identities', return_value=(changed, self.observed())):
            with self.assertRaisesRegex(ValueError, 'ARCHIVE_INSTALLED_MISMATCH'):
                identity.create_manifest(archive, self.root / 'rejected.jsonl', RELEASE, PLATFORM)
        self.assertFalse((self.root / 'rejected.jsonl').exists())

    def test_archive_rejects_hash_mismatch_paths_duplicates_and_missing_layers(self):
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            identity.config_identity(self.raws['api'], '0' * 64 + '.json')
        for path in ('../outside', '/absolute', 'back\\slash'):
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode='w') as archive: add(archive, path, b'x')
            with self.assertRaisesRegex(ValueError, 'PATH_INVALID'):
                identity.archive_identities(io.BytesIO(output.getvalue()), list(NAMES.values()))
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w') as archive:
            add(archive, 'manifest.json', b'[]'); add(archive, 'manifest.json', b'[]')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_MEMBER'):
            identity.archive_identities(io.BytesIO(output.getvalue()), list(NAMES.values()))
        output = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(fixture()), mode='r') as source, tarfile.open(fileobj=output, mode='w') as archive:
            for member in source:
                if member.name == 'layer/layer.tar': continue
                add(archive, member.name, source.extractfile(member).read())
        with self.assertRaisesRegex(ValueError, 'LAYER_MISSING'):
            identity.archive_identities(io.BytesIO(output.getvalue()), list(NAMES.values()))

    def test_stream_memory_bound_for_large_layer_and_metadata_limit(self):
        path = self.root / 'large.tar'
        # The layer is written incrementally and must be skipped incrementally too.
        class Zeros:
            def read(self, size): return b'\0' * size
        with tarfile.open(path, 'w') as archive:
            member = tarfile.TarInfo('huge/layer.tar'); member.size = 24 * 1024**2
            archive.addfile(member, Zeros())
            digest = hashlib.sha256(self.raws['api']).hexdigest()
            add(archive, digest + '.json', self.raws['api'])
            add(archive, 'manifest.json', json.dumps([{'Config': digest + '.json', 'RepoTags': [NAMES['api']], 'Layers': ['huge/layer.tar']}]).encode())
        tracemalloc.start()
        try:
            with path.open('rb') as stream: identity.archive_identities(stream, [NAMES['api']])
            self.assertLess(tracemalloc.get_traced_memory()[1], 2 * 1024**2)
        finally: tracemalloc.stop()
        with patch.object(identity, 'MAX_JSON', 100):
            with self.assertRaisesRegex(ValueError, 'JSON_TOO_LARGE'):
                identity.archive_identities(io.BytesIO(fixture()), list(NAMES.values()))

    def test_extended_tar_headers_are_bounded_before_tarfile_reads_payload(self):
        header = tarfile.TarInfo('pax'); header.type = tarfile.XHDTYPE; header.size = 1024**3
        with self.assertRaisesRegex(ValueError, 'IMAGE_ARCHIVE_HEADER_LIMIT'):
            identity.archive_identities(io.BytesIO(header.tobuf() + b'\0' * 1024), list(NAMES.values()))

    def test_cli_failures_are_nonzero_and_do_not_disclose_exception_text(self):
        command = [sys.executable, '-B', str(Path(identity.__file__)), 'verify', '--manifest', str(self.manifest),
                   '--release-id', RELEASE, '--platform', PLATFORM]
        self.manifest.write_text('{bad json}')
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout), {'status': 'FAIL', 'category': 'IMAGE_JSON_INVALID'})
        result = subprocess.run(command + ['--archive', 'secret-must-not-appear'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('secret-must-not-appear', result.stdout)
        self.assertEqual(json.loads(result.stdout)['category'], 'IMAGE_ARGUMENT_INVALID')

    def test_timeout_and_parse_failure_reap_real_child(self):
        original = subprocess.Popen; children = []
        def launch(args, **kwargs):
            proc = original([sys.executable, '-c', 'import sys,time;sys.stdout.buffer.write(b"bad"*512);sys.stdout.buffer.flush();time.sleep(30)'], **kwargs)
            children.append(proc); return proc
        with patch.object(identity, 'inspect_images', return_value=self.observed()), patch.object(identity.subprocess, 'Popen', side_effect=launch):
            with self.assertRaisesRegex(ValueError, 'IMAGE_SAVE_TIMEOUT'):
                identity.installed_identities(list(NAMES.values()), PLATFORM, timeout=1)
        self.assertTrue(all(p.poll() is not None for p in children))
        def invalid(args, **kwargs):
            proc = original([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"bad"*512)'], **kwargs)
            children.append(proc); return proc
        with patch.object(identity, 'inspect_images', return_value=self.observed()), patch.object(identity.subprocess, 'Popen', side_effect=invalid):
            with self.assertRaises(ValueError): identity.installed_identities(list(NAMES.values()), PLATFORM)
        self.assertTrue(all(p.poll() is not None for p in children))

    def test_retag_during_export_fails(self):
        path = self.root / 'installed.tar'; path.write_bytes(fixture())
        original = subprocess.Popen
        def launch(args, **kwargs):
            return original([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(open(sys.argv[1],"rb").read())', str(path)], **kwargs)
        with patch.object(identity, 'inspect_images', side_effect=[self.observed('c'), self.observed('d')]), patch.object(identity.subprocess, 'Popen', side_effect=launch):
            with self.assertRaisesRegex(ValueError, 'TAG_CHANGED_DURING_CHECK'):
                identity.installed_identities(list(NAMES.values()), PLATFORM)

    def test_inspect_selective_fields_and_bounded_output(self):
        original = subprocess.Popen
        def launch(args, **kwargs):
            self.assertNotIn('{{json .}}', args)
            raw = '\n'.join(json.dumps(v) for v in self.observed().values())
            return original([sys.executable, '-c', 'import sys;print(sys.argv[1])', raw], **kwargs)
        with patch.object(identity.subprocess, 'Popen', side_effect=launch):
            self.assertEqual(identity.inspect_images(list(NAMES.values())), self.observed())
        def huge(args, **kwargs):
            return original([sys.executable, '-c', 'import sys;sys.stdout.buffer.write(b"x"*200000)'], **kwargs)
        with patch.object(identity.subprocess, 'Popen', side_effect=huge):
            with self.assertRaisesRegex(ValueError, 'INSPECT_TOO_LARGE'): identity.inspect_images(list(NAMES.values()))

    def test_inspect_nullable_user_normalizes_only_null_and_strings(self):
        original = subprocess.Popen
        for value in (None, '', '999:999', 0, False, True, [], {}):
            with self.subTest(value=value):
                observed = self.observed(); observed[NAMES['postgres']]['user'] = value
                raw = '\n'.join(json.dumps(v) for v in observed.values())
                def launch(args, **kwargs):
                    self.assertIn('index .Config "User"', args[4])
                    self.assertNotIn('{{json .Config}}', args[4])
                    return original([sys.executable, '-c', 'import sys;print(sys.argv[1])', raw], **kwargs)
                with patch.object(identity.subprocess, 'Popen', side_effect=launch):
                    if value is None or isinstance(value, str):
                        result = identity.inspect_images(list(NAMES.values()))
                        self.assertEqual(result[NAMES['postgres']]['user'], '' if value is None else value)
                    else:
                        with self.assertRaisesRegex(ValueError, 'IMAGE_INSPECT_INVALID'):
                            identity.inspect_images(list(NAMES.values()))

    def test_preflight_identity_gate_precedes_execution_for_full_and_core(self):
        values = {'RELEASE_ID': RELEASE, 'OPS_WORK_DIR': str(self.root)}
        for core in (False, True):
            with patch.object(preflight.platform, 'system', return_value='Linux'), patch.object(preflight.platform, 'machine', return_value='x86_64'), \
                 patch.object(preflight, 'environment', return_value=values), patch('ops.verify_package.verify', return_value={'release_id': RELEASE}), \
                 patch.object(preflight.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), patch.object(preflight, 'run', return_value='') as run, \
                 patch.object(identity, 'verify_installed', side_effect=ValueError('IMAGE_CONFIG_DIGEST_MISMATCH')) as gate:
                with self.assertRaisesRegex(ValueError, 'IMAGE_CONFIG_DIGEST_MISMATCH'):
                    preflight.check('synthetic.env', core_only=core)
                gate.assert_called_once_with(f'images-{RELEASE}.manifest.jsonl', RELEASE, PLATFORM, core)
                self.assertEqual(run.call_count, 1)  # compose config --quiet only; no image execution


if __name__ == '__main__': unittest.main()
