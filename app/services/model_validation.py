"""Versioned, non-secret test summaries. Provider requests never hold DB locks."""
from app.models import Setting
from app.config import settings
from app.services.credentials import PROVIDERS


def snapshot(db, user_id, group):
    if settings.cloud:
        from app.models.access import LLMCredential
        row = db.query(LLMCredential).filter_by(user_id=user_id, group=group).populate_existing().first()
        return {'config_version': row.config_version if row else 0,
                'provider': row.provider_id if row else '', 'model': row.model if row else ''}
    row = db.query(Setting).filter_by(user_id=user_id, key='llm_' + group).populate_existing().first()
    value = row.value if row and isinstance(row.value, dict) else {}
    provider = next((key for key, url in PROVIDERS.items() if url == value.get('base_url', '').rstrip('/')), 'custom-local')
    return {'config_version': value.get('config_version', 0), 'provider': provider, 'model': value.get('model', '')}


def summary(db, user_id, group, version):
    row = db.query(Setting).filter_by(user_id=user_id, key='llm_validation_' + group).first()
    value = dict(row.value) if row and isinstance(row.value, dict) else {}
    if not value: return {'status': 'untested'}
    if value.get('config_version') != version: value['status'] = 'stale'
    return value


MESSAGES = {
    'MODEL_AUTH_FAILED': ('认证失败，请检查本供应商的 Key。', False),
    'MODEL_NOT_FOUND': ('模型不存在或无访问权限，请核对模型 ID。', False),
    'MODEL_BALANCE_INSUFFICIENT': ('余额或调用配额不足，请在官方控制台核对。', False),
    'MODEL_RATE_LIMITED': ('请求受到限流，请稍后主动重试。', True),
    'MODEL_TIMEOUT': ('请求超时，请稍后主动重试。', True),
    'MODEL_INVALID_RESPONSE': ('请求格式或返回内容不兼容，请核对聊天模型与端点。', False),
    'MODEL_BUSY': ('已有模型请求进行中，请稍后重试。', True),
    'MODEL_DAILY_LIMIT': ('今日调用预算已用完，仍可保存原文。', False),
    'MODEL_UNAVAILABLE': ('请求失败，供应商未提供可确定的原因。', True),
    'MODEL_SERVICE_ERROR': ('供应商服务异常，请稍后主动重试。', True),
}


def controlled_error(exc):
    code = str(exc).split('：', 1)[0]
    if code not in MESSAGES: code = 'MODEL_UNAVAILABLE'
    message, retryable = MESSAGES[code]
    return code, message, retryable


def provenance(config):
    return {'provider': next((name for name, url in PROVIDERS.items() if url == config.base_url), 'custom-local'),
            'model': config.model, 'config_version': config.config_version,
            'source': 'personal' if config.config_id or config.config_version else 'local-legacy'}
