"""云端 aware UTC；本地旧 SQLite 继续按原始时间解释，不启动改写历史。"""
from datetime import timezone
from sqlalchemy import DateTime as SADateTime, TypeDecorator
from app.config import settings


class DateTime(TypeDecorator):
    impl = SADateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and settings.cloud:
            if value.tzinfo is None:
                raise ValueError("云端时间必须带时区。")
            value = value.astimezone(timezone.utc)
            if dialect.name == "sqlite":
                value = value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and settings.cloud:
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value
