# 开发计划 v1.11 —— 数据安全 · 事务一致性 · 审计完整性

> **决策来源**：`docs/review/CODEX_AUDIT_2026-10-08.md`（Codex 阶段 A 只读审查，gpt-6.1-sol）+ 2026-10-08 用户拍板
> **backlog 记录**：`docs/DECISIONS.md`「v1.11 已登记待办（2026-10-08）」
> **代码基线**：v1.10 已交付（HEAD `4ae0ca56`，2026-09-30）
> **本轮范围**：**审计报告全部条目**（9 条 P0 + 9 条 P1，共 18 条，用户 2026-10-08 明确选择"全做"）
> **交付方式**：**一次性全改**（用户 2026-10-08 确认；本文档内已按批次给建议的 commit 切分，便于出错时定位）

本轮性质是**"一次地基修复"**：前十个版本一直在同一骨架上叠功能（记录 → 判定 → 金币 → 挑战 → 商店 → 成就 → 豁免券），功能越堆越多，但**骨架从来没被整体审过**。Codex 的审计结论是：**账目是干净的，但代码里有会导致半结算、重复入账、审计丢失和密钥明文回显的路径。**

本轮**不新增任何玩法**，只做三件事：**堵住会丢数据的入口**、**让结算可回滚**、**让审计真正只增不删**。

---

## 〇、总原则（必须遵守）

1. **数据红线（最高优先级，唯一不可讨论项）**：`game_of_life.db` 是真实生活数据，**禁止物理删除**。新增表走 `create_all`、加列走 `migrate_schema`；任何批量操作前**先整库备份到 `backups/`**。
   - ⚠️ **本轮修 bug 时禁止用真实库造故障数据**。验证一律在内存库（`sqlite:///:memory:`）或 `backups/` 里的副本上进行。真实库只用于"改完确认没坏"的冒烟。
2. **兼容过渡**：老数据必须容忍新字段为空。新字段一律可空或无破坏默认值；**已结算的历史记录不得被重算**。
   - 本轮唯一新增列 `events.is_deleted`：`default=False` + 启动迁移回填 `False`，**不重建表、不删列**。
3. **一个 commit = 一个逻辑单元**，中文 message `类型: 简述`（如 `fix(P0-1): 停用危险重置入口`）。**只 commit，不 push。**
4. **一致性铁律**（v1.5 B-03 教训，不得违反）：
   - 金币只有 `coin_service.grant()` 一个写入口
   - 属性值写入统一走 `judge_service._clamp_attribute_value`
   - 挑战加点必须复用 `judge_service.confirm()`
   - 任何"更新"语义**不得用"先删后建"实现**
5. **不得顺带做本轮之外的事**（禁区清单）：
   - ❌ 不做 M4 上云 / 多用户 / 认证 / CORS 收紧（第 6 节「M4 门槛」是**上云前置清单，不在本轮**）
   - ❌ 不改 13 个属性维度的名称、数量、别名
   - ❌ 不上调商店定价来"平衡"挑战奖励；不加经济奖励上限
   - ❌ 不把 `COIN_TABLE` 升回正常定价权威（v1.10 已降级为解析兜底，保持现状）
   - ❌ 不做"万能豁免券"、不做日历衰减、不做分组免扣
   - ❌ 不动 E 类未启动项（B1 拍照识别 / C1 日记追问联动 / D3 AI 分析显化）
   - ❌ 不重报已修的 bug 为 P0（Codex 第 6 节已点名：calendar 简写、五处 parent 过滤**代码已覆盖**，不要重复修）

---

## 一、必须先定的 4 个产品口径（含推荐与理由）

> 这 4 个问题会**直接改变改法**，执行者不能自行选择。以下是我给的推荐，用户已确认按此执行。**若执行者认为推荐有技术障碍，停下来报告，不要自行改口。**

### 口径 1 · 满级主维是否还能下降？

**背景**：CODE_GUIDE 写「13 维一律可涨可跌」，但代码里**主维满 100 时，负向变化会转给最低子维**（`subdimension_service.resolve_write_target`）。这两者在语义上是冲突的。

**推荐：满级主维仍然可以下降，撤销"转给最低子维"的负向分流。**

**理由**：
- 「一律可涨可跌」是**你写死的设计原则**（记忆中有明确记载："13 维属性一律可涨可跌，禁写任何'某类维度免扣'逻辑"）。转给子维 = 变相的"免扣"，违反原则。
- 满级是你努力的结果，不是"免死金牌"。一个满级智力的人熬夜打游戏，智力该跌就跌。
- 子维分流的**本意**是"细粒度记录"，不是"替主维挨扣"。负向也应该按同样的路由规则走，但**不能因为主维满了就换个落点**——应该允许主维从 100 跌下来。
- 若担心"刚满级就跌很难受"，那是**心理设计问题**，不是数据模型问题；真要缓解，应该用「满级徽章」之类**不改变数值语义**的方式，而不是偷偷改扣分落点。

**落地**：`subdimension_service.resolve_write_target()` 在目标主维达 `max_value` 时，**正负向行为一致** —— 正向按原规则分流子维，负向直接落主维（允许下降）。

---

### 口径 2 · 删除事件后金币是否撤销？

**背景**：现状删除事件只回滚属性，**金币不动**（日常奖励 +2、成就奖励、挑战押金/奖励都不撤销）。

**推荐：金币不撤销，但必须在删除审计里明确记录"本事件关联的金币未回滚"。**

**理由**：
- **金币是"已发生事实"的记录**。你当时确实记了一笔，+2 币已经进过账，也已经在你的余额里被"感知"过（可能已经花掉了）。
- **强行撤销会造成负余额**：如果 +2 已经花掉，再撤 −2 就透支了 —— 而 `coin_service.grant()` 明确**禁止透支**（会抛 `InsufficientCoins`）。为了让删除能成功，就得给金币开一个"允许负"的后门，**这个后门比不撤销危险得多**。
- **挑战经济牵连更广**：一笔挑战奖励撤销，可能导致"本已结算的挑战变成欠款"，这是你明确不想引入的复杂状态。
- **用户感知**：误提交的文章删掉、属性回滚了、但多了 2 币 —— 这几乎无感。而"删了篇日记反而欠 30 币"是极强的负面体验。
- 折中：**审计里写清楚**。删除时在 `judgment_logs` 的 payload 里加 `"coins_rolled_back": false, "coins_note": "日常/成就/挑战金币不随事件删除回滚"`，保证账目解释得清。

**落地**：`delete_event()` 只回滚 `attribute_history`，**不触碰 `coin_ledger`**，但在 `_log()` 的 payload 里显式声明。

---

### 口径 3 · 成就追溯的触发时机？

**背景**：DECISIONS 说成就"自然追溯"，但代码里**没有触发点**——打开应用不检查，打开成就墙也不检查（`achievements.py` 的 GET 只展示）。真实库有 23 条日记来源事件，成就表却是 0 条，就是这个原因。

**推荐：打开成就墙时触发（惰性追溯），不在应用首屏触发。**

**理由**：
- **成本更低**：`check_and_grant()` 要扫历史（日记连续天数、事件计数），每次打开应用都跑一遍是浪费 —— 单用户库小，但不是好习惯。
- **时机自然**：用户看不到的时候，成就"点亮了"也没意义。打开成就墙 = "我想看成就了"，此时点亮，正反馈最强。
- **并发安全**：`(user_id, code)` 唯一约束保证不会重复发币，即使两次请求同时触发，`IntegrityError` 捕获后 rollback 即可。
- **避免首屏卡顿**：如果将来历史数据变多，首屏触发会拖慢启动。
- **不采纳**"打开应用就发"：用户感知不到延迟收益，反而增加启动路径复杂度。

**落地**：`GET /achievements` 内先调 `achievement_service.check_and_grant(db, user)`（用 `try/except IntegrityError` 包住），再返回 `wall()`。App.vue **不改**。

---

### 口径 4 · 已确认入账的事件能否补充 / 反驳 / 编辑？

**背景**：现状 `supplement()` / `dispute()` **不检查判定是否已 `confirmed`**，可以从普通判定中心入口对已入账的判定再发起重判 → 重复入账。

**推荐：已入账（`confirmed`）后冻结正文与判定，禁止 supplement / dispute / 再次 confirm。允许的例外只有一个 —— 通过"删除事件"来撤销（走 P0-5 的逻辑删除 + 流水回滚）。**

