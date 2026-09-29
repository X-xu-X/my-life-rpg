# 开发计划 v1.9 —— v1.8 实测修复与增强

> **决策来源**：2026-09-29 与用户的 6 轮逐条访谈（每轮均附推荐与理由，全部结论见第一章）
> **backlog 记录**：`docs/DECISIONS.md`「Backlog：v1.8 实测反馈（2026-09-29 晚）」F1~F5
> **代码基线**：v1.8 已交付（HEAD `567a30b`，2026-09-29），本轮在其之上修补与增强
> **本轮范围**：**F1~F5 五条一次做完**（用户 2026-09-29 明确选择）
> **版本说明**：原登记的 v1.9 三项（成就 / 豁免券 / 属性满级拆分）**顺延为 v1.10**——想法已在 `DECISIONS.md` 存好，写 v1.10 文档时不必重问

本轮的性质是**"用户真实用过一轮之后的修补"**：v1.8 主闭环（挑战 → 金币 → 兑换）能跑通，但交互反馈、经济开局、搜索可用性、挑战颗粒度四处的手感不对。**不新增玩法**。

---

## 〇、总原则（必须遵守）

1. **数据红线**：`game_of_life.db` 是真实生活数据，**禁止物理删除**；新增表走 `create_all`、加列走 `migrate_schema`；任何批量操作前**先整库备份到 `backups/`**。
2. **兼容过渡**：老数据必须容忍新字段为空。`events.origin` 为 NULL 表示"普通事件"（等价旧行为）；`challenges.variants` 为空表示"单档挑战"（等价旧行为）。
3. **一个 commit = 一个逻辑单元**，中文 message `类型: 简述`（如 `feat(A2): 事件来源标记 events.origin`）。
4. **一致性铁律**（v1.5 B-03 教训，不得违反）：
   - 金币只有 `coin_service.grant()` 一个写入口
   - 属性值写入统一走 `judge_service._clamp_attribute_value`
   - 挑战加点必须复用 `judge_service.confirm()`
   - 任何"更新"语义**不得用"先删后建"实现**
5. **不得顺带做本轮之外的事**（禁区清单）：
   - ❌ 不动属性数值模型（v1.8 刚定稿：13 维一律可涨可跌、封顶 100、段位）
   - ❌ 不动雷达图 / 成长趋势图 / 活动热力图（V1~V3 未启动）
   - ❌ 不做 U1 页面合并（「今日盘点」与「记录事件」仍是两个 tab）
   - ❌ 不改 `COIN_TABLE` 的档位数值（金币经济参数本轮冻结）
   - ❌ 不给挑战事件加任何"免扣 / 额外加成"特例
   - ❌ 不调整 13 个属性维度本身（名称、数量、别名）

---

## 一、决策表（F1~F5，逐条可追溯）

### F1 · 金币初始值改为「AI 依据问卷给出，80~200」

| # | 决策 | 结论 |
|---|---|---|
| F1-1 | 数字由谁定 | **由 AI 在 onboarding 生成属性面板的同一次调用里一并给出**（新增输出字段 `initial_coins` + `initial_coins_reason`），不额外增加 LLM 调用 |
| F1-2 | 取值范围 | **保底 80 ~ 上限 200**（整数）。AI 在此区间按问卷自由裁量，**必须给理由** |
| F1-3 | 为什么是这个区间 | 保底 80 = 保证新人**无论问卷如何**都能完整走通一次「接受最高难度周挑战（押金 35）→ 兑换一件中档奖励（40）」闭环；上限 200 ≈ 一周满打满算的收入（约 150~180），再高会让新人觉得"不做挑战也够花"、削弱挑战动力 |
| F1-4 | 现有账号 | **一律不动**。当前账号已领固定 50（流水 id=1，余额 40），新规则**只对以后新建的档案生效** |
| F1-5 | 已排除方案 | ① 按"低于 60 分的维度数 × N"计算（用户否决："为什么要维度低于 60 的来算金币呢"）；② 按"问卷认真程度"计分（用户未选）；③ 固定值（不满足"每个人不一样"） |

