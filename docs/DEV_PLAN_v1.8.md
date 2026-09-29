# 开发计划 v1.8 —— 游戏化经济系统（AI 定制挑战 / 金币 / 现实奖励商店 / 属性数值模型重构）

> 交付对象：项目实现者（AI Writer）
> 版式基线：v1.7（HEAD 提交 `8b8e2f9`）
> 开工前**必读**：`docs/PRD.md`、`docs/DECISIONS.md`（全文，尤其开头的「核心设计理念」与「Backlog：v1.7 实测反馈」）、`docs/WRITER_PROMPT.md`
> 本文档为**唯一施工依据**；与旧文档冲突时以本文档为准，与 PRD 冲突时保守实现并记录到 `docs/DECISIONS.md`
> 决策来源：2026-09-28 与用户的 7 轮逐条访谈（全部结论见第一章，**不得自行发挥**）；2026-09-29 追加一轮修正，**仅涉及 N1 属性数值模型**（见第一章「修正说明」与 A2 开头）

---

## 〇、本轮定位与总原则

**这是一次「把成长变成有回报的循环」的系统性升级**，不是加个页面：现有闭环是「记录事件 → AI 判定 → 属性加点 → 用户确认入账」，反馈只有属性点一个出口，且属性点只能攒、无法兑换成任何现实回报。本轮补上**出口与挑战**：

```
AI 定制挑战  →  接受（押金币承诺）  →  完成（自报 + AI 判定）  →  加点 + 金币  →  兑换现实奖励
                     ↑                                                          ↓
                     └──────────── 金币与属性点严格隔离，避免"玩游戏刷分" ←────────┘
```

**三条不可违背的总原则**：

1. **数据红线（最高优先级）**：用户本地 `game_of_life.db` 存有真实生活记录（含 2026-09-28 的真实事件），**禁止任何物理删除**（判定、审计、事件一律只归档不删除）；新增表由 `Base.metadata.create_all` 创建，既有表加列必须走 `app/database.py::migrate_schema` 的启动自动迁移；**老数据必须全部可读、可正常展示、可正常判定**。任何批量清理必须走 `DELETE /api/events/{id}`（自带反向流水回滚 + 审计），且**执行前必须整库备份**。
2. **兼容过渡**：`events.event_type`、`events.params`、`events.item_id` 语义保持向后兼容（`item_id` 为 NULL 是正常老数据，下游必须容忍）；新增 `coin_ledger` / `challenges` / `shop_items` / `redemptions` 四张表互不影响老链路。
3. **一批一 commit，中文 message**，格式 `类型: 简述`（feat/fix/refactor/docs/chore/test）；只 commit，**不 merge、不 push**；严禁提交 `.env`、`*.db`、`*.backup-*.db`、`__pycache__/`、`node_modules/`、`.workbuddy/`。

**本轮禁区（一个都不要碰）**：

- **成就系统**（累计型 + AI 发现型、徽章/称号）→ v1.9
- **豁免券**（时段券、AI 判动机浮动定价）→ v1.9
- **属性满 100 拆分子维度**（`parent_id` 维度层级）→ v1.9
- **月挑战**（用户口径："月挑战看情况"，本版不做）
- **页面结构重构 U1/U2/U3**（今日盘点与记录事件合并、打卡项目管理迁出设置、每日任务清单）→ 用户已明确本轮不动
- **可视化重做 V1/V2/V3**（雷达图排版、成长趋势图、活动热力图）→ 未选入本轮
- **主题 / 皮肤 / 桌宠**（用户："桌宠是个不小的工程，先单独评估"）
- 饮食拍照识别、AI 分析流式显化、定时提醒（历史遗留禁区）

---

## 一、用户已确认的决策（逐条实现，不得自行发挥）

| # | 决策项 | 确认结论 |
|---|--------|----------|
| 1 | 本轮范围 | **v1.8 = 挑战系统 + 金币体系 + 现实奖励商店 + N1 属性数值模型（取消分组 / 锚点升级 / 补负面锚点 / 封顶 / 段位 / 停滞问询）**。成就、豁免券、满级拆分 → v1.9 |
| 2 | 挑战来源 | **AI 动态生成**，按个人短板定制（用户原话举例：对 i 人，挑战"去采访一个人"；简单=采访校园同学，困难=采访外校陌生人/加长时长），AI 制定专属挑战 |
| 3 | 难度分档 | **不固定档数**，AI 按事件性质自定 3~5 档（简单→困难），**奖励随难度递增** |
| 4 | 挑战类型 | **日挑战 + 周挑战**（月挑战本版不做） |
| 5 | 候选数量 | **日 3 个 / 周 2 个**候选；每天 / 每周自动换新 |
| 6 | 接受语义 | 候选**限时**（日挑战当天、周挑战当周）；**接受前无义务**；**接受即承诺**（押金币）；过期未接受自动消失；做完后用户可手动"再来一批"由 AI 生成新挑战（**免费，不消耗金币**） |
| 7 | 押金 | **押金制**：按难度 5~20 币，接受时从余额扣；完成→返还；未完成→**没收押金** |
| 8 | 启动资金 | **onboarding 生成属性面板时发放**（如 50 币），解决"新用户 0 币无法接受挑战"的死锁 |
| 9 | 完成认定 | **自报（写一句话）+ AI 判定**（是否达成 + 加点 + 金币）——与现有判定链路一致，不能空刷 |
| 10 | 奖励展示 | **金币提前显示**（接受前可见"完成可得 +N 币"）；**加点不预览**（完成后揭晓） |
| 11 | 未完成语义 | 用户三分：**主动退缩 / 接受后没完成 → 惩罚**（没收押金 + **AI 按难度等比扣相应属性点**）；**突发意外 / 做了没达标 → 不惩罚，只是没奖励** |
| 12 | 金币来源 | 挑战 + **日常事件**（确认入账时）+ **累计写日记 3/7 天**等；成就金币 v1.9 上线 |
| 13 | 金币边界 | 与属性点**完全隔离**（金币不能换点数）；**负面事件不扣金币**（只是不给），避免"双重惩罚"打击如实记录意愿 |
| 14 | 商店范围 | **只做现实奖励**：常驻物资（预置若干）+ 用户自录物品与价格 |
| 15 | 定价方式 | **不设固定基准，AI 直接定价**，且**必须输出理由并展示**（含"值不值得买"的判断）。会因情境浮动：本月没喝过奶茶→定低；已兑换好几杯→提高（出于意义/性价比/健康），本质是**劝健康生活** |
| 16 | 兑换闭环 | 兑换生成一张**"奖励券"**，用户线下兑现后手动打勾**"已兑现"** |
| 17 | N1 数值模型 | **不做维度分组——13 维一律可涨可跌**（09-29 修正，原"积累型只增不减"提案已作废，见下方「修正说明」）。下降**只由具体事件驱动**，**不做日历驱动的自动衰减**；长期停滞走 **B5 停滞问询**，不偷偷扣分 |
| 17b | 锚点升级 | 锚点从**单属性**改为**多属性**（一条锚点可同时影响多维度，如熬夜 → 健康 + 智力），并给**强度分档**；AI 在基准上按强度系数浮动（**弱 0.5 / 中 1.0 / 强 1.5~2.0**），受 [-5, 5] 约束（见 A2-2） |
| 17c | 扣分纪律 | 单次负面事件**小幅扣分**（能力类 −0.3 ~ −0.5）+ 累积效应加重；**必须对称补齐正面锚点**使损害可恢复（补觉/专注学习同样作用于认知维度），避免"只降不回的棘轮"（见 A2-3） |
| 18 | N1 上限 | 每维**封顶 100、下限 0**；靠既有**边际递减**机制让越接近 100 越难涨；面板显示**段位**回答"多还是少" |
| 19 | 满级拆分 | **v1.9**（AI 提议 + 用户确认解锁子维度），本轮只做数值模型（A2）+ 封顶 + 段位 |

