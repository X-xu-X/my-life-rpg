"""数据库连接与会话管理（SQLAlchemy 2.0）。

- 默认 SQLite（本地自用），表结构已预留 MySQL/PostgreSQL 迁移。
- SQLite 需要 check_same_thread=False 以支持 FastAPI 多线程。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# 连接参数：SQLite 需关闭同线程检查
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    # 开启 echo 便于本地调试；生产可关闭
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def get_db():
    """FastAPI 依赖：提供数据库会话，请求结束后自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
