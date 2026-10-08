"""目标系统结算服务（M2）。

职责：
- 达成目标：奖励「规划力」+ 关联属性（写属性流水 + 更新属性值）
- 到期未达成：扣「规划力」
- 修改/取消/达成/失败：记审计流水（goal.audit）
"""
import math
from datetime import datetime
from app.constants import ATTRIBUTE_DIMENSIONS_SET
from app.services.transactions import rollback_on_error, lock_profile

from sqlalchemy.orm import Session

from app.models import Attribute, AttributeHistory, Goal
from app.services.judge_service import _clamp_attribute_value as clamp_attribute_value
from app.services.user_service import get_or_create_default_user


def _ensure_attribute(db: Session, user_id: int, name: str) -> Attribute:
    if name not in ATTRIBUTE_DIMENSIONS_SET:
        raise ValueError("目标关联属性必须是标准主维度。")
    attr = db.query(Attribute).filter(Attribute.user_id == user_id, Attribute.name == name,
                                      Attribute.parent_id.is_(None)).populate_existing().first()
    if attr is None:
        raise ValueError("目标关联主维度不存在。")
    return attr


def _validate_amount(raw, positive):
    if isinstance(raw, bool):
        raise ValueError("目标点数不合法。")
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("目标点数不合法。") from exc
    if not math.isfinite(value) or abs(value) > 5 or (value < 0 if positive else value > 0):
        raise ValueError("奖励须在 0~5，扣分须在 -5~0。")
    return value


def validate_goal(data):
    if data.get("related_attribute") and data["related_attribute"] not in ATTRIBUTE_DIMENSIONS_SET:
        raise ValueError("目标关联属性必须是标准主维度。")
    for key, positive in (("reward", True), ("penalty", False)):
        if key in data: _validate_amount(data[key], positive)


def _claim_goal(db, goal, target):
    lock_profile(db, goal.user_id)
    changed = db.query(Goal).filter(Goal.id == goal.id, Goal.user_id == goal.user_id,
        Goal.status == "active").update({Goal.status: target}, synchronize_session=False)
    db.refresh(goal)
    if changed == 1:
        return True
    if goal.status == target and target != "active":
        return False
    raise ValueError("目标已结束，不能再次修改或结算。")


def _apply_delta(db: Session, user_id: int, name: str, delta: float, reason: str, evidence: str) -> dict | None:
    """对某属性应用增减，写属性流水。返回应用结果（无增减则返回 None）。

    v1.8：统一走 `judge_service._clamp_attribute_value` 封顶 100 / 下限 0，
    并以**实际变动量**记账（保证「初始值 + Σ流水 = 当前值」账目自洽）。
    """
    if name not in ATTRIBUTE_DIMENSIONS_SET:
        raise ValueError("目标关联属性必须是标准主维度。")
    delta = _validate_amount(delta, positive=True) if reason.startswith("目标达成") else _validate_amount(delta, positive=False)
    if delta == 0:
        return None
    attr = _ensure_attribute(db, user_id, name)
    before = attr.current_value
    after = round(clamp_attribute_value(before + delta, attr.max_value), 2)
    actual_delta = round(after - before, 2)
    if actual_delta == 0:
        return None  # 已封顶/已触底，本次实际无变化
    attr.current_value = after
    db.add(
        AttributeHistory(
            user_id=user_id,
            attribute_id=attr.id,
            event_id=None,
            judgment_id=None,
            delta=actual_delta,
            value_after=after,
            reason=reason,
            evidence=evidence,
        )
    )
    return {"name": name, "delta": actual_delta, "value_after": after}


def _append_audit(goal: Goal, action: str, detail: str) -> None:
    """追加一条目标操作审计。"""
    audit = list(goal.audit or [])
    audit.append(
        {"action": action, "detail": detail, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    )
    goal.audit = audit


@rollback_on_error
def achieve_goal(db: Session, goal: Goal) -> tuple[Goal, list[dict]]:
    """标记目标达成，触发奖励结算（规划力 +reward，关联属性 +reward）。"""
    if not _claim_goal(db, goal, "achieved"):
        return goal, []
    user = get_or_create_default_user(db)
    applied = []
    r = _apply_delta(
        db, user.id, "规划力", goal.reward,
        "目标达成奖励", "目标设定理论：达成目标的正反馈强化自我效能与计划执行力。",
    )
    if r:
        applied.append(r)
    validate_goal({"related_attribute": goal.related_attribute, "reward": goal.reward})
    if goal.related_attribute and goal.related_attribute != "规划力":
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


@rollback_on_error
def fail_goal(db: Session, goal: Goal) -> tuple[Goal, list[dict]]:
    """标记目标未达成，触发扣分结算（规划力 +penalty）。"""
    if not _claim_goal(db, goal, "failed"):
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


@rollback_on_error
def cancel_goal(db: Session, goal: Goal) -> Goal:
    """取消目标（记审计，不结算点数）。"""
    if not _claim_goal(db, goal, "cancelled"):
        return goal
    goal.status = "cancelled"
    _append_audit(goal, "cancel", "用户取消目标")
    db.commit()
    db.refresh(goal)
    return goal


@rollback_on_error
def update_goal(db: Session, goal: Goal, data: dict) -> Goal:
    """修改目标（记审计）。"""
    _claim_goal(db, goal, "active")
    validate_goal(data)
    for k, v in data.items():
        setattr(goal, k, v)
    _append_audit(goal, "update", "用户修改目标")
    db.commit()
    db.refresh(goal)
    return goal