**理由**：
- **"锁定"是最小稳定方案**。你真正需要的场景是"我记错了" → 那应该是**删除这笔记录**，而不是"在已入账的基础上再改一次"。后者本质上是在改写历史账目，和为审计留痕的目标冲突。
- **如果允许修订**，按 Codex 的说法，必须定义完整流程："反向旧实际流水 → 同 id 重新判定 → 重新确认"，还要定义金币是否调整。**这套流程本身就是一个版本的工作量**，且和你"审计只增不删"的理念有张力。
- **误提交有出口**：删除事件（P0-5）已经能回滚属性并保留审计。功能上没有死角。
- **挑战相关例外**：挑战完成自述**允许在挑战页原 id 重判**（挑战有自己的生命周期，`accepted` 状态下的判定不是"已入账"，而是"待结算"）。这一点区分清楚：**`confirmed` 才是入账，`accepted` 是待结算。**

**落地**：新增 `_require_reviewable(db, judgment)` —— 判定 `status == "confirmed"` 时抛 `ValueError`，路由层转 409。`supplement()` / `dispute()` / 普通 `confirm()` 入口都先过这个检查。

---

## 二、批次划分（建议的 commit 切分）

用户选择"一次性全改"，以下是**推荐的 commit 顺序**——不是为了分批交付，而是为了**出错时能定位**。每条 P0 一个 commit（或 commit 组），按此顺序做，前一条的产物是后一条的输入。

```
批次 1 · 数据安全与红线（独立、低风险、可当天冒烟）
  commit 1  P0-1  停用危险重置入口
  commit 2  P0-8  settings 隔离内部配置（含 Key 掩码）
  commit 3  P1-1  设置页挂载加载模型配置
  commit 4  P1-2  折叠缓存防崩
  commit 5  P1-3  补课挑战押金派生
  commit 6  P1-4  建档判据改用 onboarding_completed

批次 2 · 事务骨架（互相咬合，必须一起设计、一起交付）
  commit 7  P0-2  事务一致性（confirm 加 commit 参数 + 状态抢占）
  commit 8  P0-3  金币原子增减（grant 条件更新 + 启动资金锁）
  commit 9  P0-9  挑战遵守科学判定 + 豁免券时段修复
  commit 10 P1-7  停滞扣分同事务 + 计入子维度活动

批次 3 · 数据完整性与外围（全局影响面，放最后）
  commit 11 P0-5  删除改逻辑删除（改数据模型 + 11 文件消费点）
  commit 12 P0-4  锁住已入账判定（依赖口径 4）
  commit 13 P0-6  模型数值与入账聚合严格校验
  commit 14 P0-7  目标终态防重复结算
  commit 15 P1-5  成就自然追溯 + 去重复路由
  commit 16 P1-6  今日盘点重试复用事件
  commit 17 P1-8  备份路径与实际库对齐
  commit 18 P1-9  JSON 导出补齐 17 表
```

---

## 三、批次 1 · 数据安全与红线

### P0-1 · 停用危险重置入口

| 项 | 内容 |
|---|---|
| **位置** | `app/services/onboarding_service.py:332`、`app/routers/onboarding.py:62` |
| **现象** | `reset-all` 直接批量 `delete()` 事件、判定、审计、属性流水、目标；**不备份**、不走删除接口，且**不清理**金币、挑战、兑换等关联状态 → 留下悬空引用。普通 `reset` 允许重新生成面板，**覆盖当前值与初始快照**但保留旧属性流水 → **破坏"初始值 + 流水 = 当前值"恒等式**，并可能**再次发放启动资金** |
| **红线** | 违反「数据红线：禁止物理删除」「首次建档一次性」 |
| **根因** | 服务层把"重置"实现成了"清库"，且没有"是否已建档"的前置校验；`_generate_panel()` 也没有二次防线 |

**修复方案**：

1. `onboarding_service.py` 新增前置断言 `_assert_unbuilt_profile(db, profile)`：若 `profile.onboarding_completed` 或 `profile.initial_attributes_snapshot` 非空，或**已有 `attribute_history` 流水**，则抛 `ValueError`。
2. `reset_onboarding()` 改为：先断言，再清 `onboarding_state` / `pending_adjustment`（**只清问卷状态，不动任何真实数据**）。
3. `reset_all_data()` 改为**直接抛 `ValueError`**：`"真实数据清空入口已停用；批量清理必须先整库备份并走事件删除接口。"`
4. `_generate_panel()` **在第一条配置读取 / 模型调用之前**插入 `_assert_unbuilt_profile(db, profile)` —— 防止直接调 service 绕过路由。
5. 两个路由改为捕获 `ValueError` → `db.rollback()` → `HTTPException(409, str(exc))`。`reset-all` 路由直接返回 409，不进 service。
6. 前端：**移除** `SettingsView.vue` 的 reset-all 操作区、移除 `Onboarding.vue` 已建档态的"重建"按钮。**不要只隐藏前端而留下可用的清库 service。**

**影响范围**：`onboarding_service.py`、`routers/onboarding.py`、`SettingsView.vue`、`Onboarding.vue`（4 文件）
**是否改动数据模型**：否
**是否改动对外接口**：是 —— 两个重置入口在有基线/流水时返回 **409**
**预估改动量**：大（后端止损约 30–50 行，前端移除交互涉及 2 文件）

**验证方式（内存库）**：
- 在仅有基线与流水、无其他数据的库上调用两个重置入口 → 均被拒（409），且 **17 张表计数、`initial_attributes_snapshot`、13 维数值、金币余额完全不变**
- 直接调 `_generate_panel()` → 同样被拒
- 空白的、`onboarding_completed=False` 且无流水的库 → `reset_onboarding` 仍可正常重置问卷状态
- 前端：设置页找不到 reset-all 按钮；已建档后进入 Onboarding 页看不到"重建"

**验收证据**：`reset-all` 返回 409 的截图 + 调用前后 17 表计数对照（应完全相同）

---

### P0-8 · 通用设置接口不得回显或改写 BYOK 及内部审计设置

| 项 | 内容 |
|---|---|
| **位置** | `app/routers/settings.py:18`（GET）、`:35`（POST） |
| **现象** | GET 返回**全部** `Setting.value`，其中包含 **BYOK 的明文 API Key**；POST 接受**任意 key** 并原样回显，能绕过专用 BYOK 校验接口，也能覆盖 `stagnation_checks` 等内部审计记录 |
| **红线** | 违反「BYOK 掩码：GET 绝不明文」 |
| **根因** | 通用设置接口没有白名单概念，把"内部状态存储表"当成了"公开配置接口" |

**修复方案**：

1. 定义白名单常量：
   ```python
   PUBLIC_SETTING_KEYS = frozenset({
       "gamification_modules", "hidden_attributes", "disabled_attributes",
   })
   ```
2. **GET `/settings`**：查询加 `.filter(Setting.key.in_(PUBLIC_SETTING_KEYS))`；先给三个 key 填默认值（`gamification_modules` 全 False / 两个列表为空），再用库里实际值 `update()`。
3. **POST `/settings`**：`body.key` 不在白名单 → 400 `"该设置只能由专用接口修改。"`
4. **写值校验**（防止前端传垃圾）：
   - `gamification_modules`：必须是 dict、key 集合 ⊆ `GAMIFICATION_MODULES`、**值必须是 `bool`**（用 `type(v) is not bool` 而非 `isinstance`，避免 0/1 混入）
   - 另两个：必须是 list、元素必须是 str、集合 ⊆ `ATTRIBUTE_DIMENSIONS_SET`，写入前去重 `list(dict.fromkeys(value))`
5. 内部 key（`llm_config_primary` / `llm_config_aux` / `stagnation_checks` / `unreal_count` 等）**只能走专用服务**。

**影响范围**：`routers/settings.py`、设置页读取逻辑（2 文件）
**是否改动数据模型**：否
**是否改动对外接口**：是 —— GET 不再包含内部配置；任意 key 写入返回 400
**预估改动量**：中（约 50–75 行）

**验证方式（内存库）**：
- 往 `settings` 写入含测试 Key 的 `llm_config_primary` → `GET /settings` **不出现该 key、不出现 Key 明文**
- `GET /llm-config` 仍返回**掩码**值（回归）
- `POST /settings` 写内部 key → 400，且 **DB 记录未变**
- 三个公开 key 正常读写；`gamification_modules` 传字符串值 / 未知模块名 → 400
- `JSON 导出` 全文搜索测试 Key → **不存在**（与 P1-9 联动验收）

**验收证据**：`GET /settings` 响应体（无 Key）+ `POST` 内部 key 的 400 截图 + 导出文件全文无 Key

