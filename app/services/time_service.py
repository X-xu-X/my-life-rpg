"""云端 UTC 持久化、用户本地日边界；本地历史时间不自动改写。"""
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from app.config import settings
from contextvars import ContextVar

STORAGE_ZONE = ZoneInfo("Asia/Shanghai")
USER_ZONE = ContextVar("user_timezone", default="Asia/Shanghai")


def clock_now():
    value = datetime.now(zone(USER_ZONE.get()))
    return value if settings.cloud else value.replace(tzinfo=None)


def utc_now():
    return datetime.now(dt_timezone.utc)


def zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise HTTPException(422, "时区无效。") from exc


def stored_time(value=None, timezone="Asia/Shanghai"):
    source_zone = zone(timezone)
    value = value or datetime.now(source_zone)
    if value.tzinfo is None:
        value = value.replace(tzinfo=source_zone)
    return value.astimezone(dt_timezone.utc) if settings.cloud else value.astimezone(STORAGE_ZONE).replace(tzinfo=None)


def date_range(local_date, timezone):
    start = datetime.combine(local_date, datetime.min.time(), zone(timezone))
    return stored_time(start), stored_time(start + timedelta(days=1))


def local_day(value, timezone):
    if value.tzinfo is None:
        value = value.replace(tzinfo=STORAGE_ZONE)
    return value.astimezone(zone(timezone)).date()


def capture_saved_day(event, timezone, db=None):
    """Only new records: preserve first-save local date independently from content time."""
    if db is not None:
        from app.services import trial_rules
        from app.models import User
        timezone=trial_rules.zone_for(db,db.get(User,event.user_id))
    event.saved_timezone=timezone
    event.saved_on=local_day(event.created_at,timezone).isoformat()
