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


def migrate_schema(engine) -> None:
    """轻量迁移：为已存在的表补充 ORM 模型新增的缺失列（仅 ADD COLUMN，不删列、不改类型）。

    适用场景：模型迭代（如 ai_judgments 新增 analysis 字段）后，本地 SQLite 文件已存有
    旧数据，而 create_all 不会给已有表加列，导致 INSERT 报 "no column named xxx"。
    启动时调用，幂等：已存在的列会被跳过。

    说明：新增列一律按「可空」方式添加（不追加 NOT NULL 约束）——旧数据该列为 NULL，
    新写入由 ORM 的 default 提供值。这样可避开 SQLite 对 NOT NULL 无默认值列无法
    ALTER TABLE 的限制，且不破坏已有数据。
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # 新表交给 create_all 处理
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_cols:
                continue
            col_type = column.type.compile(engine.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
            with engine.begin() as conn:
                conn.execute(text(ddl))
            print(f"[migrate] 已添加缺失列 {table.name}.{column.name} ({col_type})")
