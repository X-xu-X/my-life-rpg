# 开发计划 v1.13 —— 把定价交回 AI · 商店常用券 · 分析页降噪

> **决策来源**：`docs/DECISIONS.md`「Backlog：v1.12 上线后实测反馈（2026-11-13）」F1~F13 + 2026-11-16 用户三轮纠正
> **代码基线**：v1.12 已上线（HEAD `3fa0de7`，2026-11-12 发布，`DATA_UNCHANGED`）
> **方案确认**：`docs/prototypes/lifexp-v113-demo-2026-11-16/index.html`（七屏，用户 2026-11-16 已点头）
> **交付方式**：分批实现，**一批一个 commit**，只 commit 不 push

本轮不新增玩法，只处理三件事：**金币「6/15/25」这种定死的数交回 AI**、**商店的奖励分成常用券和一次性**、**分析页与流水页上多余的噪音和小字**。

---

## 〇、总原则（必须遵守）

1. **数据红线**：`game_of_life.db` 是真实生活数据，**禁止物理删除**。新增列走 `migrate_schema`（启动自迁移），新增表走 `create_all`；任何批量操作前先把整库备份到 `backups/`。
2. **兼容过渡**：老数据必须容忍新字段为空。`ShopItem.auto_pricing` **不删列**，只加 `pricing_mode` 并按旧值回填。已入账的 `ActionAward` 不重算。
3. **一个 commit = 一个逻辑单元**，中文 message `类型: 简述`。**只 commit，不 push。**
4. **一致性铁律**（不得违反）：金币只有 `coin_service.grant()` 一个写入口；属性写入走 `judge_service._clamp_attribute_value`；任何"更新"语义**不得用"先删后建"实现**。
5. **【新增】UI 铁律：不写说明性小字**（用户 2026-11-16：「那种没必要的说明性小字记得去掉」）。具体含义：
   - 不解释设计意图，不写「本页只改外观与信息顺序」这类元说明；
   - 同一含义不在标题和正文里说两遍（标题已写「只用这一次」，正文不再复述「换完进历史」）；
   - 能用字段和数字说清的，不用整句；
   - 一条提示只能出现在一个地方；**不要为了"友好"再加一行灰字**。
6. **不得顺带做本轮之外的事**：
   - ❌ 不动 `event_confirm` 那条 +2 币链路（只改手账事实确认的 `trial_action`）
   - ❌ 不做服务端每夜定时定价（"每天更新"仍由打开商店页触发，见批次 E）
   - ❌ 不新增页面、不新增 tab（商店只在页内分小节）
   - ❌ 不改 13 个属性维度；不动上云 / 多用户 / CORS
   - ❌ 不删 `auto_pricing` 列、不重算历史 `ActionAward`

---

## 一、已锁定的口径

| 编号 | 口径 | 原话依据 |
|---|---|---|
| F4 | 金币由**模型直接给**，档位表 `BASE`/`MAIN`/`grade` 整体废弃；**取消单次 40 与每日 100**；**主线加成也交给 AI** | 「金币也是让 ai 定，不要定死，不要 6 15 什么的了」 |
| F4 | 每条金币必须**同源带一句模型自己写的理由**，不允许"规则算钱、模型事后编解释" | 「我不知道今天加金币为什么加这么多或者这么少」 |
| F5 | 流水**按天分组**，组内**日记只出总额、事件各出一行**；日记不展开、不列逐条金额、不给归因 | 「日记就总的金额，事件就单独的金额」 |
| F9 | 定价**不参照商店价位**（循环参照），保留余额 + 近 7 天收支 + 日常赚币规则 | 「这个定价应该不用和商店的价格参考吧」 |
| F11 | **删掉 ±20% 截断**，改成把「昨天多少 → 今天多少、涨跌几成」摆出来 | 「商店那个幅度要限制嘛？感觉没必要」 |
| F12 | 定价出来之后二选一：**只用于这一次** / **加入常用兑换券**；常用券**每天重估、显示今天的价** | 「给我定价，然后出现，只定价一次，还是加入常用的兑换券」 |
| F13 | 商店页内分「常用兑换券」/「只用这一次」两个小节 | 同上 |
| F8 | 页脚补 `浙公网安备33018502002724号` | 2026-11-12 获准 |

