import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ops import backup_state, backup_run, monitor, release_gates, preflight


class ReleaseOpsTests(unittest.TestCase):
    def bundle(self,root,index):
        name=f'gol-20261010T00000{index}Z-00000000000{index}'
        (root/(name+'.dump')).write_bytes(b'synthetic-dump')
        (root/(name+'.manifest.json')).write_text('{}')
        digest=hashlib.sha256(b'synthetic-dump').hexdigest()
        (root/(name+'.sha256')).write_text(digest+'  '+name+'.dump\n')
        return name,digest

    def test_cleanup_classification_keep_failed_latest_verified_and_path_guard(self):
        with tempfile.TemporaryDirectory(dir='backups',prefix='release_ops_') as temp:
            root=Path(temp).resolve();names=[]
            for index in range(4):
                name,digest=self.bundle(root,index);names.append(name)
                if index==3:continue  # failed upload: no state, must survive
                backup_state.remote(root,name,'a'*64)
                if index==2:continue  # uploaded but never restored: must survive
                backup_state.restored(root,name,{'status':'PASS','snapshot_id':'a'*64,'dump_sha256':digest,
                    'tables_verified':27,'migration_heads':['b004_reports']})
            plan=backup_state.cleanup(root,keep=1)
            self.assertEqual(plan['delete_bundles'],[names[0]])
            self.assertTrue((root/(names[0]+'.dump')).exists())
            backup_state.cleanup(root,apply=True,keep=1)
            self.assertFalse((root/(names[0]+'.dump')).exists())
            for name in names[1:]:self.assertTrue((root/(name+'.dump')).exists())
            with self.assertRaises(ValueError):backup_state.confined(root,'../outside','.dump')
            with self.assertRaises(ValueError):backup_state.cleanup(root,keep=0)

    def test_symlink_and_checksum_never_classified_or_deleted(self):
        with tempfile.TemporaryDirectory(dir='backups',prefix='release_ops_') as temp:
            root=Path(temp).resolve();name,digest=self.bundle(root,0)
            (root/(name+'.dump')).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'CHECKSUM'):backup_state.remote(root,name,'b'*64)
            self.assertFalse((root/(name+'.state.json')).exists())
            original=Path.is_symlink
            with patch.object(Path,'is_symlink',lambda p:p.name==name+'.dump' or original(p)):
                with self.assertRaisesRegex(ValueError,'ESCAPE'):backup_state.confined(root,name,'.dump')

    def test_backup_remote_password_disk_alert_failures_do_not_update_success(self):
        with tempfile.TemporaryDirectory(dir='backups',prefix='release_ops_') as temp:
            root=Path(temp).resolve();name,digest=self.bundle(root,0)
            state=backup_state.remote(root,name,'c'*64)
            before=(root/(name+'.state.json')).read_bytes()
            env={key:'synthetic' for key in ('PGSERVICE','PGSERVICEFILE','PGPASSFILE','DB_URL','RESTIC_REPOSITORY','RESTIC_PASSWORD_FILE')}
            env['BACKUP_DIR']=str(root)
            env['RESTIC_HOST']='qa-deployment-stable'
            # Fail different actual orchestration boundaries, after creating a local bundle when applicable.
            for stage in ('dump','backup','check','forget'):
                def command(args):
                    step='dump' if len(args)>1 and args[1]=='ops/backup_bundle.py' else args[1]
                    if step==stage:raise RuntimeError('synthetic '+stage+' failure')
                    if step=='dump':
                        base=Path(args[2]);payload=b'synthetic-new-dump'
                        Path(str(base)+'.dump').write_bytes(payload)
                        Path(str(base)+'.manifest.json').write_text('{}')
                        Path(str(base)+'.sha256').write_text(hashlib.sha256(payload).hexdigest()+'  '+base.name+'.dump\n')
                    return json.dumps({'snapshot_id':'d'*64}) if step=='backup' else ''
                with patch.dict(os.environ,env),patch.object(backup_run,'command',side_effect=command):
                    with self.assertRaises(RuntimeError):backup_run.main()
                self.assertEqual((root/(name+'.state.json')).read_bytes(),before)
                self.assertEqual(len(list(root.glob('*.state.json'))),1)
            with patch('urllib.request.urlopen',side_effect=OSError('synthetic notification failure')):
                with self.assertRaises(OSError):monitor.notify(['BACKUP_FAILED'],'https://authorized.test/hook')
            with self.assertRaises(ValueError):monitor.notify(['BACKUP_FAILED'],'http://unsafe.test')

    def test_monitor_detects_stale_backup_worker_api_disk_and_no_secret_payload(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir='backups',prefix='release_ops_') as temp:
            with patch('shutil.disk_usage',return_value=SimpleNamespace(free=1,total=100)),patch('subprocess.run',return_value=SimpleNamespace(returncode=1)):
                self.assertEqual(set(monitor.local_probe(temp,['docker'])),{'DISK_LOW','BACKUP_STALE','API_UNAVAILABLE','WORKER_STALE'})
            with patch('urllib.request.urlopen',side_effect=OSError('sensitive internal URL')):
                self.assertEqual(monitor.public_probe('https://public.test'),['PUBLIC_SERVICE_UNREACHABLE','PUBLIC_APPLICATION_UNAVAILABLE'])
            with patch('urllib.request.urlopen') as send:
                send.return_value.__enter__.return_value.status=200
                monitor.notify(['BACKUP_FAILED'],'https://authorized.test/hook')
                data=send.call_args.args[0].data.decode()
                self.assertEqual(json.loads(data)['alerts'],['BACKUP_FAILED'])
                self.assertNotIn('password',data)

    def test_compose_internal_ports_allowed_host_bindings_rejected(self):
        for publishers in (None,[],[{'URL':'','TargetPort':5432,'PublishedPort':0,'Protocol':'tcp'}],
                [{'URL':'0.0.0.0','TargetPort':5432,'PublishedPort':0,'Protocol':'tcp'}]):
            with self.subTest(publishers=publishers):
                preflight.check_database_ports([{'Service':'db','Publishers':publishers},
                    {'Service':'caddy','Publishers':[{'PublishedPort':443}]}])
        for address,port in (('0.0.0.0',5432),('::',15432),('127.0.0.1',5432)):
            with self.subTest(address=address,port=port),self.assertRaisesRegex(ValueError,'DATABASE_PORT_PUBLISHED'):
                preflight.check_database_ports([{'Service':'db','Publishers':[
                    {'TargetPort':5432,'PublishedPort':0},
                    {'URL':address,'TargetPort':5432,'PublishedPort':port,'Protocol':'tcp'}]}])
        for port in (None,'0',-1,65536,True):
            with self.subTest(port=port),self.assertRaisesRegex(ValueError,'DATABASE_PORT_DATA_INVALID'):
                preflight.check_database_ports([{'Service':'db','Publishers':[{'PublishedPort':port}]}])

    def test_stable_backup_identity_survives_container_hostname_changes_and_scopes_forget(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with tempfile.TemporaryDirectory(dir='backups',prefix='release_ops_') as temp:
            env={key:'synthetic' for key in ('PGSERVICE','PGSERVICEFILE','PGPASSFILE','DB_URL','RESTIC_REPOSITORY','RESTIC_PASSWORD_FILE')}
            env.update(BACKUP_DIR=str(Path(temp).resolve()),RESTIC_HOST='qa-deployment-stable')
            calls=[]
            def command(args):
                calls.append(args)
                return json.dumps({'snapshot_id':'e'*64}) if args[:2]==['restic','backup'] else ''
            with patch.object(backup_run,'command',side_effect=command),patch.object(backup_run,'remote'),redirect_stdout(StringIO()):
                for container in ('first-random-container','second-rebuilt-container'):
                    with patch.dict(os.environ,{**env,'HOSTNAME':container},clear=True):backup_run.main()
            for operation in ('backup','forget'):
                commands=[args for args in calls if args[:2]==['restic',operation]]
                self.assertEqual(len(commands),2)
                for args in commands:
                    self.assertEqual(args[args.index('--host')+1],'qa-deployment-stable')
                    self.assertEqual(args[args.index('--tag')+1],'game-of-life')
            forget=next(args for args in calls if args[:2]==['restic','forget'])
            self.assertEqual(forget[forget.index('--group-by')+1],'host,tags')
            self.assertEqual(forget[forget.index('--keep-daily')+1],'7')
            self.assertEqual(forget[forget.index('--keep-weekly')+1],'4')
            with patch.dict(os.environ,env,clear=True):
                del os.environ['RESTIC_HOST']
                with self.assertRaisesRegex(ValueError,'CONFIG_INCOMPLETE'):backup_run.main()
            for invalid in ('','replace-with-host','bad host','../../other'):
                with self.subTest(invalid=invalid),self.assertRaises(ValueError):backup_run.backup_host(invalid)

    def test_public_probe_requires_api_database_readiness_even_when_homepage_ok(self):
        from contextlib import contextmanager
        from io import BytesIO
        from types import SimpleNamespace
        from urllib.error import HTTPError
        for invalid in ('http://public.test','https://[invalid','https://user:password@public.test'):
            self.assertEqual(monitor.public_probe(invalid),['PUBLIC_HTTPS_CONFIG_INVALID'])
        for body,error in ((b'{"status":"ready"}',None),(b'<html>static page</html>',None),
                (b'{"status":"ok"}',None),(b' '*4097,None),(b'',502),(b'',503)):
            calls=[]
            @contextmanager
            def open_url(request,**kwargs):
                url=getattr(request,'full_url',request);calls.append(url)
                if url.endswith('/service-status'):
                    if error:raise HTTPError(url,error,'synthetic failure',{},None)
                    self.assertEqual(request.get_header('Cache-control'),'no-cache')
                    yield SimpleNamespace(status=200,read=BytesIO(body).read)
                else:yield SimpleNamespace(status=200)
            with self.subTest(body=body[:30],error=error),patch('urllib.request.urlopen',side_effect=open_url):
                self.assertEqual(monitor.public_probe('https://public.test/'),[] if body==b'{"status":"ready"}' else ['PUBLIC_APPLICATION_UNAVAILABLE'])
                self.assertEqual(calls,['https://public.test/','https://public.test/service-status'])

    def test_release_gate_fail_closed_and_private_env_placeholders(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory(dir='backups',prefix='release_ops_') as temp:
            path=Path(temp)/'gates.json'
            path.write_text(json.dumps({'release_id':'synthetic-release','verified_at':datetime.now(timezone.utc).isoformat(),
                'gates':{f'RR{i:02}':'PASS' for i in range(1,12)}}))
            with patch.dict(os.environ,{'RELEASE_ID':'synthetic-release'}):
                with self.assertRaisesRegex(ValueError,'incomplete'):release_gates.check(path)
            env=Path(temp)/'production.env';env.write_text('DOMAIN=replace-with-your-domain.example')
            with patch.object(preflight,'private',return_value=env):
                with self.assertRaises(ValueError):preflight.environment(env)


if __name__=='__main__':unittest.main()
