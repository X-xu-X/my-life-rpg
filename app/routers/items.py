"""打卡项目路由（v1.7）。

用户自建打卡项目（系统不预置任何项目），供事件录入时选择。
- 删除 = 停用（enabled=False），**绝不物理删除**——历史事件引用它，删了老记录会丢名称。
- 项目是判定上下文的一部分（见 judge_service.format_event_description）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CheckinItem
from app.schemas import CheckinItemIn, CheckinItemOut, CheckinItemPatch
from app.services import item_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


def _get_item(db: Session, item_id: int) -> CheckinItem:
    item = db.get(CheckinItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="打卡项目不存在")
    return item


@router.get("/items", response_model=list[CheckinItemOut])
def list_items(
    db: Session = Depends(get_db),
    enabled: bool | None = None,
    nature: str = "",
):
    """项目列表。enabled 过滤启用状态（录入页只需 enabled=true），nature 过滤性质。"""
    user = get_or_create_default_user(db)
    query = db.query(CheckinItem).filter(CheckinItem.user_id == user.id)
    if enabled is not None:
        query = query.filter(CheckinItem.enabled == enabled)
    if nature:
        query = query.filter(CheckinItem.nature == nature)
    return query.order_by(CheckinItem.sort_order.asc(), CheckinItem.id.asc()).all()


@router.get("/items/stats")
def items_stats(db: Session = Depends(get_db)):
    """各项目频率达成情况（"本周运动 1/3"这类如实提示的数据源）。

    注意：路由声明必须在 /items/{item_id} 之前，否则 "stats" 会被当作 item_id 解析。
    只提示、不扣分（决策 5）。
    """
    user = get_or_create_default_user(db)
    items = (
        db.query(CheckinItem)
        .filter(CheckinItem.user_id == user.id, CheckinItem.enabled.is_(True))
        .order_by(CheckinItem.sort_order.asc(), CheckinItem.id.asc())
        .all()
    )
    return item_service.build_stats(db, user.id, items)


@router.post("/items", response_model=CheckinItemOut)
def create_item(body: CheckinItemIn, db: Session = Depends(get_db)):
    """新建打卡项目。"""
    user = get_or_create_default_user(db)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="项目名不能为空")
    item = CheckinItem(
        user_id=user.id,
        name=name,
        nature=body.nature,
        frequency_type=body.frequency_type,
        frequency_target=body.frequency_target if body.frequency_type == "weekly" else 0,
        category=body.category,
        related_attribute=body.related_attribute,
        goal_id=body.goal_id,
        enabled=body.enabled,
        sort_order=body.sort_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/items/{item_id}", response_model=CheckinItemOut)
def update_item(item_id: int, body: CheckinItemPatch, db: Session = Depends(get_db)):
    """修改项目（局部更新；含启用/停用）。

    只覆盖请求里显式传入的字段，未传的保持原值——这样「只挂目标」这类单字段
    修改不必回传整个对象（全量语义仍由前端表单发送完整 payload 覆盖）。
    """
    item = _get_item(db, item_id)
    fields = body.model_dump(exclude_unset=True)

    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="项目名不能为空")
        item.name = name
    if "nature" in fields and fields["nature"]:
        item.nature = fields["nature"]
    if "frequency_type" in fields and fields["frequency_type"]:
        item.frequency_type = fields["frequency_type"]
    # 频率目标：仅 weekly 有意义，切换为非 weekly 时归零（与 create 一致）
    if "frequency_target" in fields and fields["frequency_target"] is not None:
        item.frequency_target = fields["frequency_target"]
    if item.frequency_type != "weekly":
        item.frequency_target = 0
    for key in ("category", "related_attribute", "sort_order"):
        if key in fields and fields[key] is not None:
            setattr(item, key, fields[key])
    if "goal_id" in fields:
        item.goal_id = fields["goal_id"]
    if "enabled" in fields and fields["enabled"] is not None:
        item.enabled = fields["enabled"]

    db.commit()
    db.refresh(item)
    return item


@router.post("/items/{item_id}/toggle", response_model=CheckinItemOut)
def toggle_item(item_id: int, db: Session = Depends(get_db)):
    """启用 / 停用切换（不改其他字段，供列表页一键操作）。"""
    item = _get_item(db, item_id)
    item.enabled = not item.enabled
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    """删除 = 停用，**不做物理删除**。

    历史事件通过 item_id 引用项目名称，物理删除会让老记录显示空白；
    故此处仅置 enabled=False，项目从录入下拉消失但名称仍可解析。
    """
    item = _get_item(db, item_id)
    item.enabled = False
    db.commit()
    return {"status": "disabled", "item_id": item_id}
