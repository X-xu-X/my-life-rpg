"""Disposable browser review; synthetic data only, no provider requests."""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
OUT = Path(__file__).resolve().parent
PORT = 19384
for name in ('TEST_PG_URL', 'TEST_CADDY_BIN', 'TEST_RESTIC_BIN'):
    os.environ.pop(name, None)
os.environ.update(DB_URL='sqlite://', RUN_MODE='local', DEEPSEEK_API_KEY='')

from test_next_iteration import CloudTests
from app.config import settings
from app.main import app
from app.services.llm_service import llm_service
from app import models as m
from app.models.analysis import AnalysisJob
from app.services.time_service import utc_now
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import ipaddress
import uvicorn

fixture = CloudTests()
fixture.setUp()
try:
    uid = fixture.register('browser_reviewer')['id']
    response = fixture.client.post('/api/onboarding/neutral', json={'acknowledge': True})
    assert response.status_code == 200
    response = fixture.client.put('/api/llm-config', json={'group': 'primary',
        'provider_id': 'deepseek', 'model': 'synthetic-review-model',
        'api_key': 'synthetic-review-key-only', 'enabled': True})
    assert response.status_code == 200
    fixture.save('浏览器审查样本：今天整理了二十分钟书桌，完成归类。', intent='never')
    pending = fixture.save('浏览器审查样本：阅读一章教材，等待补充。').json()
    with fixture.Session() as db:
        db.add(AnalysisJob(user_id=uid, event_id=pending['id'], event_version=1,
            request_key='synthetic-browser-job', payload_hash='0'*64, operation='judge', state='needs_input',
            result={'questions': ['这一章中你学到了什么？']}))
        db.commit()
    def deny_provider(*args, **kwargs):
        raise RuntimeError('Browser fixture forbids provider calls')
    llm_service.chat = deny_provider
    llm_service.chat_json = deny_provider
    settings.public_origin = f'https://127.0.0.1:{PORT}'
    app.mount('/assets', StaticFiles(directory=OUT / 'frontend-dist/assets'), name='review-assets')
    @app.get('/{path:path}')
    def static_review(path: str):
        return FileResponse(OUT / 'frontend-dist/index.html')
    with tempfile.TemporaryDirectory(dir=OUT, prefix='browser_tls_') as tmp:
        assert Path(tmp).resolve().is_relative_to(OUT.resolve())
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'isolated-browser-review')])
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=5))
            .not_valid_after(datetime.now(timezone.utc)+timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
            .sign(key, hashes.SHA256()))
        key_path = Path(tmp) / 'synthetic-key.pem'
        cert_path = Path(tmp) / 'synthetic-cert.pem'
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        print(f'ISOLATED_BROWSER_READY port={PORT}', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=PORT, lifespan='off',
            ssl_keyfile=str(key_path), ssl_certfile=str(cert_path),
            log_level='error', access_log=False)
finally:
    fixture.tearDown()
