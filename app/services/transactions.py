"""事务失败必须回滚；提交边界仍由业务入口明确控制。"""
from functools import wraps
from app.models import UserProfile


def rollback_on_error(fn):
    @wraps(fn)
    def wrapped(db, *args, **kwargs):
        try:
            return fn(db, *args, **kwargs)
        except Exception:
            db.rollback()
            raise
    return wrapped


def lock_profile(db, user_id):
    db.query(UserProfile).filter(UserProfile.user_id == user_id).update(
        {UserProfile.id: UserProfile.id}, synchronize_session=False)

    from app.config import settings
    if settings.cloud and not db.info.get('manage_profile_locks'):
        from app.models import User
        from fastapi import HTTPException
        user=db.query(User).filter_by(id=user_id).populate_existing().first()
        if not user or user.status!='active':raise HTTPException(401,'账号已停用，请重新登录。')