### F2 · 全站交互反馈规范

| # | 决策 | 结论 |
|---|---|---|
| F2-1 | 反馈形式 | **右上角浮出提示（toast）**，约 3 秒自动消失、不阻塞操作 |
| F2-2 | 失败提示 | 保留各页顶部 `error` 横幅（就近可读），同时浮出一次 toast |
| F2-3 | 覆盖范围 | **全站统一规范**：所有会发请求的按钮都必须有"进行中"文案 + 成功/失败提示。**实现时需逐页核对**（清单见批次 B） |
| F2-4 | 首个修复点 | 挑战页 `generate` 按钮——当前**完全无反馈**（按钮禁用但文案不变、成功静默），是用户实测报的第一个问题 |

### F3 · 挑战难度从"单档"改为"一卡多档"

| # | 决策 | 结论 |
|---|---|---|
| F3-1 | 实现形态 | **一张卡 + 卡内切档**（用户确认，非"每档一张卡"） |
| F3-2 | 档数 | **AI 按内容自适应**（用户原话："有的任务不好分，那就两档也行啊，有的好分，那就五档"）——好分的给最多 5 档、不好分的给 2 档；实在无法分档可只给 1 档（退回单档行为） |
| F3-3 | 每档内容 | `{label 短标签, description 要求描述, difficulty 难度}`；**金币与押金由 `COIN_TABLE` 按该档 difficulty 派生**（AI 不得给数字） |
| F3-4 | 已接受的挑战 | **保留不动**——id=2「只写三项的今日清单」（difficulty=3、押金 10 已扣）按旧规则接受、旧规则结算 |
| F3-5 | 接受后 | **档位锁定**（`candidate` 期可切换，`accepted` 后拒绝改档） |

### F4 · 手账本搜索重构

| # | 决策 | 结论 |
|---|---|---|
| F4-1 | 位置 | **只改「手账本」页（`TimelineView.vue`）**。其他页面的搜索框保持现状（用户："其他感觉暂时没必要"） |
| F4-2 | 搜索范围 | 事件**标题 + 正文 + 类别 + 参数值**，并**包含判定内容**：分析过程（`analysis`）、总结（`summary`）、**加点理由与依据**（`suggested_changes` 的 `reason`/`evidence`）、`revision_notes`、`confidence_reason`、`merged_with` |
| F4-3 | 类型筛选 | 三态切换「**全部 / 只看事件 / 只看日记**」（事件 = `source='form'`；日记 = `source='journal'`） |
| F4-4 | 命中可读性 | 搜索时在摘要行下显示**命中片段**（关键词前后各约 20 字，关键词高亮）——解决"看不出为什么命中"的观感问题 |
| F4-5 | 实现方式 | **前端本地搜索**（复用已加载的 events + judgments），不新增后端接口；但需先核对判定列表接口是否返回了 `analysis` 等字段，缺则补 |

### F5 · 挑战事件加可见标签

| # | 决策 | 结论 |
|---|---|---|
| F5-1 | 现状澄清 | **"记入事件"v1.8 已实现**：`complete()`（L295-306）与 `_make_retreat_judgment()`（L466-470）都已创建 Event，四条 outcome 全覆盖且落在当天。**本轮只补"可见标签"** |
| F5-2 | 标签承载 | **新增 `events.origin` 字段**（走现有 `migrate_schema` 自动加列，无需删库重建），值 `challenge`；NULL 表示普通事件 |
| F5-3 | 展示位置 | 手账本、判定中心、记录页「最近记录」三处列表统一显示「挑战」小徽章 |
| F5-4 | 是否排除统计 | **不排除**：挑战事件照常计入热力图与周报（它也是真实发生的事）。**已确认挑战结算不走 `reward_event_confirm`**（`settle()` 调的是 `judge_service.confirm()`，而 `reward_event_confirm` 只由 `routers/judgments.py` 的 confirm 端点调用）→ 不存在"挑战记一次又拿一次日常 +2 币"的重复激励，**本轮无需改动** |

