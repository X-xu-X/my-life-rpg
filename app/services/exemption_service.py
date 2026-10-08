"""豁免券服务（v1.10 M2）。

**这是什么**：用户花金币买一张**指定日期 + 指定时段**的券。在该时段内，他计划内的事
没完成 / 出现退缩行为时，**负向变化一律归零**；同时段内做的其他好事**照常加别的维度点数**
（绝不整条事件跳过判定）。

**用户红线**（原话）："要是买来随便一个时间都可以，感觉临时不想干活用券，感觉很奇怪，
不利于自身成长" → **绝不能做成万能券**：日期与时段必填，缺一即拒。

三条硬约束：
1. 金币只有 `coin_service.grant()` 一个写入口（新增 source=`exemption_purchase`）。
2. 属性值写入统一走 `judge_service._clamp_attribute_value()`，并以**实际变动量**记账
   （v1.5 B-03 教训：多入口必须同一写入语义）。
3. **允许跨零点**（用户 2026-09-30 拍板）：`end_time <= start_time` 表示区间延到次日。
"""

from datetime import date as _date
from datetime import datetime, time as _time
from datetime import timedelta

from sqlalchemy.orm import Session

from app.constants import ATTRIBUTE_DIMENSIONS_SET
from app.models import Attribute, AttributeHistory, Event, Exemption, User, UserProfile
from app.prompts.exemption import build_exemption_messages
from app.services import coin_service, economy_service, llm_config
from app.services.llm_service import llm_service

# 预设时段（用户 2026-09-30 选择：**预设快捷 + 可自定义**）
PERIOD_PRESETS: dict[str, dict] = {
    "morning": {"label": "上午", "start": "06:00", "end": "12:00"},
    "afternoon": {"label": "下午", "start": "12:00", "end": "18:00"},
    "evening": {"label": "晚上", "start": "18:00", "end": "23:59"},
    "allday": {"label": "全天", "start": "00:00", "end": "23:59"},
    "custom": {"label": "自定义", "start": "", "end": ""},
}
PERIOD_KEYS = tuple(PERIOD_PRESETS.keys())

# 额外扣点的上限（防止模型给出过重惩罚）
EXTRA_PENALTY_MAX = 0.5
# 额外扣点的兜底维度（AI 给出的维度非法时用它）
DEFAULT_PENALTY_ATTRIBUTE = "规划力"

# 单张券的价格兜底区间（AI 未给出合法正整数时使用）
FALLBACK_COST = 30


def _parse_hhmm(text: str) -> _time | None:
    """解析 'HH:MM'；非法返回 None。"""
    raw = (text or "").strip()
    if len(raw) != 5 or raw[2] != ":":
        return None
    try:
        hh, mm = int(raw[:2]), int(raw[3:])
    except ValueError:
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return _time(hh, mm)


def resolve_period(period: str, start_time: str = "", end_time: str = "") -> tuple[str, str, str]:
    """把 (period, start_time, end_time) 解析成最终生效的三元组。

    - 预设档（morning/afternoon/evening/allday）→ 忽略传入的起止，用预设值；
    - `custom` → **必须**给出合法的 HH:MM 起止，且两者不能相同（相同 → 视为非法）。

    返回 `(period, start_time, end_time)`；非法时抛 `ValueError`。
    """
    key = (period or "").strip().lower()
    if key not in PERIOD_PRESETS:
        raise ValueError("豁免券必须指定时段（morning/afternoon/evening/allday/custom）。")
    if key != "custom":
        preset = PERIOD_PRESETS[key]
        return key, preset["start"], preset["end"]

    st, et = _parse_hhmm(start_time), _parse_hhmm(end_time)
    if st is None or et is None:
        raise ValueError("自定义时段需要合法的起止时间（格式 HH:MM）。")
    if st == et:
        raise ValueError("自定义时段的开始与结束时间不能相同。")
    return "custom", st.strftime("%H:%M"), et.strftime("%H:%M")


