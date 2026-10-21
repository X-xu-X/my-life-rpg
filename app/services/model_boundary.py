"""Killable wall-clock boundary. Secrets travel only through the private stdin pipe."""
import json
import subprocess
import sys
import time
from types import SimpleNamespace
from app.config import settings


class ModelBoundaryError(RuntimeError):
    def __init__(self, code, status=0):
        super().__init__(code)
        self.safe_code, self.status_code = code, status


def run_deadline(command, payload, seconds):
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        output, _ = process.communicate(json.dumps(payload).encode(),
            timeout=max(0.001, seconds - (time.monotonic() - started)))
        if process.returncode or len(output) > 2_000_000:
            raise ModelBoundaryError('MODEL_UNAVAILABLE')
        try: result = json.loads(output)
        except (ValueError, TypeError): raise ModelBoundaryError('MODEL_INVALID_RESPONSE') from None
        if result.get('error'):
            raise ModelBoundaryError(result['error'], result.get('status', 0))
        return result
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()  # Reap before releasing the global supplier lock.
        raise ModelBoundaryError('MODEL_TIMEOUT') from None
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


class IsolatedClient:
    def __init__(self, config):
        self.config = config
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        result = run_deadline([sys.executable, '-m', 'app.services.model_runner'],
            {'api_key':self.config.api_key, 'base_url':self.config.base_url,
             'timeout':settings.ai_timeout, 'request':kwargs}, settings.ai_timeout)
        diagnostic=result.get('diagnostic',{})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=result['content']),finish_reason=diagnostic.get('finish_reason'))],
            usage=SimpleNamespace(**result['usage']) if result.get('usage') else None,safe_diagnostic=diagnostic)

    def close(self):
        pass
