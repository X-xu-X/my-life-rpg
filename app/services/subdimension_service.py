"""子维度服务（v1.10 M3）。

**用户场景**：某个主维度接近满级（>= 95，M3-1 原文"接近/达到 100"）后，
继续笼统加分已无信息量 → AI 结合真实记录提议 2~4 个细分方向 → **用户勾选确认**后创建子维度。
之后主维度满 100 时，加点落在匹配的子维度上，**主维度保持 100 不变**（M3-2）。

三条硬约束：
1. **只提议，不自动创建**——未确认时绝不产生任何子维度行（M3-1）。
2. **主维度未满 100 → 加点仍落主维度**（M3-3 的兼容口径，保证既有行为不变）。
3. 属性值写入仍统一走 `judge_service._clamp_attribute_value()`（v1.5 B-03 教训）。
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.constants import (
    ATTRIBUTE_DIMENSIONS_SET,
    ATTRIBUTE_FULL,
    SUBDIMENSION_MAX,
    SUBDIMENSION_MIN,
    SUBDIMENSION_THRESHOLD,
)
from app.models import Attribute, Event, User, UserProfile
from app.prompts.subdimension import build_subdimension_messages
from app.services import llm_config
from app.services.llm_service import llm_service

# 提议状态的合法取值
STATE_PENDING = "pending"
STATE_ACCEPTED = "accepted"
STATE_DISMISSED = "dismissed"


# ============ 查询 ============


def children_of(db: Session, user: User, parent_id: int) -> list[Attribute]:
    return (
        db.query(Attribute)
        .filter(Attribute.user_id == user.id, Attribute.parent_id == parent_id)
        .order_by(Attribute.id)
        .all()
    )


def all_children(db: Session, user: User) -> list[Attribute]:
    return (
        db.query(Attribute)
        .filter(Attribute.user_id == user.id, Attribute.parent_id.isnot(None))
        .order_by(Attribute.id)
        .all()
    )


def child_name_set(db: Session, user: User) -> set[str]:
    """全部子维度名（供判定链路把它当作合法属性名）。"""
    return {c.name for c in all_children(db, user)}


def candidates(db: Session, user: User) -> list[dict]:
    """可拆分的候选主维度：`current_value >= 阈值` 且**尚无子维度**。

    返回结构含提议状态，便于前端「继续上次的提议 / 重新提议 / 已忽略」三态展示。
    """
    mains = (
        db.query(Attribute)
        .filter(Attribute.user_id == user.id, Attribute.parent_id.is_(None))
        .order_by(Attribute.id)
        .all()
    )
    out = []
    for a in mains:
        if float(a.current_value or 0) < SUBDIMENSION_THRESHOLD:
            continue
        if children_of(db, user, a.id):
            continue
        prop = a.sub_proposal if isinstance(a.sub_proposal, dict) else {}
        out.append(
            {
                "id": a.id,
                "name": a.name,
                "value": a.current_value,
                "max_value": a.max_value,
                "rate": round(float(a.current_value or 0) / float(a.max_value or 100) * 100, 1),
                "state": prop.get("state") or "",
                "items": prop.get("items") or [],
                "reason": prop.get("reason") or "",
            }
        )
    return out


def hierarchy(db: Session, user: User) -> dict[str, list[dict]]:
    """主维度名 → 子维度列表（供属性面板缩进展示）。"""
    out: dict[str, list[dict]] = {}
    mains = (
        db.query(Attribute)
        .filter(Attribute.user_id == user.id, Attribute.parent_id.is_(None))
        .all()
    )
    by_id = {a.id: a for a in mains}
    for c in all_children(db, user):
        parent = by_id.get(c.parent_id)
        if parent is None:
            continue
        out.setdefault(parent.name, []).append(
            {"name": c.name, "value": c.current_value, "max_value": c.max_value,
             "description": c.description}
        )
    return out


# ============ 判定链路的落点解析 ============


def resolve_write_target(db: Session, user: User, attr: Attribute, *, delta: float = 0.0) -> tuple[Attribute, str]:
    """决定一次加点/扣点**实际**写哪一行，并给出说明（M3-3）。

    - 目标是**主维度**且未满 100 → 写自己（既有行为不变）
    - 目标是**子维度**，但其主维度未满 100 → **回流到主维度**（未满级前不改行为）
    - 目标是**主维度**且已满 100 且已有子维度 → 落到**当前值最低的子维度**（兜底；
      prompt 会要求 AI 直接给子维度名，这里是模型没照做时的安全网，不丢分）

    返回 `(实际写入的属性行, 说明文本)`；说明为空表示未发生重定向。
    """
    # 情况一：目标本身是子维度
    if attr.parent_id is not None:
        parent = db.get(Attribute, attr.parent_id)
        if parent is not None and float(parent.current_value or 0) < ATTRIBUTE_FULL:
            return parent, f"（主维度「{parent.name}」未满 100，本次仍记入主维度）"
        return attr, ""

    # 情况二：目标是主维度且已满 → 兜底落到最低子维度
    if delta > 0 and float(attr.current_value or 0) >= float(attr.max_value or ATTRIBUTE_FULL):
        kids = children_of(db, user, attr.id)
        if kids:
            target = min(kids, key=lambda k: (float(k.current_value or 0), k.id))
            return target, f"（主维度「{attr.name}」已满 100，本次记入子维度「{target.name}」）"
    return attr, ""


# ============ 提议 / 确认 / 忽略 ============


def _related_events(db: Session, user: User, parent_name: str, days: int = 120, limit: int = 20) -> str:
    """与该维度相关的历史记录摘要（按「属性流水 + 事件标题」捞，尽量贴题）。"""
    from app.models import AttributeHistory  # 局部导入，避免模块级循环

    cutoff = datetime.now() - timedelta(days=days)
    rows = (
        db.query(Event.title, Event.category, Event.content, AttributeHistory.reason)
        .filter(Event.is_deleted.is_(False))
        .join(AttributeHistory, AttributeHistory.event_id == Event.id)
        .join(Attribute, Attribute.id == AttributeHistory.attribute_id)
        .filter(
            Attribute.user_id == user.id,
            Attribute.name == parent_name,
            AttributeHistory.created_at >= cutoff,
        )
        .order_by(AttributeHistory.created_at.desc())
        .limit(limit)
        .all()
    )
    lines = []
    for title, category, _content, reason in rows:
        t = (title or "").strip() or "(无标题)"
        c = (category or "").strip()
        lines.append(f"- {t}{('（' + c + '）') if c else ''}｜判定依据：{(reason or '').strip()[:60]}")
    return "\n".join(lines)


def _long_term_memory(db: Session, user_id: int) -> str:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    return str(profile.long_term_memory)[:1000] if profile and profile.long_term_memory else ""


def _clean_items(raw) -> list[dict]:
    """解析并清洗 AI 返回的 items：去重、去非法名、夹取数量、剔除与系统维度同名的项。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()[:20]
        if not name or name in seen or name in ATTRIBUTE_DIMENSIONS_SET:
            continue
        seen.add(name)
        out.append(
            {
                "name": name,
                "description": str(item.get("description", "")).strip()[:200],
            }
        )
    return out[:SUBDIMENSION_MAX]


