"""Pydantic 请求/响应模型（API 层数据结构）。"""
from datetime import datetime, date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from app.services.receipts import MutationIn


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
    record_kind: Literal['event'] | None = None
    occurred_on: date | None = None
    time_precision: Literal['date', 'minute'] | None = None
    client_request_id: UUID | None = None
    intent: Literal["now", "later", "never"] = "later"
    timezone: str = "Asia/Shanghai"

    @model_validator(mode='after')
    def validate_precision(self):
        if self.time_precision == 'date' and (self.occurred_on is None or self.occurred_at is not None):
            raise ValueError('日期精度需要 occurred_on，不能同时声称精确时间。')
        if self.time_precision == 'minute' and self.occurred_at is None:
            raise ValueError('分钟精度需要发生时间。')
        if self.occurred_on is not None and self.time_precision is None:
            raise ValueError('请明确发生时间精度。')
        return self


class EventUpdate(BaseModel):
    """编辑事件（全部字段可选，仅更新传入的）。"""

    event_type: Literal["positive", "negative", "goal"] | None = None
    category: str | None = None
    title: str | None = None
    params: dict[str, Any] | None = None
    content: str | None = None
    item_id: int | None = None
    occurred_at: datetime | None = None
    expected_version: int | None = Field(None, ge=1)


class EventOut(BaseModel):
    record_kind: str | None = None
    id: int
    event_type: str
    category: str
    source: str
    title: str
    params: dict
    content: str
    item_id: int | None = None
    is_pure: bool
    # v1.9（F5）：None=普通记录；"challenge"=挑战结算生成。
    # 注意 EventCreate / EventUpdate **不提供**该字段（不给前端写入口）。
    origin: str | None = None
    occurred_at: datetime | None
    occurred_on: date | None = None
    time_precision: str | None = None
    created_at: datetime
    content_version: int = 1
    client_request_id: str | None = None
    analysis_intent: str = "legacy"
    timezone_at_capture: str = "Asia/Shanghai"

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
    model_provenance: dict | None = None
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


class AchievementActionIn(MutationIn):
    """v1.10 M1：AI 里程碑建议的处理动作。

    - `grant`：追授（发一次金币 + 落库）
    - `dismiss`：忽略（不发放，标记该建议已处理）
    """

    action: str = Field(..., description="grant / dismiss")


# ============ 豁免券（v1.10 M2） ============

class ExemptionIn(MutationIn):
    """购买豁免券：**必须指定日期 + 时段**（缺一即拒，不做万能券）。

    - `period` ∈ morning/afternoon/evening/allday/custom
    - `period=custom` 时必须给出 `start_time` / `end_time`（HH:MM）；
      `end_time <= start_time` 表示**跨零点**（如 22:00–02:00）
    - `reason` 会直接影响 AI 的动机判断（正当紧急 → 正常价；明显逃避 → 提价或扣点）
    """

    target_date: str = Field(..., description="目标日期 YYYY-MM-DD")
    period: str = Field(..., description="morning/afternoon/evening/allday/custom")
    start_time: str = Field("", description="HH:MM（period=custom 时必填）")
    end_time: str = Field("", description="HH:MM（period=custom 时必填）")
    reason: str = Field("", description="用户写的理由（影响 AI 动机判断）")


# ============ 子维度 / 豁免券 之外的属性层级（v1.10 M3） ============

class SubdimensionAcceptIn(BaseModel):
    """确认创建子维度：**用户勾选的名字**（未勾选的不创建）。

    多选后确认（用户 2026-09-30 拍板）——AI 建议 2~4 个，用户可只要其中一部分。
    """

    names: list[str] = Field(..., description="勾选确认的细分方向名（必须是 AI 提议里的名字）")


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
    reward: float = Field(2.0, ge=0, le=5, allow_inf_nan=False)
    penalty: float = Field(-1.0, ge=-5, le=0, allow_inf_nan=False)


class GoalUpdate(MutationIn):
    description: str | None = None
    metric: str | None = None
    deadline: datetime | None = None
    related_attribute: str | None = None
    reward: float | None = Field(None, ge=0, le=5, allow_inf_nan=False)
    penalty: float | None = Field(None, ge=-5, le=0, allow_inf_nan=False)


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
    provider_id: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    enabled: bool | None = None


# ============ 挑战（v1.8） ============

class ChallengeOut(BaseModel):
    """挑战输出。

    注意：`related_attributes`（AI 预期影响的维度）**仅内部与结算使用，不预览给用户**
    ——决策 10「金币提前显示、加点不预览」。前端若需要它，仅可用于结算后展示。
    """

    id: int
    scope: str
    period_key: str
    title: str
    description: str
    difficulty: int
    coin_reward: int
    deposit: int
    ai_reason: str
    status: str
    accepted_at: datetime | None
    expires_at: datetime | None
    outcome: str
    outcome_note: str
    related_attributes: list
    # v1.9：多档位 [{label, description, difficulty}]；空列表 = 单档（旧行为）
    variants: list = []
    event_id: int | None
    judgment_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChallengeGenerateIn(BaseModel):
    """生成挑战候选。force=True 为「再来一批」（仅补空缺，不覆盖进行中的）。"""

    scope: Literal["daily", "weekly"] = "daily"
    force: bool = False


class ChallengeVariantIn(BaseModel):
    """候选期切换难度档位（v1.9 F3）。

    `variant_index` 为 `variants` 数组下标；越界或挑战已接受都会被拒。
    """

    variant_index: int


class ChallengeResolveIn(BaseModel):
    """完成 / 放弃挑战时的一句话自述（complete 必填，abandon 可空）。"""

    note: str = ""


# ============ 商店与兑换（v1.8） ============

class ShopItemIn(BaseModel):
    """新建商店物品：只填名称与现实价格，金币价由 AI 定价。"""

    name: str = Field(..., description="物品名，如「奶茶（大杯）」")
    price_yuan: float | None = Field(None, description="现实价格（元）；0 元为时间型奖励")


class ShopItemUpdateIn(BaseModel):
    """局部修改商店物品（用户手动改价 / 停用）。字段全部可选。"""

    name: str | None = None
    price_yuan: float | None = None
    coin_price: int | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class ShopItemOut(BaseModel):
    id: int
    name: str
    kind: str
    price_yuan: float | None
    coin_price: int
    pricing_reason: str
    worth_note: str
    enabled: bool
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RedemptionOut(BaseModel):
    id: int
    shop_item_id: int | None
    item_name: str = ""
    coin_spent: int
    status: str
    redeemed_at: datetime | None
    fulfilled_at: datetime | None
    note: str


class RedeemIn(BaseModel):
    """兑换（可附备注）。"""

    note: str = ""
    request_key: UUID | None = None
    expected_version: datetime | None = None


class FulfillIn(BaseModel):
    """兑现奖励券（可附备注）。"""

    note: str = ""


# ============ 停滞觉察（v1.8） ============

class StagnationAnswerIn(MutationIn):
    """回答停滞问询。

    - stopped=True  确实停了 → 小幅扣分（−0.3）+ 生成补课挑战
    - stopped=False 在学只是没记 → 不扣分，引导补记并重置该维度停滞计时
    """

    stopped: bool
    note: str = ""