### 修正说明（2026-09-29，仅涉及 N1）

用户在审阅 v1.8 草稿时对「积累型维度只增不减」提出反例——**熬夜对智力/记忆力有负面作用**。经代码核查确认该反例成立（核查结论见 A2 开头），故：

| 原决议（09-28） | 现决议（09-29） |
|---|---|
| 积累型 8 维只增不减、状态型 5 维可涨可跌 | **取消分组**，13 维一律可涨可跌 |
| （未涉及）下降是否可由时间驱动 | **只由事件驱动**；不做日历衰减；长期停滞走 **B5 停滞问询** |
| 锚点单属性（熬夜只能扣健康） | **锚点升级为多属性 + 强度分档**（A2-2） |
| （未涉及）能力类负面锚点缺失 | **补 5 类负面锚点**（A2-3），**按证据补、不强凑** |
| （未涉及）prompt 覆盖自检偏"加分" | **自检双向化**（A2-4） |
| 代码硬校验"积累型负 delta → 归零" | **删除该校验**（改为 A2-1 的"事件驱动"约束） |

> 除 N1 外，其余 18 条决策**不变**。原方案里的「积累型负 delta → 归零」代码硬校验**一律不得实现**——它正是被本次修正否掉的东西。（注意：新编号下 A2-3 是"补负面锚点"，两者无关，勿混。）

---

## 二、批次划分与交付顺序

```
批次 A（后端 · 经济地基）   金币账户与流水 + 启动资金 + N1 数值模型（取消分组 / 锚点升级 / 补负面锚点 / 封顶 / 段位）+ 日常事件赚币
批次 B（后端 · 挑战与商店） 挑战数据模型 + AI 生成 + 接受/押金/完成判定/结算/过期 + 商店物品/AI 定价/兑换券 + 停滞觉察与问询
批次 C（前端）             新 tab「挑战」（挑战区 + 商店区）+ 金币余额/流水 + 段位显示 + 停滞提示卡
```

- A 完成后 B 才能测（B 依赖金币账户与流水）；C 依赖 A、B 的接口。
- **提交顺序 A → B → C，勿交叉**（每批一个或数个 commit，按逻辑单元拆）。

---

## 三、批次 A · 后端：经济地基

### A1 · 金币账户与流水

**设计原则**：沿用项目既有的「**当前值 + append-only 流水**」模式（与 `attributes` / `attribute_history` 一致），保证金币账目永远可对。

**新建 ORM 模型 `CoinLedger`**（表名 `coin_ledger`，`app/models/__init__.py`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增 |
| `user_id` | ForeignKey("users.id") | 多用户预留 |
| `delta` | Integer | 本次变动（正=获得，负=消耗/押金/没收） |
| `balance_after` | Integer | 变动后余额（对账用） |
| `source` | String(40) | 见下表 |
| `reason` | Text | 人类可读说明（前端直接展示） |
| `ref_type` / `ref_id` | String(30) / Integer nullable | 关联对象（challenge / event / shop_item / redemption） |
| `created_at` | DateTime | 与其他表一致 |

`source` 取值（**必须用这套枚举，前端按它分组展示与配色**）：

| source | 含义 | 符号 |
|---|---|---|
| `onboarding_bonus` | 启动资金 | + |
| `event_confirm` | 日常事件确认入账 | + |
| `journal_streak` | 连续写日记里程碑 | + |
| `challenge_reward` | 挑战完成奖励 | + |
| `challenge_deposit` | 接受挑战押金 | − |
| `challenge_refund` | 挑战完成退回押金 | + |
| `challenge_forfeit` | 挑战未完成没收押金 | −（不再变动余额，仅留痕） |
| `shop_redeem` | 商店兑换 | − |
| `achievement` | 成就奖励（v1.9 预留） | + |

**同时**：`user_profiles` 新增 `coins: Mapped[int] = mapped_column(Integer, default=0)`（由 `migrate_schema` 自动添加；有 Python 标量默认值，NULL 行会被回填为 0）。

**新建 `app/services/coin_service.py`**：

```python
STARTUP_BONUS = 50

def grant(db, user, delta: int, source: str, reason: str,
          ref_type: str | None = None, ref_id: int | None = None) -> int:
    """唯一金币写入口。正负皆可；余额不足时抛 ValueError（禁止透支）。
    写 profile.coins + coin_ledger(balance_after)，返回新余额。"""

def balance(db, user) -> int: ...
def ledger(db, user, limit: int = 50) -> list[CoinLedger]: ...  # 倒序
def grant_startup_bonus_if_needed(db, user) -> None:
    """幂等发放启动资金：仅当从未发过（ledger 无 onboarding_bonus 记录）时发放。"""
```

> **多入口一致性铁律（v1.5 B-03 教训）**：金币只有 `coin_service.grant()` 一个写入口，**任何地方不得直接改 `profile.coins`**。押金、返还、没收、兑换全部走它。

**接口**（新建 `app/routers/coins.py`，挂 `/api` 前缀）：

- `GET /api/coins` → `{balance, ledger: [{delta, balance_after, source, reason, created_at}]}`

**验收标准**：
1. 启动后 `coin_ledger` 自动建表，`user_profiles` 新增 `coins` 列（迁移日志有 `[migrate]` 记录），**现有 31 条事件 / 31 条判定全部正常可打开**
2. `grant(+50, 'onboarding_bonus')` → `GET /api/coins` 返回 `balance=50` 且流水含该条；再调一次 `grant_startup_bonus_if_needed` **不重复发放**
3. 余额 50 时尝试 `grant(-80)` → 抛 `ValueError`，余额仍 50（不透支）

### A2 · N1 属性数值模型（取消分组 / 锚点升级 / 补负面锚点 / 封顶 / 段位）