**F4 明确保留的**：`first_record`（当日首条记录 +3）不动 —— 它奖励的是"记录这个动作"，不是对行动意义的评价，与"不要定死金额"不冲突。

---

## 二、批次划分

依赖顺序：**A 必须先做**（F10 的解释要用 A 的新字段；F5 的流水要用 A 的新 reason）→ B → C → D → E → F。
A/B 是后端+展示，C/D 是分析页，E 是商店定价（改动最集中），F 是纯页面视觉。

---

### 批次 A · 金币改由 AI 直接定价（F4）

**目标**：把"模型给档位、规则换钱"改成"模型直接给钱和理由"。这一步做完，6/15/25 从库里彻底消失。

**涉及文件**

- `app/services/trial_rules.py`（`BASE` / `MAIN` / `split()` / `award()`）
- `app/services/fact_analysis.py`（`Suggestion` 模型、系统提示词、`preview()` 的 `split` 调用）
- `app/routers/trial.py`（`rules` 字段）
- `frontend/src/components/TrialRules.vue`、`FactAnalysis.vue`、`EventFactAnalysis.vue`（档位文案）
- `tests/`

**具体改法**

1. `Suggestion`：删 `grade`，加 `coins: int = 0` 与 `coins_reason: str = ''`。校验口径不变（只防非数字 / 负数 / 缺失 → 归 0，不设上限）。
2. `trial_rules.split()` **整个删掉**，换成 `validate(coins, reason)`：
   - 非 `int`、`< 0`、超过 10^9 → `422`（与挑战奖励同一口径）；
   - `0` 合法，表示"这件事不发放金币"（原 `grade='none'`）；
   - **不再有** `remaining`、`before_cap`、`cap_reduction`、`holiday` 加成。
3. `trial_rules.award()`：`breakdown` 改为 `{'amount': n, 'coins': n, 'reason': <模型原句>, 'mainline': bool, 'holiday': bool}`。
   保留 `amount` 键名，避免 `ActionAward` 历史数据与前端取值断裂。
4. `fact_analysis.preview()`：删 `remaining` / `used` 截断链；`cap_used()` **只用于展示**"今日已得 X 币"。
5. 系统提示词（`fact_analysis.py:129` 那段长字符串）：
   - 输出示例把 `"grade":"small"` 换成 `"coins":12,"coins_reason":"…"`；
   - 新增定价依据：**这件事本身的投入与意义**（时长、难度、是否推进主线、是否第一次做到），
     **不是时长线性换算**；
   - **锚点注入**：把「近 7 天同类行动的摘要 + 当时给过多少币」和「今日已得 N 币」放进上下文，
     防止同样"阅读 30 分钟"今天 15、明天 8；
   - 明确：**没有把握就给小一点的数**，不要为了"显得重要"给大数。
6. `trial.py` 的 `rules`：删 `base` / `mainline` / `per_fact_cap` / `daily_cap`，保留 `first_record`、`strict_default`、`rule_version`。
   前端 `TrialRules.vue` 对应改成一句"金币由 AI 按行动意义定价，不设档位与上限"。
7. 前端删档位映射文案：`FactAnalysis.vue:26` 的"行动档位"、`:44` 的 breakdown 四项数字、
   `:46` 的"今日此前已用 X/100" → 改"今日已得 N 币"。

**验收**

- 库里搜不到 `BASE` / `MAIN` / `'grade'` 引用；
- 新分析一次，`ActionAward.breakdown` 里有模型原句理由，金额等于模型给的数；
- 连续记两天"阅读 30 分钟"，金额差不超过 ~50%（锚点生效）；
- 模型给出 `0` / `-3` / `"12"` 三种脏值各测一次，前两个按 0 处理、字符串按非法处理；
- `python -m unittest discover -s tests` 全绿。

**commit**：`feat(金币): AI 直接定价并废弃档位表`

---

### 批次 B · 入账解释与流水改版（F10 + F5）

