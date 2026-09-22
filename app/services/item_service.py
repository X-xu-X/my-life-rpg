"""打卡项目服务（v1.7）。

职责：
- 周期统计：某打卡项目在「本期」的完成次数。本期定义——daily 取今天、
  weekly 取本周一 0 点至今、none 不计算达成率（返回 0 次，前端不展示进度）。
- 目标进度汇总：目标进度 = 关联打卡项目在本期的完成次数 / 目标次数（决策 7）。

设计要点：
- **只统计真实发生过的打卡事件**（排除纯享记录 is_pure=True，它们不走判定）。
- 事件计数用 `Event.item_id` 精确归集，不靠标题/类别模糊匹配。
- 达成率只做展示，**不自动扣分**——扣分仍由 AI 判定负责（决策 5）。
"""
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import CheckinItem, Event


def period_start(frequency_type: str, now: datetime | None = None) -> datetime | None:
    """返回「本期」起点；none 返回 None（不计算达成率）。"""
    now = now or datetime.now()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if frequency_type == "daily":
        return start_of_today
    if frequency_type == "weekly":
        # 本周一 0 点（Monday=0）
        return start_of_today - timedelta(days=start_of_today.weekday())
    return None


def count_in_period(db: Session, user_id: int, item: CheckinItem) -> int:
    """统计某项目在本期的打卡次数（none 恒为 0，不参与达成率）。"""
    start = period_start(item.frequency_type)
    if start is None:
        return 0
    return (
        db.query(func.count(Event.id))
        .filter(
            Event.user_id == user_id,
            Event.item_id == item.id,
            Event.is_pure.is_(False),
            Event.created_at >= start,
        )
        .scalar()
        or 0
    )


def period_count_map(db: Session, user_id: int, items: list[CheckinItem]) -> dict[int, int]:
    """批量统计多个项目本期次数（一次查询 + Python 分组，避免 N+1）。

    weekly 与 daily 的起点不同，故按起点分桶统计后合并。
    """
    if not items:
        return {}
    starts: dict[datetime, list[int]] = {}
    for it in items:
        st = period_start(it.frequency_type)
        if st is None:
            continue
        starts.setdefault(st, []).append(it.id)

    counts: dict[int, int] = {it.id: 0 for it in items}
    for st, ids in starts.items():
        rows = (
            db.query(Event.item_id, func.count(Event.id))
            .filter(
                Event.user_id == user_id,
                Event.item_id.in_(ids),
                Event.is_pure.is_(False),
                Event.created_at >= st,
            )
            .group_by(Event.item_id)
            .all()
        )
        for item_id, cnt in rows:
            counts[item_id] = cnt
    return counts


def item_target(item: CheckinItem) -> int | None:
    """项目本期的目标次数；无频率设定（none）返回 None。"""
    if item.frequency_type == "daily":
        return 1
    if item.frequency_type == "weekly":
        return item.frequency_target or None
    return None


def build_stats(db: Session, user_id: int, items: list[CheckinItem]) -> list[dict]:
    """各项目频率达成情况（GET /api/items/stats 与目标进度共用）。

    samples：本期内的打卡日期（升序），供前端/调试核对。
    """
    counts = period_count_map(db, user_id, items)
    out: list[dict] = []
    for it in items:
        st = period_start(it.frequency_type)
        samples: list[str] = []
        if st is not None and counts.get(it.id, 0):
            rows = (
                db.query(Event.created_at)
                .filter(
                    Event.user_id == user_id,
                    Event.item_id == it.id,
                    Event.is_pure.is_(False),
                    Event.created_at >= st,
                )
                .order_by(Event.created_at.asc())
                .all()
            )
            samples = [r[0].strftime("%Y-%m-%d") for r in rows]
        out.append(
            {
                "item_id": it.id,
                "name": it.name,
                "nature": it.nature,
                "frequency_type": it.frequency_type,
                "frequency_target": it.frequency_target,
                "this_period_count": counts.get(it.id, 0),
                "samples": samples,
            }
        )
    return out


def goal_progress(db: Session, user_id: int, goal_id: int) -> list[dict]:
    """某目标关联的打卡项目进度明细（决策 7：进度由打卡完成率自动得出）。"""
    items = (
        db.query(CheckinItem)
        .filter(CheckinItem.user_id == user_id, CheckinItem.goal_id == goal_id)
        .order_by(CheckinItem.sort_order.asc(), CheckinItem.id.asc())
        .all()
    )
    if not items:
        return []
    counts = period_count_map(db, user_id, items)
    rows: list[dict] = []
    for it in items:
        target = item_target(it)
        done = counts.get(it.id, 0)
        rows.append(
            {
                "item_id": it.id,
                "name": it.name,
                "nature": it.nature,
                "frequency_type": it.frequency_type,
                "this_period_count": done,
                "target": target,
                # rate 仅在目标次数明确且 >0 时给出；否则 None（前端不画进度条）
                "rate": round(min(done / target, 1.0), 2) if target else None,
            }
        )
    return rows


def progress_rate(progress: list[dict]) -> float | None:
    """汇总达成率 = 各项目达成率的平均；无有效项目则 None（前端不展示进度块）。

    rate 为 None 的项目（无频率设定）不参与平均，避免把"未设目标"算成 0% 拉低整体。
    """
    rates = [p["rate"] for p in progress if p.get("rate") is not None]
    if not rates:
        return None
    return round(sum(rates) / len(rates), 2)
