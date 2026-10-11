"""发布命令显式执行迁移；绝不从 API 启动调用。"""
from alembic import context
from sqlalchemy import create_engine, pool
from app.config import settings
from app.database import Base
import app.models
import app.models.access
import app.models.analysis

target_metadata = Base.metadata
url = context.config.attributes.get("database_url") or settings.db_url
if not url:
    raise RuntimeError("迁移必须显式指定 DB_URL；禁止默认操作真实 SQLite。")
if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url, poolclass=pool.NullPool).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