def window_of(row: Exemption) -> tuple[datetime, datetime]:
    """券的实际生效区间 [start, end]（**跨零点时 end 落在次日**）。"""
    d = _date.fromisoformat(row.target_date)
    st = _parse_hhmm(row.start_time) or _time(0, 0)
    et = _parse_hhmm(row.end_time) or _time(23, 59)
    start = datetime(d.year, d.month, d.day, st.hour, st.minute)
    end = datetime(d.year, d.month, d.day, et.hour, et.minute)
    if end <= start:
        end += timedelta(days=1)  # 跨零点：22:00 – 次日 02:00
    return start, end


def label_of(row: Exemption) -> str:
    """展示用标签，如「今天下午 12:00–18:00」。"""
    preset = PERIOD_PRESETS.get(row.period)
    tag = preset["label"] if preset else "自定义"
    if row.period == "custom":
        tag = "自定义时段"
    return f"{row.target_date} {tag} {row.start_time}–{row.end_time}"


def serialize(row: Exemption) -> dict:
    """前端展示用结构（含人类可读标签与生效区间）。"""
    start, end = window_of(row)
    return {
        "id": row.id,
        "target_date": row.target_date,
        "period": row.period,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "label": label_of(row),
        "cross_midnight": end.date() != start.date(),
        "reason": row.reason,
        "coin_cost": row.coin_cost,
        "motive": row.motive,
        "motive_note": row.motive_note,
        "extra_penalty": row.extra_penalty,
        "penalty_attribute": row.penalty_attribute or "",
        "status": row.status,
        "used_at": row.used_at,
        "created_at": row.created_at,
        "window_start": start,
        "window_end": end,
    }


# ============ 生效链路（judge_service 调用） ============


def expire_stale(db: Session, user: User) -> int:
    """惰性过期：已过生效区间且仍是 `active` 的券 → `expired`（已用过的保留 used）。

    参考 `challenge_service.expire_stale` 的做法：不新增定时任务，读列表/判定时顺带执行。
    """
    now = datetime.now()
    changed = 0
    rows = (
        db.query(Exemption)
        .filter(Exemption.user_id == user.id, Exemption.status == "active")
        .all()
    )
    for row in rows:
        _start, end = window_of(row)
        if now > end:
            row.status = "expired"
            changed += 1
    if changed:
        db.flush()
    return changed


def find_active(db: Session, user: User, at: datetime) -> Exemption | None:
    """查询覆盖时刻 `at` 的券。

    - 只认 `active` / `used`：**`used` 也要继续匹配**，否则「补充信息重判」时同一张券
      第一次生效、第二次不生效，重判结果会前后不一致（v1.5「重判就地更新」契约）。
    - 候选只取 `target_date` 为当天或前一天的券（跨零点最多覆盖到次日），再逐个比对真实区间。
    """
    if at is None:
        return None
    d = at.date()
    candidates = (
        db.query(Exemption)
        .filter(
            Exemption.user_id == user.id,
            Exemption.status.in_(["active", "used", "expired"]),
            Exemption.target_date.in_([d.isoformat(), (d - timedelta(days=1)).isoformat()]),
        )
        .all()
    )
    for row in candidates:
        start, end = window_of(row)
        if start <= at <= end:
            return row
    return None


def mark_used(db: Session, row: Exemption) -> None:
    """券真正发挥豁免作用时置 `used`（幂等，只记第一次）。"""
    if row.status in ("active", "expired"):
        row.status = "used"
        row.used_at = datetime.now()
        db.flush()


