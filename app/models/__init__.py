"""数据模型（SQLAlchemy ORM，共 17 张核心表）。

对应 PRD 6.3 节：users / user_profiles / attributes / attribute_history /
events / ai_judgments / judgment_logs / goals / anchors / settings。
v1.7 新增：checkin_items（打卡项目，用户自建）。
v1.8 新增：coin_ledger（金币流水）/ challenges（挑战）/ shop_items（商店物品）/
          redemptions（兑换券）。
v1.10 新增：achievements（成就）/ exemptions（豁免券）。
         另给 attributes 加 parent_id（v1.10 M3 子维度层级）。

设计原则：
- 所有业务表外键关联 user_id，V1 单用户、M4 多用户平滑扩展。
- 属性值、增减量使用 Float，支持 -0.5 这类小数增减（如熬夜 -0.5）。
- 结构化数据（画像、建议增减、事件参数）用 JSON 类型，SQLite 自动序列化。
- 表结构已预留 MySQL/PostgreSQL 迁移（类型均为通用类型）。
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    BigInteger,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.time_types import DateTime,UTCDateTime
from app.services.time_service import clock_now


def _now() -> datetime:
    """统一的时间戳生成（本地时区，个人自用场景更直观）。"""
    return clock_now()


class User(Base):
    """用户表。V1 单用户，启动时自动创建 default 用户。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    role: Mapped[str] = mapped_column(String(10), default="user")
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Shanghai")
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    credentials_version: Mapped[int] = mapped_column(Integer, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False)


class UserProfile(Base):
    """用户画像：基础信息 + AI 生成的初始属性快照 + 游戏化字段（预留）。"""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    # 基础画像：身高体重、专业、作息等（Onboarding 问答沉淀）
    basic_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    # 初始属性面板快照（AI 生成，每项含分值 + 推导依据）
    initial_attributes_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    # 首次引导是否完成（一次性约束：完成后只能补充长期信息，不可重新走引导）
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    baseline_kind: Mapped[str] = mapped_column(String(30), default="legacy")
    # 进行中的首次引导会话态（对话历史/当前问题/把握度），持久化，离开或重启不丢
    onboarding_state: Mapped[dict] = mapped_column(JSON, default=dict)
    # 补充长期信息后、待用户确认的属性调整建议
    pending_adjustment: Mapped[dict] = mapped_column(JSON, default=dict)
    # 游戏化字段（M3 实现曲线逻辑，此处预留）
    level: Mapped[int] = mapped_column(Integer, default=1)
    exp: Mapped[float] = mapped_column(Float, default=0.0)
    # 金币余额（v1.8）。唯一写入口是 coin_service.grant()，任何地方不得直接改此列。
    # 与属性点完全隔离（金币不能换点数）；负面事件不扣金币，避免双重惩罚。
    coins: Mapped[int] = mapped_column(BigInteger, default=0)
    # 长期记忆（智能体式）：LLM 压缩历史事件成的五类摘要（长期目标/关键经历/性格/偏好/当前状态），JSON 字符串
    long_term_memory: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    memory_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    user: Mapped["User"] = relationship(back_populates="profile")


