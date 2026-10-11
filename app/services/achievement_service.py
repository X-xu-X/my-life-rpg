"""成就服务（v1.10 M1）。

两类成就：
- **累计型 `cumulative`**：按规则自动统计发放。检查时机是**搭便车**——在既有的
  「事件确认入账 / 提交日记 / 挑战结算」之后顺带调一次 `check_and_grant()`，
  **不新增定时任务、不新增独立调度**。
- **AI 发现型 `discovered`**：主判定引擎认为用户达成值得纪念的里程碑时给出**建议**，
  前端展示追授卡，**必须用户确认后才发放**（`grant_discovered()`）。

两条硬约束（用户 2026-09-28 访谈确认）：
1. **奖励只发金币 + 徽章，不发属性点**——保持"点数只能靠真实行为挣"。
2. **每个成就只能解锁一次**——以 `(user_id, code)` 唯一约束 + 先查后写保证幂等。

金币入账一律走 `coin_service.grant(source='achievement')`（该 source 早已预留）。
"""
from app.services.time_service import clock_now
from datetime import datetime
from re import sub as re_sub

from sqlalchemy.orm import Session

from app.models import Achievement, Challenge, Event, Redemption, User
from app.services import coin_service

# 累计型成就目录。
# metric 取值见 _metrics()；target 为达标阈值。**成就只发金币，不发属性点。**
CATALOG: list[dict] = [
    {
        "code": "journal_total_7", "name": "日记 7 篇", "icon": "📝",
        "description": "累计写下 7 篇日记。", "coin_reward": 15,
        "metric": "journal_total", "target": 7,
    },
    {
        "code": "journal_total_30", "name": "日记 30 篇", "icon": "📝",
        "description": "累计写下 30 篇日记。", "coin_reward": 40,
        "metric": "journal_total", "target": 30,
    },
    {
        "code": "journal_total_100", "name": "日记 100 篇", "icon": "📚",
        "description": "累计写下 100 篇日记。", "coin_reward": 100,
        "metric": "journal_total", "target": 100,
    },
    {
        "code": "journal_streak_7", "name": "连续写日记 7 天", "icon": "🔥",
        "description": "连续 7 天每天写一篇日记。", "coin_reward": 30,
        "metric": "journal_streak", "target": 7,
    },
    {
        "code": "journal_streak_30", "name": "连续写日记 30 天", "icon": "🔥",
        "description": "连续 30 天每天写一篇日记。", "coin_reward": 100,
        "metric": "journal_streak", "target": 30,
    },
    {
        "code": "events_total_50", "name": "记录累计 50 条", "icon": "🗂️",
        "description": "累计记录 50 条生活事件。", "coin_reward": 30,
        "metric": "events_total", "target": 50,
    },
    {
        "code": "events_total_200", "name": "记录累计 200 条", "icon": "🗂️",
        "description": "累计记录 200 条生活事件。", "coin_reward": 120,
        "metric": "events_total", "target": 200,
    },
    {
        "code": "challenge_done_1", "name": "首次完成挑战", "icon": "✅",
        "description": "第一次完成一个挑战。", "coin_reward": 10,
        "metric": "challenge_done", "target": 1,
    },
    {
        "code": "challenge_done_10", "name": "完成挑战 10 次", "icon": "🏆",
        "description": "累计完成 10 个挑战。", "coin_reward": 50,
        "metric": "challenge_done", "target": 10,
    },
    {
        "code": "challenge_done_50", "name": "完成挑战 50 次", "icon": "👑",
        "description": "累计完成 50 个挑战。", "coin_reward": 200,
        "metric": "challenge_done", "target": 50,
    },
    {
        "code": "first_redemption", "name": "首次兑换奖励", "icon": "🎁",
        "description": "第一次把金币换成现实中的小奖励。", "coin_reward": 10,
        "metric": "redemptions", "target": 1,
    },
]
CATALOG_BY_CODE = {c["code"]: c for c in CATALOG}


def _metrics(db: Session, user: User) -> dict[str, int]:
    """一次性算出全部累计指标（避免逐个成就各查一遍）。"""
    journal_total = (
        db.query(Event)
        .filter(Event.user_id == user.id, Event.is_deleted.is_(False), Event.source == "journal")
        .count()
    )
    events_total = db.query(Event).filter(Event.user_id == user.id, Event.is_deleted.is_(False)).count()
    challenge_done = (
        db.query(Challenge)
        .filter(
            Challenge.user_id == user.id,
            Challenge.status == "settled",
            Challenge.outcome == "done",
        )
        .count()
    )
    redemptions = db.query(Redemption).filter(Redemption.user_id == user.id).count()
    return {
        "journal_total": journal_total,
        "journal_streak": coin_service._journal_days(db, user),
        "events_total": events_total,
        "challenge_done": challenge_done,
        "redemptions": redemptions,
    }


def _unlocked_map(db: Session, user: User) -> dict[str, Achievement]:
    rows = db.query(Achievement).filter(Achievement.user_id == user.id).all()
    return {a.code: a for a in rows if a.unlocked_at is not None}


