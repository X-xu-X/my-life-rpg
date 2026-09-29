"""金币路由（v1.8）：余额 + 流水。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import coin_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.get("/coins")
def get_coins(limit: int = 50, db: Session = Depends(get_db)):
    """金币余额 + 流水（倒序）。

    惰性发放启动资金（幂等）与检查连续写日记里程碑——即使用户从未打开过挑战页，
    只要查询过余额，账目也会补齐。
    """
    user = get_or_create_default_user(db)
    coin_service.grant_startup_bonus_if_needed(db, user)
    coin_service.check_journal_streak(db, user)
    db.commit()

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