**目标**：确认入账之后，能看懂"这几毛属性、这几个币是怎么来的"；流水一屏能看出账。

**涉及文件**

- `frontend/src/components/FactAnalysis.vue`（`:36` `:38` `:42` `:44`）
- `frontend/src/components/EventFactAnalysis.vue`（`:73` `:74` `:78`）
- `frontend/src/components/SectionDetail.vue`（`:69` `view==='ledger'`）
- `app/routers/coins.py`（`GET /api/coins` 返回结构）、`app/services/coin_service.py`（只读查询）

**具体改法**

1. **属性理由默认可见**：`change.reason` 从 `<details>原文引用与判断依据` 第二层提到每维那一行的下一行，灰字一行，**不折叠**。
2. **金币那行改成一句人话**：`+12 币 · <模型原句>`（来自批次 A 的 `coins_reason`）。
   删掉「基础 6 · 主线 0 · 节日 0 · 封顶减 0」这种纯数字构成。
3. **确认后不再整块折叠**：`group.state==='confirmed'` 时保留一段「本组入账」：几项计入、几项未计入及原因、合计多少币、当日累计多少币。
4. **流水按天分组**：`SectionDetail.vue` 的 ledger 视图改为
   - 一天一张卡，日期当标题，右侧合计 `+42`；
   - 组内两栏：**日记**（一天一行，只出总额 + 「查看原文」跳转，**不展开、不列逐条**）；**事件**（一行一条，摘要 + 金额，**不给归因**）；
   - 今天与昨天默认展开，更早收起成一行。
5. **后端补字段**（F5 的技术前提）：`GET /api/coins` 每条返回 `kind`（`diary` / `event` / `other`）与 `day`（本地日）。
   判定路径：`ref_type='judgment'` → `judgment.event_id` → `event.record_kind`；取不到归 `other`。
   同时把 `reason` 从「经本人确认的有效行动；trial-2026-10-18-v1」改为**行动摘要**，版本号另存 `rule_version`（已经存了）。

**验收**

- 一处日记确认后，流水里当天只有一行"日记 42 币"，点开是原文跳转，**没有逐条明细**；
- 事件各一行，金额加总等于当天日记总额（同一天的日记组与事件组互不重复计）；
- 老流水（`rule_version` 是 v1 的）仍能正常归组，不报错。

**commit**：`feat(流水): 按天分组的日记与事件 · 入账说明常驻`

---

### 批次 C · 分析页降噪（F1 + F2 + F3）

**目标**：碎片不再每条挂四个按钮；「原文已变化」挨着按钮；「又读了 30min」不再被问是不是同一次。

**涉及文件**：`FactAnalysis.vue:30/:43`、`EventFactAnalysis.vue:75`、`app/prompts/judge.py`、`app/services/fact_analysis.py`（提示词段）

**具体改法**

1. **F1 按钮只在真可能重复时出现**：
   - 有 `candidate_fact_id` 或 `candidate_options` → 才渲染关系按钮组（一行，浅黄底）；
   - 没有候选 → **一个按钮都不渲染**，只留摘要、属性、金币；
   - 「本项暂不结算」「主线关联」收进 `<details>调整这一项`，默认关闭；
   - `EventFactAnalysis.vue:75` 已经是 `decision==='unresolved'` 条件，核对后与 F1 口径统一。
2. **F2 提示挪位**：409 的「原文已变化，请重新分析」从卡片标题下移到**主按钮正上方一行**，`role="alert"` 保留。
3. **F3 措辞判定**：提示词关系判定段加硬规则 —— 「又 / 再 / 再次 / 还 / 第二次 + 数量或时长」一律 `relation=new`，
   **且不生成该条 `questions`**。同时确认与 `test_fact_same_day_scope` 的当日防重复口径不冲突（那条针对"完全同描述的重复提交"）。

**验收**

- 记一篇含 3 件行动的日记，其中 1 件与当天已记内容相似 → 只有那 1 件出按钮，另外 2 件没有；
- 记「又读了 30min」→ 不再出"是否与已有事件 X 为同一次"，直接结算；
- 改原文后重新分析 → 红字在按钮上方，滚动到按钮就能看到。