def wall(db: Session, user: User) -> dict:
    """成就墙数据：全部目录条目 + 解锁状态 + 进度（供角色档案页展示）。

    未解锁的返回 `current/target` 供前端显示"日记 12/30 篇"（纯展示，不做进度条动画）。
    """
    metrics = _metrics(db, user)
    unlocked = _unlocked_map(db, user)
    items = []
    for c in CATALOG:
        cur = int(metrics.get(c["metric"], 0))
        row = unlocked.get(c["code"])
        items.append(
            {
                "code": c["code"],
                "name": c["name"],
                "description": c["description"],
                "icon": c["icon"],
                "coin_reward": c["coin_reward"],
                "kind": "cumulative",
                "unlocked": row is not None,
                "unlocked_at": row.unlocked_at if row else None,
                "current": min(cur, c["target"]),
                "target": c["target"],
            }
        )
    # AI 发现型（追授）的已解锁项也一起返回，便于同一面墙展示
    for code, row in unlocked.items():
        if code in CATALOG_BY_CODE:
            continue
        items.append(
            {
                "code": code,
                "name": row.name,
                "description": row.description,
                "icon": row.icon,
                "coin_reward": row.coin_reward,
                "kind": row.kind,
                "unlocked": True,
                "unlocked_at": row.unlocked_at,
                "current": 1,
                "target": 1,
            }
        )
    items.sort(key=lambda x: (not x["unlocked"], x["kind"] != "cumulative", x["target"]))
    return {
        "items": items,
        "unlocked_count": sum(1 for i in items if i["unlocked"]),
        "total_count": len(items),
        "balance": coin_service.balance(db, user),
    }


def check_and_grant(db: Session, user: User) -> list[Achievement]:
    """累计型成就检查（**幂等**）：命中未解锁的成就就发金币 + 落库。

    - 由「事件确认入账 / 提交日记 / 挑战结算」之后**顺带调用**（不新增定时任务）
    - 以 `(user_id, code)` 是否已有解锁行判断幂等，**重复调用不会重复发放**
    - 金币走 `coin_service.grant(source='achievement')`
    - **本函数内部 commit**（它是流程末端的副作用操作，调用方无需再管事务）

    返回本次新解锁的成就列表（无则空）。
    """
    metrics = _metrics(db, user)
    unlocked = _unlocked_map(db, user)
    newly: list[Achievement] = []

    for c in CATALOG:
        if c["code"] in unlocked:
            continue
        if int(metrics.get(c["metric"], 0)) < c["target"]:
            continue
        row = Achievement(
            user_id=user.id,
            code=c["code"],
            name=c["name"],
            description=c["description"],
            icon=c["icon"],
            kind="cumulative",
            coin_reward=c["coin_reward"],
            unlocked_at=clock_now(),
        )
        db.add(row)
        db.flush()
        if c["coin_reward"] > 0:
            coin_service.grant(
                db,
                user,
                c["coin_reward"],
                source="achievement",
                reason=f"解锁成就「{c['name']}」",
                ref_type="achievement",
                ref_id=row.id,
            )
        newly.append(row)

    if newly:
        db.commit()
        for row in newly:
            db.refresh(row)
    return newly


def _slug(text: str) -> str:
    """把中文/符号成就名压成可用作 code 后缀的短串（保证非空）。"""
    s = re_sub(r"[\s\-—·、，。：:；;（）()【】\[\]「」\"'`]+", "_", (text or "").strip())
    s = s.strip("_")
    return s[:40] or "milestone"


def grant_discovered(db: Session, user: User, name: str, reason: str = "", *, commit: bool = True) -> Achievement:
    """追授 AI 发现型成就（**必须已获用户确认**，由路由层保证）。

    `code = discovered_<slug>`；若同名已存在则直接返回既有行（幂等，不重复发币）。
    """
    code = f"discovered_{_slug(name)}"
    exist = (
        db.query(Achievement)
        .filter(Achievement.user_id == user.id, Achievement.code == code)
        .first()
    )
    if exist is not None:
        return exist

    # 追授奖励按"里程碑"量级固定给 50 币（不随内容浮动，避免模型自由发明金额）
    reward = 50
    row = Achievement(
        user_id=user.id,
        code=code,
        name=(name or "里程碑")[:100],
        description=reason or "AI 认为这是一个值得纪念的里程碑。",
        icon="🎖",
        kind="discovered",
        coin_reward=reward,
        unlocked_at=clock_now(),
    )
    db.add(row)
    db.flush()
    coin_service.grant(
        db,
        user,
        reward,
        source="achievement",
        reason=f"追授成就「{row.name}」",
        ref_type="achievement",
        ref_id=row.id,
    )
    if commit:
        db.commit()
        db.refresh(row)
    return row


# ============ 判定链路里的「AI 发现型」建议 ============

def parse_suggestion(raw) -> dict:
    """解析主判定返回的 `achievement_suggestion`（可选字段）。

    无建议 / 结构非法 / name 为空 → 返回 `{}`（不落库、前端不显示）。
    """
    if not isinstance(raw, dict):
        return {}
    name = str(raw.get("name", "")).strip()
    if not name:
        return {}
    return {
        "name": name[:100],
        "reason": str(raw.get("reason", "")).strip(),
        "state": "pending",
    }