---

### P1-1 · 设置页挂载时真正加载已有模型配置

| 项 | 内容 |
|---|---|
| **位置** | `frontend/src/components/SettingsView.vue:259` |
| **现象** | 定义了 `loadLLMConfig`，但 `onMounted` 只调用 `load()` 和 `loadBackups()` |
| **影响** | 已绑定的模型仍显示"未配置"，`enabled` / `base_url` / `model` 不回填，**保存时可能带入错误默认状态，误关原有配置组** |
| **修复** | `onMounted` 中补上 `loadLLMConfig()` |

**影响范围**：`SettingsView.vue`（1 文件）
**是否改动数据模型**：否 ｜ **是否改动对外接口**：否 ｜ **预估改动量**：小（1 行）

**验证方式**：已有 primary/aux 配置时首次打开设置页 → 立即显示 `configured`、正确端点与开关状态；**Key 输入框仍为空，仅 placeholder 显示掩码**

---

### P1-2 · 损坏的日期折叠缓存不能让两个历史页面无法挂载

| 项 | 内容 |
|---|---|
| **位置** | `frontend/src/composables/useDateGroups.js:17` |
| **现象** | 初始化直接 `JSON.parse(localStorage.getItem(...))`，**没有 try**（写缓存反而有保护） |
| **影响** | 一个损坏的 localStorage 值就能让**手账本**或**判定中心**在 setup 阶段抛错 → **白屏** |
| **修复** | 包 `try/catch`，并校验解析结果是**非数组的普通对象**，否则回落 `{ today: true }` |

**影响范围**：共享 composable + 2 个消费者（1 文件）
**是否改动数据模型**：否 ｜ **是否改动对外接口**：否 ｜ **预估改动量**：小（约 10 行）

**验证方式**：把 localStorage 该项手动改成 `"{{{"` / `"null"` / `"[1,2]"` / 合法对象 → 四种情况下页面**均可挂载**，合法折叠状态保持

---

### P1-3 · 补课挑战押金也必须由奖励乘 0.6 派生

| 项 | 内容 |
|---|---|
| **位置** | `app/services/stagnation_service.py:224` |
| **现象** | 补课挑战直接取旧兜底表的 `reward=35 / deposit=20`，**没有走 `derive_deposit`** |
| **影响** | 同一应用出现**两种押金比例**（正常挑战 0.6，补课挑战 35→20 = 0.571） |
| **修复** | `reward, _ = challenge_service.coin_params("weekly", difficulty)`；`deposit = challenge_service.derive_deposit(reward)` |

**边界**：本小修**不自行决定**补课挑战是否也应调用 AI 定价（那是口径问题，见 Codex 第 7 节第 10 问，**留待后续版本**）。
**是否改动数据模型**：否 ｜ **是否改动对外接口**：否 ｜ **预估改动量**：小（2 行）

**验证方式**：新生成 `reward=35` 的补课挑战 → `deposit` 应为 **21**（`max(1, round(35*0.6))`）；**历史已接受挑战不重新定价**

---

### P1-4 · 是否建档应读 `onboarding_completed`，不能用属性数量判断

| 项 | 内容 |
|---|---|
| **位置** | `frontend/src/App.vue:37` |
| **现象** | 启动时 `ensure_dimensions` 已创建 13 个中性维度，App 却以 `attributes.length > 0` 当"已建档" |
| **影响** | **新库（未做问卷）也被当成已有角色**，首次引导提示失真，用户看到的是"中性占位面板"而非 AI 建档结果 |
| **修复** | `refreshProfile()` 并行取 `getAttributes()` + `getOnboardingStatus()`；`hasProfile = !!status.completed`（两个 API helper **已存在**，无需新增） |

**影响范围**：`App.vue`（1 文件） ｜ **预估改动量**：小（约 10 行）

**验证方式**：有 13 个 seed 维度但 `completed=false` → 显示**未建档**（进入引导）；完成后 → 显示已建档

---

## 四、批次 2 · 事务骨架

> ⚠️ 本批四条**互相咬合**（P0-2 改 `confirm()` 签名 → P0-3 改 `grant()` → P0-9 用新 `confirm` → P1-7 用新事务边界），**必须一起设计、一起交付**。中间态是坏的，不要分次提交后中途停止工作。

### P0-2 · 判定、属性流水、金币和挑战终态必须一次提交

| 项 | 内容 |
|---|---|
| **位置** | `app/services/judge_service.py:680`、`app/routers/judgments.py:152`、`app/services/challenge_service.py:524` |
| **现象** | ① `confirm()` **内部自己 commit**，路由随后才发金币 —— 金币失败只 rollback 第二段 → 留下「已确认但少币」的记录，重试又被状态拦住。② 挑战 `settle()` **吞掉低置信度异常**继续结算（`except ValueError: judgment.status = "adjusted"; db.commit()`），空建议甚至绕过置信度检查 → 留下「属性已入账但押金未返」。③ 挑战来源判定还能从**普通确认入口**获得日常金币，随后 `settle()` 因已 `confirmed` 而失败 |
| **红线** | 违反「统一入账」；低置信度应拦截而非绕过 |
| **根因** | 事务边界被拆散在 service 和 router 两层，各自 commit；异常被当作"可继续"而非"应停止" |

**修复方案**：

1. **`confirm()` 加事务参数**（默认保持旧调用兼容）：
   ```python
   def confirm(db: Session, judgment: AIJudgment, *, commit: bool = True) -> AIJudgment:
   ```
   `commit=False` 时把最后的 `db.commit()` 换成 `db.flush()`，由调用方决定事务边界。
2. **状态抢占防并发双结算**：在取得 user 之后、任何属性写入之前，用条件 UPDATE 抢占：
   ```python
   claimed = db.query(AIJudgment).filter(
       AIJudgment.id == judgment.id,
       AIJudgment.status != "confirmed",   # 只有未入账的才能抢占
   ).update({"status": "claimed"}, synchronize_session=False)
   if claimed != 1:
       db.rollback()
       raise ValueError("该判定已入账或正在处理中，请刷新后重试。")
   db.refresh(judgment)   # 抢占后必须刷新，再读 confidence
   ```
3. **抢占后重新校验置信度**（不要在抢占前读旧值）：
   ```python
   conf = _parse_confidence(judgment.confidence)
   if conf < CONFIDENCE_CONFIRM_MIN:
       raise ValueError("判定置信度不足或不合法，请补充信息后重新判定。")
   ```
4. **普通确认路由**（`routers/judgments.py`）：把 `confirm` + 金币发放放进**同一个事务**：
   ```python
   judgment = judge_service.confirm(db, judgment, commit=False)
   coin_service.reward_event_confirm(db, user, judgment)   # 内部只 flush
   db.commit()
   ```
   `except Exception: db.rollback(); raise`
5. **挑战 `settle()`**：`except ValueError` 改为**不吞异常** —— rollback 后**抛出**，保留 `accepted` / `pending` 状态，**不先发奖励**（即口径：低置信度锁住**整笔结算**，见 Codex 第 7 节第 3 问的推荐做法）。加点、押金、奖励、终态**同事务提交**。
6. **前端 `checkin`/`ChallengeView`**：`canSettle(c)` 需校验 `confidence` 落在 `0.8 ~ 1` 区间才允许点结算按钮，低置信度显示"需补充信息"。

**影响范围**：`judge_service.py`、`routers/judgments.py`、`challenge_service.py`、`ChallengeView.vue`（4 文件）
**是否改动数据模型**：否（`claimed` 是既有 `status` 字段的中间态，需确认 `AIJudgment.status` 无 Enum 强约束——**执行者须先查 model 定义**）
**是否改动对外接口**：是 —— 重复确认返回 409/400；低置信度挑战结算返回明确错误
**预估改动量**：大（约 150–220 行）

**验证方式（内存库）**：
- 让金币发放抛异常 → **属性值不变、流水不增、判定状态不变**（全回滚）
- 并发两个 confirm → 只有一条入账，另一条被抢占拒绝
- 挑战 `confidence=0.5` → 结算被拒，`challenge.status` 仍为 `accepted`，**押金未退、奖励未发**
- 低置信度挑战 → 状态 `adjusted` 不再出现（该伪状态应废弃）
- 完整流程冒烟：录事件 → 判定 → 确认 → 查余额 `+2`

**验收证据**：注入异常的测试脚本输出（属性/流水/状态三项前后对照）+ 并发 confirm 的两次响应

---

### P0-3 · 金币原子增减

