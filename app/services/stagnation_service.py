"""停滞觉察与问询服务（v1.8 B5，替代"时间衰减"）。

**设计来源**：用户提出"一个月没记录学习，可能真的就是没学，那智力下降也算吧"。
但**"没记录"与"没做"是两件事**——自动衰减会冤枉"学了但忘记记录"的情况。
故改为**问询制**：发现停滞 → AI 主动问 → **用户确认才扣分**。

与"不因沉默扣分"的关系（务必理解）：
- 属性值**不会**因为时间流逝自动变化（A2 已保证）
- 扣分**只发生在用户亲口确认"确实停了"之后**——此时"用户的确认"就是触发扣分的那个"事件"

问询历史存在 `settings` 表（key=`stagnation_checks`），**不写 judgment_logs**
——该表 `judgment_id` 是 NOT NULL，而停滞扣分没有对应判定，硬写会破坏外键语义。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Attribute, AttributeHistory, Setting, User, UserProfile
from app.services import judge_service

STAGNATION_DAYS = 30            # 距上次相关记录超过此天数 → 视为停滞
STAGNATION_COOLDOWN_DAYS = 90   # 同一维度两次问询的最小间隔
SETTING_KEY = "stagnation_checks"

# 用户确认"确实停了"后的小幅扣分（决策 17c：单次小幅，不夸张）
STAGNATION_PENALTY = -0.3


def _get_checks(db: Session, user_id: int) -> dict:
    """读取问询历史 {维度名: ISO 时间字符串}。"""
    row = db.query(Setting).filter(Setting.user_id == user_id, Setting.key == SETTING_KEY).first()
    if row is None or not isinstance(row.value, dict):
        return {}
    return dict(row.value)


def _set_checks(db: Session, user_id: int, data: dict) -> None:
    row = db.query(Setting).filter(Setting.user_id == user_id, Setting.key == SETTING_KEY).first()
    if row is None:
        db.add(Setting(user_id=user_id, key=SETTING_KEY, value=data))
    else:
        row.value = data
    db.commit()


def _disabled_attributes(db: Session, user_id: int) -> set[str]:
    """用户已关闭判定的维度（不参与停滞问询）。"""
    row = db.query(Setting).filter(
        Setting.user_id == user_id, Setting.key == "disabled_attributes"
    ).first()
    if row and isinstance(row.value, list):
        return set(row.value)
    return set()


def _last_activity(db: Session, user_id: int, attribute_id: int) -> datetime | None:
    """该维度最后一条属性流水的创建时间；无流水返回 None。"""
    row = (
        db.query(AttributeHistory.created_at)
        .filter(AttributeHistory.user_id == user_id, AttributeHistory.attribute_id == attribute_id)
        .order_by(AttributeHistory.created_at.desc())
        .first()
    )
    return row[0] if row else None


def detect(db: Session, user: User, now: datetime | None = None) -> list[dict]:
    """返回停滞维度列表。

    判定方式：对 attributes 中每个维度，取 attribute_history 里该维度最后一条
    created_at；若该维度无任何流水，则用 user_profiles.created_at 起算。
    排除：用户已关闭判定的维度、以及处于冷却期内的维度。
    """
    now = now or datetime.now()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    anchor_time = profile.created_at if profile and profile.created_at else now

    checks = _get_checks(db, user.id)
    disabled = _disabled_attributes(db, user.id)

    attrs = db.query(Attribute).filter(Attribute.user_id == user.id).order_by(Attribute.id).all()
    result: list[dict] = []
    for attr in attrs:
        if attr.name in disabled:
            continue
        last = _last_activity(db, user.id, attr.id)
        last_at = last or anchor_time
        days = (now - last_at).days
        if days < STAGNATION_DAYS:
            continue
        # 冷却期：同维度 STAGNATION_COOLDOWN_DAYS 内只问一次
        asked_raw = checks.get(attr.name)
        if asked_raw:
            try:
                asked_at = datetime.fromisoformat(str(asked_raw))
                if (now - asked_at).days < STAGNATION_COOLDOWN_DAYS:
                    continue
            except ValueError:
                pass
        result.append(
            {
                "name": attr.name,
                "days": days,
                "last_at": last_at.isoformat() if last_at else None,
            }
        )
    result.sort(key=lambda x: x["days"], reverse=True)
    return result


def answer(db: Session, user: User, name: str, stopped: bool, note: str = "") -> dict:
    """回答停滞问询。

    - `stopped=True`（确实停了）：小幅扣分 −0.3 → 写 attribute_history（**event_id=NULL**）
      → 生成一条"补课挑战"（周挑战，related_attributes=[该维度]）
    - `stopped=False`（在学只是没记）：**不扣分、不写任何属性流水**，返回 suggest_record=True
      并重置该维度停滞计时

    幂等：同一维度在冷却期内重复 answer 不会重复扣分（以 settings 中的问询时间为准）。
    """
    now = datetime.now()
    checks = _get_checks(db, user.id)

    # 冷却期内重复回答 → 幂等返回，不重复扣分
    asked_raw = checks.get(name)
    if asked_raw:
        try:
            asked_at = datetime.fromisoformat(str(asked_raw))
            if (now - asked_at).days < STAGNATION_COOLDOWN_DAYS:
                return {
                    "name": name,
                    "stopped": stopped,
                    "deducted": 0.0,
                    "balance_note": "该维度近期已问询过，本次不重复处理。",
                    "already_asked": True,
                    "suggest_record": not stopped,
                }
        except ValueError:
            pass

    deducted = 0.0
    challenge = None
    if stopped:
        # ① 小幅扣分（event_id=NULL —— 停滞扣分没有对应事件）
        attr = (
            db.query(Attribute)
            .filter(Attribute.user_id == user.id, Attribute.name == name)
            .first()
        )
        if attr is None:
            attr = Attribute(user_id=user.id, name=name, current_value=50.0)
            db.add(attr)
            db.flush()
        before = attr.current_value
        after = round(
            judge_service._clamp_attribute_value(before + STAGNATION_PENALTY, attr.max_value), 2
        )
        actual = round(after - before, 2)
        if actual != 0:
            attr.current_value = after
            db.add(
                AttributeHistory(
                    user_id=user.id,
                    attribute_id=attr.id,
                    event_id=None,  # 关键：不产生事件、不伪造判定
                    judgment_id=None,
                    delta=actual,
                    value_after=after,
                    reason=f"停滞确认：用户确认「{name}」维度长时间无相关行为",
                    evidence="用户主动确认长时间无相关行为，属行为驱动的变化，非日历衰减。",
                )
            )
            deducted = actual
        db.commit()

        # ② 生成一条"补课挑战"
        from app.services import challenge_service

        try:
            challenge = _build_restart_challenge(db, user, name)
        except Exception:
            challenge = None

    # 记录问询时间（两条分支都重置计时：stopped=False 时也重置，避免反复打扰）
    checks[name] = now.isoformat()
    _set_checks(db, user.id, checks)

    return {
        "name": name,
        "stopped": stopped,
        "deducted": deducted,
        "suggest_record": not stopped,
        "challenge": (
            {
                "id": challenge.id,
                "title": challenge.title,
                "description": challenge.description,
                "difficulty": challenge.difficulty,
                "coin_reward": challenge.coin_reward,
                "deposit": challenge.deposit,
                "ai_reason": challenge.ai_reason,
                "scope": challenge.scope,
                "status": challenge.status,
            }
            if challenge is not None
            else None
        ),
        "note": note,
    }


def _build_restart_challenge(db: Session, user: User, attribute_name: str):
    """为停滞维度生成一条"补课挑战"（周挑战，直接落为 candidate）。"""
    from app.models import Challenge
    from app.services import challenge_service

    difficulty = 2
    reward, deposit = challenge_service.coin_params("weekly", difficulty)
    ch = Challenge(
        user_id=user.id,
        scope="weekly",
        period_key=challenge_service.period_key("weekly"),
        title=f"重启「{attribute_name}」：本周做出一次真实投入",
        description=(
            f"你的{attribute_name}维度已经很久没有相关记录了。这周挑一件能真正带动"
            f"{attribute_name}的小事做一次——具体做什么、花多久，由你定，但要能一句话说清。"
        ),
        difficulty=difficulty,
        coin_reward=reward,
        deposit=deposit,
        related_attributes=[attribute_name],
        ai_reason=f"你的{attribute_name}维度长时间没有相关记录了，这条挑战帮你重新启动。",
        status="candidate",
        expires_at=challenge_service.period_end("weekly"),
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch
