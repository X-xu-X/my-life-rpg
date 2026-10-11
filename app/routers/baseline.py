"""由用户显式选择中性游戏基线，不能覆盖已经生效的旧账。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import UserProfile, Attribute
from app.constants import ATTRIBUTE_DIMENSIONS
from app.services.user_service import get_or_create_default_user
from app.services import onboarding_service, coin_service
from app.services.transactions import lock_profile

router = APIRouter()


class NeutralIn(BaseModel):
    acknowledge: bool


@router.post("/onboarding/neutral")
def neutral(body: NeutralIn, db: Session = Depends(get_db)):
    if not body.acknowledge:
        raise HTTPException(422, "请确认这是未评估的游戏起点。")
    user = get_or_create_default_user(db)
    lock_profile(db, user.id)
    profile = db.query(UserProfile).filter_by(user_id=user.id).populate_existing().one()
    if profile.onboarding_completed:
        if profile.baseline_kind == "neutral_opt_in":
            return {"completed": True, "baseline_kind": profile.baseline_kind, "balance": coin_service.balance(db, user)}
        db.rollback()
        raise HTTPException(409, "已有角色基线，不能重新建档。")
    try:
        onboarding_service._assert_unbuilt_profile(db, profile)
        panel = []
        for name in ATTRIBUTE_DIMENSIONS:
            attr = db.query(Attribute).filter_by(user_id=user.id, name=name).first()
            if attr is None:
                attr = Attribute(user_id=user.id, name=name)
                db.add(attr)
            attr.current_value = 50
            attr.description = "未评估的游戏起点，不是能力测量。"
            panel.append({"name": name, "value": 50, "reason": attr.description})
        profile.onboarding_completed = True
        profile.baseline_kind = "neutral_opt_in"
        profile.onboarding_state = {}
        profile.initial_attributes_snapshot = {"attributes": panel, "initial_coins": 80,
            "baseline_kind": "neutral_opt_in", "summary": "未评估的游戏起点。"}
        db.flush()
        coin_service.grant_startup_bonus_if_needed(db, user, amount=80)
        db.commit()
    except ValueError as exc:
        db.rollback(); raise HTTPException(409, str(exc)) from exc
    return {"completed": True, "baseline_kind": "neutral_opt_in", "balance": coin_service.balance(db, user)}