> **⚠️ 2026-09-29 修正（覆盖 09-28 原决议）**：原方案为"积累型 8 维只增不减 + 状态型 5 维可涨可跌"。用户提出反例——**熬夜对智力/记忆力有负面作用**——该反例成立，**分组方案作废**。
>
> **代码核查结论（写本文档时的真实情况，动手前务必先读）**：
> 1. `app/prompts/judge.py` 中**根本不存在"只增不减"规则**：13 维在 prompt 里一视同仁，「负面情绪与状态」节还明确要求"该减就减"。所以"多数维度从未减分"是**数据现象**，不是设计意图——**不要以为在实现一条既有规则，实际是在补一个缺失**。
> 2. 现有「熬夜」锚点（`anchor_service.BUILTIN_ANCHORS`）的 `target_attribute` **只写了 `健康`**，而它自己的 `evidence` 原文是"长期熬夜扰乱昼夜节律，**损害认知表现**与内分泌稳态"——**结构化字段把"认知"这一分漏掉了**。这就是"熬夜不扣智力"的直接原因。
> 3. 真正缺的是三样：**① 锚点的多属性能力 ② 能力类的负面锚点 ③ prompt 覆盖自检的双向性**。分别见 A2-2 / A2-3 / A2-4。
>
> **新原则**：**不做维度分组**。13 维一律可涨可跌；下降**只由具体事件驱动**（做了有害的事才扣），**不做日历驱动的自动衰减**（"没记录" ≠ "没做"）；长期停滞走 **B5 停滞问询**，不偷偷扣分。

**A2-1 · prompt 层：变化方向与幅度（`app/prompts/judge.py`）**

在「客观性硬约束」之后、「追问引导」之前，插入新节「**变化方向与幅度**」，明确四件事：

1. **一视同仁**：13 个维度**没有任何一个是"只增不减"的**；负面行为该减就减，不受维度类别限制。
2. **只由行为驱动**：只有记录中出现了明确有害的行为/状态才给负 delta；**严禁因为"某维度很久没出现在记录里"而扣分**（系统不惩罚沉默——这是与"时间衰减"的分界）。
3. **幅度系数**：`本次 delta = 锚点基准 × 强度系数`，强度系数取 **弱 0.5 / 中 1.0 / 强 1.5~2.0**；选了哪一档必须在「加权推导」中说明依据（事件强度/时长/频率）。
4. **可恢复**：负面事件造成的下滑应能被后续正面行为抵消（对称判定）；对单次负面事件**不得给出极端幅度**（单次熬夜不等于能力被砍）。

**A2-2 · 锚点升级：单属性 → 多属性 + 强度分档**

**数据模型**（`app/models/__init__.py::Anchor`）**新增两列（可空，由 `migrate_schema` 自动添加）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `targets` | JSON nullable | `[{"name": "健康", "base_delta": -0.5}, {"name": "智力", "base_delta": -0.4}]`。**非空时以它为准**，忽略旧的 `target_attribute` / `base_delta` |
| `intensity_note` | Text nullable | 强度梯度指引（人类可读，直接注入 prompt），如"偶尔 1 次 −0.5；每周 ≥3 次 −1.5" |

**落库与兼容（`anchor_service.seed_anchors` 扩展为三级幂等，务必按此实现）**：

1. 名字不存在 → 新增整条（沿用现有逻辑）
2. 名字已存在、**`targets IS NULL`**、且 `BUILTIN_ANCHORS` 中该锚点已定义 `targets` → **回填 `targets` 与 `intensity_note`**
3. 否则跳过

> **只填 NULL，绝不覆盖已有值，也绝不动 `calibrated_value`**（用户校准结果不可被启动流程冲掉）。旧锚点 `targets IS NULL` 时，下游一律按 `target_attribute` + `base_delta` 单属性处理，**行为与现在完全一致**。

**`anchor_service.format_anchors_text`** 输出格式扩展：有 `targets` 时逐条列出每个目标维度与基准值，并附 `intensity_note`；无 `targets` 时**保持原格式不变**。

**prompt 注入要求**：在锚点库节后补一句——"**锚点给的是基准值，不是唯一值**：请按「变化方向与幅度」的强度系数在基准上浮动，并优先落在 `intensity_note` 给定的梯度内"。

**A2-3 · 补"有害行为"负面锚点（按证据补、不强凑）**

原则：**有明确有害行为的维度就补，没有依据的不硬凑**。注意这与"分组"的本质区别——**"暂无负面锚点"是开放的**（未来发现依据可随时补），而"禁止扣分"是封闭的。

| 维度 | 拟补锚点（新增/改造） | 依据方向 | 强度 |
|---|---|---|---|
| 智力 | **改造「熬夜」为多属性**：健康 −0.5 + 智力 −0.4 | 睡眠与记忆巩固（原 `evidence` 已写"损害认知表现"，本次把它落到字段上） | 强 |
| 智力 | 新增「长时间碎片化刷屏」（连续 ≥2h 无目的刷手机）→ 智力 −0.3 | 注意力残留效应 / 注意力资源耗竭 | 中 |
| 智力 | 新增「连续多日无学习输入」（用户如实记录"这几天什么都没学"时触发）→ 智力 −0.5 | 认知用进废退（与既有「缺少运动」锚点同构） | 中 |
| 创造力 | 新增「长期机械重复、不做任何新尝试」→ 创造力 −0.3 | 创造力三成分理论（Amabile）：依赖持续输入与试错 | 弱 |
| 开放性 | 新增「固守成见 / 拒绝新体验 / 回避陌生事物」→ 开放性 −0.5 | 大五人格：开放性可由新体验维持与拓展 | 中 |
| 意义感 | 新增「空虚度过一天 / 长期无价值感产出」→ 意义感 −0.5 | 意义感研究：意义源于投入与联结 | 中 |
| 审美 | 新增「长期不接触任何美的事物（音乐/艺术/自然）」→ 审美 −0.3 | **依据较弱**：标注 `TODO`，若用户认为不妥可删该锚点 | 弱 |
| 情商 / 诚信 / 体能 / 规划力 / 健康 / 心理韧性 | **已有负面锚点**（社交回避·情绪失控 / 迟到失约 / 缺少运动 / 拖延·冲动消费·沉迷屏幕 / 抽烟·酗酒·久坐·暴食 / 消极思维） | 不改 | — |
| 感恩 | **不新增**（已有"记录感恩"正面锚点，负面由「负面情绪与状态」节承担）——**不硬凑** | — | — |

**同时必须补齐的正面锚点（"可恢复"原则的落地）**：

- 「早睡充足睡眠」→ **增加智力目标**（睡眠促进记忆巩固）：健康 +0.5 + 智力 +0.4（**与「熬夜」互为反面，形成对称**）
- 「深度专注学习」→ 保持不变（已作用智力）

**补充约束**：

- 所有新增锚点**必须带 `evidence`**（沿用"evidence 为空不落库"的既有约定）
- 新增/改造的锚点全部写进 `anchor_service.BUILTIN_ANCHORS`，由 A2-2 的三级幂等落库

**A2-4 · prompt 覆盖自检双向化（关键修补）**