def apply_to_changes(changes: list[dict], at: datetime, db: Session, user: User) -> tuple[list[dict], dict | None]:
    """**判定链路的唯一插入点**：落在券时段内的**负向变化一律归零**，正向原样保留。

    返回 `(changes, hit)`；`hit` 为 None 表示本次没有券生效。
    券只有**真的豁免掉了至少一项扣分**时才算「用过」（`mark_used`）。
    """
    row = find_active(db, user, at)
    if row is None:
        return changes, None

    zeroed = 0
    out: list[dict] = []
    for item in changes:
        if float(item.get("delta", 0.0)) < 0:
            reason = str(item.get("reason", "")).strip()
            out.append(
                {
                    **item,
                    "delta": 0.0,
                    "reason": (reason + " " if reason else "") + "【豁免券生效：该时段内不扣分】",
                }
            )
            zeroed += 1
        else:
            out.append(item)

    if zeroed == 0:
        return changes, None

    mark_used(db, row)
    return out, {
        "id": row.id,
        "label": label_of(row),
        "zeroed": zeroed,
        "motive": row.motive,
    }


# ============ 购买 ============


def _attributes_context(db: Session, user_id: int) -> str:
    # v1.10 M3：只列主维度（惩罚扣点/动机判断针对主维度语义）
    attrs = (
        db.query(Attribute)
        .filter(Attribute.user_id == user_id, Attribute.parent_id.is_(None))
        .order_by(Attribute.id)
        .all()
    )
    return "、".join(f"{a.name} {a.current_value:.0f}" for a in attrs)


def _long_term_memory(db: Session, user_id: int) -> str:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    return str(profile.long_term_memory)[:1000] if profile and profile.long_term_memory else ""


def _recent_events(db: Session, user: User, days: int = 7, limit: int = 12) -> str:
    """近 N 天记录摘要（供 AI 判断「他最近是不是已经在频繁停摆」）。"""
    cutoff = datetime.now() - timedelta(days=days)
    rows = (
        db.query(Event)
        .filter(Event.user_id == user.id, Event.created_at >= cutoff)
        .order_by(Event.created_at.desc())
        .limit(limit)
        .all()
    )
    lines = []
    for e in rows:
        when = (e.created_at or datetime.now()).strftime("%m-%d")
        title = (e.title or "").strip() or "(无标题)"
        lines.append(f"- {when} {title}（{e.event_type}）")
    return "\n".join(lines)


def _parse_pricing(raw: dict) -> dict:
    """解析 AI 返回的定价与动机判断，含全部兜底。"""
    try:
        cost = int(raw.get("coin_cost"))
    except (TypeError, ValueError):
        cost = 0
    if cost <= 0:
        cost = FALLBACK_COST

    motive = str(raw.get("motive", "")).strip().lower()
    if motive not in ("legitimate", "evasive"):
        motive = "legitimate"

    try:
        penalty = float(raw.get("extra_penalty", 0.0) or 0.0)
    except (TypeError, ValueError):
        penalty = 0.0
    penalty = max(0.0, min(EXTRA_PENALTY_MAX, round(penalty, 2)))
    if motive == "legitimate":
        penalty = 0.0  # 正当紧急不得额外扣点

    name = str(raw.get("penalty_attribute", "")).strip()
    if penalty <= 0:
        name = ""
    elif name not in ATTRIBUTE_DIMENSIONS_SET:
        name = DEFAULT_PENALTY_ATTRIBUTE

    return {
        "coin_cost": cost,
        "motive": motive,
        "motive_note": str(raw.get("motive_note", "")).strip(),
        "extra_penalty": penalty,
        "penalty_attribute": name,
    }


