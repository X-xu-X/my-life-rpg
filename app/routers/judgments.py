"""判定路由：确认 / 补充 / 反驳 + 审计日志查询。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIJudgment, Event, JudgmentLog
from app.schemas import AchievementActionIn, DisputeIn, SupplementIn
from app.services import achievement_service, coin_service, judge_service
from app.services.llm_service import LLMError
from app.services.user_service import get_or_create_default_user

router = APIRouter()


def _get_judgment(db: Session, judgment_id: int) -> AIJudgment:
    judgment = db.get(AIJudgment, judgment_id)
    if judgment is None:
        raise HTTPException(status_code=404, detail="判定记录不存在")
    return judgment


@router.get("/judgments")
def list_judgments(db: Session = Depends(get_db)):
    """判定列表（关联事件摘要），供判定中心展示。

    v1.5 A1/A3：只返回现行判定（排除 invalidated 归档），各展示端统一以本接口为唯一数据源。
    """
    user = get_or_create_default_user(db)
    rows = (
        db.query(AIJudgment, Event)
        .join(Event, AIJudgment.event_id == Event.id)
        .filter(AIJudgment.user_id == user.id, AIJudgment.status.notin_(["invalidated", "deleted"]), Event.is_deleted.is_(False))
        .order_by(AIJudgment.created_at.desc())
        .all()
    )
    # v1.5 A2/A3：从审计日志统计——最近一次用户补充/反驳内容 + 重判次数（一条查询取全量，Python 内分组）
    last_input: dict[int, dict] = {}
    rejudge_counts: dict[int, int] = {}
    judgment_ids = [j.id for j, _ in rows]
    if judgment_ids:
        logs = (
            db.query(JudgmentLog)
            .filter(
                JudgmentLog.judgment_id.in_(judgment_ids),
                JudgmentLog.action.in_(["supplement", "dispute", "rejudge"]),
            )
            .order_by(JudgmentLog.created_at.desc())
            .all()
        )
        for log in logs:
            lid = log.judgment_id
            if lid in last_input:
                if log.action == "rejudge":
                    rejudge_counts[lid] = rejudge_counts.get(lid, 0) + 1
                continue
            if log.action in ("supplement", "dispute"):
                last_input[lid] = {
                    "action": log.action,
                    "detail": log.detail,
                    "created_at": log.created_at,
                }
            elif log.action == "rejudge" and isinstance(log.payload, dict) and log.payload.get("clarification"):
                # v1.5 A4：追问流程的用户回答存于 rejudge 日志 payload，同样视为「我的补充」
                last_input[lid] = {
                    "action": "supplement",
                    "detail": str(log.payload["clarification"]),
                    "created_at": log.created_at,
                }
            if log.action == "rejudge":
                rejudge_counts[lid] = rejudge_counts.get(lid, 0) + 1
    return [
        {
            "id": j.id,
            "event_id": j.event_id,
            "event_title": e.title or e.content[:40],
            "event_type": e.event_type,
            "category": e.category,
            "origin": e.origin,  # v1.9 F5：事件来源（"challenge" → 前端显示「挑战」徽章）
            "status": j.status,
            "suggested_changes": j.suggested_changes,
            "analysis": j.analysis,
            "final_changes": j.final_changes,
            "summary": j.summary,
            "confidence": j.confidence,
            "confidence_reason": j.confidence_reason or "",  # v1.4：置信度说明
            "revision_notes": j.revision_notes or [],  # v1.6：本次修订说明
            "merged_with": j.merged_with or [],  # v1.7：跨来源合并明细
            # v1.10 M1：AI 发现型成就建议（{name, reason, state}；无建议为 {}）
            "achievement_suggestion": j.achievement_suggestion or {},
            "last_user_input": last_input.get(j.id),  # v1.5 A2：最近一次补充/反驳
            "rejudge_count": rejudge_counts.get(j.id, 0),  # v1.5 A3：重判次数
            "created_at": j.created_at,
        }
        for j, e in rows
    ]


@router.get("/judgments/{judgment_id}")
def get_judgment(judgment_id: int, db: Session = Depends(get_db)):
    """判定详情。"""
    j = _get_judgment(db, judgment_id)
    return {
        "id": j.id,
        "event_id": j.event_id,
        "status": j.status,
        "suggested_changes": j.suggested_changes,
        "analysis": j.analysis,
        "final_changes": j.final_changes,
        "summary": j.summary,
        "confidence": j.confidence,
        "confidence_reason": j.confidence_reason or "",  # v1.4：置信度说明
        "revision_notes": j.revision_notes or [],  # v1.6：本次修订说明
        "merged_with": j.merged_with or [],  # v1.7：跨来源合并明细
        "achievement_suggestion": j.achievement_suggestion or {},  # v1.10 M1
        "created_at": j.created_at,
        "updated_at": j.updated_at,
    }


@router.get("/judgments/{judgment_id}/logs")
def get_logs(judgment_id: int, db: Session = Depends(get_db)):
    """判定审计日志（确认/补充/反驳/复核全过程）。"""
    _get_judgment(db, judgment_id)
    logs = (
        db.query(JudgmentLog)
        .filter(JudgmentLog.judgment_id == judgment_id)
        .order_by(JudgmentLog.created_at.asc())
        .all()
    )
    return [
        {
            "id": l.id,
            "action": l.action,
            "detail": l.detail,
            "payload": l.payload,
            "created_at": l.created_at,
        }
        for l in logs
    ]


@router.post("/judgments/{judgment_id}/confirm")
def confirm(judgment_id: int, db: Session = Depends(get_db)):
    """确认入账：写属性流水 + 更新属性值。低置信度会被拦截。

    v1.8：入账成功后按净 delta 发放日常金币（净 delta ≤ 0 不给币也不扣币）。
    """
    judgment = _get_judgment(db, judgment_id)
    if judgment.status == "confirmed":
        raise HTTPException(status_code=409, detail="该判定已确认入账，请勿重复操作。")
    user = get_or_create_default_user(db)
    event = db.get(Event, judgment.event_id)
    if event is None or event.is_deleted:
        raise HTTPException(404, "事件不存在")
    if event.origin == "challenge":
        raise HTTPException(409, "挑战判定请在挑战页结算。")
    try:
        judgment = judge_service.confirm(db, judgment, commit=False)
        coins_gained = coin_service.reward_event_confirm(db, user, judgment, event_title=event.title or "")
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    # v1.10 M1：累计型成就顺带检查（幂等；内部自行 commit，失败不影响入账主流程）
    unlocked: list[dict] = []
    try:
        for row in achievement_service.check_and_grant(db, user):
            unlocked.append({"code": row.code, "name": row.name, "icon": row.icon,
                             "coin_reward": row.coin_reward})
    except Exception:
        db.rollback()

    return {
        "status": judgment.status,
        "final_changes": judgment.final_changes,
        "coins_gained": coin_service.EVENT_CONFIRM_REWARD if coins_gained is not None else 0,
        "balance": coin_service.balance(db, user),
        "unlocked_achievements": unlocked,  # v1.10：本次新解锁的成就
        "achievement_suggestion": judgment.achievement_suggestion or {},  # v1.10：AI 里程碑建议
    }


@router.post("/judgments/{judgment_id}/achievement")
def handle_achievement(
    judgment_id: int, body: AchievementActionIn, db: Session = Depends(get_db)
):
    """v1.10 M1：处理 AI 里程碑建议（追授 / 忽略）。

    **必须由用户点按钮触发**——判定链路本身不会自动发放任何 AI 发现型成就。
    - `grant`：`grant_discovered()` 落库 + 发一次金币（同 code 幂等，不会重复发）
    - `dismiss`：仅把建议标记为 dismissed，不发放
    """
    action = (body.action or "").strip().lower()
    if action not in ("grant", "dismiss"):
        raise HTTPException(status_code=400, detail="action 只能是 grant 或 dismiss")

    judgment = _get_judgment(db, judgment_id)
    suggestion = judgment.achievement_suggestion or {}
    name = str(suggestion.get("name", "")).strip() if isinstance(suggestion, dict) else ""
    if not name:
        raise HTTPException(status_code=400, detail="该判定没有待处理的里程碑建议")

    # 已处理过 → 幂等返回，不重复发币
    if isinstance(suggestion, dict) and suggestion.get("state") in ("granted", "dismissed"):
        return {
            "action": suggestion.get("state"),
            "achievement": None,
            "balance": coin_service.balance(db, get_or_create_default_user(db)),
        }

    user = get_or_create_default_user(db)
    achievement = None
    if action == "grant":
        reason = str(suggestion.get("reason", "")).strip()
        row = achievement_service.grant_discovered(db, user, name, reason)
        achievement = {
            "code": row.code,
            "name": row.name,
            "icon": row.icon,
            "coin_reward": row.coin_reward,
        }
        new_state = "granted"
    else:
        new_state = "dismissed"

    # 标记状态——前端据此收起追授卡（不物理删除建议内容，保留审计）
    marked = dict(suggestion)
    marked["state"] = new_state
    judgment.achievement_suggestion = marked
    # SQLAlchemy JSON 列原地改不可靠，显式赋值 + 强制脏标记
    db.add(judgment)
    db.commit()

    return {
        "action": new_state,
        "achievement": achievement,
        "balance": coin_service.balance(db, user),
    }


@router.post("/judgments/{judgment_id}/supplement")
def supplement(judgment_id: int, body: SupplementIn, db: Session = Depends(get_db)):
    """补充信息，AI 重新判定。"""
    judgment = _get_judgment(db, judgment_id)
    try:
        judgment = judge_service.supplement(db, judgment, body.detail)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {
        "status": judgment.status,
        "suggested_changes": judgment.suggested_changes,
        "summary": judgment.summary,
        "confidence": judgment.confidence,
        "confidence_reason": judgment.confidence_reason or "",  # v1.4：置信度说明
        "revision_notes": judgment.revision_notes or [],  # v1.6：本次修订说明
        "merged_with": judgment.merged_with or [],  # v1.7：跨来源合并明细
        "achievement_suggestion": judgment.achievement_suggestion or {},  # v1.10 M1
    }


@router.post("/judgments/{judgment_id}/dispute")
def dispute(judgment_id: int, body: DisputeIn, db: Session = Depends(get_db)):
    """反驳复核：仅依据事实与科学标准，无据反驳坚持原判。"""
    judgment = _get_judgment(db, judgment_id)
    try:
        result = judge_service.dispute(db, judgment, body.detail)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {
        "conclusion": result["conclusion"],
        "explanation": result["explanation"],
        "status": result["judgment"].status,
        "suggested_changes": result["judgment"].suggested_changes,
        "revision_notes": result["judgment"].revision_notes or [],  # v1.6：本次修订说明
        "merged_with": result["judgment"].merged_with or [],  # v1.7：跨来源合并明细
        "achievement_suggestion": result["judgment"].achievement_suggestion or {},  # v1.10 M1
    }
