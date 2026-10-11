"""用户服务：V1 单用户，提供默认用户的获取/创建。

V1 定位"个人自用"，所有 API 默认操作 default 用户；表结构已预留多用户（M4）。
"""
from sqlalchemy.orm import Session

from app.constants import ATTRIBUTE_DIMENSIONS
from app.models import Attribute, User, UserProfile

DEFAULT_USERNAME = "default"


def get_or_create_default_user(db: Session) -> User:
    """获取默认用户；不存在则创建（含画像空记录）。幂等。"""
    current_id = db.info.get("user_id")
    if current_id is not None:
        user = db.get(User, current_id)
        if user is None:
            from fastapi import HTTPException
            raise HTTPException(401, "请登录。")
        return user
    from app.config import settings
    if settings.cloud:
        from fastapi import HTTPException
        raise HTTPException(401, "请登录。")
    user = db.query(User).filter(User.username == DEFAULT_USERNAME).first()
    if user is None:
        user = User(username=DEFAULT_USERNAME)
        db.add(user)
        db.flush()  # 拿到 user.id
        db.add(UserProfile(user_id=user.id))
        db.commit()
        db.refresh(user)
    return user


def ensure_dimensions(db: Session, user: User) -> int:
    """确保用户拥有全部标准维度的属性记录（缺失的以中性值 50 创建）。

    用于维度扩展后（如从 6 项扩展到 12 项），给已建档用户补全新维度。
    返回本次补建的数量。
    """
    existing = {a.name for a in db.query(Attribute).filter(Attribute.user_id == user.id).all()}
    created = 0
    for name in ATTRIBUTE_DIMENSIONS:
        if name not in existing:
            db.add(Attribute(user_id=user.id, name=name, current_value=50.0))
            created += 1
    if created:
        db.commit()
    return created
