"""目标系统结算服务（M2）。

职责：
- 达成目标：奖励「规划力」+ 关联属性（写属性流水 + 更新属性值）
- 到期未达成：扣「规划力」
- 修改/取消/达成/失败：记审计流水（goal.audit）
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Attribute, AttributeHistory, Goal
from app.services.user_service import get_or_create_default_user


def _ensure_attribute(db: Session, user_id: int, name: str) -> Attribute:
    """确保属性记录存在；不存在则以中性值 50 创建。"""
    attr = db.query(Attribute).filter(Attribute.user_id == user_id, Attribute.name == name).first()
    if attr is None:
        attr = Attribute(user_id=user_id, name=name, current_value=50.0)
        db.add(attr)
        db.flush()
    return attr


def _apply_delta(db: Session, user_id: int, name: str, delta: float, reason: str, evidence: str) -> dict | None:
    """对某属性应用增减，写属性流水。返回应用结果（无增减则返回 None）。"""
    if delta == 0 or not name:
        return None
    attr = _ensure_attribute(db, user_id, name)
    attr.current_value = round(attr.current_value + delta, 2)
    db.add(
        AttributeHistory(
            user_id=user_id,
            attribute_id=attr.id,
            event_id=None,
            judgment_id=None,
            delta=delta,
            value_after=attr.current_value,
            reason=reason,
            evidence=evidence,
        )
    )
    return {"name": name, "delta": delta, "value_after": attr.current_value}


def _append_audit(goal: Goal, action: str, detail: str) -> None:
    """追加一条目标操作审计。"""
    audit = list(goal.audit or [])
    audit.append(
        {"action": action, "detail": detail, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    )
    goal.audit = audit


def achieve_goal(db: Session, goal: Goal) -> tuple[Goal, list[dict]]:
    """标记目标达成，触发奖励结算（规划力 +reward，关联属性 +reward）。"""
    if goal.status == "achieved":
        return goal, []
    user = get_or_create_default_user(db)
    applied = []
    r = _apply_delta(
        db, user.id, "规划力", goal.reward,
        "目标达成奖励", "目标设定理论：达成目标的正反馈强化自我效能与计划执行力。",
    )
    if r:
        applied.append(r)
    if goal.related_attribute:
        r2 = _apply_delta(
            db, user.id, goal.related_attribute, goal.reward,
            "目标达成关联属性奖励", "目标达成对关联能力的正向反馈。",
        )
        if r2:
            applied.append(r2)
    goal.status = "achieved"
    _append_audit(goal, "achieve", "目标达成，奖励已入账")
    db.commit()
    db.refresh(goal)
    return goal, applied


def fail_goal(db: Session, goal: Goal) -> tuple[Goal, list[dict]]:
    """标记目标未达成，触发扣分结算（规划力 +penalty）。"""
    if goal.status == "failed":
        return goal, []
    user = get_or_create_default_user(db)
    applied = []
    r = _apply_delta(
        db, user.id, "规划力", goal.penalty,
        "目标未达成扣分", "自我调节学习理论：未兑现计划反映规划执行力不足。",
    )
    if r:
        applied.append(r)
    goal.status = "failed"
    _append_audit(goal, "fail", "目标到期未达成，规划力扣分")
    db.commit()
    db.refresh(goal)
    return goal, applied


def cancel_goal(db: Session, goal: Goal) -> Goal:
    """取消目标（记审计，不结算点数）。"""
    if goal.status == "cancelled":
        return goal
    goal.status = "cancelled"
    _append_audit(goal, "cancel", "用户取消目标")
    db.commit()
    db.refresh(goal)
    return goal


def update_goal(db: Session, goal: Goal, data: dict) -> Goal:
    """修改目标（记审计）。"""
    for k, v in data.items():
        setattr(goal, k, v)
    _append_audit(goal, "update", "用户修改目标")
    db.commit()
    db.refresh(goal)
    return goal
