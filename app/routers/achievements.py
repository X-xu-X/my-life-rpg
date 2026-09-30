"""成就路由（v1.10 M1）。

- `GET /api/achievements` —— 成就墙（全目录 + 解锁状态 + 进度）
- `POST /api/judgments/{id}/achievement` —— 处理 AI 发现型建议（追授 / 忽略）
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIJudgment
from app.services import achievement_service, coin_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


class AchievementActionIn(BaseModel):
    """处理追授建议：action ∈ grant（追授）/ dismiss（忽略）。"""

    action: str = "grant"


@router.get("/achievements")
def list_achievements(db: Session = Depends(get_db)):
    """成就墙：已解锁（彩色）+ 未解锁（灰态 + 进度）。"""
    user = get_or_create_default_user(db)
    return achievement_service.wall(db, user)


@router.post("/judgments/{judgment_id}/achievement")
def handle_achievement(judgment_id: int, body: AchievementActionIn, db: Session = Depends(get_db)):
    """处理某条判定上的 AI 里程碑建议。

    - `grant`   —— **追授**：创建 discovered 成就并发金币（幂等，同一建议只发一次）
    - `dismiss` —— **忽略**：标记为已忽略，之后不再提示（不发任何奖励）

    **必须用户点按钮才会走到这里**——判定链路本身绝不自动发放。
    """
    user = get_or_create_default_user(db)
    judgment = db.get(AIJudgment, judgment_id)
    if judgment is None or judgment.user_id != user.id:
        raise HTTPException(status_code=404, detail="判定不存在")

    suggestion = dict(judgment.achievement_suggestion or {})
    if not suggestion.get("name"):
        raise HTTPException(status_code=400, detail="该判定没有里程碑建议")
    if suggestion.get("state") != "pending":
        raise HTTPException(status_code=409, detail="该建议已处理过，请勿重复操作。")

    if body.action not in ("grant", "dismiss"):
        raise HTTPException(status_code=400, detail="action 只能是 grant 或 dismiss")

    if body.action == "dismiss":
        suggestion["state"] = "dismissed"
        judgment.achievement_suggestion = suggestion
        db.commit()
        return {"status": "dismissed", "balance": coin_service.balance(db, user)}

    row = achievement_service.grant_discovered(
        db, user, suggestion["name"], suggestion.get("reason", "")
    )
    suggestion["state"] = "granted"
    suggestion["code"] = row.code
    judgment.achievement_suggestion = suggestion
    db.commit()
    return {
        "status": "granted",
        "achievement": {
            "code": row.code,
            "name": row.name,
            "icon": row.icon,
            "coin_reward": row.coin_reward,
        },
        "balance": coin_service.balance(db, user),
    }
