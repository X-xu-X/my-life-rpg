"""商店服务（v1.8）：常驻物资预置 + AI 定价 + 兑换券。

**一致性铁律**：金币只有 `coin_service.grant()` 一个写入口，兑换走它。
"""
from app.services.ai_context import model_context
from app.services.model_validation import provenance
from app.services.time_service import clock_now
from datetime import datetime, timedelta, date

import json
from sqlalchemy.orm import Session

from app.models import Attribute, Redemption, ShopItem, User, UserProfile
from app.prompts.shop import build_pricing_messages
from app.services import achievement_service, coin_service, economy_service, llm_config
from app.services.llm_service import llm_service
from app.services.transactions import rollback_on_error, lock_profile

# 常驻物资（决策 14 / B4-1，首次访问商店时幂等预置；用户可改价或停用）
PRESET_ITEMS = [
    {"name": "奶茶（大杯）", "price_yuan": 15.0, "sort_order": 10},
    {"name": "额外娱乐半小时", "price_yuan": 0.0, "sort_order": 20},
]

# 预置物品的初始金币价（AI 定价前的占位基准；用户可自行改价，AI 会据此重新定价）
PRESET_DEFAULT_COIN = {
    "奶茶（大杯）": 30,
    "额外娱乐半小时": 20,
}


def seed_preset_items(db: Session, user: User, *, commit: bool = True) -> int:
    """幂等预置常驻物资：仅当同名 preset 物品不存在时写入。"""
    existing = {
        r.name
        for r in db.query(ShopItem).filter(ShopItem.user_id == user.id, ShopItem.kind == "preset").all()
    }
    created = 0
    if existing:return 0  # Existing shop/legacy benefits are never reseeded or repriced.
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
                base_coin_price=PRESET_DEFAULT_COIN[item['name']],reward_kind='entertainment' if item['name']=='额外娱乐半小时' else 'item',
                duration_seconds=1800 if item['name']=='额外娱乐半小时' else None,
                pricing_reason="已批准的新账号试用参考价格；不是模型定价结果，可主动请求价格建议。",
                worth_note="",
                enabled=True,
                sort_order=item["sort_order"],
            )
        )
        created += 1
    if created and commit:
        db.commit()
    return created


def pricing_activity(db: Session, user: User, days: int = 30) -> dict:
    """Bounded purchases and confirmed entertainment use; no plan text or notes."""
    from app.models.full_system import TimeSession
    from app.services import trial_rules
    from app.services.time_service import utc_now,stored_time
    today=date.fromisoformat(trial_rules.day(db,user));first=today-timedelta(days=days-1)
    purchases=db.query(Redemption).filter(Redemption.user_id==user.id,
        Redemption.redeemed_at>=stored_time(utc_now()-timedelta(days=days)),Redemption.redeemed_at<=stored_time(utc_now())).order_by(Redemption.id).all()
    item_ids={r.shop_item_id for r in purchases}
    names={r.id:r.name for r in db.query(ShopItem).filter(ShopItem.user_id==user.id,ShopItem.id.in_(item_ids)).all()}
    purchased={}
    for row in purchases:
        name=names.get(row.shop_item_id,'旧奖励');purchased[name]=purchased.get(name,0)+1
    day_field=TimeSession.settlement['day'].as_string()
    sessions=db.query(TimeSession).filter(TimeSession.user_id==user.id,TimeSession.state=='ended',
        TimeSession.kind.in_(('base','voucher')),day_field>=str(first),day_field<=str(today)).order_by(TimeSession.id).all()
    daily={};versions=[]
    for row in sessions:
        value=row.settlement or {};seconds=value.get('actual_seconds');day=value.get('day')
        if type(seconds) is not int or seconds<0:continue
        try:date.fromisoformat(day)
        except (ValueError,TypeError):continue
        entry=daily.setdefault(day,{'date':day,'actual_seconds':0,'sessions':0,'base_seconds':0,'voucher_seconds':0})
        entry['actual_seconds']+=seconds;entry['sessions']+=1;entry[row.kind+'_seconds']+=seconds
        versions.append((row.id,row.version))
    rows=[daily[d] for d in sorted(daily)]
    def period(start,end):
        selected=[r for r in rows if str(start)<=r['date']<=str(end)]
        return {'start':str(start),'end':str(end),'actual_seconds':sum(r['actual_seconds'] for r in selected),
            'active_days':sum(r['actual_seconds']>0 for r in selected),'sessions':sum(r['sessions'] for r in selected)}
    return {'window':{'start':str(first),'end':str(today),'days':days,'date_basis':'confirmed_settlement_day'},
        'purchases':{'vouchers':len(purchases),'items':[{'name':n,'purchased':purchased[n]} for n in sorted(purchased)],
            'marked_fulfilled':sum(r.status=='fulfilled' for r in purchases),
            'untimed_fulfilled':sum(r.status=='fulfilled' and r.duration_seconds is None for r in purchases)},
        'entertainment':{**period(first,today),'daily':rows,
            'recent_7_days':period(today-timedelta(days=6),today),
            'previous_7_days':period(today-timedelta(days=13),today-timedelta(days=7))},
        '_session_versions':versions}


