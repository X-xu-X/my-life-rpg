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
    'MODEL_NOT_CONFIGURED':('请先保存并启用本人模型配置。',False),
    'MODEL_ENDPOINT_BLOCKED':('端点不符合公网HTTPS要求，请核对高级配置。',False),
    'MODEL_REQUEST_INCOMPATIBLE':('供应商不接受本次请求参数或端点，请核对聊天API支持情况。',False),
    'MODEL_OUTPUT_TRUNCATED':('输出已截断。请核对模型输出预算和思考模式；本次未自动重试。',False),
    'MODEL_EMPTY_RESPONSE':('供应商返回空正文；可能有其他输出，请查看诊断并核对模型模式。',False),
    'MODEL_JSON_INVALID':('聊天已返回，但不是有效业务JSON；请核对模型的结构化输出能力。',False),
    'MODEL_NETWORK_ERROR':('网络连接失败，请检查端点与网络后主动重试。',True),
    'MODEL_DISABLED':('你已关闭 AI，原文仍可保存。',False),
    'MODEL_INPUT_LIMIT':('内容超过站点模型输入上限，请缩短相关内容。',False),
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
    return {'provider': next((name for name, url in PROVIDERS.items() if url == config.base_url), 'custom' if settings.cloud else 'custom-local'),
            'model': config.model, 'config_version': config.config_version,
            'source': 'hosted' if getattr(config,'scope','personal')=='hosted' else 'personal' if config.config_id or config.config_version else 'local-legacy'}