| 项 | 内容 |
|---|---|
| **位置** | `app/services/coin_service.py:97`、`app/services/onboarding_service.py:186` |
| **现象** | `grant()` 用 `current = int(profile.coins or 0)` → `new_balance = current + delta` → `profile.coins = new_balance`，**读-算-写不是原子的**；并发两个 grant 会**互相覆盖**（经典 lost update）。`grant_startup_bonus_if_needed()` 用"先查有无流水，再 grant"，非原子 → **并发可能发两次启动资金** |
| **红线** | 违反「金币只有 grant 一个写入口 + 账目恒等」的精神（余额和流水会脱节） |
| **根因** | 用 ORM 对象赋值而非数据库条件更新；幂等检查与写入之间有竞态窗口 |

**修复方案**：

1. **`grant()` 改用条件更新**（原子递增 + 余额校验同时完成）：
   ```python
   from sqlalchemy import func

   new_balance = db.query(func.coalesce(UserProfile.coins, 0) + int(delta)).filter(
       UserProfile.user_id == user.id,
       func.coalesce(UserProfile.coins, 0) + int(delta) >= 0,   # 禁止透支
   ).scalar()
   if new_balance is None:
       raise InsufficientCoins(...)
   ```
   或等价方案：单条 `UPDATE ... SET coins = coins + :delta WHERE user_id = :uid AND coins + :delta >= 0`，用 `rowcount` 判断是否成功。**关键是不要在 Python 里做 `current + delta`。**
2. **启动资金加锁**：`grant_startup_bonus_if_needed()` 调用前先对 `UserProfile` 行加写锁（`db.query(UserProfile).filter(...).update({UserProfile.id: UserProfile.id}, synchronize_session=False)`），再做"有无 onboarding_bonus 流水"的判断——**先锁后查**，消除竞态窗口。
3. `onboarding_service.py:186` 发放启动资金的调用点同步改用新路径。

**影响范围**：`coin_service.py`、`onboarding_service.py`（2 文件）
**是否改动数据模型**：否
**是否改动对外接口**：否
**预估改动量**：大（约 90–130 行）

**验证方式（内存库）**：
- 并发 10 次 `grant(+10)` → 余额恰好 `+100`，流水 10 笔，**每笔 `balance_after` 单调正确**
- `grant(-1000)`（余额不足）→ 抛 `InsufficientCoins`，**余额与流水均不变**
- 并发调 `grant_startup_bonus_if_needed()` 两次 → **只发一次**，`onboarding_bonus` 流水只有 1 笔
- 全局对账：`sum(coin_ledger.delta) == user_profiles.coins`

**验收证据**：并发测试脚本输出 + 对账 SQL 结果

---

### P0-9 · 挑战也要遵守科学判定和豁免；过期券仍应保护其有效时段内的补录事件

| 项 | 内容 |
|---|---|
| **位置** | `app/services/challenge_service.py:459`、`app/services/exemption_service.py:156` |
| **现象** | ① 挑战完成调用**独立 prompt**，缺锚点、子维度上下文、`disabled` 与 `realistic` 校验 → **同一生活行为从普通记录和挑战入口得到不同科学约束**。② 普通券按 `occurred_at` 判断，但查询排除了 `expired` → **先打开券列表使其过期，再补录昨日事件，就失去原时段保护** —— 是否先读过券列表会改变历史事件的扣分！③ 挑战退缩扣分没有统一券 hook |
| **红线** | 违反「科学底线（锚点 + realistic）」「豁免券按事件发生时间命中」 |
| **根因** | 挑战走了旁路 prompt；券的状态机把"现在过期"和"过去时段无效"混为一谈 |

**修复方案**：

1. **扩展现有挑战完成 prompt**（**保留一次 LLM 调用，不新增模型调用**）：
   - `messages[0]["content"] +=` 六条硬约束：依据锚点判定不许迎合、必须输出 `realistic` + `realistic_reason`、不科学则 `realistic=false` 无正向结果、`confidence` 必须 0~1、禁用主维及子维不得给分、可用合法子维名。
   - `messages[1]["content"] +=` 注入：**科学锚点**（`format_anchors_text`）、**主维现状**（`_attribute_context`）、**子维度上下文**（`_subdimension_context`）、**禁用维度**（`json.dumps(sorted(disabled))`）。
2. **模型返回后、任何 commit 之前**：
   ```python
   if result.get("realistic") is not True:
       db.rollback()
       raise ValueError("挑战自述未通过真实性校验：" + str(result.get("realistic_reason", "请补充可验证的真实细节。")))
   confidence = judge_service._parse_confidence(result.get("confidence"))
   changes = judge_service._parse_changes(result.get("affected_attributes"), subdimension_service.child_name_set(db, user))
   changes = _apply_outcome_changes(changes, outcome, challenge)
   ```
   然后按标准主维及子维父级过滤 `disabled`。
3. **`confirm` 内统一应用券**（覆盖挑战完成、主动放弃、到期退缩三种路径）：取 Event → `_apply_exemption(db, user, event, suggested_changes)` → 用返回的 `changes` 入账。
4. **审计 payload 保存三段**：`{"raw_changes": ..., "applied_changes": ..., "exemption": exemption_hit}`。
5. **历史券命中修复**：
   ```python
   # find_active：状态条件改为
   Exemption.status.in_(["active", "used", "expired"])

   # mark_used：
   def mark_used(db, row):
       if row.status in ("active", "expired"):
           row.status = "used"; row.used_at = datetime.now(); db.flush()
   ```
   **语义澄清**：`expired` 只表示"现在已过时段"，**不表示过去时段内失效**；有效性仍由 `window_of(row)` + 事件 `occurred_at` 判断。

**影响范围**：`challenge_service.py`、`judge_service.py`、`exemption_service.py`、`prompts/challenge.py`（3–4 文件）
**是否改动数据模型**：否
**是否改动对外接口**：否（非法真实性结果返回 400）
**预估改动量**：大（约 80–120 行）

**验证方式（内存库）**：
- 捕获挑战 messages → 确认含真实锚点 / 主子维 / disabled 段落
- 不科学自述（如"我一口气做完 500 个俯卧撑"）→ `realistic=false` → 不产生可入账结果
- **券时段测试**：造一张"昨天下午"的券 → ① 先读券列表使其 `expired` → 补录昨天下午事件 → **仍命中豁免**；② 不读列表直接补录 → **结果相同**
- 挑战 `retreated` 的负点被券归零；**正点和金币规则不变**

**验收证据**：两种读取顺序下的事件 `final_changes` 对照（必须相同）+ realistic 拦截的返回体

---

### P1-7 · 停滞扣分与冷却记录同事务，并计入子维度活动

| 项 | 内容 |
|---|---|
| **位置** | `app/services/stagnation_service.py:56`、`:180` |
| **现象** | ① 扣分先 `commit`，冷却记录最后**另 commit** → 冷却写入失败时重试**可能重复扣 0.3**。② `_last_activity()` **只查主属性 id**，忽略子维度活动 → 满级用户持续练子维仍被问"停滞"。③ `answer` 传未知名字会**创建 50 分属性** |
| **红线** | 合理（不引入日历衰减，保留"只问不自动扣、用户确认才扣"） |
| **根因** | 两个事务边界；活动查询没有下钻子维；名字未做白名单校验 |

**修复方案**：

1. `answer` 进入后先**锁 `UserProfile` 行**，再校验合法主维；**不建未知属性**：
   ```python
   attr = db.query(Attribute).filter(
       Attribute.user_id == user.id,
       Attribute.name == name,
       Attribute.parent_id.is_(None),
   ).populate_existing().first()
   if attr is None or name in _disabled_attributes(db, user.id):
       raise ValueError("该主维度不存在或已关闭判定。")
   ```
2. `_set_checks()` 和 `_build_restart_challenge()` 里的 `db.commit()` → `db.flush()`；`answer` 第 180 行的 commit 也改 flush。
3. **补课挑战创建用 savepoint 保护**（避免可选创建失败破坏已准备好的扣分/冷却事务）：
   ```python
   try:
       with db.begin_nested():
           challenge = _build_restart_challenge(db, user, name)
   except Exception:
       challenge = None
   checks[name] = now.isoformat()
   _set_checks(db, user.id, checks)
   db.commit()
   ```
4. **`_last_activity()` 下钻子维**：
   ```python
   from sqlalchemy import or_
   ids = db.query(Attribute.id).filter(
       Attribute.user_id == user_id,
       or_(Attribute.id == attribute_id, Attribute.parent_id == attribute_id),
   )
   row = db.query(AttributeHistory.created_at).filter(
       AttributeHistory.user_id == user_id,
       AttributeHistory.attribute_id.in_(ids),
   ).order_by(AttributeHistory.created_at.desc()).first()
   ```

