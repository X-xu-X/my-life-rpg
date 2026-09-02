"""数据模型（SQLAlchemy ORM，共 10 张核心表）。

对应 PRD 6.3 节：users / user_profiles / attributes / attribute_history /
events / ai_judgments / judgment_logs / goals / anchors / settings。

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
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    """统一的时间戳生成（本地时区，个人自用场景更直观）。"""
    return datetime.now()


class User(Base):
    """用户表。V1 单用户，启动时自动创建 default 用户。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
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
    # 进行中的首次引导会话态（对话历史/当前问题/把握度），持久化，离开或重启不丢
    onboarding_state: Mapped[dict] = mapped_column(JSON, default=dict)
    # 补充长期信息后、待用户确认的属性调整建议
    pending_adjustment: Mapped[dict] = mapped_column(JSON, default=dict)
    # 游戏化字段（M3 实现曲线逻辑，此处预留）
    level: Mapped[int] = mapped_column(Integer, default=1)
    exp: Mapped[float] = mapped_column(Float, default=0.0)
    # 长期记忆（智能体式）：LLM 压缩历史事件成的五类摘要（长期目标/关键经历/性格/偏好/当前状态），JSON 字符串
    long_term_memory: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    user: Mapped["User"] = relationship(back_populates="profile")


class Attribute(Base):
    """属性定义 + 当前值。内置 6 个标准维度（见 DECISIONS.md D5）。"""

    __tablename__ = "attributes"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_attribute_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # 体能/智力/情商/创造力/规划力/健康
    description: Mapped[str] = mapped_column(Text, default="")
    attr_type: Mapped[str] = mapped_column(String(50), default="")  # physical/mental/social/...
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    max_value: Mapped[float] = mapped_column(Float, default=100.0)
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


class Event(Base):
    """生活事件。类型 positive/negative/goal，来源 form/journal。"""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # positive/negative/goal
    category: Mapped[str] = mapped_column(String(50), default="")  # 锻炼/学习/作息/社交/饮食/理财...
    source: Mapped[str] = mapped_column(String(20), default="form")  # form/journal
    title: Mapped[str] = mapped_column(String(200), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)  # 结构化参数（时长/距离/配速/强度...）
    content: Mapped[str] = mapped_column(Text, default="")  # 自由日记原文
    # 纯享版记录：True 表示只记录不加点、不走 AI 判定（生活手账）
    is_pure: Mapped[bool] = mapped_column(Boolean, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_now)  # 事件发生时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AIJudgment(Base):
    """AI 判定记录。状态：pending/confirmed/adjusted/rejected。"""

    __tablename__ = "ai_judgments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # AI 原始建议增减：[{name, delta, reason, evidence}]
    suggested_changes: Mapped[list] = mapped_column(JSON, default=list)
    # AI 分析过程（推理链路：要素解析 → 锚点比对 → 加权推导），v1.1 新增
    analysis: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")  # AI 判定总结
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 置信度 0~1
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
    """

    __tablename__ = "anchors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 标准事件名
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="")  # 锻炼/学习/作息/目标
    target_attribute: Mapped[str] = mapped_column(String(50), default="")  # 影响属性
    base_value: Mapped[float] = mapped_column(Float, default=0.0)  # 基准量
    unit: Mapped[str] = mapped_column(String(20), default="")  # 单位
    base_delta: Mapped[float] = mapped_column(Float, default=0.0)  # 基准增减点数
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
