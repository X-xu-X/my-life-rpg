"""挑战路由（v1.8）：生成 / 列表 / 接受 / 完成 / 结算 / 放弃。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIJudgment, Challenge
from app.schemas import ChallengeGenerateIn, ChallengeResolveIn, ChallengeVariantIn
from app.services import challenge_service, coin_service
from app.services.llm_service import LLMError
from app.services.user_service import get_or_create_default_user

router = APIRouter()


def _judgment_map(db: Session, rows: list[Challenge]) -> dict[int, AIJudgment]:
    """批量取判定（避免逐条 N+1），供前端在刷新后仍能看到加减点明细。"""
    ids = [c.judgment_id for c in rows if c.judgment_id]
    if not ids:
        return {}
    return {j.id: j for j in db.query(AIJudgment).filter(AIJudgment.id.in_(ids)).all()}


def _out(ch: Challenge, jmap: dict[int, AIJudgment] | None = None) -> dict:
    j = (jmap or {}).get(ch.judgment_id) if ch.judgment_id else None
    return {
        "id": ch.id,
        "scope": ch.scope,
        "period_key": ch.period_key,
        "title": ch.title,
        "description": ch.description,
        "difficulty": ch.difficulty,
        "coin_reward": ch.coin_reward,
        "deposit": ch.deposit,
        "ai_reason": ch.ai_reason,
        "status": ch.status,
        "accepted_at": ch.accepted_at,
        "expires_at": ch.expires_at,
        "resolved_at": ch.resolved_at,
        "outcome": ch.outcome,
        "outcome_note": ch.outcome_note,
        # related_attributes 仅用于结算后展示（决策 10：加点不预览）
        "related_attributes": ch.related_attributes or [],
        # v1.9 F3：多档位（空 = 单档）；前端据此渲染候选期的档位按钮组
        "variants": ch.variants or [],
        "event_id": ch.event_id,
        "judgment_id": ch.judgment_id,
        # 判定明细：刷新后仍可展示（suggested=建议加点；final=实际入账）
        "judgment_status": j.status if j else "",
        "judgment_confidence": j.confidence if j else None,
        "judgment_changes": (j.suggested_changes or []) if j else [],
        "judgment_final_changes": (j.final_changes or []) if j else [],
        "created_at": ch.created_at,
    }


def _out_many(db: Session, rows: list[Challenge]) -> list[dict]:
    jmap = _judgment_map(db, rows)
    return [_out(c, jmap) for c in rows]


def _get(db: Session, user, challenge_id: int) -> Challenge:
    ch = db.get(Challenge, challenge_id)
    if ch is None or ch.user_id != user.id:
        raise HTTPException(status_code=404, detail="挑战不存在")
    return ch


@router.get("/challenges")
def list_challenges(scope: str | None = None, db: Session = Depends(get_db)):
    """当前全部挑战（返回前先做惰性过期处理）。"""
    user = get_or_create_default_user(db)
    rows = challenge_service.list_challenges(db, user, scope=scope)
    return {"challenges": _out_many(db, rows)}


@router.get("/challenges/current")
def current_challenges(db: Session = Depends(get_db)):
    """本期（日 / 周）挑战，供前端分组展示。"""
    user = get_or_create_default_user(db)
    grouped = challenge_service.current_period(db, user)
    return {
        "daily": _out_many(db, grouped["daily"]),
        "weekly": _out_many(db, grouped["weekly"]),
        "period_key": {
            "daily": challenge_service.period_key("daily"),
            "weekly": challenge_service.period_key("weekly"),
        },
    }


@router.post("/challenges/generate")
def generate_challenges(body: ChallengeGenerateIn, db: Session = Depends(get_db)):
    """生成挑战候选（幂等；force=True 为「再来一批」，仅补空缺）。"""
    user = get_or_create_default_user(db)
    try:
        rows = challenge_service.generate(db, user, scope=body.scope, force=body.force)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"challenges": _out_many(db, rows)}


@router.post("/challenges/{challenge_id}/accept")
def accept_challenge(challenge_id: int, db: Session = Depends(get_db)):
    """接受挑战（扣除押金）。余额不足返回 400。"""
    user = get_or_create_default_user(db)
    ch = _get(db, user, challenge_id)
    try:
        ch = challenge_service.accept(db, user, ch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"challenge": _out(ch), "balance": coin_service.balance(db, user)}


@router.put("/challenges/{challenge_id}/variant")
def switch_variant(challenge_id: int, body: ChallengeVariantIn, db: Session = Depends(get_db)):
    """候选期切换难度档位（v1.9 F3）。

    - 挑战不存在 / 不属于当前用户 → 404
    - 已接受或已结算 → 400「挑战已接受，档位已锁定」
    - `variant_index` 越界 → 400
    切换后 description / difficulty 写回顶层，coin_reward / deposit 按新难度重算。
    """
    user = get_or_create_default_user(db)
    ch = _get(db, user, challenge_id)
    try:
        ch = challenge_service.switch_variant(db, user, ch, body.variant_index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"challenge": _out(ch)}


@router.post("/challenges/{challenge_id}/complete")
def complete_challenge(challenge_id: int, body: ChallengeResolveIn, db: Session = Depends(get_db)):
    """提交一句话自述 → AI 判定是否达成（生成待确认判定，尚未入账）。"""
    user = get_or_create_default_user(db)
    ch = _get(db, user, challenge_id)
    try:
        result = challenge_service.complete(db, user, ch, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return result


@router.post("/challenges/{challenge_id}/settle")
def settle_challenge(challenge_id: int, db: Session = Depends(get_db)):
    """确认结算：加点入账 + 押金/奖励发放。"""
    user = get_or_create_default_user(db)
    ch = _get(db, user, challenge_id)
    try:
        result = challenge_service.settle(db, user, ch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.post("/challenges/{challenge_id}/abandon")
def abandon_challenge(challenge_id: int, body: ChallengeResolveIn | None = None, db: Session = Depends(get_db)):
    """放弃挑战。带说明 → 交 AI 判定（可能 excused 退押金）；不带 → 直接按未完成处理。"""
    user = get_or_create_default_user(db)
    ch = _get(db, user, challenge_id)
    note = (body.note if body else "") or ""
    try:
        result = challenge_service.abandon(db, user, ch, note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return result