现有「多属性联动与生活面覆盖自检」与「输出前维度硬校验」的措辞是"复核确实无据**可加**才可跳过"——**隐含加分倾向**，这正是能力类长期不减分的隐性成因之一。改为双向：

- 逐生活面自检时，**既问"这个面该不该加分"，也问"这个面该不该减分"**，两者都要在「要素解析」中交代。
- 明确写：**"没有负面判定"不是默认值**——记录中出现明确有害行为时必须给出对应负 delta，不得因"怕影响用户心情"而回避（与既有"不要因为温和而回避减分"一致）。
- 保留既有的「输出前维度硬校验」步骤与"维度数量不得明显缩水"要求，**但不得再加入任何"某类维度负 delta 归零"的规则**。

**A2-5 · 封顶 100 / 下限 0**

`Attribute.max_value` 字段**已存在**（默认 100），**无需加列**。所有写属性值的位置必须把新值夹到 `[0, attr.max_value]`：

- `judge_service.confirm`（置信度加权入账）
- `judge_service._handle_unrealistic`（诚信扣分）
- `judge_service.delete_event`（回滚，负向）
- `goal_service` 的 achieve / fail 结算
- `onboarding_service.confirm_adjustment`
- `challenge_service` 的加点结算（本批新增）
- **B5 停滞扣分**（本批新增）

**统一做法**：在 `judge_service` 里加一个小工具 `def _clamp_attribute_value(value: float, max_value: float) -> float: return max(0.0, min(max_value, value))`，各处调用，**不要各写各的**。

**A2-6 · 段位随属性返回**

`GET /api/attributes` 每项新增 `tier`（段位名）**一个字段**（`app/routers/attributes.py` + `app/schemas`），**不改任何既有字段**。**不要新增 `group` 字段**（分组已作废）。段位定义放 `app/constants.py`：

```python
# 段位（0~100 分 5 档，用于回答"我点数算多还是少"）
ATTRIBUTE_TIERS = [
    (0,  20,  "入门"),
    (20, 40,  "见习"),
    (40, 60,  "熟练"),
    (60, 80,  "精通"),
    (80, 101, "大师"),
]

def tier_of(value: float) -> str:
    """按当前值返回段位名。"""
```

**验收标准（必须用真实 DeepSeek 验证并给出证据）**：

1. **熬夜双扣（本次修正的核心验证）**：提交"熬夜到 3 点"→ 判定结果**同时**包含 `健康 −0.5` 与 `智力 −0.4` 左右**两项负 delta**；附"输入 → 输出 JSON"证据
2. **负面行为不再被免疫**：构造一条明确负面记录（如"连续三天没学习，一直在打游戏"）→ 智力等能力维度**出现负 delta**（若仍为 0，说明 A2-4 没做到位）
3. **浮动有据**：同一锚点在不同强度输入下 delta 不同，且「加权推导」说明了强度系数的取值理由
4. **不因沉默扣分**：把某维度全部流水时间改到 60 天前、且不提交任何事件 → 属性值**纹丝不动**（无日历衰减）
5. **封顶与下限**：把某维度 `current_value` 手动设为 99.5，confirm 一条 `+2` 判定 → 落库值 **100.0（不是 101.5）**、`attribute_history.value_after=100.0`；反向把某维度设为 0.3，confirm 一条 `−2` → 落库值 **0.0（不为负）**
6. `GET /api/attributes` 每项含 `tier`；`智力=72.95` → `tier="精通"`；**响应中不存在 `group` 字段**

### A3 · 日常事件与连续日记赚币（决策 12）

**A3-1 · 事件确认入账给币**

在 `POST /api/judgments/{id}/confirm`（`app/routers/judgments.py` L136）成功入账后追加：

- 取该判定 `final_changes` 的**净 delta 总和**：
  - 净 delta **> 0** → `coin_service.grant(db, user, +2, source='event_confirm', reason=f"记录「{事件标题}」", ref_type='event', ref_id=event.id)`
  - 净 delta **≤ 0** → **不给币，也不扣币**（决策 13：负面不扣）
- **幂等**：confirm 已 confirmed 的判定仍返回 409（现有行为），天然不会重复发币

**A3-2 · 连续写日记里程碑**

新建 `app/services/coin_service.py::check_journal_streak(db, user)`（在**日记事件创建并判定后**调用，或由 `GET /api/coins` 惰性触发）：

- 统计**最近连续有日记（`source='journal'`）的天数**（按 `created_at` 自然日，允许当天尚未写）
- 首次达到 **3 天** → `+10 币`（`journal_streak`, reason="连续写日记 3 天"）；首次达到 **7 天** → `+30 币`
- **幂等**：以 `coin_ledger` 中是否已存在对应 reason 的记录为准（reason 用固定文案如 `连续写日记 3 天`，查重后不重复发放）

**验收标准**：确认一条净 delta>0 的判定 → `GET /api/coins` 余额 +2 且流水有 `event_confirm`；确认一条净 delta<0 的 → 余额不变、**无流水**；连续日记达 3 天 → 发放一次 +10，再次触发不重复。

---

## 四、批次 B · 后端：挑战与商店

### B1 · 挑战数据模型

**新建 ORM 模型 `Challenge`**（表名 `challenges`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | |
| `user_id` | ForeignKey("users.id") | |
| `scope` | String(10) | `daily` / `weekly` |
| `period_key` | String(20) | 归属周期：日=`2026-09-28`，周=`2026-W40`（用于过期与"每天换新"） |
| `title` | String(120) | 挑战名，如"向陌生人做一次小采访" |
| `description` | Text | 具体内容（做什么、对谁、多久） |
| `difficulty` | Integer | 1~5（AI 按事件自定，档数不必统一） |
| `coin_reward` | Integer | 完成可得金币（**接受前展示**） |
| `deposit` | Integer | 押金 |
| `related_attributes` | JSON | AI 预期影响的维度（**仅内部与结算用，不预览给用户**） |
| `ai_reason` | Text | 为什么给你这个挑战（**展示给用户**，个性化说服力所在） |
| `status` | String(20) | `candidate` / `accepted` / `settled` / `expired` / `abandoned` |
| `accepted_at` / `resolved_at` | DateTime nullable | |
| `expires_at` | DateTime | 候选与承诺的截止时间 |
| `event_id` | ForeignKey("events.id") nullable | 完成时创建的记录（复用判定链路） |
| `judgment_id` | ForeignKey("ai_judgments.id") nullable | 完成判定 |
| `outcome` | String(20) | `done` / `partial` / `excused` / `retreated`（结算后写入） |
| `outcome_note` | Text | AI 的判定说明（展示给用户） |
| `created_at` / `updated_at` | DateTime | |

