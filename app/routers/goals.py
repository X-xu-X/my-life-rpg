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
from app.services.time_service import stored_time
from app.services import receipts
from app.services.transactions import lock_profile
from fastapi.encoders import jsonable_encoder

router = APIRouter()


def _run_goal_action(db, action, *args):
    try:
        return action(db, *args)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


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
        "updated_at": goal.updated_at,
    }


@router.get("/goals")
def list_goals(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    goals = db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.created_at.desc()).all()
    return [_goal_out(g, item_service.goal_progress(db, user.id, g.id)) for g in goals]


@router.post("/goals")
def create_goal(body: GoalCreate, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    _run_goal_action(db, lambda session, data: goal_service.validate_goal(data), body.model_dump())
    goal = Goal(
        user_id=user.id,
        description=body.description,
        metric=body.metric,
        deadline=stored_time(body.deadline, user.timezone) if body.deadline else None,
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
    user = get_or_create_default_user(db)
    lock_profile(db, user.id)
    db.refresh(goal)
    fingerprint, prior = receipts.replay(db,user.id,f'goal-update:{goal_id}',body)
    if prior is not None: return prior
    if body.expected_version is not None and body.expected_version != goal.updated_at:
        raise HTTPException(409, '目标已更新，请重新读取。')
    data = body.model_dump(exclude_unset=True,exclude={'request_key','expected_version'})
    if data.get('deadline'):
        user = get_or_create_default_user(db)
        data['deadline'] = stored_time(data['deadline'], user.timezone)
    try:
        goal = goal_service.update_goal(db, goal, data, commit=False)
        db.flush()
        result=jsonable_encoder(_goal_out(goal))
        receipts.record(db,user.id,f'goal-update:{goal_id}',body,fingerprint,goal_id,result)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409,str(exc)) from exc
    except Exception:
        db.rollback()
        raise


def terminal(db, goal_id, action, body):
    user=get_or_create_default_user(db)
    goal=db.get(Goal,goal_id)
    if goal is None: raise HTTPException(404,'目标不存在')
    lock_profile(db,user.id);db.refresh(goal)
    operation=f'goal-{action}:{goal_id}'
    fingerprint,prior=receipts.replay(db,user.id,operation,body)
    if prior is not None:return prior
    if body.expected_version is not None and body.expected_version != goal.updated_at:
        raise HTTPException(409,'目标已更新，请重新读取。')
    try:
        value=getattr(goal_service,action+'_goal')(db,goal,commit=False)
        db.flush()
        result=jsonable_encoder(_goal_out(value) if action=='cancel' else {'goal':_goal_out(value[0]),'applied':value[1]})
        receipts.record(db,user.id,operation,body,fingerprint,goal_id,result);db.commit()
        return result
    except ValueError as exc:
        db.rollback();raise HTTPException(409,str(exc)) from exc
    except Exception:
        db.rollback();raise


@router.post("/goals/{goal_id}/achieve")
def achieve_goal(goal_id: int, db: Session = Depends(get_db), body: receipts.MutationIn = receipts.MutationIn()):
    """标记目标达成，触发奖励结算。"""
    return terminal(db,goal_id,'achieve',body)


@router.post("/goals/{goal_id}/fail")
def fail_goal(goal_id: int, db: Session = Depends(get_db), body: receipts.MutationIn = receipts.MutationIn()):
    """标记目标未达成，触发扣分结算。"""
    return terminal(db,goal_id,'fail',body)


@router.post("/goals/{goal_id}/cancel")
def cancel_goal(goal_id: int, db: Session = Depends(get_db), body: receipts.MutationIn = receipts.MutationIn()):
    """取消目标（记审计，不结算）。"""
    return terminal(db,goal_id,'cancel',body)
