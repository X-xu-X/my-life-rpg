"""成长周报/月报路由：基于一段时间的数据，AI 生成成长总结与建议。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import prompts
from app.database import get_db
from app.models import AIJudgment, Attribute, AttributeHistory, Event, Goal
from app.services.llm_service import LLMError, llm_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.get("/report")
def generate_report(db: Session = Depends(get_db), period: str = "week"):
    """生成成长报告。period=week（近 7 天）或 month（近 30 天）。"""
    if period not in ("week", "month"):
        raise HTTPException(status_code=400, detail="period 只支持 week/month")
    user = get_or_create_default_user(db)
    days = 7 if period == "week" else 30
    now = datetime.now()
    start = now - timedelta(days=days)

    # 事件统计
    events = (
        db.query(Event)
        .filter(Event.user_id == user.id, Event.created_at >= start)
        .all()
    )
    by_cat: dict[str, int] = {}
    pure_count = 0
    for e in events:
        if e.is_pure:
            pure_count += 1
        by_cat[e.category] = by_cat.get(e.category, 0) + 1

    # 属性变化汇总（join 属性名）
    rows = (
        db.query(AttributeHistory, Attribute.name)
        .join(Attribute, AttributeHistory.attribute_id == Attribute.id)
        .filter(AttributeHistory.user_id == user.id, AttributeHistory.created_at >= start)
        .all()
    )
    attr_changes: dict[str, float] = {}
    for h, name in rows:
        attr_changes[name] = round(attr_changes.get(name, 0) + h.delta, 2)

    # 确认入账判定数
    confirmed_count = (
        db.query(AIJudgment)
        .filter(
            AIJudgment.user_id == user.id,
            AIJudgment.created_at >= start,
            AIJudgment.status == "confirmed",
        )
        .count()
    )

    # 目标情况
    goals = db.query(Goal).filter(Goal.user_id == user.id).all()
    goals_stat: dict[str, int] = {"active": 0, "achieved": 0, "failed": 0, "cancelled": 0}
    for g in goals:
        goals_stat[g.status] = goals_stat.get(g.status, 0) + 1

    stats = {
        "events_count": len(events),
        "events_by_category": by_cat,
        "attribute_changes": attr_changes,
        "confirmed_count": confirmed_count,
        "pure_count": pure_count,
        "goals": goals_stat,
    }

    messages = prompts.build_report_messages(
        period=period,
        start=start.strftime("%Y-%m-%d"),
        end=now.strftime("%Y-%m-%d"),
        stats=stats,
    )
    try:
        report = llm_service.chat_json(messages)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=f"报告生成失败：{exc}")

    return {
        "period": period,
        "start": start.strftime("%Y-%m-%d"),
        "end": now.strftime("%Y-%m-%d"),
        "stats": stats,
        "report": report,
    }
