"""商店服务（v1.8）：常驻物资预置 + AI 定价 + 兑换券。

**一致性铁律**：金币只有 `coin_service.grant()` 一个写入口，兑换走它。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Attribute, Redemption, ShopItem, User, UserProfile
from app.prompts.shop import build_pricing_messages
from app.services import coin_service, llm_config
from app.services.llm_service import llm_service

# 常驻物资（决策 14 / B4-1，首次访问商店时幂等预置；用户可改价或停用）
PRESET_ITEMS = [
    {"name": "奶茶（大杯）", "price_yuan": 15.0, "sort_order": 10},
    {"name": "一顿想吃的正餐", "price_yuan": 40.0, "sort_order": 20},
    {"name": "一部电影（影院）", "price_yuan": 45.0, "sort_order": 30},
    {"name": "一小时游戏时间", "price_yuan": 0.0, "sort_order": 40},
    {"name": "睡到自然醒（一个上午）", "price_yuan": 0.0, "sort_order": 50},
]

# 预置物品的初始金币价（AI 定价前的占位基准；用户可自行改价，AI 会据此重新定价）
PRESET_DEFAULT_COIN = {
    "奶茶（大杯）": 30,
    "一顿想吃的正餐": 80,
    "一部电影（影院）": 90,
    "一小时游戏时间": 20,
    "睡到自然醒（一个上午）": 40,
}


def seed_preset_items(db: Session, user: User) -> int:
    """幂等预置常驻物资：仅当同名 preset 物品不存在时写入。"""
    existing = {
        r.name
        for r in db.query(ShopItem).filter(ShopItem.user_id == user.id, ShopItem.kind == "preset").all()
    }
    created = 0
    for item in PRESET_ITEMS:
        if item["name"] in existing:
            continue
        db.add(
            ShopItem(
                user_id=user.id,
                name=item["name"],
                kind="preset",
                price_yuan=item["price_yuan"],
                coin_price=PRESET_DEFAULT_COIN.get(item["name"], 30),
                pricing_reason="常驻物资的初始定价，可随时让 AI 依据你的近况重新定价。",
                worth_note="",
                enabled=True,
                sort_order=item["sort_order"],
            )
        )
        created += 1
    if created:
        db.commit()
    return created


def _redemption_history(db: Session, user: User, days: int = 30) -> str:
    """近 N 天兑换历史摘要（AI 定价的情境浮动输入）。"""
    cutoff = datetime.now() - timedelta(days=days)
    rows = (
        db.query(Redemption)
        .filter(Redemption.user_id == user.id, Redemption.redeemed_at >= cutoff)
        .order_by(Redemption.redeemed_at.desc())
        .all()
    )
    if not rows:
        return ""
    # 按物品名聚合计数
    names: dict[str, int] = {}
    item_ids = [r.shop_item_id for r in rows if r.shop_item_id]
    item_map = {}
    if item_ids:
        for it in db.query(ShopItem).filter(ShopItem.id.in_(item_ids)).all():
            item_map[it.id] = it.name
    for r in rows:
        nm = item_map.get(r.shop_item_id, "已删除的物品")
        names[nm] = names.get(nm, 0) + 1
    detail = "、".join(f"{k} ×{v}" for k, v in names.items())
    return f"近 {days} 天共兑换 {len(rows)} 次：{detail}"


def _attributes_context(db: Session, user_id: int) -> str:
    attrs = db.query(Attribute).filter(Attribute.user_id == user_id).order_by(Attribute.id).all()
    return "、".join(f"{a.name} {a.current_value:.0f}" for a in attrs)


def _long_term_memory(db: Session, user_id: int) -> str:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    return str(profile.long_term_memory)[:1000] if profile and profile.long_term_memory else ""


def price_item(db: Session, user: User, name: str, price_yuan: float | None) -> dict:
    """一次 LLM 调用为物品定价，返回 {coin_price, pricing_reason, worth_note}。"""
    messages = build_pricing_messages(
        name=name,
        price_yuan=price_yuan,
        redemption_history=_redemption_history(db, user),
        attributes_context=_attributes_context(db, user.id),
        recent_memory=_long_term_memory(db, user.id),
    )
    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_AUX)
    result = llm_service.chat_json(messages, config=config)

    try:
        coin_price = int(result.get("coin_price"))
    except (TypeError, ValueError):
        coin_price = 0
    if coin_price <= 0:
        # 兜底：模型给出非法值时不至于让物品无法兑换
        coin_price = max(1, int(round((price_yuan or 0) * 2)) or 30)
    return {
        "coin_price": coin_price,
        "pricing_reason": str(result.get("pricing_reason", "")).strip(),
        "worth_note": str(result.get("worth_note", "")).strip(),
    }


def create_item_with_pricing(db: Session, user: User, name: str, price_yuan: float | None) -> ShopItem:
    """新建用户自录物品（AI 定价）。"""
    priced = price_item(db, user, name, price_yuan)
    item = ShopItem(
        user_id=user.id,
        name=name.strip()[:120],
        kind="custom",
        price_yuan=price_yuan,
        coin_price=priced["coin_price"],
        pricing_reason=priced["pricing_reason"],
        worth_note=priced["worth_note"],
        enabled=True,
        sort_order=100,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def repricing(db: Session, user: User, item: ShopItem) -> ShopItem:
    """对已有物品重新定价（用于验证"情境浮动"）。"""
    priced = price_item(db, user, item.name, item.price_yuan)
    item.coin_price = priced["coin_price"]
    item.pricing_reason = priced["pricing_reason"]
    item.worth_note = priced["worth_note"]
    db.commit()
    db.refresh(item)
    return item


def redeem(db: Session, user: User, item: ShopItem, note: str = "") -> Redemption:
    """兑换：校验启用与余额 → 扣币 → 生成待兑现的奖励券。"""
    if not item.enabled:
        raise ValueError("该物品已停用。")
    balance = coin_service.balance(db, user)
    if balance < item.coin_price:
        raise ValueError(
            f"金币不足（需 {item.coin_price} 币，当前 {balance} 币）。"
            "可以先记录日常事件或完成挑战攒币。"
        )
    coin_service.grant(
        db,
        user,
        -item.coin_price,
        source="shop_redeem",
        reason=f"兑换「{item.name}」",
        ref_type="shop_item",
        ref_id=item.id,
    )
    redemption = Redemption(
        user_id=user.id,
        shop_item_id=item.id,
        coin_spent=item.coin_price,  # 快照，防物品改价影响历史账目
        status="pending",
        redeemed_at=datetime.now(),
        note=note,
    )
    db.add(redemption)
    db.commit()
    db.refresh(redemption)
    return redemption


def fulfill(db: Session, user: User, redemption: Redemption, note: str = "") -> Redemption:
    """兑现奖励券：仅状态变更，**不再动金币**。已兑现再调幂等返回。"""
    if redemption.status == "fulfilled":
        return redemption
    redemption.status = "fulfilled"
    redemption.fulfilled_at = datetime.now()
    if note:
        redemption.note = note
    db.commit()
    db.refresh(redemption)
    return redemption


def list_redemptions(db: Session, user: User) -> list[dict]:
    """全部奖励券（附物品名，供前端两栏展示）。"""
    rows = (
        db.query(Redemption)
        .filter(Redemption.user_id == user.id)
        .order_by(Redemption.id.desc())
        .all()
    )
    item_ids = [r.shop_item_id for r in rows if r.shop_item_id]
    item_map = {}
    if item_ids:
        for it in db.query(ShopItem).filter(ShopItem.id.in_(item_ids)).all():
            item_map[it.id] = it.name
    return [
        {
            "id": r.id,
            "shop_item_id": r.shop_item_id,
            "item_name": item_map.get(r.shop_item_id, "已删除的物品"),
            "coin_spent": r.coin_spent,
            "status": r.status,
            "redeemed_at": r.redeemed_at,
            "fulfilled_at": r.fulfilled_at,
            "note": r.note,
        }
        for r in rows
    ]
