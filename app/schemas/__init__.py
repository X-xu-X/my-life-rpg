"""Pydantic 请求/响应模型（API 层数据结构）。"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============ 事件 ============

class EventCreate(BaseModel):
    """录入事件。form 通道传 params，journal 通道传 content（event_type 由 AI 提取）。"""

    event_type: Literal["positive", "negative", "goal"] | None = None
    category: str = Field("", description="类别：锻炼/学习/作息/社交/饮食/理财…")
    source: Literal["form", "journal"] = "form"
    title: str = ""
    params: dict[str, Any] = Field(default_factory=dict, description="结构化参数（时长/距离/配速/强度…）")
    content: str = Field("", description="自由日记原文")
    is_pure: bool = Field(False, description="纯享记录：只记录不加点、不走 AI 判定")
    occurred_at: datetime | None = None


class EventUpdate(BaseModel):
    """编辑事件（全部字段可选，仅更新传入的）。"""

    event_type: Literal["positive", "negative", "goal"] | None = None
    category: str | None = None
    title: str | None = None
    params: dict[str, Any] | None = None
    content: str | None = None
    occurred_at: datetime | None = None


class EventOut(BaseModel):
    id: int
    event_type: str
    category: str
    source: str
    title: str
    params: dict
    content: str
    is_pure: bool
    occurred_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============ AI 判定 ============

class JudgeIn(BaseModel):
    """触发判定的入参。clarification 为对 AI 追问的补充回答（可选）。"""

    clarification: str = Field("", description="对 AI 追问的补充回答（日记追问流程使用）")

class AttributeChange(BaseModel):
    """AI 判定的单条属性增减。"""

    name: str
    delta: float
    reason: str = ""
    evidence: str = ""


class JudgmentResult(BaseModel):
    """AI 判定输出（对应 PRD 11 节 JSON 结构）。"""

    affected_attributes: list[AttributeChange] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0


class JudgmentOut(BaseModel):
    id: int
    event_id: int
    status: str
    suggested_changes: list[dict]
    final_changes: list[dict]
    summary: str
    confidence: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============ 判定操作 ============

class SupplementIn(BaseModel):
    """补充信息重判。"""

    detail: str = Field(..., description="补充说明")


class DisputeIn(BaseModel):
    """反驳理由。"""

    detail: str = Field(..., description="反驳理由")


# ============ Onboarding ============

class OnboardingAnswerIn(BaseModel):
    """提交一轮回答（首次引导）。"""

    answers: list[dict[str, Any]] = Field(..., description="[{question, answer}]")


class SupplementProfileIn(BaseModel):
    """补充长期信息（首次引导完成后）。"""

    detail: str = Field(..., description="补充的长期信息（性格、习惯、能力自评等）")


# ============ 目标 ============

class GoalCreate(BaseModel):
    description: str = ""
    metric: str = Field(..., description="量化指标")
    deadline: datetime | None = None
    related_attribute: str = ""
    reward: float = 2.0
    penalty: float = -1.0


class GoalUpdate(BaseModel):
    description: str | None = None
    metric: str | None = None
    deadline: datetime | None = None
    related_attribute: str | None = None
    reward: float | None = None
    penalty: float | None = None


class GoalOut(BaseModel):
    id: int
    description: str
    metric: str
    deadline: datetime | None
    related_attribute: str
    status: str
    reward: float
    penalty: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ============ 锚点 ============

class AnchorCalibrateIn(BaseModel):
    """校准锚点基准值。"""

    calibrated_value: float | None = Field(None, description="用户校准后的基准量；null 恢复默认")


# ============ 设置 ============

class SettingIn(BaseModel):
    key: str
    value: Any  # 设置值可为任意 JSON 类型（dict / list / bool / 数字 / 字符串）