def _apply_extra_penalty(db: Session, user: User, row: Exemption) -> dict | None:
    """判为「明显逃避」时的额外属性扣点——**购买时立刻扣**（用户 2026-09-30 拍板）。

    属性写入统一走 `judge_service._clamp_attribute_value()`，并以**实际变动量**记账。
    （局部导入 judge_service：它在模块级 import 本模块，避免循环依赖。）
    """
    if row.extra_penalty is None or float(row.extra_penalty) <= 0:
        return None
    from app.services import judge_service  # 局部导入，避免与 judge_service 循环依赖

    name = row.penalty_attribute or DEFAULT_PENALTY_ATTRIBUTE
    attr = judge_service._ensure_attribute(db, user.id, name)
    before = attr.current_value
    after = round(judge_service._clamp_attribute_value(before - float(row.extra_penalty), attr.max_value), 2)
    actual = round(after - before, 2)
    if actual == 0:
        return None
    attr.current_value = after
    db.add(
        AttributeHistory(
            user_id=user.id,
            attribute_id=attr.id,
            event_id=None,
            judgment_id=None,
            delta=actual,
            value_after=after,
            reason=f"豁免券动机被判为「明显逃避」，额外扣点（券 #{row.id}）",
            evidence=row.motive_note or "",
        )
    )
    db.flush()
    return {"name": name, "delta": actual, "value_after": after}


def buy(
    db: Session,
    user: User,
    target_date: str,
    period: str,
    start_time: str = "",
    end_time: str = "",
    reason: str = "",
) -> dict:
    """购买一张豁免券：校验 → AI 定价与判动机 → 扣币（+ 可能的额外扣点）→ 落库。

    校验（**「万能券不可能」**）：
    - `target_date` 必须是合法日期，且**不能是过去的日期**；
    - 时段必须能解析（预设或合法自定义）；
    - 余额不足 → `ValueError`（400）。

    返回 `{"exemption": Exemption, "penalty": {...}|None, "balance": int}`。
    """
    try:
        target = _date.fromisoformat((target_date or "").strip())
    except ValueError as exc:
        raise ValueError("请指定合法的目标日期（YYYY-MM-DD）。") from exc
    if target < datetime.now().date():
        raise ValueError("豁免券只能为今天或之后的日期购买（过期作废，不能补买）。")

    key, start, end = resolve_period(period, start_time, end_time)

    messages = build_exemption_messages(
        target_date=target.isoformat(),
        period_label=PERIOD_PRESETS[key]["label"],
        start_time=start,
        end_time=end,
        reason=reason,
        attributes_context=_attributes_context(db, user.id),
        recent_memory=_long_term_memory(db, user.id),
        recent_events=_recent_events(db, user),
        economy_context=economy_service.snapshot(db, user),
        dimension_list="、".join(sorted(ATTRIBUTE_DIMENSIONS_SET)),
    )
    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_AUX)
    priced = _parse_pricing(llm_service.chat_json(messages, config=config))

    row = Exemption(
        user_id=user.id,
        target_date=target.isoformat(),
        period=key,
        start_time=start,
        end_time=end,
        reason=(reason or "").strip()[:500],
        coin_cost=priced["coin_cost"],
        motive=priced["motive"],
        motive_note=priced["motive_note"],
        extra_penalty=priced["extra_penalty"],
        penalty_attribute=priced["penalty_attribute"],
        status="active",
    )
    db.add(row)
    db.flush()

    # 金币：唯一写入口（余额不足会抛 InsufficientCoins，继承 ValueError）
    coin_service.grant(
        db,
        user,
        -row.coin_cost,
        source="exemption_purchase",
        reason=f"购买豁免券（{label_of(row)}）",
        ref_type="exemption",
        ref_id=row.id,
    )
    # 额外扣点：购买时立刻生效，并与 motive_note 一起展示给用户
    penalty = _apply_extra_penalty(db, user, row)

    db.commit()
    db.refresh(row)
    return {"exemption": row, "penalty": penalty, "balance": coin_service.balance(db, user)}


def list_for_user(db: Session, user: User, limit: int = 30) -> list[Exemption]:
    """券列表（倒序）。顺带做惰性过期。"""
    expire_stale(db, user)
    db.commit()
    return (
        db.query(Exemption)
        .filter(Exemption.user_id == user.id)
        .order_by(Exemption.created_at.desc(), Exemption.id.desc())
        .limit(limit)
        .all()
    )
