"""金币服务（v1.8）：账户余额 + append-only 流水。

**唯一写入口铁律**：全项目只有本模块的 `grant()` 可以改金币余额，
任何地方（押金/返还/没收/兑换/赚币）都不得直接改 `profile.coins`
—— 沿用 v1.5 B-03「多入口必须同一写入语义」的教训。

金币与属性点**完全隔离**：金币不能兑换属性点，属性点也不能换金币。
"""
from app.services.time_service import clock_now
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.services.transactions import lock_profile

from app.models import CoinLedger, Event, User, UserProfile

# 启动资金兜底值（v1.8 起：解决"新用户 0 币无法接受挑战"的押金死锁）
# v1.9（F1）：正常路径改由 onboarding 的 AI 按问卷给出 80~200 并直接发放；
# 本值上调为 80（与新保底一致）作为**兜底**——万一 onboarding 路径异常未发放，
# 用户仍能拿到保底并走通「周挑战押金 35 + 中档奖励 40」的闭环。
STARTUP_BONUS = 80

# 日常事件确认入账的固定奖励（决策 12）
EVENT_CONFIRM_REWARD = 2

# 连续写日记里程碑：天数 → 金币
JOURNAL_STREAK_REWARDS = [(7, 30), (3, 10)]  # 从高到低匹配，避免 3 天档先命中

# source 合法取值（与 CoinLedger 类 docstring 保持一致）
SOURCES = (
    "onboarding_bonus",
    "event_confirm",
    "journal_streak",
    "challenge_reward",
    "challenge_deposit",
    "challenge_refund",
    "challenge_forfeit",
    "shop_redeem",
    "achievement",
    "exemption_purchase",
)


class InsufficientCoins(ValueError):
    """余额不足（禁止透支）。继承 ValueError，调用方可直接按 ValueError 捕获。"""


def _profile(db: Session, user: User) -> UserProfile:
    """取用户画像行；缺失则补建（V1 单用户，正常流程下必然已存在）。"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile is None:
        profile = UserProfile(user_id=user.id, coins=0)
        db.add(profile)
        db.flush()
    return profile


def balance(db: Session, user: User) -> int:
    """当前金币余额。"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    return int(profile.coins or 0) if profile else 0


def grant(
    db: Session,
    user: User,
    delta: int,
    source: str,
    reason: str = "",
    ref_type: str | None = None,
    ref_id: int | None = None,
) -> int:
    """**唯一金币写入口**。正负皆可；余额不足时抛 InsufficientCoins（禁止透支）。

    写入两处并保持一致：
    1. `user_profiles.coins`（当前余额）
    2. `coin_ledger`（流水，含 `balance_after` 便于对账）

    返回变动后的新余额。**不 commit**，由调用方控制事务边界（便于与判定入账同事务）。
    """
    if isinstance(delta, bool) or not isinstance(delta, int) or not -(2**63) <= delta < 2**63:
        raise ValueError("金币金额超出整数存储范围或不合法。")
    if delta == -(2**63):
        raise InsufficientCoins("金币不足。")
    profile = _profile(db, user)
    from app.config import settings
    if settings.cloud and not profile.onboarding_completed:
        raise ValueError("记录已保存；游戏结算前请先选择角色基线。")
    updated = db.query(UserProfile).filter(
        UserProfile.user_id == user.id,
        func.coalesce(UserProfile.coins, 0) >= max(0, -delta),
        func.coalesce(UserProfile.coins, 0) <= (2**63 - 1) - max(delta, 0),
    ).update({UserProfile.coins: func.coalesce(UserProfile.coins, 0) + delta}, synchronize_session=False)
    if updated != 1:
        raise InsufficientCoins("金币不足或余额超出整数存储范围。")
    db.refresh(profile)
    new_balance = int(profile.coins or 0)
    db.add(CoinLedger(user_id=user.id, delta=delta, balance_after=new_balance,
                      source=source, reason=reason, ref_type=ref_type, ref_id=ref_id))
    db.flush()
    return new_balance


