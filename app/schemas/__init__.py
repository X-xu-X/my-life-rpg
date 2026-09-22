"""Pydantic 请求/响应模型（API 层数据结构）。"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============ 事件 ============

class EventCreate(BaseModel):
    """录入事件。form 通道传 params，journal 通道传 content（event_type 由 AI 提取）。

    v1.7：form 通道改为「选打卡项目 + 写正文」——item_id 可选（不传=纯自由记一笔），
    content 为正文（打卡正文 / 日记原文），params 为可选数字键值对（键名自由，不校验白名单）。
    """

    event_type: Literal["positive", "negative", "goal"] | None = None
    category: str = Field("", description="类别：锻炼/学习/作息/社交/饮食/理财…")
    source: Literal["form", "journal"] = "form"
    title: str = ""
    params: dict[str, Any] = Field(default_factory=dict, description="可选数字键值对（如 时长(分钟): 30）")
    content: str = Field("", description="用户手写正文（打卡正文 / 自由日记原文）")
    item_id: int | None = Field(None, description="所属打卡项目（v1.7，可空=纯自由记一笔）")
    is_pure: bool = Field(False, description="纯享记录：只记录不加点、不走 AI 判定")
    occurred_at: datetime | None = None


class EventUpdate(BaseModel):
    """编辑事件（全部字段可选，仅更新传入的）。"""

    event_type: Literal["positive", "negative", "goal"] | None = None
    category: str | None = None
    title: str | None = None
    params: dict[str, Any] | None = None
    content: str | None = None
    item_id: int | None = None
    occurred_at: datetime | None = None


class EventOut(BaseModel):
    id: int
    event_type: str
    category: str
    source: str
    title: str
    params: dict
    content: str
    item_id: int | None = None
    is_pure: bool
    occurred_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============ 打卡项目（v1.7） ============

class CheckinItemIn(BaseModel):
    """新建 / 修改打卡项目。系统不预置任何项目，全部由用户自建。"""

    name: str = Field(..., description="项目名，如 晨跑 / 背单词 / 久坐")
    nature: Literal["planned", "optional", "negative", "other"] = Field(
        "other", description="planned 规划内 / optional 可选 / negative 负面 / other 其他"
    )
    frequency_type: Literal["daily", "weekly", "none"] = "none"
    frequency_target: int = Field(0, description="weekly 时的每周目标次数；daily/none 忽略")
    category: str = Field("", description="生活面：学习/运动/作息/社交/饮食/情绪/其他")
    related_attribute: str = Field("", description="主要影响的属性维度（可空）")
    goal_id: int | None = Field(None, description="关联目标（可空）")
    enabled: bool = True
    sort_order: int = 0


class CheckinItemPatch(BaseModel):
    """局部修改打卡项目：字段全部可选，仅更新传入的（未传的保留原值）。

    主要供「把项目挂到某个目标」这类单字段改动使用，避免调用方为了改一个字段
    而不得不回传整个对象。
    """

    name: str | None = None
    nature: Literal["planned", "optional", "negative", "other"] | None = None
    frequency_type: Literal["daily", "weekly", "none"] | None = None
    frequency_target: int | None = None
    category: str | None = None
    related_attribute: str | None = None
    goal_id: int | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class CheckinItemOut(BaseModel):
    """打卡项目输出。"""

    id: int
    name: str
    nature: str
    frequency_type: str
    frequency_target: int
    category: str
    related_attribute: str
    goal_id: int | None
    enabled: bool
    sort_order: int
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


# ============ AI 模型配置（BYOK，v1.4） ============

class LLMConfigIn(BaseModel):
    """写入一组模型配置。group: primary（判定）/ aux（辅助）。

    api_key 传 "__KEEP__" 表示不改（配合掩码回显）；传空串表示清除。
    """

    group: Literal["primary", "aux"]
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    enabled: bool | None = None
