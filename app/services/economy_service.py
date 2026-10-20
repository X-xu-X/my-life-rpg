"""经济行情服务（v1.10）。

**为什么需要它**：v1.8 定的铁律是"金币金额必须由 `COIN_TABLE` 派生、AI 只得给 difficulty"。
v1.10（N1）推翻该铁律 —— 金额**完全交给 AI 判断**（用户原话："绝对上限 AI 自己判断不出来吗？"）。

但 AI 的失控根源不是"不可信"，而是**看不到全貌**（它不知道 90 币在这个人的经济里是大钱还是小钱）。
所以本模块提供一份**只读的「行情快照」**注入 prompt：事前给锚 → AI 仍是唯一决策者。

**两条使用约束**：
1. 挑战定价（`prompts/challenge.py`）与商店定价（`prompts/shop.py`）**必须注入同一套快照**
   —— 否则挑战奖励上调后"最贵 90 币的电影"会显得极便宜，**两套经济脱节**（N1-7）。
2. 快照里**只给商店价位区间，不给逐件商品清单**（N1-4，用户明确："奖励和商店不能太挂钩，
   那不然我都不能攒金币换奖励了"）。

`snapshot()` 是**只读**函数：不写库、不改余额、不发币。
"""
from app.services.time_service import clock_now
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import CoinLedger, ShopItem, User
from app.services import coin_service

# 行情快照的回看窗口（天）
LOOKBACK_DAYS = 7


def recent_flow(db: Session, user: User, days: int = LOOKBACK_DAYS) -> tuple[int, int]:
    """近 N 天的（收入合计, 支出合计）。只统计非零变动（0 值留痕不计入收支）。"""
    since = clock_now() - timedelta(days=days)
    rows = (
        db.query(CoinLedger.delta)
        .filter(CoinLedger.user_id == user.id, CoinLedger.created_at >= since)
        .all()
    )
    income = sum(int(d or 0) for (d,) in rows if (d or 0) > 0)
    expense = sum(-int(d or 0) for (d, ) in rows if (d or 0) < 0)
    return income, expense


def shop_price_range(db: Session, user: User) -> tuple[int, int] | None:
    """商店在售物品的金币价区间（最便宜, 最贵）。无在售物品返回 None。

    **只返回区间，不返回任何单件商品名与价格**（N1-4）。
    """
    rows = (
        db.query(ShopItem.coin_price)
        .filter(ShopItem.user_id == user.id, ShopItem.enabled.is_(True))
        .all()
    )
    prices = [int(p or 0) for (p,) in rows if (p or 0) > 0]
    if not prices:
        return None
    return min(prices), max(prices)


def snapshot(db: Session, user: User) -> str:
    """构建「行情快照」文本（供挑战定价与商店定价共用，N1-5）。

    内容严格限定为四项：余额 / 近 7 天收支 / 日常赚币规则 / 商店价位区间。
    """
    bal = coin_service.balance(db, user)
    income, expense = recent_flow(db, user)
    lines = [f"【金币余额】{bal} 币"]
    lines.append(f"【近 {LOOKBACK_DAYS} 天收支】收入 +{income} 币，支出 -{expense} 币")

    journal_rules = "；".join(
        f"连续写日记 {days} 天 +{amount} 币" for days, amount in coin_service.JOURNAL_STREAK_REWARDS
    )
    lines.append(
        f"【日常赚币】记录事件 +{coin_service.EVENT_CONFIRM_REWARD} 币/条；{journal_rules}"
    )
    from app.services import trial_rules
    config=trial_rules.account(db,user)
    if config and config.enabled:lines[-1]='【已采用试用规则】有效行动基础6/15/25币；本人主线另加4/10/15，单事实40、每日100封顶。首记3币独立；必要休息免费。'

    rng = shop_price_range(db, user)
    if rng is not None:
        lines.append(f"【商店价位】最便宜约 {rng[0]} 币，最贵约 {rng[1]} 币")

    return "\n".join(lines)