**影响范围**：`stagnation_service.py`（1 文件）
**是否改动数据模型**：否 ｜ **是否改动对外接口**：路径不变，未知/禁用维度返回 400 ｜ **预估改动量**：中（约 40–70 行）

**验证方式（内存库）**：
- 让冷却写入抛异常 → **扣分一并回滚**
- 重复回答同一维度 → **只扣一次**
- 传未知维度名 → 400，且 `attributes` 表**仍是 13 行**
- 最近有**子维度**流水时，主维**不被视为无活动**
- 回答"做了没记" → 不产生扣分

---

## 五、批次 3 · 数据完整性与外围

### P0-5 · 删除事件必须保留审计，并按真实入账流水回滚 ⭐ 本轮最重

| 项 | 内容 |
|---|---|
| **位置** | `app/services/judge_service.py:828` |
| **现象** | ① 先写 `delete` 审计，随后**把所有审计和判定物理删除** → **删除操作把自身证据也消灭了**。② 回滚用 `final_changes or suggested_changes` → **实际入账为空时会错误回退到"名义建议值"**（比如 100 封顶导致实际加 0，却按建议值 −5 反扣）。③ 不实事件直接物理删 Event → 可能**留下已有判定或诚信扣分引用**（悬空外键）。 |
| **红线** | **违反「审计只增不删」（v1.5 立的最硬的一条）** |
| **根因** | 用物理删除实现"误提交兜底"；用建议值而非真实流水做回滚依据 |

**修复方案**：

1. **`Event` 新增逻辑删除标记**：
   ```python
   is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
   ```
   由 `migrate_schema` **补列并回填 `False`**，不重建表、不删列。
2. **重写 `delete_event()`**：
   - 用条件 UPDATE 抢占 `is_deleted`（`UPDATE ... SET is_deleted=1 WHERE id=? AND user_id=? AND is_deleted=0`，`rowcount != 1` 则抛"已删除或不存在"）
   - 查该事件下**真实入账流水**：`AttributeHistory.filter(event_id=?, judgment_id.in_(ids))`，按 `attribute_id` 汇总 `delta`
   - **按真实汇总值反向**（不再用 `final_changes or suggested_changes`）；单属性一次夹取
   - 判定状态改 `judgment.status = "deleted"`，写 `_log(..., "delete", payload={"source_history_ids": [...], "reversed_changes": [...], "coins_rolled_back": False, "coins_note": "日常/成就/挑战金币不随事件删除回滚"})`
   - **不删任何行**
3. **⚠️ 必须给 10 处消费点加过滤** `Event.is_deleted.is_(False)` —— **只改删除函数是不够的，漏一处用户就会看到"删掉的事件还在影响 AI 判断"**：

   | 文件 | 函数 | 已核实 |
   |---|---|---|
   | `routers/events.py` | `list_events` | ✅ :100 |
   | `routers/events.py` | `get_heatmap` | ✅ :120 |
   | `routers/events.py` | `judge/get/update/delete` 的 `db.get(Event,...)` 后**检查 is_deleted** | ✅ :150/189/199/227 |
   | `routers/judgments.py` | `list_judgments` 的 Event join；普通 confirm 取 Event 后检查 | ✅ :158 |
   | `routers/report.py` | `generate_report` | ✅ :18 |
   | `services/achievement_service.py` | `_metrics` 的 journal 和 event 计数 | ✅ :86 |
   | `services/coin_service.py` | `_journal_days` | ✅ :152 |
   | `services/exemption_service.py` | `_recent_events` | ✅ :247 |
   | `services/item_service.py` | `count_in_period`、`period_count_map`、`build_stats` | ✅ :33/51/92 |
   | `services/judge_service.py` | `_recent_same_category_count`、`_recent_events_context`、`_recent_24h_context`、`_today_events_context`；supplement/dispute 取 Event 后检查 | ✅ :86/113/139/178/692/758 |
   | `services/memory_service.py` | `_events_summary` | ✅ :37 |
   | `services/subdimension_service.py` | `_related_events` | ✅ :146 |

   > 上表 13 个函数**已逐个用 Grep 核实存在**（2026-10-08），执行者可对照行号定位。
4. **判定列表同时排除** `AIJudgment.status == "deleted"`。
5. **导出与备份保留删除记录**（`export.py`、`backup`）—— **不把"逻辑隐藏"误当成"彻底遗忘"**。
6. **不实事件处理**：保留 Event（逻辑删除即可），拒绝已有现行判定，追加审计；**不留可确认的旧 `pending`**。

**影响范围**：`models/__init__.py`、`judge_service.py`、`events.py`、`judgments.py`、`report.py`、`achievement_service.py`、`coin_service.py`、`exemption_service.py`、`item_service.py`、`memory_service.py`、`subdimension_service.py`（**11 文件**）
**是否改动数据模型**：**是**（`events.is_deleted`）
**是否改动对外接口**：接口路径不变；重复删除返回明确错误
**预估改动量**：大（约 150–220 行）

**验证方式（内存库）**：
- 删一个已确认事件 → 属性**按真实流水**回滚（构造"100 封顶导致实际 +0"的场景 → 回滚也应为 0，**不能反扣**）
- `ai_judgments` 行**仍存在**，`status="deleted"`；`judgment_logs` **只增不减**
- 删除后：`list_events` 不返回该事件；**热力图、周报、成就计数、日记连续天数、豁免券近期事件、打卡统计、判定上下文、记忆摘要、子维关联事件**全部不含该事件 —— **逐个函数验证，不抽样**
- 重复删除 → 报错，无第二次回滚
- 导出 JSON **仍包含**该事件与判定（保留证据）

**验收证据**：删除前后 13 个消费点查询结果对照表（每项都应减少 1 或不变）+ `judgment_logs` 计数只增不减

---

### P0-4 · 锁住已入账判定

| 项 | 内容 |
|---|---|
| **位置** | `app/services/judge_service.py:687`（`supplement`）、`:750`（`dispute`）、`app/routers/events.py:195`（编辑） |
| **现象** | `supplement` / `dispute` **不检查判定是否已 `confirmed`** → 已入账的判定可再次重判 → **重复入账**；编辑接口在已有入账流水时仍可修改正文，且**继续追加 `invalidate` 日志但保留已确认分数**，前端还提示"旧判定全部作废"（**文案与事实不符**） |
| **红线** | 违反「一条事件一条现行判定」「审计只增不删」 |
| **根因** | 缺少"已入账即冻结"的前置校验 |

**修复方案**（依据**口径 4**）：

1. 新增 `_require_reviewable(db, judgment)`：`judgment.status == "confirmed"` → 抛 `ValueError("该判定已入账，不能重复修订。如需撤销请删除事件。")`。
2. `supplement()` / `dispute()` / **普通 `confirm()` 入口**都在最前面调用它。
3. 编辑接口（`events.py:195` 区域）：修改前对 Event 做写锁，并**拒绝已有入账流水或 `confirmed` 判定**的事件；未确认的编辑**继续追加 `invalidate` 日志，不删除判定**。
4. **前端必须同步**：判定卡编辑交互要展示该限制，**不能继续提示"旧判定全部作废"却保留已确认分数**。
5. **挑战例外（重要）**：挑战的判定在 `accepted` 状态下是"待结算"而非"已入账"，**允许在挑战页原 id 重判**（正常 `supplement` 不会同步 `challenge.outcome`，这是 Codex 第 7 节第 4 问，**本轮按"挑战页原 id 重判"实现，普通判定中心对挑战判定只读**）。

**影响范围**：`judge_service.py`、`routers/events.py`、`JudgmentList.vue`（3 文件）
**是否改动数据模型**：否（用现有行写锁，**不新增唯一索引、不重建表**）
**是否改动对外接口**：是 —— 已入账的修订/编辑返回明确拒绝
**预估改动量**：大（约 100–150 行）

**验证方式（内存库）**：
- `confirmed` 后调 supplement / dispute / 再次 confirm → **属性和流水均不变**
- `pending` → 编辑 → 重判 **id 不变**、日志**增加**
- 并发首判 → 最终**只有一条**判定
- 判定期间编辑正文 → 旧响应被拒绝
- 挑战 `pending` 判定可在挑战页重判；普通判定中心对挑战判定**只读**

**验收证据**：confirmed 后三种操作均报错且账目零变化的前后对照

---