**新建 ORM 模型 `ShopItem`**（表名 `shop_items`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` / `user_id` | | |
| `name` | String(120) | 物品名，如"奶茶（大杯）" |
| `kind` | String(10) | `preset` 常驻预置 / `custom` 用户自录 |
| `price_yuan` | Float nullable | 现实价格（元）；自录时由用户填，AI 定价的输入 |
| `coin_price` | Integer | AI 定出的金币价（用户可改） |
| `pricing_reason` | Text | **AI 定价理由（必须展示）** |
| `worth_note` | Text | AI 的"值不值得买"判断（如"本月已兑换 2 次，建议缓一缓"） |
| `enabled` | Boolean | 停用不删除 |
| `sort_order` | Integer | |
| `created_at` / `updated_at` | DateTime | |

**新建 ORM 模型 `Redemption`**（表名 `redemptions`，兑换券）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` / `user_id` / `shop_item_id` | | |
| `coin_spent` | Integer | 兑换消耗（快照，防物品改价影响历史） |
| `status` | String(10) | `pending` 待兑现 / `fulfilled` 已兑现 |
| `redeemed_at` / `fulfilled_at` | DateTime nullable | |
| `note` | Text | 用户备注（兑现时可写） |

**同步交付**：`sql/schema.sql` 补三张表建表语句；`app/schemas/__init__.py` 增 `ChallengeOut` / `ChallengeResolveIn` / `ShopItemIn` / `ShopItemOut` / `RedemptionOut`。

**验收标准**：启动后三张表自动创建；**现有 31 条事件与 31 条判定零影响**（判定中心回归正常）。

### B2 · 挑战生成（AI prompt）

**新建 `app/prompts/challenge.py`**：

- `CHALLENGE_SYSTEM_PROMPT`（挑战设计师角色）
- `build_challenge_messages(scope, profile_context, attributes_context, recent_events, recent_memory, existing_titles)`

**注入上下文**：用户画像 / 当前属性值（**含最低的 3~5 维，作为短板提示**）/ 近期事件摘要 / 长期记忆 / **已给出或已完成的挑战标题**（防重复）

**输出 JSON 契约**（严格）：

```json
{
  "challenges": [
    {
      "title": "向陌生人做一次小采访",
      "description": "在校园里找一位不认识的同学，聊 5 分钟，了解他/她的专业或爱好。",
      "difficulty": 3,
      "coin_reward": 10,
      "deposit": 10,
      "related_attributes": ["情商", "开放性"],
      "reason": "你的记录显示社交面偏窄、开放性近期无变化，小剂量社交暴露对你是性价比最高的挑战。"
    }
  ],
  "summary": "本轮挑战围绕社交暴露与作息调整设计。"
}
```

**prompt 硬性要求**（写进 system prompt）：

1. **具体可执行**：必须有明确动作、对象、时长（"采访一位陌生人，聊 5 分钟" 而非 "多社交"）
2. **略超舒适区但不危险**：不涉及违法、危险、大额花钱、冒犯他人
3. **可自证**：用户写一句话就能说清做没做、做到什么程度
4. **对准短板**：优先针对当前值最低的维度与近期缺失的生活面
5. **不重复**：不得与 `existing_titles` 中的挑战重复或高度相似
6. **档次**：`difficulty` ∈ [1,5]，**档数按内容自然分布，不必凑满 5 档**；`coin_reward` / `deposit` **必须落在下方参数表内**
7. **格式**：JSON、**禁止全角引号**（沿用现有格式警告）

**金币参数表（AI 必须按档取值，不得自由发明）**：

| 类型 | difficulty | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 日挑战 | `coin_reward` | 5 | 8 | 10 | 13 | 15 |
| 日挑战 | `deposit` | 5 | 7 | 10 | 12 | 15 |
| 周挑战 | `coin_reward` | 30 | 35 | 40 | 45 | 50 |
| 周挑战 | `deposit` | 15 | 20 | 25 | 30 | 35 |

**服务层 `app/services/challenge_service.py::generate(db, scope, force=False)`**：

- 生成本期候选：日挑战 **3 条**、周挑战 **2 条**
- **幂等**：若本 `period_key` 下已有 `candidate`/`accepted` 挑战且 `force=False` → 直接返回现有列表，**不重复调用 LLM**
- `force=True`（用户点"再来一批"）→ 仅对**已结算/已过期**的位置补生成，**不覆盖仍在进行中的挑战**；`existing_titles` 需含本期已给过的全部标题
- 落库后返回列表

**验收标准（必须真实调用 DeepSeek 并给出证据）**：
1. `POST /api/challenges/generate?scope=daily` → 返回 **3 条**，每条含 `title/description/difficulty/coin_reward/deposit/related_attributes/reason`；`coin_reward`/`deposit` 与参数表完全一致
2. 同一 `period_key` 内重复调用 → **不新增**（返回同一批）；附第二次调用**无新增 LLM 请求**的证据（日志或计数）
3. **个性化验证**：当前值最低的维度是 `审美`（50.0）与 `质量类低分项`，生成结果中至少有一条挑战的 `related_attributes` 命中低分维度，且 `reason` 引用了该短板
4. **不重复验证**：`force=True` 后新一批的 `title` 与旧批不重复

### B3 · 接受 / 押金 / 完成判定 / 结算 / 过期

**状态机（务必严格）**：

```
candidate ──接受(扣押金)──> accepted ──完成并确认结算──> settled
    │                          │
    │过期未接受                 │过期未处理
    v                          v
 expired                    expired        （押金没收 + 按难度扣点，无需 LLM）
    │                          │
    └──────(abandon 主动放弃)──> abandoned  （押金没收 + 按难度扣点）
```

**B3-1 · 接受（`POST /api/challenges/{id}/accept`）**

1. 校验：状态必须是 `candidate` 且未过期
2. 余额校验：`balance >= deposit`，否则 **400**「金币不足（需 N 币，当前 M 币）。可以先记录日常事件或写日记攒币。」
3. `coin_service.grant(-deposit, source='challenge_deposit', reason=f"接受挑战「{title}」押金", ref_type='challenge', ref_id=id)`
4. `status='accepted'`, `accepted_at=now`
5. `expires_at` 重设为周期末（日挑战当天 23:59:59；周挑战当周周日 23:59:59）

**B3-2 · 完成（`POST /api/challenges/{id}/complete`，body `{note}`）**

用户写一句话自述 → **一次 LLM 调用**完成"是否达成"判定（**不要拆成两次调用**，判定耗时 20~60s，两次会不可接受）。

**新建 prompt（并入 `app/prompts/challenge.py`）**：`build_completion_messages(challenge, note, today_events_context)`

输出 JSON：

```json
{
  "outcome": "done",
  "explanation": "用户描述在食堂与一位陌生同学聊了约 8 分钟，包含专业与爱好，符合挑战要求。",
  "confidence": 0.88,
  "confidence_reason": "",
  "affected_attributes": [
    {"name": "情商", "delta": 1.5, "reason": "主动发起陌生社交并有实质交流", "evidence": "社交暴露练习对 EQ 的有效性"}
  ],
  "summary": "挑战达成，社交面得到真实扩展。"
}
```

`outcome` 四值判定标准（写进 prompt）：

