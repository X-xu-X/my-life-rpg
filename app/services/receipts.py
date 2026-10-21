"""写操作回执与输入指纹；须与业务更改在同一事务提交。"""
import hashlib
import json
from datetime import datetime
from uuid import UUID
from fastapi import HTTPException
from pydantic import BaseModel
from app.config import settings
from app.models.access import RequestReceipt


class MutationIn(BaseModel):
    request_key: UUID | None = None
    expected_version: int | datetime | None = None


def replay(db, user_id, operation, body, *, require_version=True):
    if settings.cloud and (body.request_key is None or (require_version and body.expected_version is None)):
        raise HTTPException(422, "操作需要 request_key 和 expected_version。")
    payload=body.model_dump(mode='json')
    if 'reward_preview_id' not in body.model_fields_set:payload.pop('reward_preview_id',None)
    # Preserve the exact pre-upgrade fingerprint of an already accepted request.
    evolved={'DiaryIn':('ai_permission','correction_reason'),'ScheduleIn':('goal_id','planned_minutes','category'),'ResultIn':('ai_permission',),'StartIn':('source_version','source_type'),'QuoteIn':('auto_check',),'SaveIn':('uses',),'ItemIn':('start','interval','category','planned_minutes','goal_id'),'EntryIn':('correction','reason')}
    for name in evolved.get(type(body).__name__,()):
        if name not in body.model_fields_set:payload.pop(name,None)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if body.request_key:
        row = db.query(RequestReceipt).filter_by(user_id=user_id, operation=operation,
            request_key=str(body.request_key)).first()
        if row:
            if row.payload_hash != fingerprint:
                raise HTTPException(409, "同一操作标识对应的输入发生变化。")
            return fingerprint, row.response_snapshot
    return fingerprint, None


def record(db, user_id, operation, body, fingerprint, resource_id, response):
    if body.request_key:
        db.add(RequestReceipt(user_id=user_id, operation=operation, request_key=str(body.request_key),
            payload_hash=fingerprint, resource_id=resource_id, response_snapshot=response))