### P0-6 · 模型数值与入账聚合统一严格校验

| 项 | 内容 |
|---|---|
| **位置** | `app/services/llm_service.py:172`、`app/services/judge_service.py:304`、`app/services/onboarding_service.py:172` |
| **现象** | ① `json.loads` **接受 `NaN` / `Infinity`** → AI 返回后可能污染数值。② **重复属性名可累计突破 ±5**（同一条建议里写两次"体能"各 +5 → 实际 +10）。③ `confidence` 非法/缺失时**默认为 0.85**（挑战路径）。④ 初始面板缺维度时**自行发明评分**；画像补充传未知名字会**新建 50 分属性** |
| **红线** | 违反「单次单属性 delta 绝对值 ≤5」「13 维固定」 |
| **根因** | `json.loads` 默认允许非标准常量；`_parse_changes` 未按名字合并；缺维度时用兜底猜测 |

**修复方案**：

1. **`_strict_json_loads()`**：`json.loads(..., parse_constant=reject_constant)`，`reject_constant` 对 `NaN`/`Infinity`/`-Infinity` 抛异常。
2. **`_finite_float(raw, fallback)`**：`bool` 直接返回 fallback（**`True` 不能当 1**）；`float()` 捕获 `TypeError/ValueError/OverflowError`；`math.isfinite` 检查。
3. **`_parse_confidence()`**：非法或不在 `[0,1]` → **返回 0.0**（不再默认 0.85）。**所有**首判/补充/反驳/挑战路径统一使用它。
4. **`_parse_changes()` 按名字合并**：
   - 规范化名字（`_normalize_attribute_name`，含别名）
   - **同名字 `delta` 累加**，然后**整体一次 `_clamp_delta`**
   - `reason` / `evidence` 用 `dict.fromkeys` 去重后 `；` 连接
5. **`confirm()` 入账改为"先规范化 → 再按实际写入的 `Attribute.id` 聚合 → 一次夹取"**（**关键**：多个子维度回流同一主维后，也要保证合计 ≤5）：
   ```python
   targets = {}   # key = 最终落点 Attribute.id
   for item in changes:
       attr = by_name.get(item["name"])
       if attr is None: continue
       if attr.name in disabled or (parent and parent.name in disabled): continue
       target, note = subdimension_service.resolve_write_target(db, user, attr)
       # 二次检查 target 是否禁用
       group = targets.setdefault(target.id, {"attr": target, "delta": 0.0, ...})
       group["delta"] += item["delta"] * conf
   for group in targets.values():
       delta = round(_clamp_delta(group["delta"]), 2)   # ← 这里才夹取
       ...
   ```
6. **初始面板严格解析**：`_parse_initial_panel()` —— 非法/重复/缺标准维度直接抛错；**`诚信` 强制 50 起步**；**不发明缺失维度的评分**；`_generate_panel()` 在第一条配置读取前调 `_assert_unbuilt_profile`（与 P0-1 联动）。
7. **画像补充**：`adjustments` 先过 `_parse_changes` 规范化，**删除"未知名字新建 50 分属性"的分支**（`attr is None` → 跳过）。
8. 启动资金 parser 的异常捕获**增加 `OverflowError`**。

**影响范围**：`llm_service.py`、`judge_service.py`、`onboarding_service.py`、`challenge_service.py`（4 文件）
**是否改动数据模型**：否
**是否改动对外接口**：否（非法模型结果变为**可解释的拒绝/重试**）
**是否引入新依赖**：否（`math` 是标准库）
**预估改动量**：大（约 150–220 行）

**验证方式（内存库）**：
- `NaN` / `Infinity` / `1e309` / `bool` / 字符串 delta / 非数组 changes / 非 dict 条目 / 重复别名 → **均不污染库**
- `confidence` 缺失 / 2 / −1 → 一律 0.0（**不再默认 0.85**）
- **同一最终落点的两条 +5 → 累计 ≤5**
- `99 + 5` → 实记 `+1`
- 禁用后确认旧建议 → **不加点**
- 初始快照与实际写入值**相同**（含 `诚信=50`）

---

### P0-7 · 目标终态不能相互切换重复发分

| 项 | 内容 |
|---|---|
| **位置** | `app/services/goal_service.py:66`、`app/schemas/__init__.py:219` |
| **现象** | ① `achieve` 只防"已是 achieved"、`fail` 只防"已是 failed" → **可 `achieve → fail → achieve`** 循环结算。② `related_attribute` 若为**规划力**，达成时**规划力加两次**。③ `reward` / `penalty` **没有有限值、符号、±5 边界校验**；用户可创建 `reward=100` 或未知属性，**造成大额加点或新建维度** |
| **红线** | 违反「单属性 ≤5」「13 维固定」「目标一次结算」 |
| **根因** | 状态转换没做条件原子更新；缺 Schema 边界约束 |

**修复方案**：

1. **新增 `_claim_goal(db, goal, target)`**：条件 UPDATE（`WHERE id=? AND user_id=? AND status='active'`），`affected == 1` → True；若已是目标态 → False；**否则抛错**（终态不可再变）。
2. 各入口替换：
   ```python
   # achieve_goal
   if not _claim_goal(db, goal, "achieved"): return goal, []
   # fail_goal
   if not _claim_goal(db, goal, "failed"): return goal, []
   # cancel_goal
   if not _claim_goal(db, goal, "cancelled"): return goal
   # update_goal：先取 active 写锁，再改字段
   ```
3. **规划力不重复加**：关联奖励判断改 `if goal.related_attribute and goal.related_attribute != "规划力":`
4. **Schema 加边界**（**Service 也须自保，不能只靠新请求 Schema**）：
   ```python
   # GoalCreate
   reward: float = Field(2.0, ge=0, le=5, allow_inf_nan=False)
   penalty: float = Field(-1.0, ge=-5, le=0, allow_inf_nan=False)
   # GoalUpdate
   reward: float | None = Field(None, ge=0, le=5, allow_inf_nan=False)
   penalty: float | None = Field(None, ge=-5, le=0, allow_inf_nan=False)
   ```
5. **`_apply_delta` 硬校验**（防止旧库对象绕过）：
   ```python
   if name not in ATTRIBUTE_DIMENSIONS_SET:
       raise ValueError("目标关联属性必须是标准主维度。")
   if isinstance(delta, bool): raise ValueError("目标点数不合法。")
   delta = float(delta)   # 捕获 TypeError/ValueError/OverflowError
   if not math.isfinite(delta) or abs(delta) > 5:
       raise ValueError("目标单次属性变化必须在 -5 到 5 之间。")
   ```
   `achieve` 检查 `reward` 非负；`fail` 检查 `penalty` 非正。**不新增属性行来"修复"错误输入。**
6. **Router 包装**：`_run_goal_action(db, action, *args)` 捕获 `ValueError` → `db.rollback()` → `HTTPException(409)`。

**影响范围**：`goal_service.py`、`schemas/__init__.py`、`routers/goals.py`（3 文件）
**是否改动数据模型**：否
**是否改动对外接口**：是 —— 非法数值 422、非法终态动作 409
**预估改动量**：大（约 80–110 行）

**验证方式（内存库）**：
- `achieve → fail → achieve` → **不能新增流水**
- 并发 achieve → **仅一次**
- 关联规划力 → **只加一次**
- `unknown` / `NaN` / `Inf` / `100` / 反符号金额 → **被拒**
- 取消 → **不改点数**

---

### P1-5 · 成就墙触发自然追溯，并删除重复的追授路由

| 项 | 内容 |
|---|---|
| **位置** | `app/routers/achievements.py:24`、`app/routers/judgments.py:188` |
| **现象** | ① 成就墙 GET **只展示不检查** → 旧达成项**不自然点亮**（真实库：日记来源事件 23 条、成就表 0 条）。② 同一个 `POST /judgments/{id}/achievement` **注册在两个文件里**，响应和重复处理行为不同 → **路由顺序决定实际执行谁** |
| **红线** | 违反「成就自然追溯」；重复注册是隐患 |
| **根因** | 缺触发点；两处开发各写了一份 |

**修复方案**（依据**口径 3**）：

1. **保留 `judgments.py` 的 canonical 追授处理器**（它已有完整逻辑）。
2. **`achievements.py` 完整收敛为**：
   ```python
   @router.get("/achievements")
   def list_achievements(db: Session = Depends(get_db)):
       user = get_or_create_default_user(db)
       try:
           achievement_service.check_and_grant(db, user)
       except IntegrityError:
           # 并发请求可能已先解锁；唯一约束保证不会重复发币
           db.rollback()
       return achievement_service.wall(db, user)
   ```
   **删除该文件里的重复 POST 路由。**