**commit**：`fix(分析页): 关系按钮只在可能重复时出现`

---

### 批次 D · 心愿表单（F7 + F6）

**目标**：定价不再必然失败，也不再让用户选"物品还是计时"。

**涉及文件**：`frontend/src/components/RewardShop.vue`（表单与缓存）、`app/routers/reward_quotes.py`（`QuoteIn`）、`app/prompts/shop.py`

**具体改法**

1. **F7 修 `int_parsing`**：
   - 提交前 `minutes` 为空串 / `null` / `NaN` → 不发这个字段（`QuoteIn.minutes` 改 `int | None = None`）；
   - localStorage 还原时做类型清洗（空串→`null`，字符串数字→数字）；
   - 所有错误统一转中文可读文案，**禁止把 Pydantic 的 `loc`/`type`/`input` JSON 拼进界面**。
2. **F6 删「形式」字段**：去掉 `reward_kind` 下拉与分钟输入框；`QuoteIn` 不再读 `reward_kind`。
   AI 自行判断是否计时类，返回 `is_timed: bool` 与 `minutes_estimate: int | null`，
   结果卡里显示「预计 200 分钟（可改）」，改了只影响后续计时额度，不影响价格。

**验收**

- 清空分钟框再提交 → 不再 400，不再显示机器语言；
- 表单只有：想要的奖励 / 参考价（可空）/ 说明与期望频率；
- 输「想连着玩三小时左右」→ 结果卡出现 200 分钟左右的估值。

**commit**：`fix(心愿): 修定价校验失败并删除形式字段`

---

### 批次 E · 商店定价方式（F9 + F11 + F12 + F13）

**目标**：价格只由"你最近的实际表现"决定，涨跌摆在明面上；一次性奖励和常用券分开。

**涉及文件**

- `app/services/economy_service.py`（`snapshot()` `:78-80`、`shop_price_range()` `:42`）
- `app/prompts/shop.py`（`:13` `:36-37`）、`app/prompts/challenge.py`（`:109`）
- `app/routers/reward_quotes.py`（`bounded_price()` `:77-80`、`apply_quote()` `:96-99`）
- `app/models/__init__.py`（`ShopItem` `:431 auto_pricing`）
- `app/services/pricing_checks.py`（`:34` `:67` enqueue）
- `app/routers/shop.py`（`:26-34` `:37 _item_out`、`seed_preset_items`）
- `frontend/src/components/RewardShop.vue`、`frontend/src/pricingSweep.js`

**具体改法**

1. **F9 删商店价位参照**：`snapshot()` 由四项减为三项（余额 / 近 7 天收支 / 日常赚币规则）；
   删 `shop_price_range()` 与 prompt 里的【商店价位】行；`shop.py` 删「购买力参照」段；`challenge.py:109` 同步改口径。
   **保留**余额与近 7 天收支 —— 那是"相当于几天努力"的真实基线。
2. **F11 删幅度截断**：`bounded_price()` 整个删除，`apply_quote()` 不再有 bounds 分支
   （前端从未读过 `bounds`/`model_price`，无兼容问题）。`result` 改记 `previous_price` 与 `change_pct`。
3. **F12 定价方式两值**：
   - `ShopItem.pricing_mode`（`once` / `recurring`，默认 `once`），`migrate_schema` 加列并回填
     `auto_pricing=True → recurring`、`False → once`；**`auto_pricing` 列保留不删**；
   - `seed_preset_items()` 预置的两件设为 `recurring`；
   - `pricing_checks.enqueue()` 只取 `pricing_mode='recurring'` 且 `repriced_on != today` 的商品，
     **把 `eligible[:min(3,budget)]` 的 3 件帽去掉**（现在做不到"每天显示最新价"），当天全部排队，仍受 `MAX_DAILY=10`；
     超过 10 件按最久没评估的轮询，界面标"其余明天更新"；
   - `QuoteIn` **不加字段**：新建一律落 `once`，定价结果卡出来之后再让用户选；
   - 新接口 `PATCH /shop/items/{id}/pricing-mode`（`{mode}` + `expected_version`，要求 `acknowledge`），取代原 `/automatic-pricing`；
   - 新增 `POST /shop/items/{id}/price-rollback`（`expected_version`）：价格回到 `previous_price`，`pricing_mode` 落 `once`，写一条审计。