| outcome | 触发条件 | 结算 |
|---|---|---|
| `done` | 如实达成挑战目标 | 退押金 + 全额金币 + 加点 |
| `partial` | 做了但未达标（如时长不够、深度不足） | 退押金 + **无金币** + **加点 ≤ 标准的一半** |
| `excused` | 突发意外导致无法完成，且说明合理 | 退押金 + 无金币 + **不加点** |
| `retreated` | 临时退缩、找借口、说明明显不成立 | **没收押金** + **按难度等比扣点**（见下） |

**服务层 `challenge_service.resolve(db, challenge, note)`**：

1. 创建 `Event`（`source='form'`, `title=f"挑战：{challenge.title}"`, `content=note`, `params={"_challenge_id": challenge.id}`）→ 记入 `event_id`
   - `params` 的 `_` 前缀键已被 `format_event_description` 跳过，**不会污染判定输入**
2. 调 LLM（上面那个 prompt）→ 解析 `outcome` / `explanation` / `affected_attributes`
3. 复用 `judge_service._parse_changes` + `_clamp_delta` + `_clamp_attribute_value`（封顶）——**禁止另写一套解析**（v1.5 B-03「多入口必须同一写入语义」）。**注意：09-29 修正后不再有"积累型过滤"这一步**
4. 按 `outcome` 调整 `changes`：
   - `partial` → 每条 delta 乘以 `0.5` 后取整到 0.5
   - `excused` → `changes = []`
   - `retreated` → delta 取**负值**，幅度 = `min(该挑战 related_attributes 的预期加分量, 1.5)`；**无维度分组，全维度可扣**（09-29 修正后不存在"积累型跳过"）
5. 创建 `AIJudgment(status='pending', suggested_changes=changes, analysis=[explanation], confidence=..., confidence_reason=..., summary=...)` + `judge_service._log(..., action='create')` → 记入 `judgment_id`
6. `challenge.status='accepted'` 保持不变，**等待用户确认结算**（遵守"AI 建议 → 用户确认 → 才入账"原则）

**B3-3 · 结算（`POST /api/challenges/{id}/settle`）**

用户点「确认结算」后：

1. **加点**：复用 `judge_service.confirm(db, judgment)`（置信度加权 + 低置信度拦截 + 写 `attribute_history` + 审计）——**必须复用，不得另写**
2. **押金 / 金币**：
   - `done` → `grant(+deposit, 'challenge_refund')` + `grant(+coin_reward, 'challenge_reward')`
   - `partial` / `excused` → `grant(+deposit, 'challenge_refund')`（无奖励）
   - `retreated` → 押金不退（`grant` 在 accept 时已扣，此处仅写一条 `challenge_forfeit` 的 0 值留痕说明）
3. `challenge.status='settled'`, `resolved_at=now`, `outcome`, `outcome_note`
4. 返回 `{outcome, explanation, coins_delta, balance, applied_changes}`

**B3-4 · 放弃（`POST /api/challenges/{id}/abandon`，body `{note?}`）**

- 若带 `note` → 走与完成相同的 LLM 判定，允许 `excused`（有正当理由）或 `retreated`
- 若不带 `note` → **直接按 `retreated`** 处理（没收押金 + 扣点），`outcome_note="用户主动放弃"`
- `challenge.status='abandoned'`

**B3-5 · 过期（惰性结算，无需 LLM）**

- 任何查询挑战的接口在返回前，先把 `expires_at < now` 且状态为 `candidate` 的置为 `expired`（无需任何结算）
- `accepted` 且过期的 → 置 `expired`，**押金没收** + **按难度扣点**（走 `retreated` 同一套：幅度 ≤1.5、全维度可扣）+ 写一条 `challenge_forfeit` 留痕
- **必须幂等**：同一挑战只结算一次（以状态判断）

**验收标准（必须真实调用 DeepSeek 并给出证据）**：
1. **完整闭环**：生成 → 接受（余额 −押金）→ 完成并写自述 → 结算 → 余额 = 原余额 −押金 +押金 +奖励，且 `attribute_history` 有对应加点、`coin_ledger` 有押金/返还/奖励三条
2. **退缩惩罚**：接受后调 `abandon`（不带 note）→ 押金不退（`challenge_forfeit` 留痕）、相关维度被扣分（**无分组限制**）；附证据
3. **`excused` 不惩罚**：接受后 `abandon` 且说明"突发急事/身体不适" → 押金**全额退回**、不加点不扣点
4. **余额不足**：把余额调成 3，接受一个押金 10 的挑战 → **400** 且提示文案正确，余额不变
5. **过期幂等**：手动把 `expires_at` 改成过去时间，连续查询两次 → 只结算一次（`coin_ledger` 只多一条 `challenge_forfeit`）
6. **老数据零影响**：`events` 仍为 31 条（+ 挑战产生的记录），判定中心打开正常

### B4 · 商店（现实奖励 + AI 定价 + 兑换券）

**B4-1 · 常驻物资预置**

预置若干 `kind='preset'` 物品（**首次访问商店时幂等写入**，参考 `anchor_service` 的种子模式）。建议清单（可由用户改价/停用）：

| 物品 | 现实价格 | 说明 |
|---|---|---|
| 奶茶（大杯） | 15 元 | |
| 一顿想吃的正餐 | 40 元 | |
| 一部电影（影院） | 45 元 | |
| 一小时游戏时间 | 0 元 | 时间型奖励 |
| 睡到自然醒（一个上午） | 0 元 | 时间型奖励 |

**B4-2 · AI 定价（`POST /api/shop/items`）**

请求：`{name, price_yuan}`（`kind='custom'`）

服务层 `shop_service.price_item(db, user, name, price_yuan)` → **一次 LLM 调用**（新建 `app/prompts/shop.py`）：

**输入上下文**：物品名 / 现实价格 / **用户最近的兑换历史**（近 30 天兑换次数、近期同类物品频率）/ 用户近期状态（属性值、长期记忆摘要）

**输出 JSON**：

```json
{
  "coin_price": 30,
  "pricing_reason": "按 1 元 ≈ 2 币的隐含基准，15 元奶茶约 30 币；已按你的近期金币获取速度（日均约 5 币）折算为约 6 天挑战量。",
  "worth_note": "你本月还没喝过奶茶，奖励自己一杯没问题。"
}
```

**prompt 硬性要求（决策 15 的核心）**：

1. **不设固定汇率**，由 AI 综合判断给出金币数；但需**给出可理解的折算逻辑**（写进 `pricing_reason`）
2. **必须考虑情境浮动**：
   - **健康/节制导向**：若近 30 天已兑换同类多次（如已换 3 杯奶茶）→ **提高价格** 并在 `worth_note` 说明（如"本月已兑换 3 次，建议把价格提到 50 币，或换成别的奖励"）
   - **正向激励**：若长时间未兑换（如本月一次没换）→ **适度降低**门槛，鼓励正当犒赏