def propose(db: Session, user: User, attr: Attribute) -> dict:
    """让 AI 提议细分方向并落库为 `pending`（**不创建任何子维度行**）。

    幂等：已有 `pending` 提议且未过期时直接复用，不重复调 AI。
    """
    if attr.parent_id is not None:
        raise ValueError("子维度不能再拆分。")
    if float(attr.current_value or 0) < SUBDIMENSION_THRESHOLD:
        raise ValueError(
            f"「{attr.name}」当前 {attr.current_value:.1f} 分，未达到拆分子维度的阈值 "
            f"{SUBDIMENSION_THRESHOLD:.0f} 分。"
        )
    kids = children_of(db, user, attr.id)
    if kids:
        raise ValueError(f"「{attr.name}」已经拆分过子维度，暂不支持重复拆分。")

    prop = attr.sub_proposal if isinstance(attr.sub_proposal, dict) else {}
    if prop.get("state") == STATE_PENDING and prop.get("items"):
        return prop  # 幂等：复用上次提议

    messages = build_subdimension_messages(
        parent_name=attr.name,
        parent_value=float(attr.current_value or 0),
        parent_description=attr.description or "",
        dimension_list="、".join(sorted(ATTRIBUTE_DIMENSIONS_SET)),
        recent_events=_related_events(db, user, attr.name),
        memory_context=_long_term_memory(db, user.id),
    )
    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_AUX)
    result = llm_service.chat_json(messages, config=config)

    items = _clean_items(result.get("items"))
    if len(items) < SUBDIMENSION_MIN:
        raise ValueError(
            f"AI 只给出了 {len(items)} 个有效细分方向（少于 {SUBDIMENSION_MIN} 个），请稍后重试。"
        )

    proposal = {
        "state": STATE_PENDING,
        "items": items,
        "reason": str(result.get("reason", "")).strip()[:300],
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    attr.sub_proposal = proposal
    db.commit()
    db.refresh(attr)
    return proposal


def accept(db: Session, user: User, attr: Attribute, names: list[str]) -> list[Attribute]:
    """按用户**勾选的名字**创建子维度（未勾选的不创建 → M3-1 的「确认后才解锁」）。"""
    if attr.parent_id is not None:
        raise ValueError("子维度不能再拆分。")
    prop = attr.sub_proposal if isinstance(attr.sub_proposal, dict) else {}
    items = prop.get("items") or []
    if not items:
        raise ValueError("还没有可确认的细分方向，请先让 AI 提议。")

    allowed = {str(i.get("name", "")).strip(): str(i.get("description", "")).strip() for i in items}
    picked = [str(n).strip() for n in (names or []) if str(n).strip() in allowed]
    picked = list(dict.fromkeys(picked))  # 去重且保序
    if not picked:
        raise ValueError("请至少勾选一个细分方向。")

    # 名称冲突保护：attributes 有 (user_id, name) 唯一约束，撞名会直接 500
    existing = {
        a.name for a in db.query(Attribute).filter(Attribute.user_id == user.id).all()
    }
    clash = [n for n in picked if n in existing]
    if clash:
        raise ValueError(f"以下名称已存在，请换一个或跳过：{'、'.join(clash)}。")

    if children_of(db, user, attr.id):
        raise ValueError(f"「{attr.name}」已经拆分过子维度，暂不支持重复拆分。")

    created: list[Attribute] = []
    for name in picked:
        row = Attribute(
            user_id=user.id,
            name=name[:50],
            description=allowed.get(name, "") or f"{attr.name} 的细分方向。",
            attr_type=attr.attr_type or "",
            current_value=0.0,
            max_value=attr.max_value or ATTRIBUTE_FULL,
            parent_id=attr.id,
        )
        db.add(row)
        created.append(row)
    db.flush()

    attr.sub_proposal = {**prop, "state": STATE_ACCEPTED,
                         "accepted": picked, "accepted_at": datetime.now().isoformat(timespec="seconds")}
    db.commit()
    for row in created:
        db.refresh(row)
    return created


def dismiss(db: Session, user: User, attr: Attribute) -> None:
    """忽略本次提议（**不创建任何子维度**）。保留 items 以便审计。"""
    prop = attr.sub_proposal if isinstance(attr.sub_proposal, dict) else {}
    attr.sub_proposal = {**prop, "state": STATE_DISMISSED,
                         "dismissed_at": datetime.now().isoformat(timespec="seconds")}
    db.commit()


def serialize_children(db: Session, user: User, parent_id: int) -> list[dict]:
    return [
        {"id": c.id, "name": c.name, "value": c.current_value,
         "max_value": c.max_value, "description": c.description}
        for c in children_of(db, user, parent_id)
    ]
