"""豁免券路由（v1.10 M2）：购买 / 列表。

设计要点（用户红线）：**绝不能做成万能券**——日期与时段必填，缺一即 400。
定价与动机判断由 AI 完成（`exemption_service.buy`），购买时扣币；
判为「明显逃避」时的额外属性扣点也**在购买时立刻生效**（用户 2026-09-30 拍板）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ExemptionIn
from app.services import coin_service, exemption_service
from app.services.llm_service import LLMError
from app.services.user_service import get_or_create_default_user
from app.services import receipts
from app.services.transactions import lock_profile
from fastapi.encoders import jsonable_encoder
from uuid import UUID
from app.models.access import RequestReceipt

router = APIRouter()


@router.get("/exemptions")
def list_exemptions(db: Session = Depends(get_db)):
    """券列表（含预设时段，供前端渲染购买表单）。顺带做惰性过期。"""
    user = get_or_create_default_user(db)
    rows = exemption_service.list_for_user(db, user)
    return {
        "items": [exemption_service.serialize(r) for r in rows],
        "balance": coin_service.balance(db, user),
        "presets": [
            {"key": k, "label": v["label"], "start": v["start"], "end": v["end"]}
            for k, v in exemption_service.PERIOD_PRESETS.items()
        ],
    }


@router.get('/exemption-submissions/{request_key}')
def submission(request_key: UUID, db: Session = Depends(get_db)):
    user=get_or_create_default_user(db)
    row=db.query(RequestReceipt).filter_by(user_id=user.id,operation='exemption-buy',request_key=str(request_key)).first()
    if row is None:raise HTTPException(404,'购买回执尚不存在；可沿用原操作标识恢复。')
    return row.response_snapshot


@router.post("/exemptions")
def buy_exemption(body: ExemptionIn, db: Session = Depends(get_db)):
    """购买一张豁免券（AI 定价 + 判动机 → 扣币 → 落库）。

    - 非法/缺失日期或时段 → 400（**万能券不可能**）
    - 余额不足 → 400
    - AI 不可用 → 503
    """
    user = get_or_create_default_user(db)
    try:
        lock_profile(db,user.id)
        fingerprint,prior=receipts.replay(db,user.id,'exemption-buy',body,require_version=False)
        if prior is not None:return prior
        db.commit()
        result = exemption_service.buy(
            db,
            user,
            target_date=body.target_date,
            period=body.period,
            start_time=body.start_time,
            end_time=body.end_time,
            reason=body.reason,
            commit=False,
            before_write=lambda:receipts.replay(db,user.id,'exemption-buy',body,require_version=False)[1],
        )
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    if 'replayed' in result:return result['replayed']
    row = result["exemption"]
    response = jsonable_encoder({
        "exemption": exemption_service.serialize(row),
        "penalty": result["penalty"],
        "balance": result["balance"],
    })
    receipts.record(db,user.id,'exemption-buy',body,fingerprint,row.id,response)
    db.commit()
    return response