3. **`worth_note` 必须输出"值不值得买"的判断**，允许出现**劝阻**（如"这个月预算紧、且刚换过两次，建议先不换"）——**这是本功能的价值观所在，不得写成中性废话**
4. `coin_price` 为正整数；`price_yuan` 为 0 的时间型奖励，按"占用时长 + 稀缺度"定价

**用户可改价**：`PUT /api/shop/items/{id}` 支持直接改 `coin_price`（并记录 `pricing_reason` 追加"（用户手动调整为 N 币）"）

**B4-3 · 兑换（`POST /api/shop/items/{id}/redeem`）**

1. 校验 `enabled` 且 `balance >= coin_price`
2. `coin_service.grant(-coin_price, source='shop_redeem', reason=f"兑换「{name}」", ref_type='shop_item', ref_id=id)`
3. 创建 `Redemption(status='pending', coin_spent=coin_price, redeemed_at=now)`
4. 返回该券（前端展示为"奖励券"）

**B4-4 · 兑现（`POST /api/redemptions/{id}/fulfill`，body `{note?}`）**

- `status='fulfilled'`, `fulfilled_at=now`；仅状态变更，不再动金币
- **幂等**：已 fulfilled 再调 → 200 返回当前状态，不重复处理

**接口清单**（新建 `app/routers/shop.py`）：
`GET /api/shop/items` / `POST /api/shop/items`（触发 AI 定价）/ `PUT /api/shop/items/{id}` / `DELETE /api/shop/items/{id}`（停用）/ `POST /api/shop/items/{id}/redeem` / `GET /api/redemptions` / `POST /api/redemptions/{id}/fulfill`

**验收标准（必须真实调用 DeepSeek 并给出证据，重点验证"情境浮动"）**：
1. 录入「15 元奶茶」→ 返回 `coin_price`（30 上下）、`pricing_reason` 非空、`worth_note` 有明确判断
2. **情境浮动验证（关键）**：先将"奶茶"兑换 3 次，再**重新定价**同一物品 → `coin_price` **高于**首次定价，且 `worth_note` 出现"已兑换多次/建议缓一缓"类表述；附两次输出对比证据
3. **劝阻能力验证**：某物品价格明显偏高（如 200 元大餐）→ `worth_note` 出现理性劝导表述
4. 兑换 30 币的奶茶 → 余额 −30、`coin_ledger` 有 `shop_redeem`、`redemptions` 新增 `pending` 券；点「已兑现」→ `status='fulfilled'`，**余额不再变动**
5. 余额不足时兑换 → 400 且余额不变

### B5 · 停滞觉察与问询（替代"时间衰减"；09-29 修正新增）

> **设计来源**：用户提出"一个月没记录学习，可能真的就是没学，那智力下降也算吧"。但**"没记录"与"没做"是两件事**——自动衰减会冤枉"学了但忘了记"的情况。故改为**问询制**：发现停滞 → AI 主动问 → **用户确认才扣分**。

**B5-1 · 停滞检测（新建 `app/services/stagnation_service.py`）**

```python
STAGNATION_DAYS = 30            # 距上次相关记录超过此天数 → 视为停滞
STAGNATION_COOLDOWN_DAYS = 90   # 同一维度两次问询的最小间隔

def detect(db, user) -> list[dict]:
    """返回停滞维度列表：[{"name": "智力", "days": 34, "last_at": "2026-08-26T..."}]。

    判定方式：对 attributes 中每个维度，取 attribute_history 里该维度最后一条
              created_at；若该维度无任何流水，则用 user_profiles.created_at 起算。
    排除：用户已关闭判定的维度（disabled_attributes）、以及处于冷却期内的维度。
    """
```

**B5-2 · 接口**

- `GET /api/stagnation` → `{"items": [{"name", "days", "last_at"}]}`（惰性刷新；已问过的维度在冷却期内不再列出）
- `POST /api/stagnation/{name}/answer`，body `{"stopped": true|false, "note": ""}`

**分支处理（务必严格）**：

| 用户回答 | 处理 |
|---|---|
| `stopped=true`（确实停了） | ① **小幅扣分**：`delta = −0.3` → 写 `attribute_history`（**`event_id=NULL`**，`reason="停滞确认：该维度 N 天无相关记录"`）→ ② **生成一条"补课挑战"**：调 `challenge_service` 生成 `scope='weekly'`、`related_attributes=[该维度]`、`ai_reason` 写明停滞事实（如"你的智力维度 34 天没有相关记录了，这条挑战帮你重新启动"） |
| `stopped=false`（在学只是没记） | **不扣分、不写任何属性流水**；返回 `{"suggest_record": true}`，前端引导跳转记录页；**重置**该维度停滞计时 |

**幂等与审计（重要——注意 `judgment_logs.judgment_id` 是 NOT NULL）**：

- 问询历史**记在 `settings` 表**（`key='stagnation_checks'`，`value={"智力": "2026-09-29T10:00:00"}`）——**不要**往 `judgment_logs` 写（该表 `judgment_id` 非空，停滞扣分没有对应判定，硬写会破坏外键语义）
- 同一维度在 `STAGNATION_COOLDOWN_DAYS` 内**只问一次**；重复 `answer` 幂等返回，不重复扣分

**与"不因沉默扣分"的关系（务必理解，否则会实现错）**：

- 属性值**不会**因为时间流逝自动变化（A2 验收标准 4 保证这一点）
- 扣分**只发生在用户亲口确认"确实停了"之后**——此时"用户的确认"就是触发扣分的那个"事件"

**验收标准**：

1. 把某维度最后一条 `attribute_history.created_at` 改为 40 天前 → `GET /api/stagnation` 列出该维度及天数
2. `answer {stopped: true}` → 该维度 **−0.3**、`attribute_history` 新增一条 **`event_id=NULL`** 的记录（附证据）；**不产生新事件**（`events` 条数不变）
3. `answer {stopped: false}` → **无属性流水、无扣分**；再次 `GET /api/stagnation` 该维度不再出现
4. 冷却期内重复询问 / 重复回答 → 幂等，**不重复扣分**
5. 已关闭判定的维度**不出现**在停滞列表中

---

## 五、批次 C · 前端

### C1 · 新 tab「挑战」

- `frontend/src/App.vue` 的 `tabs` 数组在「目标」之后插入 `{ key: 'challenge', label: '挑战' }`；导入并挂载新组件 `<ChallengeView v-else-if="activeTab === 'challenge'" />`
- 新组件 `frontend/src/components/ChallengeView.vue`，内部用**分段控件**切两个区：**「挑战」/「商店」**（金币余额常驻顶部，两个区都能看到）

**顶部金币条**：`金币 128` + 点击展开**流水 drawer/section**（`GET /api/coins`，按 `source` 分组、正绿负灰——**注意本项目是"涨红跌绿"的中国习惯，但金币非股票，建议正值用绿色正向色、消耗用灰色，不做红绿歧义**）