3. **App.vue 不改**（依据口径 3：只在打开成就墙时触发，不在首屏触发）。

**影响范围**：`routers/achievements.py`（主体）、`routers/judgments.py`（确认为 canonical）
**是否改动数据模型**：否
**是否改动对外接口**：路径不变，**去除重复注册**；GET 增加既定惰性授予副作用
**预估改动量**：中（约 20–50 行有效变更）

**验证方式（内存库副本：23 篇日记 + 无成就）**：
- 首次 `GET /achievements` → **解锁 7 篇档**；**再次不重发**
- 余额增加额 **等于**新增成就流水之和
- 追授 POST **只注册一次**（用 `/openapi.json` 或路由表核对）；**忽略不发币**

---

### P1-6 · 今日盘点重试 AI 失败时复用已经保存的事件

| 项 | 内容 |
|---|---|
| **位置** | `frontend/src/components/TodayCheckin.vue:130` |
| **现象** | `createEvent` 成功、`judgeEvent` 失败后保留草稿；**再次提交又 createEvent** → 造重复生活记录 |
| **影响** | 影响计数、频率和未来判定上下文；**用户越重试，日记越重复** |
| **根因** | 失败分支没有保存已创建的 `eventId` |

**修复方案**：

1. `submitOne(it)` 完整重写：
   - 入口防重：`if (previous.busy) return false`
   - **复用已存事件**：`let eventId = previous.savedText === text ? previous.eventId : null`；为空才 `createEvent`，成功后 `setRow(it.id, { eventId, savedText: text })`
   - 判定成功 → 清 `eventId` / `savedText`，清草稿，`load()` 刷新
   - 判定失败 → **保留 `eventId` 与 `savedText`**，提示"记录可能已保存，可重试判定"
2. **`EventForm.vue` 同样需要**：保存 `create` 成功的 `eventId`，且**不能在判定成功前直接清除草稿**，**不能把 create 成功当成整条处理完成**。

**影响范围**：`TodayCheckin.vue`；若一并处理自由记录则扩展 `EventForm.vue` 两条提交函数（2 文件）
**是否改动数据模型**：否 ｜ **是否改动对外接口**：否 ｜ **预估改动量**：中（今日盘点约 40–60 行；加自由记录则大）

**验证方式**：
- `create` 成功、让 `judge` 失败 → 重试时 **`create` 调用次数仍为 1**
- 双击 → **仅一条**记录
- 成功后行统计更新
- 用户**改文字** → 创建新事件，**旧记录仍可见**

**注**：跨刷新的"待判记录入口"属于功能构想（Codex 第 5 节），**不在本轮**。

---

### P1-8 · 备份应覆盖实际数据库路径，迁移前留副本，并保护失败清理

| 项 | 内容 |
|---|---|
| **位置** | `app/services/backup_service.py:17`、`app/main.py:66` |
| **现象** | ① 备份用 `settings.db_file` 而非**实际 engine URL** → 配上 `database_url` 后**可能备错库**。② `BACKUP_DIR.mkdir()` **在 try 之外** → 失败会**影响启动**。③ 秒级文件名 → **同秒覆盖**。④ **启动备份发生在迁移之后** → **没有"迁移前"的原始副本**（迁移出错无法回到原状） |
| **红线** | 违反「真实数据保护」 |
| **根因** | 路径来源不对；顺序不对；文件名精度不够 |

**修复方案**：

1. **`backup_now()` 完整重写**：
   - 用 `engine.url.database` 取真实路径；非 sqlite 或 `:memory:` → 返回 `None`
   - `BACKUP_DIR.mkdir(parents=True, exist_ok=True)` **移进 try**
   - 文件名加**微秒 + 随机后缀**：`f"game_of_life_{stamp}_{uuid4().hex[:8]}.db"`（`stamp` 用 `%Y%m%d_%H%M%S_%f`）
   - 用 `closing(sqlite3.connect(...))` + `src.backup(dst)`（**在线备份 API，不是文件拷贝**）
   - 异常时**清理残留目标文件**并返回 `None`
   - `_cleanup()` 单独 try（`OSError` 不影响返回）
2. **`main.py` 把启动备份移到 `create_all` / `migrate_schema` 之前** —— 新库不存在时无旧数据可备份；已有库备的是**迁移前副本**。

**影响范围**：`backup_service.py`、`main.py`（2 文件）
**是否改动数据模型**：否 ｜ **是否改动对外接口**：否 ｜ **预估改动量**：中（约 35–55 行）

**验证方式**：
- `db_url` 指向另一个 SQLite 文件 → **备份的是该文件**
- **同秒两次备份 → 得到不同文件**
- `mkdir` / 连接 / 清理失败 → **不泄漏异常**，启动正常
- 旧 schema 升级前副本**保留旧列结构且完整可读**

**注**：每日调度、失败通知属于 **M4（上云）**，**不在本轮**。

---

### P1-9 · JSON 导出补齐基线、审计和 v1.10 经济数据，继续排除 Key

| 项 | 内容 |
|---|---|
| **位置** | `app/routers/export.py:40`、`frontend/src/components/SettingsView.vue:384` |
| **现象** | 界面写"全部数据"，实现**只有旧六类**；`attributes` 没有 `id`，而 `attribute_history` 只给 `attribute_id` → **导出无法关联历史、无法重算基线和余额**；不含新功能资产（金币/挑战/成就/豁免券等） |
| **红线** | 违反「个人数据可带走」；**绝不能导出 BYOK** |
| **根因** | 导出实现没跟上表增长 |

**修复方案**：

1. 原 `_collect` 重命名 `_collect_legacy`（**保留旧字段兼容旧下载脚本**）。
2. 新增 `_encode_export(value)`（datetime/date → isoformat，**递归处理 dict/list**）与 `_export_row(row)`（按 `row.__table__.columns` 全列导出）。
3. 新增 `_collect(db, user_id)`：对 **17 张表**逐表导出。
   ```python
   table_models = (
       models.UserProfile, models.Attribute, models.AttributeHistory,
       models.CheckinItem, models.Event, models.AIJudgment,
       models.JudgmentLog, models.Goal, models.CoinLedger,
       models.Challenge, models.ShopItem, models.Redemption,
       models.Achievement, models.Exemption,
   )
   ```
   加 `users`（单行）、`anchors`（全局）、`settings`（**只导出安全 key**：`gamification_modules` / `hidden_attributes` / `disabled_attributes` / `stagnation_checks` / `unreal_count`）。
4. 返回体加 `format_version = 2` 和 `tables`；**旧字段保留**。
5. **⚠️ 两条硬约束**：
   - **完整表区保留逻辑删除记录** —— 业务列表的 `is_deleted` 过滤条件**不能误用到这一区**
   - **嵌套快照直接保留原结构**，**不要把 `initial_attributes_snapshot` 的 attributes 误转成平铺基线**（这是记忆里明确记录的坑）
   - **导出不得含任何 API Key**（与 P0-8 联动验收）

**影响范围**：`routers/export.py`、`SettingsView.vue`（导出说明文案）（2 文件）
**是否改动数据模型**：否
**是否改动对外接口**：是 —— JSON 增加 `format_version` 和 `tables`，**旧字段保留**
**预估改动量**：中（约 50–75 行）

**验证方式**：
- 用导出文件**重算 40 币余额**与**各维基线 + 流水**（应吻合）
- 通过 `id` **关联历史**（`attributes.id` ↔ `attribute_history.attribute_id`）
- **17 表区完整**
- 全文搜索测试 Key → **不存在**
- CSV 事件导出**仍可用**

---

## 六、验收总则

### 6.1 全程禁止事项

1. **不要清洗或"修正"当前数据库。** 审计已做恒等式和引用检查，**当前账目正常，没有证据需要回填**。
   - 历史启动资金 40 币**不能**因新规则 80–200 就被自动补齐。
