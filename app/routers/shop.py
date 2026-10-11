"""商店路由（v1.8）：物品管理 + AI 定价 + 兑换券。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Redemption, ShopItem
from app.schemas import FulfillIn, RedeemIn, ShopItemIn, ShopItemUpdateIn
from app.services import coin_service, shop_service
from app.services.llm_service import LLMError
from app.services.user_service import get_or_create_default_user
from app.services import receipts
from app.services.transactions import lock_profile
from fastapi.encoders import jsonable_encoder
from uuid import UUID
from app.models.access import RequestReceipt

router = APIRouter()


def _item_out(it: ShopItem) -> dict:
    return {
        "id": it.id,
        "name": it.name,
        "kind": it.kind,
        "price_yuan": it.price_yuan,
        "coin_price": it.coin_price,
        "pricing_reason": it.pricing_reason,
        "worth_note": it.worth_note,
        "enabled": it.enabled,
        "sort_order": it.sort_order,
        "created_at": it.created_at,
        "updated_at": it.updated_at,
    }


def _get_item(db: Session, user, item_id: int) -> ShopItem:
    it = db.get(ShopItem, item_id)
    if it is None or it.user_id != user.id:
        raise HTTPException(status_code=404, detail="物品不存在")
    return it


@router.get("/shop/items")
def list_items(db: Session = Depends(get_db)):
    """物品列表（首次访问时幂等预置常驻物资）。"""
    user = get_or_create_default_user(db)
    from app.config import settings
    if not settings.cloud:
        shop_service.seed_preset_items(db, user)
    rows = (
        db.query(ShopItem)
        .filter(ShopItem.user_id == user.id)
        .order_by(ShopItem.sort_order.asc(), ShopItem.id.asc())
        .all()
    )
    return {"items": [_item_out(i) for i in rows], "balance": coin_service.balance(db, user)}


@router.post("/shop/items")
def create_item(body: ShopItemIn, db: Session = Depends(get_db)):
    """新建自录物品 → **触发 AI 定价**（一次 LLM 调用，返回定价理由与建议）。"""
    user = get_or_create_default_user(db)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="物品名不能为空")
    try:
        item = shop_service.create_item_with_pricing(db, user, name, body.price_yuan)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _item_out(item)


@router.put("/shop/items/{item_id}")
def update_item(item_id: int, body: ShopItemUpdateIn, db: Session = Depends(get_db)):
    """局部修改物品（用户手动改价 / 停用）。改价会在定价理由后追加说明。"""
    user = get_or_create_default_user(db)
    it = _get_item(db, user, item_id)
    lock_profile(db, user.id)
    db.refresh(it)
    fields = body.model_dump(exclude_unset=True)

    if "name" in fields and fields["name"] is not None:
        nm = str(fields["name"]).strip()
        if not nm:
            raise HTTPException(status_code=400, detail="物品名不能为空")
        it.name = nm[:120]
    if "price_yuan" in fields:
        it.price_yuan = fields["price_yuan"]
    if "coin_price" in fields and fields["coin_price"] is not None:
        new_price = int(fields["coin_price"])
        if new_price <= 0:
            raise HTTPException(status_code=400, detail="金币价必须为正整数")
        it.coin_price = new_price
        suffix = f"（用户手动调整为 {new_price} 币）"
        if suffix not in (it.pricing_reason or ""):
            it.pricing_reason = (it.pricing_reason or "") + suffix
    if "enabled" in fields and fields["enabled"] is not None:
        it.enabled = fields["enabled"]
    if "sort_order" in fields and fields["sort_order"] is not None:
        it.sort_order = int(fields["sort_order"])
    db.commit()
    db.refresh(it)
    return _item_out(it)


@router.post("/shop/items/{item_id}/reprice")
def reprice_item(item_id: int, db: Session = Depends(get_db)):
    """让 AI 依据近况与兑换历史**重新定价**（验证"情境浮动"用）。"""
    user = get_or_create_default_user(db)
    it = _get_item(db, user, item_id)
    try:
        it = shop_service.repricing(db, user, it)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _item_out(it)


@router.delete("/shop/items/{item_id}")
def disable_item(item_id: int, db: Session = Depends(get_db)):
    """停用物品（**不做物理删除**，保留历史兑换记录的名称引用）。"""
    user = get_or_create_default_user(db)
    it = _get_item(db, user, item_id)
    lock_profile(db, user.id)
    db.refresh(it)
    it.enabled = False
    db.commit()
    return {"status": "disabled", "item_id": item_id}


@router.post("/shop/items/{item_id}/redeem")
def redeem_item(item_id: int, body: RedeemIn | None = None, db: Session = Depends(get_db)):
    """兑换 → 生成一张待兑现的「奖励券」。余额不足返回 400。"""
    user = get_or_create_default_user(db)
    it = _get_item(db, user, item_id)
    body = body or RedeemIn()
    lock_profile(db, user.id)
    db.refresh(it)
    operation = f'redeem:{item_id}'
    fingerprint, prior = receipts.replay(db, user.id, operation, body)
    if prior is not None:
        return prior
    if body.expected_version is not None and body.expected_version != it.updated_at:
        db.rollback()
        raise HTTPException(409, '物品价格已更新，请重新读取。')
    note = (body.note if body else "") or ""
    try:
        redemption = shop_service.redeem(db, user, it, note, commit=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = {
        "redemption": {
            "id": redemption.id,
            "shop_item_id": redemption.shop_item_id,
            "item_name": it.name,
            "coin_spent": redemption.coin_spent,
            "status": redemption.status,
            "redeemed_at": redemption.redeemed_at,
            "fulfilled_at": redemption.fulfilled_at,
            "note": redemption.note,
        },
        "balance": coin_service.balance(db, user),
    }
    receipts.record(db, user.id, operation, body, fingerprint, redemption.id, jsonable_encoder(result))
    db.commit()
    return result


@router.get("/shop/items/{item_id}/redemption-submissions/{request_key}")
def redemption_submission(item_id: int, request_key: UUID, db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    _get_item(db, user, item_id)
    row = db.query(RequestReceipt).filter_by(user_id=user.id, operation=f'redeem:{item_id}',
        request_key=str(request_key)).first()
    if row is None:
        raise HTTPException(404, "兑换回执尚不存在；可使用原操作标识恢复。")
    return row.response_snapshot


@router.get("/redemptions")
def list_redemptions(db: Session = Depends(get_db)):
    """奖励券列表（待兑现 / 已兑现，供前端两栏展示）。"""
    user = get_or_create_default_user(db)
    return {"redemptions": shop_service.list_redemptions(db, user)}


@router.post("/redemptions/{redemption_id}/fulfill")
def fulfill_redemption(redemption_id: int, body: FulfillIn | None = None, db: Session = Depends(get_db)):
    """线下兑现后手动打勾「已兑现」（幂等；不再变动金币）。"""
    user = get_or_create_default_user(db)
    r = db.get(Redemption, redemption_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="奖励券不存在")
    note = (body.note if body else "") or ""
    r = shop_service.fulfill(db, user, r, note)
    return {
        "id": r.id,
        "status": r.status,
        "fulfilled_at": r.fulfilled_at,
        "balance": coin_service.balance(db, user),
    }
