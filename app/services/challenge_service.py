"""挑战服务（v1.8）：AI 生成 → 接受（押金）→ 完成判定 → 结算 → 过期。

**一致性铁律**（v1.5 B-03 教训）：
- 金币只有 `coin_service.grant()` 一个写入口，押金/返还/没收/奖励全部走它
- 加点结算必须复用 `judge_service.confirm()`，属性解析必须复用
  `judge_service._parse_changes`，**禁止另写一套**
- 属性值写入统一走 `judge_service._clamp_attribute_value`（封顶 100 / 下限 0）
- **不存在任何"某类维度免扣"的逻辑**（v1.8 09-29 修正：分组方案已作废，13 维一律可涨可跌）

状态机：candidate → accepted → settled；candidate/accepted 过期 → expired；
        candidate/accepted 主动放弃 → abandoned（押金没收 + 按难度扣点）。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import AIJudgment, Challenge, Event, User
from app.prompts.challenge import build_challenge_messages, build_completion_messages
from app.services import coin_service, judge_service, llm_config
from app.services.llm_service import llm_service

# 候选数量（决策 5：日 3 个 / 周 2 个）
CANDIDATE_COUNT = {"daily": 3, "weekly": 2}

# 金币参数表（DEV_PLAN_v1.8 §四 B2，AI 必须按档取值）
# 结构：scope -> difficulty -> (coin_reward, deposit)
COIN_TABLE = {
    "daily": {1: (5, 5), 2: (8, 7), 3: (10, 10), 4: (13, 12), 5: (15, 15)},
    "weekly": {1: (30, 15), 2: (35, 20), 3: (40, 25), 4: (45, 30), 5: (50, 35)},
}

# 退缩（retreated）扣点上限与难度梯度（单次未完成不至于重罚）
RETREAT_DELTA_CAP = 1.5
RETAIN_OUTCOMES = ("done", "partial", "excused")  # 这三种都退押金
VALID_OUTCOMES = ("done", "partial", "excused", "retreated")


# ============ 周期计算 ============

def period_key(scope: str, now: datetime | None = None) -> str:
    """归属周期键：日=`2026-09-28`，周=`2026-W40`（用于过期与"每天换新"）。"""
    now = now or datetime.now()
    if scope == "weekly":
        iso = now.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return now.strftime("%Y-%m-%d")


def period_end(scope: str, now: datetime | None = None) -> datetime:
    """周期截止时间：日=当天 23:59:59；周=当周周日 23:59:59。"""
    now = now or datetime.now()
    if scope == "weekly":
        # weekday(): 周一=0 … 周日=6
        days_to_sunday = 6 - now.weekday()
        end = now + timedelta(days=days_to_sunday)
    else:
        end = now
    return end.replace(hour=23, minute=59, second=59, microsecond=0)


def coin_params(scope: str, difficulty: int) -> tuple[int, int]:
    """按参数表取 (coin_reward, deposit)。

    **以参数表为准**：AI 只负责给出 difficulty，金币数由本表派生，
    这样既满足"奖励随难度递增"，也杜绝模型自由发明数字。
    """
    table = COIN_TABLE.get(scope) or COIN_TABLE["daily"]
    d = max(1, min(5, int(difficulty or 1)))
    return table[d]


def retreat_magnitude(difficulty: int) -> float:
    """退缩扣点幅度：按难度等比（0.5 / 0.75 / 1.0 / 1.25 / 1.5），上限 1.5。"""
    d = max(1, min(5, int(difficulty or 1)))
    return min(RETREAT_DELTA_CAP, round(0.5 + 0.25 * (d - 1), 2))


# ============ 上下文 ============

def _attributes_context_with_weakness(db: Session, user_id: int) -> str:
    """属性上下文，并按**短板优先**排列（最低 3~5 维作为短板提示）。"""
    from app.models import Attribute

    attrs = (
        db.query(Attribute)
        .filter(Attribute.user_id == user_id)
        .order_by(Attribute.current_value.asc())
        .all()
    )
    if not attrs:
        return ""
    ordered = "、".join(f"{a.name} {a.current_value:.1f}" for a in attrs)
    weakest = "、".join(f"{a.name}（{a.current_value:.1f}）" for a in attrs[:5])
    return f"{ordered}\n【短板（数值最低的 5 维，请重点针对）】{weakest}"


def _existing_titles(db: Session, user_id: int, scope: str, pkey: str) -> list[str]:
    """本期已给过的全部挑战标题（防重复）。"""
    rows = (
        db.query(Challenge.title)
        .filter(
            Challenge.user_id == user_id,
            Challenge.scope == scope,
            Challenge.period_key == pkey,
        )
        .all()
    )
    return [r[0] for r in rows if r[0]]


# ============ B2 · 生成 ============

def generate(db: Session, user: User, scope: str = "daily", force: bool = False) -> list[Challenge]:
    """生成本期挑战候选（幂等）。

    - 非 force 且本期已有 candidate/accepted → 直接返回现有，**不重复调用 LLM**
    - force=True（"再来一批"）→ **仅对空缺位置补生成**，不覆盖进行中的挑战
    - `existing_titles` 含本期已给过的全部标题，避免重复
    """
    scope = "weekly" if scope == "weekly" else "daily"
    pkey = period_key(scope)
    target = CANDIDATE_COUNT[scope]

    existing = (
        db.query(Challenge)
        .filter(
            Challenge.user_id == user.id,
            Challenge.scope == scope,
            Challenge.period_key == pkey,
        )
        .order_by(Challenge.id.asc())
        .all()
    )
    active = [c for c in existing if c.status in ("candidate", "accepted")]

    if not force and active:
        return existing  # 幂等：本期已有候选，不再调用 LLM

    need = target - len(active)
    if need <= 0:
        return existing  # force 但位置已满 → 不动进行中的挑战

    messages = build_challenge_messages(
        scope=scope,
        count=need,
        profile_context=judge_service._profile_context(db, user.id),
        attributes_context=_attributes_context_with_weakness(db, user.id),
        recent_events=judge_service._recent_events_context(db, user.id, exclude_event_id=0),
        recent_memory=_long_term_memory(db, user.id),
        existing_titles=_existing_titles(db, user.id, scope, pkey),
    )

    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_AUX)
    result = llm_service.chat_json(messages, config=config)
    raw_list = result.get("challenges") or []

    expires = period_end(scope)
    created: list[Challenge] = []
    for item in raw_list[:need]:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        difficulty = max(1, min(5, int(item.get("difficulty") or 1)))
        reward, deposit = coin_params(scope, difficulty)
        related = [
            judge_service._normalize_attribute_name(str(n))
            for n in (item.get("related_attributes") or [])
        ]
        related = [r for r in related if r]
        row = Challenge(
            user_id=user.id,
            scope=scope,
            period_key=pkey,
            title=title[:120],
            description=str(item.get("description", "")).strip(),
            difficulty=difficulty,
            coin_reward=reward,
            deposit=deposit,
            related_attributes=related,
            ai_reason=str(item.get("reason", "")).strip(),
            status="candidate",
            expires_at=expires,
        )
        db.add(row)
        created.append(row)

    db.commit()
    for row in created:
        db.refresh(row)
    return existing + created


def _long_term_memory(db: Session, user_id: int) -> str:
    """读取用户长期记忆摘要（可选上下文）。"""
    from app.models import UserProfile

    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None or not profile.long_term_memory:
        return ""
    return str(profile.long_term_memory)[:1200]


# ============ B3-1 · 接受（扣押金） ============

def accept(db: Session, user: User, challenge: Challenge) -> Challenge:
    """接受挑战：校验状态与余额 → 扣押金 → 置 accepted 并重设截止时间。"""
    if challenge.status != "candidate":
        raise ValueError(f"该挑战当前状态为 {challenge.status}，无法接受。")
    now = datetime.now()
    if challenge.expires_at and challenge.expires_at < now:
        raise ValueError("该挑战已过期，请刷新后接受新挑战。")

    balance = coin_service.balance(db, user)
    if balance < challenge.deposit:
        raise ValueError(
            f"金币不足（需 {challenge.deposit} 币，当前 {balance} 币）。"
            "可以先记录日常事件或写日记攒币。"
        )

    coin_service.grant(
        db,
        user,
        -challenge.deposit,
        source="challenge_deposit",
        reason=f"接受挑战「{challenge.title}」押金",
        ref_type="challenge",
        ref_id=challenge.id,
    )
    challenge.status = "accepted"
    challenge.accepted_at = now
    # 重设为周期末：日挑战当天 23:59:59；周挑战当周周日 23:59:59
    challenge.expires_at = period_end(challenge.scope, now)
    db.commit()
    db.refresh(challenge)
    return challenge


# ============ B3-2 · 完成（一次 LLM 判定） ============

def _apply_outcome_changes(
    changes: list[dict], outcome: str, challenge: Challenge
) -> list[dict]:
    """按 outcome 调整 AI 给出的加点建议。

    - done      → 原样
    - partial   → 每条 delta × 0.5，取整到 0.5（加点 ≤ 标准的一半）
    - excused   → 清空（不加点不扣点）
    - retreated → delta 取负值，幅度按难度等比、上限 1.5（**全维度可扣，无分组限制**）
    """
    if outcome == "done":
        return changes
    if outcome == "excused":
        return []
    if outcome == "partial":
        out = []
        for c in changes:
            half = round(float(c.get("delta", 0)) * 0.5 * 2) / 2  # 取整到 0.5
            if half == 0:
                continue
            out.append({**c, "delta": half})
        return out
    # retreated
    magnitude = retreat_magnitude(challenge.difficulty)
    names = [c.get("name") for c in changes if c.get("name")] or list(
        challenge.related_attributes or []
    ) or ["规划力"]
    seen = set()
    out = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        out.append(
            {
                "name": name,
                "delta": -magnitude,
                "reason": f"挑战「{challenge.title}」未完成（临时退缩）",
                "evidence": "自我调节学习：接受承诺后未兑现，反映规划执行力与承诺一致性不足。",
            }
        )
    return out


def complete(db: Session, user: User, challenge: Challenge, note: str) -> dict:
    """用户自报完成情况 → 一次 LLM 调用判定 outcome 与加点 → 生成待确认判定。

    不在此处入账（遵守"AI 建议 → 用户确认 → 才入账"）；结算见 `settle`。
    """
    if challenge.status != "accepted":
        raise ValueError(f"该挑战当前状态为 {challenge.status}，无法提交完成。")
    if challenge.judgment_id:
        raise ValueError("该挑战已完成判定，请在下方确认结算。")

    # 1. 创建记录（复用判定链路；params 的 "_" 前缀键会被 format_event_description 跳过）
    event = Event(
        user_id=user.id,
        event_type="positive",
        category="目标",
        source="form",
        title=f"挑战：{challenge.title}",
        content=note or "",
        params={"_challenge_id": challenge.id},
        occurred_at=datetime.now(),
    )
    db.add(event)
    db.flush()

    # 2. 一次 LLM 调用同时拿 outcome 与加点
    messages = build_completion_messages(
        challenge_title=challenge.title,
        challenge_description=challenge.description,
        challenge_attributes=list(challenge.related_attributes or []),
        note=note,
        today_events_context=judge_service._today_events_context(db, user.id, exclude_event_id=event.id),
    )
    config = llm_config.resolve_llm_config(db, user.id, llm_config.PURPOSE_JUDGE)
    result = llm_service.chat_json(messages, config=config)

    outcome = str(result.get("outcome", "")).strip()
    if outcome not in VALID_OUTCOMES:
        outcome = "retreated"  # 无法识别 → 保守按未完成处理（不给奖励）
    explanation = str(result.get("explanation", "")).strip()
    confidence = result.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.85

    # 3. 复用主判定链路的解析（禁止另写一套）
    changes = judge_service._parse_changes(result.get("affected_attributes") or [])
    changes = _apply_outcome_changes(changes, outcome, challenge)

    # 4. 落一条待确认判定
    judgment = AIJudgment(
        event_id=event.id,
        user_id=user.id,
        suggested_changes=changes,
        analysis=[explanation] if explanation else [],
        summary=str(result.get("summary", "")).strip(),
        confidence=confidence,
        confidence_reason=str(result.get("confidence_reason", "") or ""),
        status="pending",
    )
    db.add(judgment)
    db.flush()

    challenge.event_id = event.id
    challenge.judgment_id = judgment.id
    challenge.outcome = outcome
    challenge.outcome_note = explanation
    db.commit()

    judge_service._log(
        db, judgment.id, user.id, "create",
        detail=f"挑战「{challenge.title}」完成判定（{outcome}）",
        payload={"challenge_id": challenge.id, "outcome": outcome, "note": note},
    )
    db.refresh(judgment)
    db.refresh(challenge)

    return {
        "challenge_id": challenge.id,
        "judgment_id": judgment.id,
        "outcome": outcome,
        "explanation": explanation,
        "confidence": confidence,
        "suggested_changes": changes,
        "summary": judgment.summary,
    }


# ============ B3-3 · 结算 ============

def settle(db: Session, user: User, challenge: Challenge, final_status: str = "settled") -> dict:
    """确认结算：加点（复用 judge_service.confirm）+ 押金/奖励发放。

    `final_status` 用于区分「正常结算」(settled) 与「放弃后结算」(abandoned)，
    两者在钱与点上的处理完全一致（excused 退押金 / retreated 没收）。
    """
    if challenge.status != "accepted":
        raise ValueError(f"该挑战当前状态为 {challenge.status}，无法结算。")
    if not challenge.judgment_id:
        raise ValueError("该挑战还没有完成判定，请先提交自述。")

    judgment = db.get(AIJudgment, challenge.judgment_id)
    if judgment is None:
        raise ValueError("挑战的判定记录不存在。")
    if judgment.status == "confirmed":
        raise ValueError("该挑战已结算，请勿重复操作。")

    outcome = challenge.outcome or "retreated"
    coins_delta = 0

    # 1. 加点：**必须复用** judge_service.confirm（置信度加权 + 低置信度拦截 + 封顶）
    applied_changes: list[dict] = []
    if judgment.suggested_changes:
        try:
            judge_service.confirm(db, judgment)
            applied_changes = judgment.final_changes or []
        except ValueError:
            # 置信度不足等：不加点，但结算流程照常（不卡住押金与金币）
            judgment.status = "adjusted"
            db.commit()
    else:
        # 无加点（excused 等）：直接标记为已确认，避免留下悬空 pending 判定
        judgment.status = "confirmed"
        judgment.final_changes = []
        db.commit()

    # 2. 押金 / 金币
    if outcome in RETAIN_OUTCOMES:
        coin_service.grant(
            db, user, challenge.deposit,
            source="challenge_refund",
            reason=f"完成挑战「{challenge.title}」，退回押金",
            ref_type="challenge", ref_id=challenge.id,
        )
        coins_delta += challenge.deposit
        if outcome == "done":
            coin_service.grant(
                db, user, challenge.coin_reward,
                source="challenge_reward",
                reason=f"完成挑战「{challenge.title}」奖励",
                ref_type="challenge", ref_id=challenge.id,
            )
            coins_delta += challenge.coin_reward
    else:
        # retreated：押金在 accept 时已扣，此处仅写一条 0 值留痕说明
        coin_service.grant(
            db, user, 0,
            source="challenge_forfeit",
            reason=f"挑战「{challenge.title}」未完成，押金不退",
            ref_type="challenge", ref_id=challenge.id,
        )

    challenge.status = final_status
    challenge.resolved_at = datetime.now()
    db.commit()
    db.refresh(challenge)

    return {
        "challenge_id": challenge.id,
        "outcome": outcome,
        "explanation": challenge.outcome_note,
        "coins_delta": coins_delta,
        "balance": coin_service.balance(db, user),
        "applied_changes": applied_changes,
    }


# ============ B3-4 · 放弃 ============

def _make_retreat_judgment(db: Session, user: User, challenge: Challenge, note_text: str) -> AIJudgment:
    """构造一条「按 retreated 处理」的待结算判定（无 LLM）。"""
    magnitude = retreat_magnitude(challenge.difficulty)
    names = list(challenge.related_attributes or []) or ["规划力"]
    changes = [
        {
            "name": n,
            "delta": -magnitude,
            "reason": f"挑战「{challenge.title}」未完成",
            "evidence": "自我调节学习：接受承诺后未兑现，反映承诺一致性与执行力不足。",
        }
        for n in dict.fromkeys(names)
    ]
    event = Event(
        user_id=user.id, event_type="negative", category="目标", source="form",
        title=f"挑战：{challenge.title}", content=note_text,
        params={"_challenge_id": challenge.id}, occurred_at=datetime.now(),
    )
    db.add(event)
    db.flush()
    judgment = AIJudgment(
        event_id=event.id, user_id=user.id, suggested_changes=changes,
        analysis=[note_text],
        summary=f"挑战「{challenge.title}」未完成。", confidence=1.0, status="pending",
    )
    db.add(judgment)
    db.flush()
    challenge.event_id = event.id
    challenge.judgment_id = judgment.id
    challenge.outcome = "retreated"
    challenge.outcome_note = note_text
    db.commit()
    judge_service._log(
        db, judgment.id, user.id, "create",
        detail=f"挑战「{challenge.title}」未完成（retreated）",
        payload={"challenge_id": challenge.id, "outcome": "retreated"},
    )
    return judgment


def abandon(db: Session, user: User, challenge: Challenge, note: str = "") -> dict:
    """主动放弃。

    - 带 note → 走与完成相同的 LLM 判定，允许 excused（正当理由 → **押金全额退回**）
      或 retreated（没收押金 + 扣点）
    - 不带 note → **直接按 retreated** 处理（不调用 LLM），outcome_note=「用户主动放弃」

    两条路径最终都走同一套 `settle`（final_status='abandoned'），保证钱与点的
    处理语义只有一处实现。
    """
    if challenge.status != "accepted":
        raise ValueError(f"该挑战当前状态为 {challenge.status}，无法放弃。")

    if note and note.strip():
        result = complete(db, user, challenge, note)
        settled = settle(db, user, challenge, final_status="abandoned")
        return {**result, **settled}

    # 不带说明：直接 retreated，无需 LLM
    _make_retreat_judgment(db, user, challenge, "用户主动放弃")
    db.refresh(challenge)
    return settle(db, user, challenge, final_status="abandoned")


# ============ B3-5 · 过期（惰性结算，无需 LLM，幂等） ============

def expire_stale(db: Session, user: User) -> int:
    """把已过期的挑战置为 expired；accepted 过期的同时完成结算（幂等）。

    - candidate 过期 → 仅置 expired（押金尚未扣除，无需任何结算）
    - accepted 过期 → 押金没收 + 按难度扣点（走 retreated 同一套）
    - 以状态判断实现幂等：已 expired/settled/abandoned 的不再处理
    """
    now = datetime.now()
    rows = (
        db.query(Challenge)
        .filter(
            Challenge.user_id == user.id,
            Challenge.status.in_(("candidate", "accepted")),
            Challenge.expires_at.isnot(None),
            Challenge.expires_at < now,
        )
        .all()
    )
    for ch in rows:
        if ch.status == "candidate":
            ch.status = "expired"
            ch.resolved_at = now
            ch.outcome = ""
            ch.outcome_note = "候选期结束，未接受"
            db.commit()
            continue
        # accepted 过期 → 押金没收 + 按难度扣点（走 retreated 同一套）
        _make_retreat_judgment(db, user, ch, "到期未完成")
        db.refresh(ch)
        try:
            settle(db, user, ch, final_status="expired")
        except ValueError:
            # 结算过程异常不应阻塞过期状态推进
            ch.status = "expired"
            ch.resolved_at = now
            db.commit()

    return len(rows)


def list_challenges(db: Session, user: User, scope: str | None = None) -> list[Challenge]:
    """列出挑战（先惰性过期结算，再返回；按 scope 过滤可选）。"""
    expire_stale(db, user)
    q = db.query(Challenge).filter(Challenge.user_id == user.id)
    if scope:
        q = q.filter(Challenge.scope == scope)
    return q.order_by(Challenge.id.desc()).all()


def current_period(db: Session, user: User) -> dict:
    """本期（日/周）挑战概览，供前端分组展示。"""
    expire_stale(db, user)
    result: dict[str, list[Challenge]] = {}
    for scope in ("daily", "weekly"):
        pkey = period_key(scope)
        rows = (
            db.query(Challenge)
            .filter(
                Challenge.user_id == user.id,
                Challenge.scope == scope,
                Challenge.period_key == pkey,
            )
            .order_by(Challenge.id.asc())
            .all()
        )
        result[scope] = rows
    return result