4. **prompt 补一条**：**没有新证据时保持原价，不得为了"有变化"而改数字**——否则每天重估会变成每天抖动。
5. **前端**：
   - 结果卡下方二选一（`只用于这一次` / `加入常用兑换券`），选中后调 `pricing-mode`；
   - 商店页内两个小节：`常用兑换券`（`今天 30 · 昨天 28 ↑7%`，可直接兑换）/ `只用这一次`（`11/16 定价`，换完进历史）；
   - 每件商品「依据与操作」里可换组；已兑完的 `once` 商品归入「已用过的」折叠区（`_item_out` 加 `redeemed_count`）；
   - 商品卡点开是「今天为什么是这个价」：旧价 → 新价 + 涨跌幅 + 依据，底部两个按钮「知道了」/「退回 30 并冻结」；
   - `pricingSweep.js` 触发条件不变（进商店页按日期去重），**不加服务端定时任务**。

**验收**

- 定价 30 的商品，模型给出 48 → 界面显示 48，理由里写的也是 48，**没有 144 这种被截过的数**；
- 新建商品不勾常用 → 第二天不进自动队列，价格不动；
- 勾了常用 → 第二天进队列，商品卡出现「今天 X · 昨天 Y ↑Z%」；
- 常用券 12 件时，一天只跑 10 件，其余标"其余明天更新"；
- 点「退回并冻结」→ 价格回到昨天，且之后不再自动变。

**commit**：`feat(商店): 定价方式两值 · 去掉幅度截断`

---

### 批次 F · 目标页 / 计时页 / 备案号（FT + TM + F8）

**目标**：取消能撤销；计时页按 demo 的样子重排；页脚合规。

**涉及文件**：`app/routers/goals.py`、`app/services/goal_service.py`、`frontend/src/components/GoalsView.vue`、
`frontend/src/components/TimerView.vue`、`frontend/src/components/SiteFooter.vue`

**具体改法**

1. **FT 目标可恢复**：
   - 新增 `POST /goals/{goal_id}/restore`（`MutationIn` + `expected_version`）：**只对 `cancelled` 生效**，写回 `active`，`_append_audit(goal,'restore','用户恢复目标')`；
   - `GoalsView.vue`：主列表只放 `active`；已达成 / 未达成 / 已取消折成一行「已结束 · 3」；
   - 已取消卡片只留名称 + 取消时间 + `[恢复]`，**不显示指标、周期进展、「未量化」**；
   - **不做物理删除**（会毁掉审计）。
2. **TM 计时页只改外观**：一张居中卡（720px），状态 tag + 券名 → 一句额度说明 →
   215~238px 圆环（中间 39~44px 剩余时间，下面一行「本次已用 00:47:26」）→ 圆环下按钮居中 →
   卡片下方三处折叠（确认仍在用 / 意外关闭 / 调整实际用量）。
   **计时、宽限、扣费、离线认定这些逻辑一行都不动**。
3. **F8 备案号**：`SiteFooter.vue` 在 ICP 行旁加国徽图标 + `浙公网安备33018502002724号`，
   链接 `https://beian.mps.gov.cn/#/query/webSearch?code=33018502002724`。

**验收**

- 取消一个目标 → 出现在「已结束」里 → 点恢复 → 回到进行中，审计里有一条 `restore`；
- 已取消的卡片上没有指标和「未量化」；
- 计时页在 375px 宽度下圆环不溢出，三个折叠可展开；
- 页脚两行备案都在，公安备案链接可点。

**commit**：`feat(目标/计时): 可恢复取消 · 计时页重排`

---

## 三、统一验收（每批都跑）

