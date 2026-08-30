"""用户服务：V1 单用户，提供默认用户的获取/创建。

V1 定位"个人自用"，所有 API 默认操作 default 用户；表结构已预留多用户（M4）。
"""
from sqlalchemy.orm import Session

from app.models import User, UserProfile

DEFAULT_USERNAME = "default"


def get_or_create_default_user(db: Session) -> User:
    """获取默认用户；不存在则创建（含画像空记录）。幂等。"""
    user = db.query(User).filter(User.username == DEFAULT_USERNAME).first()
    if user is None:
        user = User(username=DEFAULT_USERNAME)
        db.add(user)
        db.flush()  # 拿到 user.id
        db.add(UserProfile(user_id=user.id))
        db.commit()
        db.refresh(user)
    return user