### F6 · 顺带修复（实现 A 批时一并处理）

| # | 问题 | 结论 |
|---|---|---|
| F6-1 | `PANEL_SYSTEM_PROMPT` 写"**12 项**"且维度列表**漏列「诚信」**，而 `constants.ATTRIBUTE_DIMENSIONS` 实际是 **13 维** | 改成"13 项"并补齐「诚信」。否则 AI 生成初始面板时可能不给诚信打分 |
| F6-2 | `PANEL_DISPUTE_SYSTEM_PROMPT` 写着"输出完整的、调整后的属性面板（含所有 **6 项**）" | 过时文案（早期 6 维时代的残留），改为"全部维度" |

---

## 二、批次划分与交付顺序

```
批次 A（后端 · 金币初始化 + 事件来源标记）  F1 + F5 + F6
批次 B（前端 · 全站交互反馈规范）            F2
批次 C（后端 + 前端 · 挑战多档）             F3
批次 D（前端 · 手账本搜索重构）              F4
```

**顺序理由**：A 是数据层（后面几批都依赖 `origin` 字段与金币逻辑）；B 是纯前端规范且能给后续 C/D 的开发过程提供反馈工具（自己调试时也更好用）；C 动挑战模型（改动面最大、风险最高，放在反馈规范之后，出问题看得见）；D 独立、最后做。

---

## 三、批次 A · 后端（金币初始化 + 事件来源标记）

### A1 · F1 金币初始化改为 AI 依据问卷给出

**A1-1 · prompt 改造（`app/prompts/onboarding.py` 的 `PANEL_SYSTEM_PROMPT`）**

输出格式新增两个字段：

```json
{
  "attributes": [
    {"name": "体能", "value": 62, "reason": "推导依据"}
  ],
  "initial_coins": 120,
  "initial_coins_reason": "给用户看的一句话说明",
  "summary": "整体评估总结"
}
```

新增规则（追加到「评分要求」之后）：

- `initial_coins` 是这位用户**建立角色档案时获得的启动资金**，必须是 **80（含）~ 200（含）之间的整数**。
- **判断依据**：综合问卷体现的**起点情况、提升空间、生活管理的紧迫程度与目标清晰度**，给出一个"能让他真正开始行动"的数。**不要机械套用单一指标**（不要写成"某项低于多少分就加多少"）。
- **必须用满区间、避免都挤在中间值**：不同问卷应当给出明显不同的数（同质化就失去了"每个人开局不一样"的意义）。
- `initial_coins_reason` 是**展示给用户看的**，要说明"为什么给你这个数"，语气自然、不评判、不贬低。
- 缺失或无法判断时给 **80**（保底）。

> ⚠️ **实现者注意**：Agent（本 AI）不干预具体数值算法——数值完全由 AI 按上述意图裁量。**不要**在代码里加"按短板数计算"之类的兜底公式（那是被用户否决的方案）；代码只做**区间夹取**。

**A1-2 · 服务层改造（`app/services/onboarding_service.py` 的 `_generate_panel`）**

`_generate_panel`（L126）当前：

```python
profile.initial_attributes_snapshot = {"attributes": panel, "summary": summary}
```

改为：

1. 从 LLM 返回里取 `initial_coins`，**夹到 `[80, 200]`**（`int`，非整数或缺失取 80）
2. 取 `initial_coins_reason`（字符串，缺省给一句通用文案）
3. 存入快照：`{"attributes": panel, "initial_coins": coins, "initial_coins_reason": reason, "summary": summary}`
4. **发放金币**（这是本批最关键的一步）：

```python
coin_service.grant(
    db, user, coins,
    source="onboarding_bonus",
    reason=f"角色档案建立，获得启动资金 {coins} 币 —— {reason}",
)
```