def ledger(db: Session, user: User, limit: int = 50) -> list[CoinLedger]:
    """金币流水，按时间倒序（最新的在前）。"""
    return (
        db.query(CoinLedger)
        .filter(CoinLedger.user_id == user.id)
        .order_by(CoinLedger.created_at.desc(), CoinLedger.id.desc())
        .limit(limit)
        .all()
    )


def grant_startup_bonus_if_needed(db: Session, user: User, amount: int = STARTUP_BONUS, reason: str = "") -> bool:
    """幂等发放启动资金：仅当从未发过（ledger 无 onboarding_bonus 记录）时发放。

    返回 True 表示本次真的发了。
    """
    _profile(db, user)
    lock_profile(db, user.id)
    exists = (
        db.query(CoinLedger)
        .filter(CoinLedger.user_id == user.id, CoinLedger.source == "onboarding_bonus")
        .first()
    )
    if exists is not None:
        return False
    grant(
        db,
        user,
        amount,
        source="onboarding_bonus",
        reason=reason or f"角色档案建立，发放启动资金 {amount} 币",
    )
    return True


def _journal_days(db: Session, user: User) -> int:
    """统计最近连续写日记的天数（按 `created_at` 自然日，允许当天尚未写）。

    从"今天"往回数：今天有日记就从今天起算，今天没有就从昨天起算
    （否则用户晚上还没写日记时，连续天数会提前断掉）。
    """
    rows = (
        db.query(Event.created_at)
        .filter(Event.user_id == user.id, Event.is_deleted.is_(False), Event.source == "journal")
        .order_by(Event.created_at.desc())
        .all()
    )
    from app.services.time_service import local_day
    days = {local_day(r[0], user.timezone) for r in rows if r[0] is not None}
    if not days:
        return 0

    today = clock_now().date()
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def reward_event_confirm(db: Session, user: User, judgment, event_title: str = "") -> int | None:
    """事件确认入账后的金币奖励（决策 12 / A3-1）。

    - `final_changes` 的**净 delta 总和 > 0** → +2 币（source=event_confirm）
    - 净 delta **≤ 0** → **不给币，也不扣币**（决策 13：负面不扣，避免"双重惩罚"
      打击如实记录的意愿）

    只应由 `POST /api/judgments/{id}/confirm` 调用——挑战结算走的是
    `judge_service.confirm()` 但不该拿这笔日常奖励。

    返回新余额；未发放返回 None。
    """
    net = 0.0
    for c in judgment.final_changes or []:
        try:
            net += float(c.get("delta", 0) or 0)
        except (TypeError, ValueError):
            continue
    if net <= 0:
        return None
    return grant(
        db,
        user,
        EVENT_CONFIRM_REWARD,
        source="event_confirm",
        reason=f"记录「{event_title or '事件'}」",
        ref_type="event",
        ref_id=judgment.event_id,
    )


def check_journal_streak(db: Session, user: User) -> list[dict]:
    """检查连续写日记里程碑，达到则发币（幂等）。

    幂等口径：以 `coin_ledger` 中是否已存在**相同 reason 文案**的记录为准
    （reason 固定为「连续写日记 N 天」），故重复调用不会重复发放。

    返回本次新发放的列表（供接口回显）。
    """
    streak = _journal_days(db, user)
    granted: list[dict] = []
    if streak <= 0:
        return granted

    for days, amount in JOURNAL_STREAK_REWARDS:
        if streak < days:
            continue
        reason = f"连续写日记 {days} 天"
        already = (
            db.query(CoinLedger)
            .filter(
                CoinLedger.user_id == user.id,
                CoinLedger.source == "journal_streak",
                CoinLedger.reason == reason,
            )
            .first()
        )
        if already is not None:
            continue
        grant(db, user, amount, source="journal_streak", reason=reason)
        granted.append({"days": days, "amount": amount})
    return granted