class Attribute(Base):
    """属性定义 + 当前值。内置 6 个标准维度（见 DECISIONS.md D5）。

    v1.10（M3）：支持**层级**——`parent_id` 为 NULL 即主维度（既有 13 维全为 NULL，行为不变）；
    非空即某主维度的**子维度**（独立 0~100 累积，不影响主维度数值）。
    子维度**由用户确认后才创建**（AI 只提议），提议内容落在 `sub_proposal`。
    """

    __tablename__ = "attributes"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_attribute_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # 体能/智力/情商/创造力/规划力/健康
    description: Mapped[str] = mapped_column(Text, default="")
    attr_type: Mapped[str] = mapped_column(String(50), default="")  # physical/mental/social/...
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    max_value: Mapped[float] = mapped_column(Float, default=100.0)
    # v1.10 M3：父维度。NULL = 主维度；非空 = 子维度（指向主维度行）
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("attributes.id"), nullable=True)
    # v1.10 M3：子维度提议（{state: pending|accepted|dismissed, items:[{name, description}], at}）。
    # **只提议不自动创建**——用户勾选确认后才落库为真正的子维度行。
    sub_proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_sources: Mapped[list | None] = mapped_column(JSON,nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class AttributeHistory(Base):
    """属性值变更流水。每次点数变动记录：时间 / 事件 / 增减量 / 依据。"""

    __tablename__ = "attribute_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attributes.id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    judgment_id: Mapped[int | None] = mapped_column(ForeignKey("ai_judgments.id"), nullable=True)
    delta: Mapped[float] = mapped_column(Float, nullable=False)  # 增减量，正负皆可
    value_after: Mapped[float] = mapped_column(Float, nullable=False)  # 变动后的属性值
    reason: Mapped[str] = mapped_column(Text, default="")  # AI 给出的原因
    evidence: Mapped[str] = mapped_column(Text, default="")  # 科学依据
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CheckinItem(Base):
    """打卡项目（v1.7，用户自建，系统不预置任何项目）。

    打卡体系的核心：用户先定义"我每天/每周要盯的事"（跑步、背单词、久坐…），
    记录事件时选一个项目 + 写正文，而非填固定三件套（时长/距离/强度）。

    nature 四类：
    - planned  规划内（必做，未完成不单独扣分，进度页面如实提示）
    - optional 可选（不机械加分，AI 视"是否额外主动投入"判断）
    - negative 负面（每次出现都减分，绝不去重）
    - other    其他/杂项兜底

    停用不删除（enabled=False）：历史事件仍引用它，删了会让老记录丢失名称。
    """

    __tablename__ = "checkin_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 项目名，如"晨跑""背单词""久坐"
    nature: Mapped[str] = mapped_column(String(20), default="other")  # planned/optional/negative/other
    frequency_type: Mapped[str] = mapped_column(String(20), default="none")  # daily/weekly/none
    frequency_target: Mapped[int] = mapped_column(Integer, default=0)  # weekly 时的每周目标次数
    category: Mapped[str] = mapped_column(String(50), default="")  # 生活面：学习/运动/作息/社交/饮食/情绪/其他
    related_attribute: Mapped[str] = mapped_column(String(50), default="")  # 主要影响的属性维度（可空）
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id"), nullable=True)  # 关联目标（可空）
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # 停用不删除，保留历史引用
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # 手工排序
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Event(Base):
    """生活事件。类型 positive/negative/goal，来源 form/journal。

    v1.7：新增 item_id 关联打卡项目。老事件该列为 NULL（正常），
    所有下游逻辑必须容忍 NULL（项目上下文块整块跳过）。
    """

    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("user_id", "client_request_id", name="uq_event_submission"),)
    record_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    diary_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    ai_permission: Mapped[str] = mapped_column(String(12), default='private')
    ai_permission_version: Mapped[int] = mapped_column(Integer, default=1)
    ai_permission_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    economy_version: Mapped[str | None] = mapped_column(String(30),nullable=True)
    client_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    analysis_intent: Mapped[str] = mapped_column(String(10), default="legacy")
    timezone_at_capture: Mapped[str] = mapped_column(String(60), default="Asia/Shanghai")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # positive/negative/goal
    category: Mapped[str] = mapped_column(String(50), default="")  # 锻炼/学习/作息/社交/饮食/理财...
    source: Mapped[str] = mapped_column(String(20), default="form")  # form/journal
    title: Mapped[str] = mapped_column(String(200), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)  # 结构化参数（时长/距离/配速/强度...）
    content: Mapped[str] = mapped_column(Text, default="")  # 用户手写正文（打卡正文 / 日记原文）
    # v1.7：所属打卡项目（可空——老数据一律 NULL，下游必须容忍）
    item_id: Mapped[int | None] = mapped_column(ForeignKey("checkin_items.id"), nullable=True)
    # 纯享版记录：True 表示只记录不加点、不走 AI 判定（生活手账）
    is_pure: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    # v1.9（F5）：事件来源标记。None=普通记录（默认，老数据一律 NULL）；
    # "challenge"=挑战结算生成。**只由 challenge_service 的两处写入**，
    # 用户录入的事件永远不可能是挑战来源（EventCreate 不提供该字段）。
    origin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_now)  # 事件发生时间
    saved_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    saved_timezone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    occurred_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    time_precision: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AIJudgment(Base):
    """AI 判定记录。状态：pending/confirmed/adjusted/rejected。"""

    __tablename__ = "ai_judgments"
    source_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # AI 原始建议增减：[{name, delta, reason, evidence}]
    suggested_changes: Mapped[list] = mapped_column(JSON, default=list)
    # AI 分析过程（推理链路：要素解析 → 锚点比对 → 加权推导），v1.1 新增
    analysis: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")  # AI 判定总结
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 置信度 0~1
    # 置信度说明（v1.4）：confidence < 0.95 时 AI 必填——哪里不确定/缺什么信息/建议补充什么
    confidence_reason: Mapped[str] = mapped_column(Text, default="")
    # 本次修订说明（v1.6）：重判时逐条说明改了什么（新增/撤销/调整），无修订为 []
    revision_notes: Mapped[list] = mapped_column(JSON, default=list)
    # 跨来源合并明细（v1.7）：[{ref, note}]，与当天/近期记录是同一件事时列出；无合并为 []
    merged_with: Mapped[list] = mapped_column(JSON, default=list)
    model_provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # AI 发现型成就建议（v1.10 M1）：{name, reason, state}。
    # state ∈ pending/granted/dismissed；无建议为 {}。
    # **必须用户确认后才发放**（不自动发），所以需要落库以便刷新后仍可操作。
    achievement_suggestion: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/confirmed/adjusted/rejected
    # 最终生效的增减（反驳/补充后可能调整），确认入账时写入
    final_changes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class JudgmentLog(Base):
    """判定审计日志。记录确认/补充/反驳/复核全过程，保证可回溯。"""

    __tablename__ = "judgment_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    judgment_id: Mapped[int] = mapped_column(ForeignKey("ai_judgments.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)  # create/confirm/supplement/dispute/rejudge
    detail: Mapped[str] = mapped_column(Text, default="")  # 操作说明/用户备注
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # 结构化载荷（补充信息/反驳理由/复核结果）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Goal(Base):
    """目标。设定→达成奖励/到期扣点，修改取消记审计。"""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")  # 目标描述
    metric: Mapped[str] = mapped_column(String(200), default="")  # 量化指标，如"本月跑步累计50km"
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 期限
    related_attribute: Mapped[str] = mapped_column(String(50), default="")  # 关联属性
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/achieved/failed/cancelled
    reward: Mapped[float] = mapped_column(Float, default=2.0)  # 达成奖励点数
    penalty: Mapped[float] = mapped_column(Float, default=-1.0)  # 未达成扣点
    # 操作审计：修改/取消/达成/失败的流水记录 [{action, detail, created_at}]
    audit: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Anchor(Base):
    """量化锚点库。内置标准事件基准表，用户可校准。

    base_value 为基准量（如 30 表示 30 分钟），unit 为单位（分钟/小时/次）。
    calibrated_value 为用户校准后的基准量（NULL 表示未校准，使用 base_value）。

    v1.8 升级（A2-2）：单属性 → **多属性 + 强度分档**。
    - `targets` 非空时**以它为准**，忽略旧的 `target_attribute` / `base_delta`；
      `targets IS NULL` 的老锚点仍按单属性处理，行为与升级前完全一致。
    - `intensity_note` 为人可读的强度梯度指引，直接注入 prompt。
    """

    __tablename__ = "anchors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 标准事件名
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="")  # 锻炼/学习/作息/目标
    target_attribute: Mapped[str] = mapped_column(String(50), default="")  # 影响属性（单属性，兼容保留）
    base_value: Mapped[float] = mapped_column(Float, default=0.0)  # 基准量
    unit: Mapped[str] = mapped_column(String(20), default="")  # 单位
    base_delta: Mapped[float] = mapped_column(Float, default=0.0)  # 基准增减点数（单属性，兼容保留）
    # v1.8 多属性目标：[{"name": "健康", "base_delta": -0.5}, {"name": "智力", "base_delta": -0.4}]
    targets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # v1.8 强度梯度指引（人类可读，注入 prompt）
    intensity_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="")  # 科学依据（ACSM 指南/学习科学/睡眠研究）
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True)
    calibrated_value: Mapped[float | None] = mapped_column(Float, nullable=True)  # 用户校准值
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Setting(Base):
    """系统配置。模型参数 / 游戏化模块开关 / 锚点版本等。"""

    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_setting_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CoinLedger(Base):
    """金币流水（v1.8）。append-only，与 attributes/attribute_history 同构。

    设计原则：**当前值 + append-only 流水** —— `user_profiles.coins` 存当前余额，
    本表存每一次变动，两者配合保证账目永远可对（余额可由流水求和复原）。

    **唯一写入口是 `app/services/coin_service.grant()`**，任何地方不得直接改
    `profile.coins`（v1.5 B-03「多入口必须同一写入语义」教训）。

    source 枚举（前端按它分组展示与配色）：
    - onboarding_bonus  启动资金            +
    - event_confirm     日常事件确认入账     +
    - journal_streak    连续写日记里程碑     +
    - challenge_reward  挑战完成奖励        +
    - challenge_deposit 接受挑战押金        −
    - challenge_refund  挑战完成退回押金     +
    - challenge_forfeit 挑战未完成没收押金   −（押金在 accept 时已扣，此处仅留痕）
    - shop_redeem       商店兑换            −
    - achievement       成就奖励（v1.9 预留） +
    """

    __tablename__ = "coin_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 本次变动，正=获得，负=消耗
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 变动后余额（对账用）
    source: Mapped[str] = mapped_column(String(40), nullable=False)  # 见类 docstring
    reason: Mapped[str] = mapped_column(Text, default="")  # 人类可读说明（前端直接展示）
    ref_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # challenge/event/shop_item/redemption
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Challenge(Base):
    """AI 定制挑战（v1.8）。

    主闭环：AI 生成候选 → 用户接受（押金币承诺）→ 完成（自报 + AI 判定）→
    加点 + 退回押金 + 金币奖励 → 用户确认结算。

    状态机（严格，勿绕过）：
        candidate ──接受(扣押金)──> accepted ──完成并确认结算──> settled
            │                          │
            │过期未接受                 │过期未处理
            v                          v
         expired                    expired   （押金没收 + 按难度扣点，无需 LLM）
            │                          │
            └──────(abandon 主动放弃)──> abandoned（押金没收 + 按难度扣点）

    金币与属性点**完全隔离**；`related_attributes` 仅供内部结算用，**不预览给用户**。
    """

    __tablename__ = "challenges"
    ai_sources: Mapped[list | None] = mapped_column(JSON,nullable=True)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(10), default="daily")  # daily/weekly
    period_key: Mapped[str] = mapped_column(String(20), default="")  # 日=2026-09-28，周=2026-W40
    title: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=1)  # 1~5，AI 按事件自定
    coin_reward: Mapped[int] = mapped_column(BigInteger, default=0)  # 完成可得（接受前展示）
    deposit: Mapped[int] = mapped_column(BigInteger, default=0)  # 押金
    related_attributes: Mapped[list] = mapped_column(JSON, default=list)  # AI 预期影响的维度（不预览）
    ai_reason: Mapped[str] = mapped_column(Text, default="")  # 为什么给你这个挑战（展示）
    # v1.9：同主题的多难度档位 [{label, description, difficulty}]。
    # 空列表 = 单档挑战（等价旧行为）；difficulty/description/coin_reward/deposit
    # 四个字段始终表示「当前选中的档位」。
    variants: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    judgment_id: Mapped[int | None] = mapped_column(ForeignKey("ai_judgments.id"), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), default="")  # done/partial/excused/retreated
    outcome_note: Mapped[str] = mapped_column(Text, default="")  # AI 判定说明（展示）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ShopItem(Base):
    """现实奖励商店物品（v1.8）。

    只做**现实奖励**（决策 14）：常驻物资（`kind='preset'`，首次访问商店时幂等预置）
    + 用户自录物品（`kind='custom'`）。
    `coin_price` 由 AI 定价（决策 15：不设固定基准，但必须输出 `pricing_reason`
    与"值不值得买"的 `worth_note`，会因近期兑换频率浮动以劝导健康生活）。
    """

    __tablename__ = "shop_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="")
    reward_kind: Mapped[str | None] = mapped_column(String(20),nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer,nullable=True)
    base_coin_price: Mapped[int | None] = mapped_column(BigInteger,nullable=True)
    repriced_on: Mapped[str | None] = mapped_column(String(10),nullable=True)
    auto_pricing: Mapped[bool] = mapped_column(Boolean,default=False)
    # once=只用这一次；recurring=常用兑换券，每天可重估。auto_pricing 保留做兼容，不再读取。
    pricing_mode: Mapped[str] = mapped_column(String(10),default='once')
    description: Mapped[str] = mapped_column(Text,default='')
    priced_at: Mapped[datetime | None] = mapped_column(DateTime,nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="custom")  # preset/custom
    price_yuan: Mapped[float | None] = mapped_column(Float, nullable=True)  # 现实价格（元）
    coin_price: Mapped[int] = mapped_column(BigInteger, default=0)  # AI 定出的金币价（用户可改）
    pricing_reason: Mapped[str] = mapped_column(Text, default="")  # AI 定价理由（必须展示）
    worth_note: Mapped[str] = mapped_column(Text, default="")  # "值不值得买"判断（必须展示）
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # 停用不删除
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Redemption(Base):
    """兑换券（v1.8）。

    兑换生成一张待兑现的"奖励券"，用户线下真正兑现后手动打勾「已兑现」。
    `coin_spent` 为**快照**，防止物品后续改价影响历史账目。
    """

    __tablename__ = "redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    shop_item_id: Mapped[int | None] = mapped_column(ForeignKey("shop_items.id"), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer,nullable=True)
    coin_spent: Mapped[int] = mapped_column(BigInteger, default=0)  # 兑换消耗（快照）
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending/fulfilled
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")  # 用户备注


