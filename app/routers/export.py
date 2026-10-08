"""数据导出路由（个人数据主权，PRD 4.7）。

GET /api/export?format=json → 完整数据 JSON
GET /api/export?format=csv  → 事件列表 CSV
"""
import csv
import io
from datetime import datetime, date
from app import models

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIJudgment, Anchor, Attribute, AttributeHistory, Event, Goal
from app.services.user_service import get_or_create_default_user

router = APIRouter()


def _dt(v):
    """datetime 转字符串（JSON 可序列化）。"""
    return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v


def _event(e: Event) -> dict:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "category": e.category,
        "source": e.source,
        "title": e.title,
        "params": e.params,
        "content": e.content,
        "occurred_at": _dt(e.occurred_at),
        "created_at": _dt(e.created_at),
    }


def _collect_legacy(db: Session, user_id: int) -> dict:
    """收集用户全部数据。"""
    events = db.query(Event).filter(Event.user_id == user_id).order_by(Event.created_at).all()
    attrs = db.query(Attribute).filter(Attribute.user_id == user_id).all()
    history = db.query(AttributeHistory).filter(AttributeHistory.user_id == user_id).order_by(AttributeHistory.created_at).all()
    goals = db.query(Goal).filter(Goal.user_id == user_id).all()
    judgments = db.query(AIJudgment).filter(AIJudgment.user_id == user_id).order_by(AIJudgment.created_at).all()
    anchors = db.query(Anchor).all()

    return {
        "exported_at": _dt(datetime.now()),
        "events": [_event(e) for e in events],
        "attributes": [
            {"name": a.name, "value": a.current_value, "description": a.description} for a in attrs
        ],
        "attribute_history": [
            {
                "attribute_id": h.attribute_id,
                "delta": h.delta,
                "value_after": h.value_after,
                "reason": h.reason,
                "evidence": h.evidence,
                "created_at": _dt(h.created_at),
            }
            for h in history
        ],
        "goals": [
            {
                "id": g.id,
                "description": g.description,
                "metric": g.metric,
                "deadline": _dt(g.deadline),
                "related_attribute": g.related_attribute,
                "status": g.status,
                "audit": g.audit,
                "created_at": _dt(g.created_at),
            }
            for g in goals
        ],
        "judgments": [
            {
                "id": j.id,
                "event_id": j.event_id,
                "status": j.status,
                "suggested_changes": j.suggested_changes,
                "analysis": j.analysis,
                "final_changes": j.final_changes,
                "summary": j.summary,
                "confidence": j.confidence,
                "created_at": _dt(j.created_at),
            }
            for j in judgments
        ],
        "anchors": [
            {
                "name": a.name,
                "base_value": a.base_value,
                "unit": a.unit,
                "base_delta": a.base_delta,
                "calibrated_value": a.calibrated_value,
                "evidence": a.evidence,
            }
            for a in anchors
        ],
    }


SAFE_EXPORT_SETTINGS = frozenset({"gamification_modules", "hidden_attributes", "disabled_attributes", "stagnation_checks", "unreal_count"})


def _encode_export(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _encode_export(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode_export(v) for v in value]
    return value


def _export_row(row):
    return {column.name: _encode_export(getattr(row, column.name)) for column in row.__table__.columns}


def _collect(db: Session, user_id: int) -> dict:
    data = _collect_legacy(db, user_id)
    table_models = (models.UserProfile, models.Attribute, models.AttributeHistory,
        models.CheckinItem, models.Event, models.AIJudgment, models.JudgmentLog, models.Goal,
        models.CoinLedger, models.Challenge, models.ShopItem, models.Redemption,
        models.Achievement, models.Exemption)
    tables = {model.__tablename__: [_export_row(row) for row in db.query(model).filter(
        model.user_id == user_id).order_by(model.id).all()] for model in table_models}
    tables["users"] = [_export_row(row) for row in db.query(models.User).filter(models.User.id == user_id).all()]
    tables["anchors"] = [_export_row(row) for row in db.query(models.Anchor).order_by(models.Anchor.id).all()]
    tables["settings"] = [_export_row(row) for row in db.query(models.Setting).filter(
        models.Setting.user_id == user_id, models.Setting.key.in_(SAFE_EXPORT_SETTINGS)).order_by(models.Setting.id).all()]
    return {**data, "format_version": 2, "tables": tables}


@router.get("/export")
def export_data(db: Session = Depends(get_db), format: str = "json"):
    """导出用户数据。format=json 返回完整数据；format=csv 返回事件 CSV。"""
    user = get_or_create_default_user(db)
    data = _collect(db, user.id)

    if format == "csv":
        # 仅导出事件列表为 CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "event_type", "category", "source", "title", "params", "content", "occurred_at", "created_at"])
        for e in data["events"]:
            writer.writerow([
                e["id"], e["event_type"], e["category"], e["source"], e["title"],
                e["params"], e["content"], e["occurred_at"], e["created_at"],
            ])
        csv_text = "\ufeff" + output.getvalue()  # BOM，避免 Excel 中文乱码
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=game_of_life_events.csv"},
        )

    return data


# ============ 备份 ============

@router.post("/backup")
def create_backup():
    """手动触发数据库备份。"""
    from app.services.backup_service import backup_now

    dest = backup_now()
    return {"status": "ok", "backup_file": dest.name if dest else None}


@router.get("/backup/list")
def list_backups():
    """列出已有备份。"""
    from app.services.backup_service import list_backups

    return list_backups()
