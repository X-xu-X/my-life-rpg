"""Durable no-repeat boundary for synchronous paid model operations.

Call only after configuration/input validation and before contacting a supplier.
Business completion and its response receipt still commit together in finish().
"""
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.models.daily_use import ModelDispatch


def mark(db,user,operation,body,fingerprint):
    if not body.request_key:
        # Local legacy requests did not carry UUIDs. Cloud validation is in begin.
        db.commit();return
    previous=db.query(ModelDispatch).filter_by(user_id=user.id,operation=operation,request_key=str(body.request_key)).first()
    if previous:
        if previous.payload_hash!=fingerprint:raise HTTPException(409,'同一分析标识的内容发生变化。')
        raise HTTPException(409,'本次分析已发送，不会重复调用模型。请先查看已保存建议；没有结果时可主动发起新的分析。')
    db.add(ModelDispatch(user_id=user.id,operation=operation,request_key=str(body.request_key),payload_hash=fingerprint))
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'本次分析已发送，请查看当前状态，不会重复调用模型。') from None