class Achievement(Base):
    """成就（v1.10 M1）。

    两类来源：
    - `cumulative` 累计型：按规则自动统计发放（日记累计 / 连续写日记 / 记录累计 /
      完成挑战 / 首次兑换），在既有"确认入账、提交日记、挑战结算"之后**顺带检查**
      （不新增定时任务）。
    - `discovered` AI 发现型：主判定 prompt 认为用户达成值得纪念的里程碑时**建议追授**，
      **必须用户确认后才发放**（不自动发）。

    **每个成就只能解锁一次** —— 以 `(user_id, code)` 唯一约束保证幂等。
    奖励只发金币 + 徽章（走 `coin_service.grant(source='achievement')`），
    **不发属性点**（保持"点数只能靠真实行为挣"）。
    """

    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_achievement_user_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)  # 如 journal_streak_7
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 展示名
    description: Mapped[str] = mapped_column(Text, default="")  # 解锁说明
    icon: Mapped[str] = mapped_column(String(20), default="🏅")  # emoji
    kind: Mapped[str] = mapped_column(String(20), default="cumulative")  # cumulative/discovered
    coin_reward: Mapped[int] = mapped_column(BigInteger, default=0)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # NULL = 未解锁
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Exemption(Base):
    """豁免券（v1.10 M2）—— **时段券**，只对指定日期 + 时段生效，过期作废。

    **不是万能券**（用户明确要求："要是买来随便一个时间都可以，感觉临时不想干活用券，
    感觉很奇怪，不利于自身成长"）：`target_date` + 时段必填，缺一即拒绝购买。

    效果：该时段内**目标类**的未完成 / 退缩 → 不扣分（v1.10 定稿口径：负向一律归零）；
    时段内做的**其他事情照常加别的维度点数**（不得整条事件跳过判定）。

    代价：`coin_cost` 由 AI **判动机后浮动**——正当紧急 → 正常价；
    明显逃避 → 提价 或 `extra_penalty`（额外属性扣点，**购买时立刻扣**），二者至少取其一，
    且必须在 `motive_note` 里说清（展示给用户）。

    v1.10 实现口径（用户 2026-09-30 拍板，覆盖文档原「period 四档枚举」的写法）：
    - 时段支持**自定义起止时间**，`period` 降级为**预设标签**（morning/.../allday/custom）；
    - **允许跨零点**：`end_time <= start_time` 表示区间延到次日（如 22:00–02:00）。
    """

    __tablename__ = "exemptions"
    timezone_at_capture: Mapped[str] = mapped_column(String(60), default="Asia/Shanghai")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD（必填）
    period: Mapped[str] = mapped_column(String(20), nullable=False)  # morning/afternoon/evening/allday/custom
    # v1.10：实际生效的起止时刻（HH:MM）。end_time <= start_time → **跨零点**
    start_time: Mapped[str] = mapped_column(String(5), default="00:00")
    end_time: Mapped[str] = mapped_column(String(5), default="23:59")
    reason: Mapped[str] = mapped_column(Text, default="")  # 用户写的理由
    coin_cost: Mapped[int] = mapped_column(BigInteger, default=0)  # AI 判动机后的实际价格
    motive: Mapped[str] = mapped_column(String(20), default="legitimate")  # legitimate/evasive
    motive_note: Mapped[str] = mapped_column(Text, default="")  # AI 的动机判断说明（展示）
    extra_penalty: Mapped[float] = mapped_column(Float, default=0.0)  # 判为逃避时的额外扣点
    # v1.10：额外扣点落在哪个维度（AI 指定，非法值回落「规划力」）
    penalty_attribute: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/used/expired
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 券真正发挥豁免作用的时刻
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

from app.models.workflow import DiaryRevision, ReviewSession, ReviewTurn, ReviewAnalysis, LifeChecklist

import app.models.accounts

import app.models.policies
import app.models.full_system
import app.models.daily_use