2. **不要通过删库、重建表、删列解决迁移。** 保留 `create_all` + `migrate_schema` 补列路线；新增约束前先检查历史数据。
3. **不要把删除改成"删旧判定再建新判定"。** 破坏 id 和审计，正是 v1.5 禁止的方式。
4. **不要把 `COIN_TABLE` 重新升为定价权威，也不要加经济奖励上限。**
5. **不要用"全局商品 id 唯一流水"阻止重复兑换。** 同一现实奖励可购买多次；网络重试幂等需要**独立请求标识**，不能把合法第二次购买一起封死。
6. **不要把所有行为副作用绑成一个巨大事务。** 基础积分、基础币、押金与挑战终态**同事务**；**累计成就作为后续可重试检查**。
7. **不要重报已修的 bug 为 P0。** Codex 已点名 `calendar` 简写与五处 `parent` 过滤**代码已覆盖**；浏览器实测可验证渲染，**不能把已看到的修复忽略掉**。
8. **不要现在给四个旧游戏化开关扩建业务开关系统。** 其文案"开启后对应入口才出现"**缺少实现** → 建议**先将这组开关标注为"尚未接入已交付模块"并禁用操作**，避免用户误以为已生效；**删除还是接线由用户人工定夺**。
9. **不要直接拿旧 `sql/schema.sql` 初始化真实 SQLite。** 它是**过时的迁移参考**，当前事实以 ORM 和实际库为准。

### 6.2 每条完成的定义

一条算完成，必须同时满足：

- [ ] 代码改动已 commit（**中文 message `类型: 简述`，一个 commit 一个逻辑单元**）
- [ ] **只 commit 不 push**
- [ ] 在**内存库或副本**上跑过该条的"验证方式"全部用例
- [ ] **真实库冒烟**：启动后端不报错；打开前端关键页面不白屏
- [ ] 对该条的**验收证据**已记录（截图 / SQL 输出 / 对照表）
- [ ] **若该条修的是红线违反项**（P0-1 / P0-5 / P0-8），**必须在 `docs/learning/CODE_GUIDE.md` 第 11 章「Bug Ledger」建档**（现象 → 定位过程（含证据）→ 根因 → 修复实现 → 防复发），并**在索引表登记一行**

### 6.3 全局回归（全部改完后跑一次）

| 项 | 期望 |
|---|---|
| `sum(coin_ledger.delta)` vs `user_profiles.coins` | **恒等**（当前 40） |
| 各维 `current_value` vs `初始快照 + Σ delta` | **13/13 吻合** |
| 17 张表计数 | 除新增成就/流水外**不应意外变动** |
| `attribute_history` / `judgment_logs` | **只增不减** |
| `GET /settings` / JSON 导出 | **无 Key 明文** |
| 完整链路 | 录事件 → 判定 → 确认 → 属性变化 + 金币 +2 |
| 删除事件 | 属性回滚、审计保留、事件不再出现在任何业务查询 |
| 挑战链路 | 生成 → 接受（扣押金）→ 完成自述 → 结算（加点 + 退押金 + 发奖励） |

---

## 七、明确不在本轮的内容

### 7.1 功能构想（Codex 第 5 节，**非必须，不在本轮**）

| 构想 | 说明 | 工作量 |
|---|---|---|
| 待判记录入口 | 模型失败后记录已保存，用户在今日盘点看到"已保存、待判定"，按已有 event id 补判（不重新创建事件） | 中到大，80–150 行 |
| 只读账目体检 | 按嵌套快照 + 真实 delta + 金币流水给出**只读**检查结果；**只报差异，不自动修账** | 中，60–100 行 |
| 奖励兑现备注 | 兑换成功后可记一句实际奖励体验；**不兑换属性点、不引入徽章商品** | 小到中 |

> B1（饮食拍照识别）/ C1（日记追问联动）/ D3（AI 分析显化）**仍保持暂缓**。

### 7.2 M4 上云自用门槛（**上云前置清单，不混入本轮**）

> 以下是上云前必须补齐的缺口。**本轮不做，也不在本轮建议开展多用户认证。**

| 门槛 | 当前证据 | 上云自用前的处理 |
|---|---|---|
| 访问密码 | `app/main.py:47` 注册业务 API，**无访问校验** | 给静态页及全部业务/导出/备份接口加**单一访问密码**；**不开放注册** |
| 同源生产部署 | `main.py` **无前端静态挂载** | 构建 Vue 并由后端提供；**SPA 回退不得吞掉 `/api` 错误** |
| CORS | `main.py:40` 为 `["*"]` | 同源部署**移除不必要跨域**，或仅列明确域名；**CORS 不能替代访问密码** |
| Key 环境变量 | `settings.py:83` 仍允许写数据库 BYOK | 云端自用改**环境变量主导**；停用云端 Key 编辑；**单独安排旧 Key 迁出，不盲删用户 settings** |
| HTTPS | **项目没有生产 TLS 配置** | 在实际部署入口配置 HTTPS；密码、日记和 Key **不经明文 HTTP** |
| 每日备份与恢复 | `backup_service.py` 只有启动/手动备份 | **每日调度 + 失败通知 + 至少一次恢复验证**；备份**不能挂到公开静态目录** |
| 私密文件暴露 | 单库包含日记、画像、明文 BYOK | 发布目录**只提供构建资源**；`.env`、数据库、`backups/`、导出中间文件**不得通过静态路径访问** |

**记忆中的已知技术债（同样留给上云）**：① API Key 明文存 `settings` 表 ② `anchors.calibrated_value` 无 `user_id`（多用户会串号）③ CORS `allow_origins=["*"]`。

### 7.3 需要用户后续拍板的问题（Codex 第 7 节，**本轮已按推荐处理，此处留档**）

| # | 问题 | 本轮处理 |
|---|---|---|
| 1 | 已确认事件能否补充/反驳/编辑 | **已定：冻结**（口径 4），撤销走删除事件 |
| 2 | 满级主维是否还能下降 | **已定：能下降**（口径 1），撤销负向子维分流 |
| 3 | 挑战低置信度是否锁整笔结算 | **已定：锁整笔**（P0-2），保留 `accepted` / `pending`，不先发奖励 |
| 4 | 挑战如何补充自述 | **已定：挑战页原 id 重判**，普通判定中心对挑战判定只读（P0-4） |
| 5 | 购券能否追溯到购买之前 | **本轮不改**（保留现状：券不校验 `created_at ≤ occurred_at`），**留待后续** |
| 6 | `HH:MM` 结束时间如何解释 | **本轮不改**（现状：全天结束 23:59:00，相邻时段都含 12:00）→ **建议后续统一半开区间**，属产品口径 |
| 7 | 删除事件后金币是否撤销 | **已定：不撤销 + 审计声明**（口径 2） |
| 8 | 历史撤销遇到后续封顶/触底 | **按真实流水反向 + 再夹取**（P0-5），**不保证"从来没有该事件"的反事实值** |
| 9 | 成就追溯时机与连续日记口径 | **已定：打开成就墙触发**（口径 3）；**连续天数仍取最近连续段**（非历史最长段），留待后续 |
| 10 | 补课挑战是否也 AI 主导定价 | **本轮只修押金比例**（P1-3），定价**留待后续** |
| 11 | 两个项目管理入口与四个未接线开关 | **保留双入口**（不由执行者自删）；开关**标注未接入 + 禁用** |
| 12 | 经济无上限的存储边界 | **不另设经济上限**；超出 SQLite 可存储范围时**明确解析失败**，**不任意截断成某个奖励上限**（P0-6 的 `_finite_float` 已覆盖） |

---

## 八、给执行者的开场指令

```
请按 docs/DEV_PLAN_v1.11.md 实施，规则如下：

1. 一次性全改，但按第二章的 commit 顺序执行（批次 1 → 2 → 3），
   一个 commit 一个逻辑单元，中文 message「类型: 简述」。
2. 只 commit，不 push。
3. 严格遵守第〇章总原则，特别是第 1 条数据红线和第 5 条禁区清单。
4. 第一、二章有 4 个已拍板的产品口径（含推荐与理由），
   照做即可；若你认为技术上做不到，停下来报告，不要自行改口。
5. 每一条的「验证方式」必须在内存库或 backups/ 副本上跑，
   严禁用真实库造故障数据。
6. P0-5 要改 10 处消费点，第五章已列出函数与行号（已用 Grep 核实），
   逐个核验，不要抽样。
7. 修完 P0-1 / P0-5 / P0-8 后，按第 6.2 节在
   docs/learning/CODE_GUIDE.md 第 11 章 Bug Ledger 建档。
8. 全部完成后跑一次第 6.3 节全局回归，输出对照表。
```

---

> **文档状态**：已实施并验收（2026-10-08）；18/18 完成，详见 `docs/review/V1_11_DELIVERY_2026-10-08.md`。
> **上游**：`docs/review/CODEX_AUDIT_2026-10-08.md`（18 条全部纳入，无遗漏、无新增）
> **下游**：执行完成后回写 `docs/DECISIONS.md`「v1.11 已登记待办」状态