> **幂等保障**：`grant_startup_bonus_if_needed()`（`coin_service.py` L126）保留作为**兜底**——它以"ledger 中是否已有 `onboarding_bonus` 记录"判断，因此 onboarding 路径已发放时不会重复发放（`GET /api/coins` 也不会再补一次）。
>
> 兜底金额 `STARTUP_BONUS` 从 **50 上调为 80**（与新保底一致）：万一 onboarding 路径异常未发放，用户仍能拿到保底并走通闭环。

**A1-3 · 前端展示（`frontend/src/components/Onboarding.vue`）**

生成面板的结果卡里，除属性列表外**多显示一行**：

```
🎁 启动资金 +120 币
   为什么给你这个数：<initial_coins_reason>
```

- 数据来源：`GET /api/onboarding/status` 或生成面板的返回（实现者按现有返回结构接入，能拿到即可）
- 若历史档案的快照里没有 `initial_coins` 键（老数据），**不显示这一行**（优雅降级）

**A1-4 · 验收标准（必须用真实 DeepSeek 验证并给出证据）**

> **测试必须在副本库上进行**（复制 `game_of_life.db` 到临时文件，改 `DATABASE_URL` 或其等价方式），**不得污染真实库**（真实库 31 条事件 / 余额 40 必须保持不变）。

1. 在副本库上走一遍完整 onboarding（或直接调用 `_generate_panel`）→ 返回含 `initial_coins`（整数）与 `initial_coins_reason`；附"输入问卷 → 输出 JSON"证据
2. `coin_ledger` 新增一条 `source='onboarding_bonus'`，`delta` == `initial_coins`，`balance_after` 正确；`user_profiles.coins` == 该数额
3. 边界：手动构造 AI 返回 `initial_coins=50` → 夹到 **80**；返回 `300` → 夹到 **200**；返回 `"abc"`/缺失 → 取 **80**
4. **幂等**：发放后再次调用 `grant_startup_bonus_if_needed()` → 返回 `False`、不产生新流水
5. **老档案不受影响**：真实库的 `coin_ledger` 仍为 2 条、余额仍为 **40**
6. 验证 F6：`PANEL_SYSTEM_PROMPT` 中出现"13 项"与「诚信」；`PANEL_DISPUTE_SYSTEM_PROMPT` 不再出现"6 项"

### A2 · F5 事件来源标记（`events.origin`）

**A2-1 · 模型（`app/models/__init__.py`）**

`Event` 类新增：