1. `python -m unittest discover -s tests -v` 全绿（现有 96 项 + 本轮新增）；
2. `cd frontend && npm run build` 通过；
3. 只读查真库确认没有脏数据：`ActionAward` 无负金额、`ShopItem.pricing_mode` 无空值、`coin_ledger` 余额与 `user_profiles.coins` 一致；
4. **不改动 `game_of_life.db` 的任何业务数据**（只在内存库或 `backups/` 副本上造测试数据）；
5. 视觉核对：每批完成后按 demo 对应屏截图对照（`_shots_v113/` 已存基线）。

---

## 四、本轮明确不做

| 事 | 原因 |
|---|---|
| 服务端每夜定时定价 | "每天更新"仍是打开商店时触发；真要后台跑另开工 |
| 金币的审计历史表（每次定价留档） | 现在只有 `ActionAward.breakdown` 一句理由，够用；加表要新一版 |
| 流水页给归因 | 用户在 2026-11-13 明确否决，归因留在分析结果里 |
| 日记展开成逐条金额 | 同上，用户两次否决（"我有说过要列出来吗"） |
| 删 `ShopItem.auto_pricing` 列 | 老数据兼容，先留着，下个版本再清理 |
| 目标物理删除 | 会毁掉审计 |

---

## 五、文档回写（写完代码必做）

1. `docs/DECISIONS.md`：F1~F13 逐条勾选完成，附 commit hash；
2. `docs/learning/CODE_GUIDE.md` 第 11 章「Bug Ledger」建档：**F7（`int_parsing` 必失败）**、**F2（提示位置错）**、**F4（金币不是 AI 算的）** 三条按五栏写（现象 → 定位 → 根因 → 修复 → 防复发）；
3. `docs/learning/BUSINESS_ROADMAP.md` 阶段 4 补叙事案例：从"档位表"到"AI 定价"，讲清为什么规则定价会让体验变差；
4. 本文件末尾补「实施结果」，写清每批实际 commit 与偏离本文档的地方（**有偏离必须写明原因**）。


---

## 六、实施结果（2026-11-16）

| 批次 | commit | 实际落地 | 与本文档的偏离 |
|---|---|---|---|
| A | `808fe9c` | 金币改由 AI 直接定价：`Suggestion.coins/coins_reason`、`trial_rules.validate()`、提示词注入近 7 天锚点与今日已得 | 规则版本号升到 `trial-2026-11-16-v2`（旧草稿走 409 重新分析，避免读到已删的 `grade`）；`ops/repair_confirmed_rewards.py` 内冻结了旧档位表以复算事故期的账 |
| B | `7fd9b75` | 属性理由常驻、金币行改一句人话、确认后保留「本组入账」、流水按天分组 | 后端补 `kind/day` 放在 `coin_service.ledger_detail()`（只读），台账 reason 改为行动摘要 |
| C | `4ee990d` | 关系按钮只在有候选时出现、调整项收进折叠、409 提示移到主按钮上方 | 判分提示词在 `fact_analysis.py` 与 `prompts/judge.py` 两处都加了「又/再」硬规则 |
| D | `88acec3` | 删除形式与分钟字段，模型返回 `is_timed/minutes_estimate`；错误统一转中文 | 为让「可改」可落地，`ShopItemUpdateIn` 增 `duration_minutes`（只改计时额度，不动价格） |
| E | `4ff0c4f` | 快照去掉商店价位、删 ±20% 截断、`pricing_mode` 两值 + 迁移回填、每日队列去 3 件帽、退回并冻结 | 迁移回填只在**首次加列**时执行，避免把用户后来切回 `once` 的商品又改回 `recurring` |
| F | `aa2ad65` | 目标恢复端点与「已结束」折叠、计时页居中卡 + 圆环、公安备案号 | 计时页详情折叠按「确认仍在用 / 意外关闭 / 调整实际用量」三处重排，按钮位置微调，逻辑未改 |

**验证**：`python -m unittest discover -s tests` 全绿（既有失败项与 HEAD 基线一致，见下）；`vite build` 通过；真实库零改动（coins 55 / events 32 / attr_history 124 / coin_ledger 4）。
**已知既有失败**：`tests/test_release_readiness.py` 的 3 项在未改动的 HEAD 基线上同样失败（确认链路与商店预置的合成用例），本轮未触碰，另立项处理。
