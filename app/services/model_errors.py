"""Allowlisted supplier categories only. Never expose provider messages/bodies."""
def category(exc):
    safe = getattr(exc, 'safe_code', None)
    if safe in {'MODEL_AUTH_FAILED','MODEL_NOT_FOUND','MODEL_BALANCE_INSUFFICIENT','MODEL_RATE_LIMITED',
                'MODEL_TIMEOUT','MODEL_INVALID_RESPONSE','MODEL_SERVICE_ERROR','MODEL_UNAVAILABLE'}: return safe
    status = getattr(exc, 'status_code', 0) or 0
    body = getattr(exc, 'body', None)
    error = body.get('error', body) if isinstance(body, dict) else {}
    code = error.get('code') if isinstance(error, dict) else None
    if code in ('insufficient_quota', 'insufficient_balance', 'billing_hard_limit_reached'): return 'MODEL_BALANCE_INSUFFICIENT'
    if type(exc).__name__ in ('APITimeoutError','ReadTimeout','ConnectTimeout') or status in (408,504): return 'MODEL_TIMEOUT'
    if isinstance(status, int) and status >= 500: return 'MODEL_SERVICE_ERROR'
    return {400:'MODEL_INVALID_RESPONSE',401:'MODEL_AUTH_FAILED',402:'MODEL_BALANCE_INSUFFICIENT',
            403:'MODEL_NOT_FOUND',404:'MODEL_NOT_FOUND',429:'MODEL_RATE_LIMITED'}.get(status,'MODEL_UNAVAILABLE')