**挑战区**：
- 两组：**日挑战**（3 张）/ **周挑战**（2 张）
- 每张候选卡显示：`title` / `description` / **难度徽章**（1~5）/ **`完成可得 +N 币`**（决策 10：金币提前显示）/ **押金 N 币** / `ai_reason`（"为什么给你这个"）/ `[接受挑战]`
- **不显示加点预览**（决策 10）
- 已接受的卡：显示截止时间 + 一句话自述输入 + `[我完成了]` / `[放弃]`；判定返回后显示 `outcome_note` 与加点明细 + `[确认结算]`（调用 settle）
- 已结算/已过期卡：置灰，显示 `outcome` 徽章（达成/部分达成/意外豁免/未完成）与说明
- 底部：`[再来一批]`（`generate?force=true`，仅补空缺）+ `[刷新]`
- **提交交互必须复用 v1.7 C 的成果**：提交期间按钮变「AI 正在分析…」+ 禁用 + 可取消（判定耗时 20~60s，**不得回退**）

### C2 · 商店区

- 物品卡：名称 / 现实价格 / **金币价** / `pricing_reason`（定价理由，**必须展示**）/ `worth_note`（值不值得买，**必须展示**，若有劝阻语义用醒目但不刺眼的提示色）
- `[兑换]` → 二次确认（显示"将消耗 N 币，余额将剩 M 币"）→ 成功后弹出"奖励券"
- **奖励券列表**：待兑现 / 已兑现 两栏；待兑现券有 `[已兑现]` 按钮
- `[+ 添加我想要的东西]`：填名称 + 现实价格 → 提交后**展示 AI 定价过程**（loading："AI 正在为它定价…"）→ 回填 `coin_price` 与理由，允许用户手动改价

### C3 · 段位显示（配合 A2）

- `frontend/src/components/AttributePanel.vue`：每个维度名旁显示段位徽章（如 `智力 · 精通`），数据取 `GET /api/attributes` 新增的 `tier`
- **只加不改**：**不调整**雷达图/趋势图/热力图的任何配置（V1/V2/V3 本轮禁区），段位只以文字徽章形式出现

### C4 · 停滞提示卡（配合 B5）

- 挑战 tab 顶部（金币条下方）：若 `GET /api/stagnation` 有 items，显示提示卡，文案如：
  「**智力已经 34 天没有相关记录了** — 是真的停了，还是忘了记？」+ 两个按钮 `[确实停了]` / `[在学，只是没记]`
- `[确实停了]` → `answer {stopped:true}` → 显示扣分明细（−0.3）与新生成的补课挑战（跳转挑战区并高亮该卡）
- `[在学，只是没记]` → `answer {stopped:false}` → 不扣分，弹一个"去补记"的入口
- **文案必须中性、不指责**（"是真的停了，还是忘了记？"，而不是"你已经荒废 34 天"）——与"引导者而非裁判"的产品定位一致

**批次 C 验收标准**：
1. `npm run build` 零错误；新增 tab 可切换，两个区都能正常加载
2. 候选卡显示"完成可得 +N 币"与押金，**不显示加点**；接受后余额立即减少并可看到流水
3. 完成 → 自述 → 判定中按钮变「AI 正在分析…」且禁点 → 结算后卡上显示 outcome 与加点明细
4. 商店物品卡显示定价理由与"值不值得买"；兑换后奖励券出现在"待兑现"，点「已兑现」后转入"已兑现"
5. 属性面板每个维度旁显示段位徽章，**雷达图/趋势图/热力图与改造前完全一致**（附截图对比）
6. 停滞提示卡出现在挑战 tab 顶部；`[确实停了]` → 显示 −0.3 扣分与新补课挑战；`[在学，只是没记]` → 无扣分且有补记入口

---

## 六、全局验收与交付要求

1. **每批次完成后**：
   - 后端：`py_compile` 全部改动文件 + 启动服务实测相关接口（附 curl 或日志证据）
   - 前端：`npm run build` 零错误
   - **老数据回归**：启动后确认 **31 条事件 / 31 条判定**在判定中心、手账本、事件列表、今日盘点**全部正常显示**（附说明）
2. **LLM 相关改动（B2 生成 / B3 完成判定 / B4 定价）必须用真实 DeepSeek 调用验证**，给出"输入 → 输出 JSON"证据；**B4 的"情境浮动"与"劝阻"能力是必验项**
3. **一致性铁律**：
   - 金币只有 `coin_service.grant()` 一个写入口
   - 挑战的加点结算必须复用 `judge_service.confirm()`
   - 属性值写入必须统一走 `_clamp_attribute_value`（封顶 100 / 下限 0）
   - **任何"更新"语义不得用"先删后建"实现**（v1.5 B-03 教训）
   - **不得实现任何"某类维度免扣"的逻辑**（09-29 修正：分组方案已作废，13 维一律可涨可跌）
4. **一键启动**：`start.bat` / `start.sh` 保持可用；启动后 `GET /api/health` 正常；启动日志出现 `[migrate]` 新增列与新建表记录
5. **数据库迁移**：**严禁要求用户删库重建**；`user_profiles.coins` 由 `migrate_schema` 回填 0
6. **文档回写**：完成后
   - `README.md` 勾选本轮完成状态
   - `docs/DECISIONS.md`：把「Backlog：v1.7 实测反馈」中的 **G1（游戏化）** 勾选并简述实现；**N1（只增不减）** 勾选并写明最终采用"**取消分组 + 全维度可涨跌（事件驱动）+ 锚点升级 + 封顶/段位 + 停滞问询**"（**不要再写"分层"**）；把 **成就 / 豁免券 / 满级拆分** 显式登记为 v1.9 待办；**U1/U2/U3 与 V1/V2/V3 保持未完成并注明"用户已确认延后"**
   - 若有与原设计的偏离或新发现，追加记录
7. **不确定处**：写 `TODO` 注释 + 记入 `docs/DECISIONS.md`，**不要自行扩大功能边界**

---

## 七、遗留（本轮明确不做，勿动）

| 项 | 状态 |
|---|---|
| 成就系统（累计型 + AI 发现型；奖励金币 + 徽章；称号/徽章挂角色档案） | **v1.9** |
| 豁免券（时段券；事前买；AI 判动机浮动，可提价或扣少量属性点） | **v1.9** |
| 属性满 100 拆分子维度（AI 提议 + 用户确认，需 `parent_id` 维度层级 + 面板改版） | **v1.9** |
| 月挑战 | 用户口径"看情况"，未定 |
| U1 今日盘点与记录事件合并（痛点已确认：**职责重叠**） | 用户确认延后 |
| U2 打卡项目管理迁出设置 | 用户确认延后（随 U1） |
| U3 每日任务清单与目标/每日事项结合 | 用户确认延后 |
| V1 雷达图排版 / V2 成长趋势图 / V3 活动热力图 | 未选入本轮 |
| 主题 / 皮肤 / 桌宠 | 待单独评估（桌宠为独立工程） |
| 饮食拍照识别 / AI 分析流式显化 / 定时提醒 / 低置信度只提醒一次 | 历史遗留，未定 |
