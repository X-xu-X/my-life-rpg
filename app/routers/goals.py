"""目标路由：目标 CRUD + 结算（达成奖励 / 未达成扣分 / 修改取消记审计）。

v1.7 决策 7：目标进度 = 关联打卡项目本期的完成率（**查询时计算**，goals 表不加列）。
进度只做展示，**不自动达成**——达成仍由用户手动点「达成」（避免系统替用户拍板）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Goal
from app.schemas import GoalCreate, GoalOut, GoalUpdate
from app.services import goal_service, item_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


def _goal_out(goal: Goal, progress: list[dict] | None = None) -> dict:
    """序列化目标（含审计流水 + v1.7 关联打卡项目进度）。"""
    progress = progress or []
    return {
        "id": goal.id,
        "description": goal.description,
        "metric": goal.metric,
        "deadline": goal.deadline,
        "related_attribute": goal.related_attribute,
        "status": goal.status,
        "reward": goal.reward,
        "penalty": goal.penalty,
        "audit": goal.audit or [],
        # v1.7：进度明细（无关联项目则为空数组，前端不展示进度块）
        "progress": progress,
        "progress_rate": item_service.progress_rate(progress),
        "created_at": goal.created_at,
    }


@router.get("/goals")
def list_goals(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    goals = db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.created_at.desc()).all()
    return [_goal_out(g, item_service.goal_progress(db, user.id, g.id)) for g in goals]


@router.post("/goals")
def create_goal(body: GoalCreate, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    goal = Goal(
        user_id=user.id,
        description=body.description,
        metric=body.metric,
        deadline=body.deadline,
        related_attribute=body.related_attribute,
        reward=body.reward,
        penalty=body.penalty,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _goal_out(goal)


@router.get("/goals/{goal_id}")
def get_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    return _goal_out(goal)


@router.put("/goals/{goal_id}")
def update_goal(goal_id: int, body: GoalUpdate, db: Session = Depends(get_db)):
    """修改目标（记审计）。"""
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    data = body.model_dump(exclude_unset=True)
    goal = goal_service.update_goal(db, goal, data)
    return _goal_out(goal)


@router.post("/goals/{goal_id}/achieve")
def achieve_goal(goal_id: int, db: Session = Depends(get_db)):
    """标记目标达成，触发奖励结算。"""
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    goal, applied = goal_service.achieve_goal(db, goal)
    return {"goal": _goal_out(goal), "applied": applied}


@router.post("/goals/{goal_id}/fail")
def fail_goal(goal_id: int, db: Session = Depends(get_db)):
    """标记目标未达成，触发扣分结算。"""
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    goal, applied = goal_service.fail_goal(db, goal)
    return {"goal": _goal_out(goal), "applied": applied}


@router.post("/goals/{goal_id}/cancel")
def cancel_goal(goal_id: int, db: Session = Depends(get_db)):
    """取消目标（记审计，不结算）。"""
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    goal = goal_service.cancel_goal(db, goal)
    return _goal_out(goal)