```python
# v1.9：事件来源标记。None=普通记录（默认，老数据一律 NULL）；"challenge"=挑战结算生成
origin: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

> 可空、无默认值 → `migrate_schema` 会自动 `ALTER TABLE ADD COLUMN`（沿用 v1.7 `item_id`、v1.8 `coins` 的同一路径），**不需要删库重建**。

**A2-2 · schema（`app/schemas/__init__.py`）**

- `EventOut` 新增 `origin: str | None = None`
- `EventCreate` / `EventUpdate` **不加入** `origin`（用户录入的事件永远不可能是挑战来源，不给前端写入口）

**A2-3 · 写入点（`app/services/challenge_service.py`，共 2 处）**

1. `complete()` L295-306 的 `Event(...)` 构造：增加 `origin="challenge"`
2. `_make_retreat_judgment()` L466-470 的 `Event(...)` 构造：增加 `origin="challenge"`

> **唯一写入口原则**：`origin="challenge"` **只**在这两处写入（挑战结算链路的两个分支）。其他任何地方不得写 `origin`。

**A2-4 · 前端徽章（3 处列表）**

| 文件 | 改动 |
|---|---|
| `frontend/src/components/TimelineView.vue` | 列表行摘要区：`v-if="e.origin === 'challenge'"` 显示 `<span class="tag">挑战</span>` |
| `frontend/src/components/JudgmentList.vue` | 同上（判定列表已有 `event_title`，可判断该事件是否挑战来源——若接口未返回 `origin`，**需在 `list_judgments` 返回里补该字段**） |
| `frontend/src/components/EventForm.vue` | 「最近记录」列表行同样显示徽章 |

- 徽章样式复用现有 `.tag`，**不新增配色**（避免视觉噪音）
- `origin` 为 NULL / 非 `challenge` 时**不渲染**

**A2-5 · 验收标准**

1. 在副本库上走一条挑战的完整 `complete → settle` 流程 → 对应 `events` 行的 `origin == 'challenge'`、`created_at` 为当天；附证据
2. 走一条 `abandon`（不带说明，直接 retreated）→ 同样 `origin == 'challenge'`
3. 普通记录（`POST /api/events`）→ `origin` 为 **NULL**
4. 真实库老数据 31 条 → `origin` 全部为 NULL，页面行为与改造前**完全一致**（不显示任何新徽章）
5. `GET /api/events` 返回的每条含 `origin` 字段

### A3 · F6 prompt 维度文案修正

一并完成（见 F6，`onboarding.py` 两处过时文案）。

---

## 四、批次 B · 前端（全站交互反馈规范）

### B1 · 全局轻提示（toast）

**新增文件**：

1. `frontend/src/composables/useToast.js` —— 全局单例（`reactive` 数组 + `push/dismiss`），导出 `toast.success(msg)` / `toast.error(msg)` / `toast.info(msg)`
2. `frontend/src/components/ToastHost.vue` —— 渲染层：固定在右上角、纵向堆叠、约 3 秒自动消失、可手动关闭、不阻塞点击（`pointer-events: none` 于容器、`auto` 于单条）

在 `App.vue` 挂载一次 `<ToastHost />`。

**样式约束**：亮色主题、圆角卡片、左侧色条区分成功（绿）/ 失败（红）/ 信息（灰蓝）；**不使用**涨跌红绿语义（本项目金币与股票无关）。

### B2 · 逐页排查"进行中"文案与成功提示

**已确认的缺陷（用户实测）**：

| 位置 | 现状 | 需改为 |
|---|---|---|
| 挑战页「生成挑战 / 再来一批」 | 按钮禁用但**文案不变**、成功**静默** | 按钮变「**AI 正在生成…**」（带 spinner）+ 成功后 `toast.success('已生成 N 条新挑战')` |

**排查清单（实现者必须逐页点一遍，把缺的补齐）**：

| 页面 | 按钮 / 操作 |
|---|---|
| `ChallengeView.vue` | 生成挑战、再来一批、接受挑战、我完成了、确认结算、放弃、AI 重新定价、改价、兑换、已兑现、添加物品 |
| `EventForm.vue` | 提交打卡、提交日记、提交追问回答 |
| `TodayCheckin.vue` | 逐项打卡提交 |
| `JudgmentList.vue` | 确认入账、补充、反驳、删除事件 |
| `SettingsView.vue` | 保存设置、查看/修改 LLM 配置、导出、备份、重置档案、重置全部数据 |
| `Onboarding.vue` | 提交答案、补充画像、确认调整、重置 |
| `GoalsView.vue` / `AnchorsView.vue` | 新建/达成/失败/取消、校准锚点 |
| `ItemManager.vue` | 新建/修改/停用打卡项目 |

**规范**：
- 任何 `await api.*()` 触发点：**处理中必须有文案变化**（如「保存中…」「提交中…」）+ 按钮禁用
- **长耗时的 AI 操作**（生成挑战、判定、定价）额外接入现有 `slowHintId` 慢响应提示（参考 `ChallengeView` 已有实现）
- 成功后 `toast.success('<动词>成功')`，失败后 `toast.error(e.message)` + 保留顶部横幅
- **不改变任何业务逻辑**（本批是纯交互层改造）

### B3 · 验收标准

1. 点「生成挑战」→ 按钮立刻变「AI 正在生成…」且不可再点 → 完成后恢复原文案 + 右上角浮出"已生成 N 条新挑战"
2. 快速连点任意异步按钮 → 不产生重复请求（防重复仍生效）
3. 逐页对照 B2 清单点一遍，**每个按钮都有进行中文案**（附逐页截图或清单打勾）
4. 人为制造一次失败（如断开后端）→ 顶部横幅 + toast 同时出现
5. `npm run build` 零错误

---

## 五、批次 C · 挑战多档（一卡多档）

### C1 · 数据模型（`app/models/__init__.py`）

`Challenge` 新增：

```python
# v1.9：同主题的多难度档位 [{label, description, difficulty}]。
# 空列表 = 单档挑战（等价旧行为）；difficulty/description/coin_reward/deposit
# 四个字段始终表示「当前选中的档位」。
variants: Mapped[list] = mapped_column(JSON, default=list)
```

> 走 `migrate_schema` 自动加列。老挑战 `variants` 为 NULL → 反序列化为 `[]`。

### C2 · prompt 契约（`app/prompts/challenge.py`）

**C2-1 · `CHALLENGE_SYSTEM_PROMPT` 输出格式扩展**

每个 challenge 除原有字段外，新增 `variants` 数组：

```json
{
  "title": "整理一份今日任务清单",
  "description": "（默认档的要求描述）",
  "difficulty": 3,
  "coin_reward": 10,
  "deposit": 10,
  "related_attributes": ["规划力"],
  "variants": [
    {"label": "3 项", "description": "只列 3 项今天必须完成的事，并按优先级排序。", "difficulty": 2},
    {"label": "5 项", "description": "列出 5 项任务并按优先级排序，完成其中至少 3 项。", "difficulty": 3},
    {"label": "10 项", "description": "列出 10 项任务并排序，当天完成至少 6 项。", "difficulty": 5}
  ],
  "reason": "为什么给你这个挑战（展示给用户）"
}
```

**C2-2 · 新增 rules（追加到「硬性要求」）**

- `variants` 是**同一挑战的不同强度档位**，让用户自己挑难度。
- **档数按内容自然决定**（用户明确要求）：容易分档的（数量型、时长型、次数型）给 **3~5 档**；不易分档的给 **2 档**；实在无法分档时给**空数组 `[]`**（退回单档）。
- 每档必须包含：
  - `label`：**不超过 6 字的短标签**（如"3 项""5 项""10 项"，或"轻松""标准""硬核"）
  - `description`：**具体可执行**的要求描述（遵守与 `description` 相同的"具体可执行、可自证"标准）
  - `difficulty`：1~5 的整数
- 档位之间必须**难度递增**、**描述实质不同**（不能只改数字，要真的改变要求）；相邻档的 `difficulty` 应当有区分。
- 顶层 `description` / `difficulty` 填写**默认选中的档**（建议取中间档或最低档），且必须与 `variants` 中某一档一致。
- **`coin_reward` / `deposit` 仍不得自由发明**（由参数表按 difficulty 派生，见下方服务层）。

### C3 · 服务层（`app/services/challenge_service.py`）

**C3-1 · `generate()` 解析 variants**

1. 解析 `item.get("variants")`，逐档校验：
   - `label` 非空且 ≤ 6 字（超长截断）
   - `description` 非空（空则丢弃该档）
   - `difficulty` 夹到 `[1, 5]`
   - 丢弃非法档后若 **剩余 ≤ 1 档 → `variants = []`**（退回单档，避免"只有一档还显示按钮组"的蠢交互）
2. 落库：
   - `variants` 存全部有效档
   - `difficulty` / `description` 取 `variants` 中**与顶层 difficulty 最接近的那一档**（若无则取第一档）
   - `coin_reward` / `deposit` 一律**由 `coin_params(scope, difficulty)` 重新派生**（覆盖 AI 可能给错的数字）
3. 单档挑战（`variants == []`）走原有逻辑，行为不变

**C3-2 · 新增接口 `PUT /api/challenges/{id}/variant`**

- 入参：`{"variant_index": int}`
- 校验：
  - 挑战存在且属于当前用户 → 否则 404
  - `status == "candidate"` → 否则 400「挑战已接受，档位已锁定」
  - `0 <= variant_index < len(variants)` → 否则 400
- 行为：把该档的 `description` / `difficulty` 写回顶层字段，并**重算** `coin_reward` / `deposit = coin_params(scope, difficulty)`
- 返回：更新后的挑战对象（含 `variants` 与新的金币/押金）
- **不写审计**（候选期的选择不是关键操作，且此时还没有 `judgment_id`）

**C3-3 · 列表接口补充字段**

`GET /api/challenges/current` 与 `GET /api/challenges` 返回的每条挑战需含 `variants`（供前端渲染按钮组）。实现者核对现有序列化方式，缺则补。

### C4 · 前端（`frontend/src/components/ChallengeView.vue`）

**C4-1 · 卡内档位切换（仅候选期）**

在「完成可得 N 币 / 押金 N 币」那一行**上方**插入档位按钮组：

```
[ 3 项 ] [ 5 项 ] [ 10 项 ]        ← 选中态高亮（.seg-btn 复用）
完成可得 +10 币 · 押金 10 币
```

- 按钮数量 = `c.variants.length`
- `c.variants.length <= 1` → **不渲染按钮组**（单档挑战与旧挑战的行为完全不变）
- 点击 → `runAction('variant-<id>', ...)` 调新接口 → 成功后 `loadChallenges()` 刷新（描述与金币同步变化）+ `toast.success('已切换到「5 项」档')`
- **`status !== 'candidate'` 时不渲染按钮组**（锁定）

**C4-2 · 当前档位提示**

- 已接受 / 已结算的挑战：若 `variants.length > 1`，在描述旁显示一行「档位：5 项」（只读文本，不可点）

### C5 · 验收标准（必须用真实 DeepSeek 验证并给出证据）

1. 在副本库上生成一批新挑战 → **至少一条含 ≥2 档**；档位 `description` 实质不同、`difficulty` 递增；附"AI 原始返回 → 落库结果"证据
2. 档位金币/押金**与 `COIN_TABLE` 完全一致**（逐档核对，附对照表）
3. 前端切档 → 描述与金币/押金同步变化；切到第 3 档后接受 → **扣的押金是第 3 档的数额**（附 `coin_ledger` 证据）
4. 接受后调 `PUT /variant` → 返回 **400**（档位锁定）
5. `variant_index` 越界 → 400
6. **老挑战不受影响**：id=1/2/3 的 `variants` 为空、前端不显示按钮组、行为与改造前一致；**id=2（已接受）继续按旧规则结算**
7. 同一批里若 AI 给出 `variants: []` → 落库为空、前端不显示按钮组（不报错）

---

## 六、批次 D · 手账本搜索重构

**只改 `frontend/src/components/TimelineView.vue`**（其他页面搜索保持现状）。

### D1 · 先核对判定接口字段（实现前必做）

搜索要覆盖"加点理由与依据"，需要 `listJudgments`（`app/routers/judgments.py` L22）返回的数据里包含：

- `analysis`（数组，AI 推理链）
- `summary`
- `suggested_changes`（含每条的 `reason` / `evidence`）
- `final_changes`
- `revision_notes`（v1.6）
- `confidence_reason`（v1.4）
- `merged_with`（v1.7）

**核对结论若为"缺"** → 在 `list_judgments` 的返回 dict 中补齐（**仅加字段，不改现有字段**；注意 payload 大小，必要时只补搜索所需的文本字段）。

### D2 · 搜索实现

**D2-1 · 类型筛选（三态）**

顶部在搜索框旁新增分段控件：

```
[ 全部 ] [ 只看事件 ] [ 只看日记 ]
```

- 事件 = `source === 'form'`（含挑战来源事件）
- 日记 = `source === 'journal'`
- 默认「全部」；与搜索框、与下面的日期分组折叠**同时生效**

**D2-2 · 可搜索文本构建**

为每个事件构造一段"可搜索文本"（`haystack`），包含：

1. 事件自身：`title`、`content`、`category`、`params` 的**值**（跳过 `_` 前缀键）
2. 关联判定（按 `event_id` 匹配）：`summary`、`analysis` 各项、`suggested_changes` 的 `reason` 与 `evidence`、`final_changes` 的 `reason`、`revision_notes` 的文本、`confidence_reason`、`merged_with` 的 `note`

匹配时统一小写比较（现有实现已用小写，保持）。

**D2-3 · 命中片段与高亮**

- 有搜索词时，在每条记录的摘要行下方显示**命中片段**：
  - 取第一个命中的字段，截取关键词**前后各约 20 字**
  - 关键词用 `<mark>` 或等价样式**高亮**
  - 片段前标注来源（如「正文」「加点理由」）——让用户一眼看懂"命中在哪"
- 无搜索结果时显示：「没有找到包含「xxx」的记录」
- 保留现有行为：搜索时所在日期组与详情**自动展开**（清空后恢复折叠）

### D3 · 验收标准

1. 搜一个**只出现在正文**（不在标题）的词 → 能找到该记录，并显示正文片段 + 高亮；附证据
2. 搜一个**只出现在加点理由**里的词（如某条 `reason` 中的词）→ 能找到，片段来源标注为「加点理由」
3. 切换「只看日记」→ 结果只剩 `source='journal'` 的；「只看事件」同理
4. 搜索 + 类型筛选 + 日期分组折叠**三者叠加**行为正确（筛选后组内计数正确）
5. 清空搜索 → 恢复默认折叠状态（记忆的展开组不被打乱）
6. 搜索词为空时**不显示**任何片段（避免常态噪音）
7. `npm run build` 零错误；其他页面的搜索框行为**完全不变**

---

## 七、全局验收铁律

1. **启动无错**：`start.bat` 启动后端，`migrate_schema` 打印新增列 `events.origin` / `challenges.variants`；不出现 `sqlite3.OperationalError`
2. **老数据完好**（改造前后逐项对比）：

   | 对象 | 改造前基线 | 改造后要求 |
   |---|---|---|
   | `events` | 31 | 31（不改动既有行） |
   | `ai_judgments` | 31 | 31 |
   | `attribute_history` | 122 | 122 |
   | `coin_ledger` | 2（+50 / -10） | 2（**不动**） |
   | `user_profiles.coins` | 40 | **40（不动）** |
   | 13 维账目 | 自洽 | 仍自洽（初始值 + Σ流水 = 当前值） |
   | `challenges` | 3（id=1/2/3） | 3（`variants` 为 NULL，行为不变） |

3. **金币守恒**：`Σ coin_ledger.delta == user_profiles.coins`
4. **前端构建**：`npm run build` 零错误
5. **禁区未动**：雷达图 / 成长趋势图 / 活动热力图与改造前**完全一致**（附改造前后截图对比）
6. **每条决策可追溯**：实现内容能对应到第一章 F1~F6 的某一条
7. **副本库测试**：一切涉及"新建档案 / 生成挑战"的验证都在**副本库**上做，真实库只做只读核对

---

## 八、遗留与顺延

- **原 v1.9 三项 → 顺延 v1.10**（想法已在 `DECISIONS.md` 存好，不必重问）：
  - 成就系统（累计型 + AI 发现型，奖励金币 + 徽章）
  - 豁免券（时段券 + AI 判动机浮动）
  - 属性满 100 拆分子维度（`parent_id` 层级）
- **仍未启动**（用户已确认延后）：
  - U1「今日盘点」与「记录事件」合并（痛点已指认：**两个页面职责重叠**）
  - U2 打卡项目管理从设置页迁出 / U3 每日任务清单与目标结合
  - V1 雷达图排版 / V2 成长趋势图换形式或删除 / V3 活动热力图排查
- **本轮新登记的观察项**：
  - 挑战事件是否应参与"连续写日记"等统计口径，本轮未动，待有真实使用体感后再评估
  - `useDateGroups` 与 `EventForm` 的最近记录分组仍是两套实现（v1.7 遗留偏离），未在本轮统一
- **完成后必须回写**（同前几轮约定）：
  - `docs/DECISIONS.md`：F1~F5 逐条勾选并附实现摘要；登记本轮实施记录（commit、验收证据、偏离项）
  - 若动了判定列表接口字段 → 同步 `docs/learning/CODE_GUIDE.md` 对应小节
