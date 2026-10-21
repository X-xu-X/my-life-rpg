"""Single supplier call. No database connection, retry, fallback, or credential logging."""
import json
import sys


def main():
    payload = json.load(sys.stdin)
    if sys.platform.startswith('linux'):
        import ctypes
        import os
        import signal
        # The runner also has its own deadline and dies if the worker is killed.
        parent=os.getppid()
        if ctypes.CDLL(None).prctl(1, signal.SIGKILL)!=0: return {'error':'MODEL_UNAVAILABLE'}
        if os.getppid()!=parent: return {'error':'MODEL_UNAVAILABLE'}
        signal.setitimer(signal.ITIMER_REAL, float(payload['timeout']))
    from openai import OpenAI
    from app.services.credentials import http_client,validate_endpoint
    try:validate_endpoint(payload['base_url'])
    except Exception:return {'error':'MODEL_ENDPOINT_BLOCKED'}
    client = None
    try:
        client = OpenAI(api_key=payload['api_key'], base_url=payload['base_url'],
            max_retries=0, timeout=payload['timeout'], http_client=http_client(payload['base_url']))
        response = client.chat.completions.create(**payload['request'])
        from app.services.model_diagnostics import response_summary
        summary=response_summary(response)
        content=response.choices[0].message.content if response.choices else ''
        return {'content':content if isinstance(content,str) else '', 'diagnostic':summary,'usage':summary['usage'] or None}
    except Exception as exc:
        status = getattr(exc, 'status_code', 0)
        from app.services.model_errors import category
        return {'error':category(exc), 'status':status}
    finally:
        if client: client.close()


if __name__ == '__main__':
    try: result = main()
    except Exception: result = {'error':'MODEL_UNAVAILABLE'}
    sys.stdout.write(json.dumps(result))
