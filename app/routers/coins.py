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
        "ledger": coin_service.ledger_detail(db, user, rows),
    }


@router.post('/coins/check-streak')
def check_streak(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    from app.services.transactions import lock_profile
    lock_profile(db, user.id)
    granted = coin_service.check_journal_streak(db, user)
    db.commit()
    return {'granted':granted,'balance':coin_service.balance(db, user)}