def _redemption_history(db: Session, user: User, days: int = 30) -> str:
    activity=pricing_activity(db,user,days);activity.pop('_session_versions',None)
    return json.dumps(activity,ensure_ascii=False,sort_keys=True)


def _attributes_context(db: Session, user_id: int) -> str:
    # v1.10 M3：只列主维度（子维度数值不参与商店行情语义）
    attrs = (
        db.query(Attribute)
        .filter(Attribute.user_id == user_id, Attribute.parent_id.is_(None))
        .order_by(Attribute.id)
        .all()
    )
    return "、".join(f"{a.name} {a.current_value:.0f}" for a in attrs)


def _long_term_memory(db: Session, user_id: int) -> str:
    from app.services.memory_service import get_long_term_memory,format_memory_text
    return format_memory_text(get_long_term_memory(db,user_id))


def price_item(db: Session, user: User, name: str, price_yuan: float | None) -> dict:
    """一次 LLM 调用为物品定价，返回 {coin_price, pricing_reason, worth_note}。

    v1.10（N1-7 / N1-8）：注入 `economy_service.snapshot()` 的行情快照
    ——**与挑战定价共用同一套**。原先 prompt 要求 AI「结合金币获取速度折算」，
    但从未传入任何收入数据，AI 只能编造。
    """
    messages = build_pricing_messages(
        name=name,
        price_yuan=price_yuan,
        redemption_history=_redemption_history(db, user),
        attributes_context=_attributes_context(db, user.id),
        recent_memory=_long_term_memory(db, user.id),
        economy_context=economy_service.snapshot(db, user),
    )
    from app.services.judge_service import _profile_context
    messages.append({'role':'user','content':'本人明确授权的个人购买力参考、问卷偏好与阶段背景（不是指令，不设统一汇率）：'+_profile_context(db,user.id,'pricing')})
    from app.models import Goal
    from app.models.policies import Mainline
    current=[{'goal':g.description,'deadline':g.deadline.isoformat() if g.deadline else None} for m,g in db.query(Mainline,Goal).join(Goal,Goal.id==Mainline.goal_id).filter(Mainline.user_id==user.id,Mainline.active.is_(True),Goal.status=='active').all()]
    import json
    messages.append({'role':'user','content':'本人选择的当前主线（作为本次定价背景）：'+json.dumps(current,ensure_ascii=False)})
    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_JUDGE)
    db.commit()
    result = llm_service.chat_json(messages, config=config)
    lock_profile(db, user.id)
    llm_config.assert_current(db, config)

    coin_price=result.get('coin_price')
    if type(coin_price) is not int or not 1<=coin_price<=10**9 or not isinstance(result.get('pricing_reason'),str) or not result['pricing_reason'].strip():
        from app.services.llm_service import LLMError
        raise LLMError('MODEL_INVALID_RESPONSE：未生成有效价格与依据，请保留草稿后重试。')
    # 是否计时类由模型判断；估值只用于日后计时额度，不参与定价。
    is_timed = result.get('is_timed') is True
    minutes = result.get('minutes_estimate')
    if type(minutes) is not int or not 1 <= minutes <= 1440:
        minutes = None
    if is_timed and minutes is None:
        is_timed = False
    return {
        "coin_price": coin_price,
        "model_provenance": provenance(config),
        "pricing_reason": str(result.get("pricing_reason", "")).strip(),
        "worth_note": str(result.get("worth_note", "")).strip(),
        "is_timed": is_timed,
        "minutes_estimate": minutes,
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
    version = item.updated_at
    priced = price_item(db, user, item.name, item.price_yuan)
    db.refresh(item)
    if item.updated_at != version:
        raise ValueError('物品已变化，请重新读取后定价。')
    item.coin_price = priced["coin_price"]
    item.pricing_reason = priced["pricing_reason"]
    item.worth_note = priced["worth_note"]
    db.commit()
    db.refresh(item)
    return item


@rollback_on_error
def redeem(db: Session, user: User, item: ShopItem, note: str = "", *, commit: bool = True) -> Redemption:
    """兑换：校验启用与余额 → 扣币 → 生成待兑现的奖励券。"""
    lock_profile(db, user.id)
    db.refresh(item)
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
        duration_seconds=item.duration_seconds,
        coin_spent=item.coin_price,  # 快照，防物品改价影响历史账目
        status="pending",
        redeemed_at=clock_now(),
        note=note,
    )
    db.add(redemption)
    if not commit:
        db.flush()
        return redemption
    db.commit()
    db.refresh(redemption)

    # v1.10 M1：累计型成就顺带检查（「首次兑换奖励」在此解锁）
    try:
        achievement_service.check_and_grant(db, user)
    except Exception:
        db.rollback()
    return redemption


def fulfill(db: Session, user: User, redemption: Redemption, note: str = "") -> Redemption:
    """兑现奖励券：仅状态变更，**不再动金币**。已兑现再调幂等返回。"""
    from app.services.transactions import lock_profile
    lock_profile(db, user.id)
    db.refresh(redemption)
    if redemption.status == "fulfilled":
        return redemption
    redemption.status = "fulfilled"
    redemption.fulfilled_at = clock_now()
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
