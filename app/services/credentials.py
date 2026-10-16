"""个人 BYOK 认证加密和固定供应商出口；不保存明文到普通设置表。"""
import ipaddress
import re
import json
import secrets
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from app.config import settings
from app.models.access import LLMCredential

PROVIDERS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
}


def keyring():
    try:
        data = json.loads(Path(settings.credential_key_file).read_text(encoding="utf-8"))
        keys = {key: Fernet(value.encode()) for key, value in data["keys"].items()}
        if data["active"] not in keys:
            raise ValueError()
        return data["active"], keys
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("凭据密钥文件不可用；不允许降级为明文存储。") from exc


def decrypt(row):
    if not row.encrypted_key:
        return ""
    _, keys = keyring()
    try:
        return keys[row.key_id].decrypt(row.encrypted_key.encode()).decode()
    except (KeyError, InvalidToken) as exc:
        raise RuntimeError("凭据解密失败，请检查密钥版本。") from exc


def group_out(row):
    from app.services.llm_config import mask_key
    return {"provider_id": row.provider_id if row else "deepseek",
        "model": row.model if row else "", "enabled": bool(row and row.enabled),
        "base_url": PROVIDERS.get(row.provider_id, "") if row else PROVIDERS["deepseek"],
        "api_key_masked": mask_key(decrypt(row)) if row else "",
        "api_key": mask_key(decrypt(row)) if row else "",
        "configured": bool(row and row.encrypted_key),
        "config_version": row.config_version if row else 0}


def read_config(db, user_id):
    from app.services.model_validation import summary
    rows = {r.group: r for r in db.query(LLMCredential).filter_by(user_id=user_id).all()}
    return {g: {**group_out(rows.get(g)), 'source': 'personal',
                'validation': summary(db, user_id, g, rows[g].config_version if g in rows else 0)} for g in ("primary", "aux")} | {
        "providers": PROVIDERS, "env_fallback": {"ready": False, "model": "", "base_url": ""}}


def save_config(db, user_id, body):
    from app.services.transactions import lock_profile
    lock_profile(db, user_id)
    row = db.query(LLMCredential).filter_by(user_id=user_id, group=body.group).first()
    provider = body.provider_id or (row.provider_id if row else "deepseek")
    if provider not in PROVIDERS or (body.base_url and body.base_url.rstrip("/") != PROVIDERS[provider]):
        raise HTTPException(422, "请选择批准的供应商端点。")
    changed_provider = bool(row and row.provider_id != provider)
    fresh_key = body.api_key not in (None, "__KEEP__") and bool(body.api_key.strip())
    clearing = body.api_key not in (None, "__KEEP__") and not body.api_key.strip()
    enabled = body.enabled if body.enabled is not None else bool(row and row.enabled)
    if clearing: enabled = False
    # A ciphertext has one provider identity. Never carry it across an endpoint change.
    if changed_provider and enabled and not fresh_key:
        raise HTTPException(422, "更换供应商并启用时，必须重新填写该供应商的 API Key。")
    if body.model is not None and (not re.fullmatch(r'[^\s\x00-\x1f\x7f]{1,100}', body.model)):
        raise HTTPException(422, "请填写模型名称。")
    encrypted = None
    active = None
    if fresh_key:
        active, keys = keyring()
        encrypted = keys[active].encrypt(body.api_key.strip().encode()).decode()
    if not row:
        row = LLMCredential(user_id=user_id, group=body.group, provider_id=provider, model="", config_version=0)
        db.add(row)
    row.provider_id = provider
    if body.model is not None:
        row.model = body.model.strip()
    if fresh_key:
        row.key_id = active
        row.encrypted_key = encrypted
    elif changed_provider or body.api_key == "" or (body.api_key not in (None, "__KEEP__") and not body.api_key.strip()):
        row.encrypted_key = ""
        row.key_id = ""
    if enabled and not row.encrypted_key:
        db.rollback()
        raise HTTPException(422, "启用前请绑定该供应商的 API Key。")
    row.enabled = enabled
    row.config_version = (row.config_version or 0) + 1
    db.commit()
    return {"ok": True, "group": body.group, "model_changed": True,
            "message": "配置已保存，历史结果保留；连通测试需主动发起。"}


def public_addresses(host):
    addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("MODEL_ENDPOINT_BLOCKED")
    return addresses


class PinnedTransport(httpx.HTTPTransport):
    """每次连接前验证 DNS，并连接验证后的 IP，TLS 仍验证原始供应商主机。"""
    def handle_request(self, request):
        allowed = {urlsplit(value).hostname for value in PROVIDERS.values()}
        host = request.url.host
        if request.url.scheme != "https" or host not in allowed or request.url.port not in (None, 443):
            raise ValueError("MODEL_ENDPOINT_BLOCKED")
        address = public_addresses(host)[0]
        request.headers["Host"] = host
        request.extensions["sni_hostname"] = host
        request.url = request.url.copy_with(host=address)
        return super().handle_request(request)


def http_client():
    return httpx.Client(transport=PinnedTransport(retries=0), trust_env=False,
        follow_redirects=False, timeout=httpx.Timeout(settings.ai_timeout, connect=5.0))
