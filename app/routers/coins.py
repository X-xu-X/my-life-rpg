"""金币路由（v1.8）：余额 + 流水。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import coin_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.get("/coins")
def get_coins(limit: int = 50, db: Session = Depends(get_db)):
    """只读金币余额 + 流水（倒序）；启动资金仅在建档事务发放。"""
    user = get_or_create_default_user(db)

    profile_balance = coin_service.balance(db, user)
    rows = coin_service.ledger(db, user, limit=limit)
    return {
        "balance": profile_balance,
        "ledger": [
            {
                "id": r.id,
                "delta": r.delta,
                "balance_after": r.balance_after,
                "source": r.source,
                "reason": r.reason,
                "ref_type": r.ref_type,
                "ref_id": r.ref_id,
                "created_at": r.created_at,
            }
            for r in rows
        ],
    }
