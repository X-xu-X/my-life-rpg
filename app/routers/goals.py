"""目标路由：目标 CRUD + 状态操作。

说明：目标达成/未达成的属性点结算逻辑在 M2 完善（TODO）。
M1 提供 CRUD 与状态标记（达成/取消），结算扣分遵循锚点默认值（规划力 +2/-1）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Goal
from app.schemas import GoalCreate, GoalOut, GoalUpdate
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.get("/goals", response_model=list[GoalOut])
def list_goals(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    return db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.created_at.desc()).all()


@router.post("/goals", response_model=GoalOut)
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
    return goal


@router.get("/goals/{goal_id}", response_model=GoalOut)
def get_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    return goal


@router.put("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: GoalUpdate, db: Session = Depends(get_db)):
    """修改目标（记审计，M2 完善审计流水）。"""
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(goal, k, v)
    db.commit()
    db.refresh(goal)
    return goal


@router.post("/goals/{goal_id}/achieve", response_model=GoalOut)
def achieve_goal(goal_id: int, db: Session = Depends(get_db)):
    """标记目标达成。TODO(M2)：触发奖励结算（规划力 +2 及关联属性）。"""
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    goal.status = "achieved"
    db.commit()
    db.refresh(goal)
    return goal


@router.post("/goals/{goal_id}/fail", response_model=GoalOut)
def fail_goal(goal_id: int, db: Session = Depends(get_db)):
    """标记目标未达成。TODO(M2)：触发扣分结算（规划力 -1）。"""
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    goal.status = "failed"
    db.commit()
    db.refresh(goal)
    return goal


@router.post("/goals/{goal_id}/cancel", response_model=GoalOut)
def cancel_goal(goal_id: int, db: Session = Depends(get_db)):
    """取消目标（记审计，M2 完善审计流水）。"""
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="目标不存在")
    goal.status = "cancelled"
    db.commit()
    db.refresh(goal)
    return goal
