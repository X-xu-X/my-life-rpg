"""Optional real binaries, exclusively loopback and synthetic local repositories.

Set TEST_RESTIC_BIN and TEST_CADDY_BIN to verified tools. These tests never use
Docker, a real repository, public TLS issuance, production DBs or real receivers.
"""
import hashlib
import importlib
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from ops.backup_run import snapshot_commands


class OpsReviewIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('TEST_RESTIC_BIN'),'requires verified portable restic')
    def test_real_restic_retention_stable_host_and_other_deployment_preserved(self):
        binary=os.environ['TEST_RESTIC_BIN']
        with tempfile.TemporaryDirectory(dir='backups',prefix='ops_retention_') as temp:
            root=Path(temp).resolve()
            self.assertTrue(root.is_relative_to(Path('backups').resolve()))
            env=os.environ.copy()
            env.pop('RESTIC_PASSWORD_FILE',None)
            env.update(RESTIC_REPOSITORY=str(root/'repository'),RESTIC_PASSWORD='synthetic-test-only-password',
                RESTIC_CACHE_DIR=str(root/'cache'),RESTIC_HOST='wrong-inherited-host',GOMAXPROCS='2')
            def run(args):
                result=subprocess.run([binary,*args],env=env,capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr)
                return result.stdout
            run(['init'])
            host='qa-stable-installation'
            for day in range(35):
                env['HOSTNAME']=f'rebuilt-container-{day}'
                base=root/f'gol-20260801T000000Z-{day:012x}'
                Path(str(base)+'.dump').write_bytes(f'synthetic bundle {day}'.encode())
                Path(str(base)+'.manifest.json').write_text('{}')
                Path(str(base)+'.sha256').write_text(hashlib.sha256(Path(str(base)+'.dump').read_bytes()).hexdigest())
                backup,forget=snapshot_commands(host,base)
                stamp=(datetime(2026,8,1,12)+timedelta(days=day)).strftime('%Y-%m-%d %H:%M:%S')
                run(['backup','--time',stamp,*backup[2:]])
            backup,_=snapshot_commands('qa-other-installation',base)
            run(backup[1:])
            # Same host but another backup set must also survive.
            run(['backup','--host',host,'--tag','unrelated-set',str(base)+'.dump'])
            before=json.loads(run(['snapshots','--json']))
            main=[row for row in before if row['hostname']==host and row.get('tags')==['game-of-life']]
            others={row['id'] for row in before if row not in main}
            self.assertEqual(len(main),35)
            self.assertEqual(len(others),2)
            run(forget[1:])
            after=json.loads(run(['snapshots','--json']))
            self.assertTrue(others.issubset({row['id'] for row in after}))
            retained=[row for row in after if row['hostname']==host and row.get('tags')==['game-of-life']]
            expected={(datetime(2026,8,1)+timedelta(days=day)).date().isoformat() for day in range(28,35)}
            expected.update(('2026-08-16','2026-08-23'))
            self.assertEqual({row['time'][:10] for row in retained},expected)
            self.assertEqual(len(retained),9)
            run(['check'])
            print('REAL_RESTIC: 35 same-deployment snapshots -> 9; 2 unrelated snapshots unchanged; check PASS')

    @unittest.skipUnless(os.environ.get('TEST_CADDY_BIN'),'requires verified portable Caddy')
    def test_real_caddy_homepage_stays_ok_api_stop_and_db_failure_alert(self):
        import uvicorn
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        main=importlib.import_module('app.main')
        with tempfile.TemporaryDirectory(dir='backups',prefix='ops_probe_') as temp:
            root=Path(temp).resolve()
            self.assertTrue(root.is_relative_to(Path('backups').resolve()))
            cert_file=root/'qa-cert.pem';key_file=root/'qa-key.pem'
            key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
            subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
            now=datetime.now(timezone.utc)
            cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
                .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
                .sign(key,hashes.SHA256()))
            cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            context=ssl.create_default_context(cafile=str(cert_file))
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
            notices=[]
            class Receiver(BaseHTTPRequestHandler):
                def do_POST(self):
                    notices.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                    self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
                def log_message(self,*args):pass
            receiver=ThreadingHTTPServer(('127.0.0.1',0),Receiver)
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert_file,key_file)
            receiver.socket=tls.wrap_socket(receiver.socket,server_side=True)
            receiver_thread=threading.Thread(target=receiver.serve_forever,daemon=True);receiver_thread.start()
            db=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
            missing=(root/'missing.sqlite').as_posix()
            failed_db=create_engine('sqlite:///file:'+missing+'?mode=ro&uri=true')
            api_socket=socket.socket();api_socket.bind(('127.0.0.1',0));api_port=api_socket.getsockname()[1]
            server=uvicorn.Server(uvicorn.Config(main.app,lifespan='off',log_level='error',access_log=False))
            api_thread=threading.Thread(target=lambda:server.run(sockets=[api_socket]),daemon=True)
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1',0));https_port=port_socket.getsockname()[1]
            web=root/'web';web.mkdir();(web/'index.html').write_text('<html>synthetic static homepage</html>')
            source=Path('deploy/Caddyfile').read_text(encoding='utf-8')
            source=source.replace('    admin off','    admin off\n    auto_https disable_redirects')
            source=source.replace('{$DOMAIN} {','{$DOMAIN} {\n    bind 127.0.0.1\n    tls "'+cert_file.as_posix()+'" "'+key_file.as_posix()+'"')
            source=source.replace('api:8000',f'127.0.0.1:{api_port}').replace('root * /srv','root * "'+web.as_posix()+'"')
            config=root/'Caddyfile';config.write_text(source,encoding='utf-8')
            env=os.environ.copy();env.update(DOMAIN=f'127.0.0.1:{https_port}',ACME_EMAIL='qa@example.test',
                XDG_DATA_HOME=str(root/'caddy-data'),XDG_CONFIG_HOME=str(root/'caddy-config'),SSL_CERT_FILE=str(cert_file),
                NO_PROXY='127.0.0.1,localhost',
                ALERT_WEBHOOK_URL=f'https://127.0.0.1:{receiver.server_port}/notify')
            public=f'https://127.0.0.1:{https_port}/'
            process=None
            with patch.object(main,'engine',db), (root/'caddy.log').open('w',encoding='utf-8') as output:
                try:
                    api_thread.start()
                    for _ in range(100):
                        if server.started:break
                        time.sleep(.05)
                    self.assertTrue(server.started)
                    process=subprocess.Popen([os.environ['TEST_CADDY_BIN'],'run','--config',str(config),'--adapter','caddyfile'],
                        env=env,stdout=output,stderr=output,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    for _ in range(100):
                        if process.poll() is not None:self.fail('Caddy failed: '+(root/'caddy.log').read_text(encoding='utf-8'))
                        try:
                            with opener.open(public,timeout=.3) as response:
                                if response.status==200:break
                        except Exception:time.sleep(.05)
                    def probe(expected):
                        with opener.open(public,timeout=3) as response:self.assertEqual(response.status,200)
                        result=subprocess.run([sys.executable,'ops/monitor.py','--public-url',public],env=env,
                            capture_output=True,text=True,timeout=35)
                        self.assertEqual(result.returncode,expected,result.stderr)
                    probe(0)
                    with opener.open(public+'service-status',timeout=3) as response:
                        self.assertEqual(json.load(response),{'status':'ready'})
                        self.assertEqual(response.headers['Cache-Control'],'no-store')
                    from urllib.error import HTTPError
                    for internal in ('api/ready','api/health','docs','openapi.json','redoc'):
                        with self.assertRaises(HTTPError) as blocked:
                            opener.open(public+internal,timeout=3)
                        self.assertEqual(blocked.exception.code,404)
                    with patch.object(main,'engine',failed_db):probe(2)
                    self.assertFalse((root/'missing.sqlite').exists())
                    probe(0)
                    server.should_exit=True;api_thread.join(5);self.assertFalse(api_thread.is_alive());api_socket.close()
                    probe(2)
                    self.assertEqual(notices,[{'service':'game-of-life','alerts':['PUBLIC_APPLICATION_UNAVAILABLE']}]*2)
                    print('REAL_CADDY_HTTPS: healthy PASS; DB unreachable and API stopped each keep homepage200 but monitor exits2 and synthetic HTTPS alert arrives')
                finally:
                    server.should_exit=True
                    if api_thread.is_alive():api_thread.join(5)
                    api_socket.close()
                    if process is not None and process.poll() is None:
                        process.terminate()
                        try:process.wait(5)
                        except subprocess.TimeoutExpired:process.kill();process.wait(5)
                    receiver.shutdown();receiver.server_close();receiver_thread.join(3)
                    db.dispose();failed_db.dispose()


if __name__=='__main__':unittest.main()
