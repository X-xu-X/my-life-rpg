"""Shared ownership/version/receipt boundaries for new workflows."""
from fastapi import HTTPException
from pydantic import ConfigDict
from app.services.receipts import MutationIn, replay, record
from app.services.transactions import lock_profile
from app.services.owned_repository import get_owned


class WriteIn(MutationIn):
    model_config = ConfigDict(extra='forbid')


def begin(db, user, operation, body, *, create=False):
    lock_profile(db, user.id)
    return replay(db, user.id, operation, body, require_version=not create)


def version(row, expected):
    if type(expected) is not int or expected != (row.version if row else 0):
        raise HTTPException(409, '版本已变化；输入已保留，请重新读取后比较。')


def finish(db, user, operation, body, fingerprint, row, output):
    db.flush()
    record(db, user.id, operation, body, fingerprint, row.id, output)
    db.commit()
    return output


def fields(row):
    from app.routers.export import _export_row
    return _export_row(row)
