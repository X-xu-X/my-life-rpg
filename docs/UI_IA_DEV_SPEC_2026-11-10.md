> **执行状态（2026-11-11 补记）：已执行完毕，本文档转为变更记录。**
>
> 批次 A/B/C 已全部落地：`c91e923`（导航）、`9b898ac`（今天页入口）、`a34a549`（今日安排）、`b61a441`（命名）、`305a043`（去重与返回）、`55cb175`（空状态）、`9c769cb`（偏好字段）、`00d07da`（行级提示）。
> **批次 D（新用户首用态）未执行**，仍待产品确认。
> 遗留缺陷的修补见 `docs/UI_IA_FOLLOWUP_SPEC_2026-11-10.md` 与 `docs/UI_IA_FOLLOWUP2_SPEC_2026-11-11.md`。
> 阅读时请注意：本文档中的行号基于落地前基线，与当前代码已有偏移。

# 开发规格 · 信息架构收敛与提示可关闭（UI-IA v1）

> **决策来源**：`docs/review/UX_AUDIT_2026-11-10.md`（新用户视角 UX 审查）+ 2026-11-10 用户就 Demo 的逐条拍板（导航删手账、今日安排收敛、提示可关闭）
> **设计参照**：`docs/prototypes/life-journal-v3-2026-11-10/`（v7→v9 已定稿的手机/桌面 Demo，**只作视觉与交互参照，不作代码来源**）
> **代码基线**：`frontend/src` + `app/`（本文档所有行号与文案均为 2026-11-10 实读结果）
> **本文档性质**：可直接派发给 Writer 执行。**不含探索性任务**；凡标"执行前先 grep 确认"的，是文案可能随代码演进而移动，不是不确定要不要做。
> **交付方式**：按批次 A→B→C 顺序实施，一个 commit 一个逻辑单元，只 commit 不 push。批次 D 默认不执行，需用户点头。

---

## 〇、三十秒速览

| 批次 | 项 | 一句话 | 是否动后端 | 涉及文件 |
|---|---|---|---|---|
| **A** | F1 | 手账移出主导航，`/journal` 归「今天」分区并自动获得返回 | 否 | `App.vue`、`router.js`、`daily-use.css` |
| **A** | F2 | 今天页「最近记下的」右侧入口文案统一为「搜索 ›」 | 否 | `PageHub.vue` |
| **B** | F3 | 「今天的安排」卡：去角标、右侧「全部 N 条 ›」、只列未记录最多 2 条、补完成态 | 否 | `PageHub.vue` |
| **B** | F4 | 命名统一（手账/日记/奖励/成就/成长报告/金币收支/属性变化历史/挑战） | 否 | 5 个组件 + 1 处文案表 |
| **B** | F5 | 删重复入口（我的页头像卡账号、3 处组件内自建返回） | 否 | `PageHub.vue`、`PendingView.vue`、`ReportHistory.vue`、`ReviewView.vue` |
| **B** | F6 | 空状态三件套（公告页、待处理页补动作） | 否 | `AnnouncementsView.vue`、`PendingView.vue` |
| **C** | F7 | 教学型说明句可逐条永久关闭（跨设备） | **是** | `models/daily_use.py`、`routers/daily_use.py`、新增 `useTipPrefs.js`、`TipLine.vue`、`tips.css`、6 处接入 |
| **D** | F8 | 无记录的新用户首用态（默认不做，待确认） | 否 | `PageHub.vue` |

**规模预估**：A 约 60 行改动；B 约 120 行；C 约 260 行（后端 60 / 前端 200）；D 约 50 行。

---

## 一、总原则与禁区

### 1.1 五条铁律

1. **只改本规格点名的地方**（用户 2026-11-10 明确定下的规矩）。发现范围外的问题，写进 `docs/DECISIONS.md` 的 backlog，**不许顺手修**。
2. **数据红线**：不得物理删除任何用户数据；改表只走 `migrate_schema`（`app/database.py:39`）或 `create_all`；本地 SQLite 手动冒烟前先备份到 `backups/`。
3. **不动业务逻辑**：金币、属性、判定、挑战、兑换、问卷相关代码一行不改。本规格只碰壳层（导航/页面结构/文案/空状态）与一个偏好字段。
4. **一个 commit = 一个逻辑单元**，中文 message `类型(域): 简述`（例：`feat(nav): 手账移出主导航并补返回`）。**只 commit，不 push；禁止 `git add .`**，逐个 `git add <路径>`。
5. **改完必须自证**：每个 commit 附「改前/改后」证据（页面截图或断言输出），不写"应该没问题"。

### 1.2 明确不做（禁区清单）

- ❌ 不动三个**无引用死代码组件**：`HomeView.vue`、`PlansView.vue`、`RewardsView.vue`。已核实全仓无 import（`grep -rn "HomeView\|PlansView\|RewardsView" frontend/src` 仅命中自身）。**不得以它们的文案为基准**，也不要顺手删它们。
- ❌ 不做 `guide` / `演示工具` 收编 —— 那是 Demo 独有概念，真站没有 `/guide` 路由。
- ❌ 不新增依赖、不引入 UI 组件库、不换图标体系。
- ❌ 不改 13 维属性的名称/数量、不改金币文案中的数值、不改任何 `api.js` 方法签名。
- ❌ 不重构 `PageHub.vue` 的分区加载逻辑（`requests` / `loaders` 表），只在 today 分区新增两个 computed。
- ❌ 不统一全站入口组件（审查 P1-11）。本轮只规定"新增入口必须用 `hub-row` 或卡片标题右侧链接"，存量不动。

### 1.3 真站已满足，切勿重复改（关键，避免做无用功）

审查报告是针对 **Demo** 写的，其中 4 条在**真站已天然正确**。执行前请对照下表，**这些不是待办**：

| 审查项 | 真站现状（证据） | 结论 |
|---|---|---|
| P0-1 返回按来源 | `App.vue:17` 用 `returnTarget(router,route)`；`navigation.js:11-22` 在 `router.afterEach` 里按来源记 `sessionStorage` | **已满足**。F1 只是让 `/journal` 也进入这套机制 |
| P0-4 挑战页归属 | `router.js:45` `/challenges` → `meta.section:'plans'`；`ChallengeView.vue:517` 自己的 h1，无成长 tab | **已满足**，仅需统一文案（F4） |
| P0-5 首屏零引导 | `PageHub.vue:52` 写卡已有「今天发生了什么？／一件小事，或一篇晚间日记。」 | **已满足** |
| P0-6 无首用态 | `App.vue:37` 未建档强制 `/onboarding`；`PageHub.vue:90` 有「选择游戏起点」卡 | **基本满足**，F8 是可选增强 |

> **推论**：本规格的 P0 只有两条 —— F1（手账层级）与 F3（今日安排占位）。其余是 P1 收敛。

---

## 二、功能范围

### 2.1 需求映射（用户原话 → 需求编号）

| 用户原话 | 需求 | 本规格条目 |
|---|---|---|
| 「手账那就只是搜索的，会不会单独一个导航栏太浪费」 | 手账移出主导航 | F1 |
| 「写日记那里手账也能进去」「今日那记录事件的地方，可以进到手账」 | 手账保留唯一入口：今天页「最近记下的」 | F1 + F2 |
| 「电脑端也要同步修正一下」 | 两端同源（真站 `personalTabs` 一个数组喂两端，天然一致） | F1 |
| 「今日安排这里，右边直接变成跳转到全部四条的东西吧，管理项目这个，直接我自己点计划去那边改」 | 去角标 + 右侧「全部 N 条 ›」+ 去管理入口 | F3 |
| 「高数这个例子，要么显示主线的几个安排，要么不显示吧」 | 已记录的安排不在首页占位 | F3 |
| 「其他这种要填的地方，没必要的也都去除」 | 输入框示例文案清理（**真站已于 2026-10-21 轮完成，本轮不重做**） | 见 1.3 |
| 「有没有哪种提示语是新用户看一遍就可以不再提示的」 | 教学句可关闭 | F7 |
| 「以新用户视角审查…必须修/建议修」 | 命名统一、去重、空状态 | F4 / F5 / F6 |

### 2.2 逐项说明

#### F1 · 手账移出主导航，`/journal` 归「今天」分区

**现状（证据）**
- `App.vue:16` `personalTabs` 6 项：今天 / 手账 / 计划 / 成长 / 奖励 / 我的。
- `router.js:18` `/journal` → `meta:{section:'journal'}`。
- `App.vue:57` 全局返回按钮条件 `v-if="route.path!==sectionRoot(route)||route.query.date"`；`sectionRoot` 对手账返回 `/journal`（`navigation.js:5`）→ **手账页当前永远没有返回按钮**。
- `daily-use.css:3` `.mobile-nav{grid-template-columns:repeat(6,minmax(0,1fr))}`（覆盖了 `ui-layout.css:53` 的 5 列）→ **删项后必须同步改列数**，否则 5 个 tab 挤在 6 列里，右侧留空一格。

**改成**
1. `App.vue:16`：删掉 `{ key:'journal', path:'/journal', label:'手账' }`，得到 5 项，顺序 今天 / 计划 / 成长 / 奖励 / 我的（两端共用此数组，顺序自动一致）。
2. `router.js:18`：`/journal` 的 meta 改为 `{ section:'today', title:'手账' }`。
   - `section:'today'` → 进手账时侧栏/底栏高亮「今天」，且 `sectionRoot` 变为 `/`，`App.vue:57` 自动显示返回按钮。
   - `title:'手账'` → 返回按钮文案读 `meta.title`（`App.vue:18`），从手账进事件详情时显示「← 返回手账」而不是「← 返回今天」。
3. `router.js:20`：`/events/:id` 的 meta 改为 `{ section:'today' }`（同理：记录详情归「今天」高亮；返回目标由 `returnTarget` 按来源决定，不受影响）。
4. `daily-use.css:3`：`.mobile-nav{grid-template-columns:repeat(5,minmax(0,1fr))}`。
5. `navigation.js:2`：`roots` 里的 `journal:'/journal'` 保留（`valid()` 仍需要它能 resolve），**不删**。

**边界**
- `/me/account` → `/security` 的 redirect（`router.js:71`）不动。
- 事件详情被删除后回退逻辑不动。
- 手账的搜索、筛选、分页行为一行不改。

**为什么不用"加 `meta.parent` 机制"**：`section` 归并是既有机制的复用，只有 2 行改动；新增 `parent` 字段要在 `sectionRoot` / `backLabel` / `selected` 三处加分支，收益相同而回归面更大。

#### F2 · 手账入口文案统一为「搜索 ›」

**现状**：`PageHub.vue:61` 卡片标题「最近记下的」，右侧 `<RouterLink to="/journal">手账 ›</RouterLink>`。

**改成**：链接文案 `搜索 ›`（目标不变）。理由：手账在导航里消失后，入口名要说明"点进去能干什么"；卡片本身已在展示最近记录，"手账"这个词不提供新信息。

**边界**：`/journal` 页自己的标题仍是「手账」（`RecordList.vue:29`），副标题「原文一直在这里。是否分析，都可以回看。」保留不动。

#### F3 · 「今天的安排」卡收敛

**现状（`PageHub.vue:54-55`）**
```html
<h2>今天的安排 <span class="hub-count">{{ todayProjects.filter(p=>p.category==='plan').length }}</span></h2>
<RouterLink to="/plans/today">查看全部 ›</RouterLink>
...
<RouterLink v-for="p in todayProjects.filter(p=>p.category==='plan').slice(0,3)" ...>
  <small>{{ planned_minutes }} 分钟 · {{ completion(p) }}</small>
```
问题：① 数字角标与「查看全部」重复表达同一件事；② 已记录（`entry` 非空）的安排仍占首页位置，且只显示状态文字，信息量低；③ `completion()` 在无 entry 时返回「待记录」，与"还没记"重复。

**改成**
```js
const planToday = computed(()=>todayProjects.value.filter(p=>p.category==='plan'))
const pendingToday = computed(()=>planToday.value.filter(p=>!p.entry).slice(0,2))
```
```html
<h2>今天的安排</h2>
<RouterLink to="/plans/today">全部 {{ planToday.length }} 条 ›</RouterLink>
<RouterLink v-for="p in pendingToday" ...>   <!-- 行内不再显示 completion() -->
<p v-else-if="planToday.length" class="hub-empty">今天的安排都记下了，剩下的时间交给休息。</p>
<p v-else class="hub-empty">今天没有排期，按自己的节奏来。</p>
```

**判定口径**
- **「未记录」= `!p.entry`**。`/projects` 接口对当天无 `Entry` 记录的项目返回 `entry:null`（`app/routers/projects.py:78`），有则返回快照对象。**不要**用 `completion(p)==='待记录'` 判断 —— 该函数还覆盖 `skipped/missed` 等已记录状态，用它会把"今天跳过了"重新塞回首页。
- **最多 2 条**，顺序沿用接口既有排序（`projects.py:80` 按 `position` 排序），**不新增"主线优先级"字段**。真站没有 project 级 mainline 标记（`mainlines` 表是 goal 维度，见 `app/models/policies.py:22`），Demo 里那个「主线」徽章是演示数据，不得在真站伪造。
- 角标 `.hub-count` 删除；「查看全部」改为「全部 N 条」，N = 今日计划总数（含已记录），让人知道总量。

**边界**：照顾自己（`category==='care'`）那段 `<details>` 不动；点击行仍跳 `/plans/item?key=`。

#### F4 · 命名统一

按附表 A 逐条替换。原则：**导航项、页面 h1、入口链接三者用同一个功能名**；文艺句只允许出现在 `PageHeader` 的 `description`（副标题）里。

#### F5 · 删重复入口

| 位置 | 重复内容 | 处理 |
|---|---|---|
| `PageHub.vue:90` 我的页头像卡 | `账号 ›` → `/me/account` → redirect `/security`，与 `:92` 列表「账号安全 ›」同页同目标 | 删头像卡里的 `账号 ›` 链接，头像卡只留用户名与一句话 |
| `PendingView.vue:18` | 自建 `<RouterLink to="/">← 今天</RouterLink>`，与 `App.vue:57` 全局返回重复 | 删自建返回 |
| `ReportHistory.vue:16` | 自建 `<RouterLink to="/growth">← 成长</RouterLink>`，同上 | 删自建返回 |
| `ReviewView.vue:29` | 自建 `<RouterLink to="/">← 今天</RouterLink>`，同上 | 删自建返回 |

> 删自建返回后，返回目标由 `returnTarget` 决定（从成长进报告就回成长，从今天进待处理就回今天），比写死更准。这三个页面都在 `meta.section` 对应的 root 之外，`App.vue:57` 条件成立，返回按钮一定显示，**不会出现"没有返回"**。执行时逐页确认按钮存在再删。

#### F6 · 空状态三件套

统一格式：**这里会有什么 + 怎么让它有内容 + 一个动作**。

| 页面 | 现状 | 改成 |
|---|---|---|
| `AnnouncementsView.vue` | `暂无已发布公告。` | 「站点公告会在这里出现，由管理员发布。」+ 无动作（用户无权限创建，不许造假按钮） |
| `PendingView.vue` | 「暂时没有待处理的记录。安心过今天。」 | 保留原句，追加动作 `<RouterLink to="/capture">去记一件事 ›</RouterLink>` |
| `RecordList.vue` | 已有完整空态（含"清除搜索与筛选"） | **不动**（正面样板） |

#### F7 · 教学型说明句逐条可关闭

**目标**：读一遍就够的说明句，行尾给一个淡「×」，点击后**跨设备永久消失**；恢复入口复用现有「我的 → 显示与提示 → 恢复一般提示」。

**分工**（重要，避免两套机制打架）

| 场景 | 用哪个 | 原因 |
|---|---|---|
| 整块提示，带「知道了 / 不再提示」动作，内容会随状态变 | 现有 `HintCard.vue`（块级，`suppressed` 6 个 id） | 已有机制，语义是"这次别烦我" |
| 页面里一句固定说明，读完就够 | 新增 `TipLine.vue`（行级，`suppressed_lines`） | 不该为一句小字弹整块卡 |

同一句文案**不得**同时出现在 `HintCard` 与 `TipLine` 里。

**落地清单（6 条，执行前用原文 grep 确认唯一命中）**

| # | id | 文件 | 现有原文 |
|---|---|---|---|
| 1 | `today.write-hint` | `PageHub.vue` today 写卡 | `一件小事，或一篇晚间日记。` |
| 2 | `journal.pure-flag` | `RecordList.vue:31` | `历史纯享标记与当前是否分析是两种设置。` |
| 3 | `growth.ability-note` | `PageHub.vue` growth 能力数值 details | `展开查看游戏数值，也可以继续追溯变化。` |
| 4 | `growth.baseline` | `PageHub.vue` me 页未建档卡 | `可以继续问卷，也可以先用未评估基线开始。` |
| 5 | `diary.same-day` | `DiaryView.vue` | `同一日期保存为同一原稿的新版，不新增第二篇。辅助回答独立保留。` |
| 6 | `calendar.dot` | `SectionDetail.vue` calendar 视图 | `有圆点的日期留下过记录；点日期查看当天手账。` |

**明确不做成可关闭的**（属边界承诺或状态信息，删了会误解）：
- `DiaryView` 的「主动生成会发送原文、来源快照和问答至所选模型，可能计费。」——费用告知。
- `PendingView` 的「延后处理不会自动确认或扣分。」——结算承诺。
- 各页 `PageHeader` 副标题（品牌句）。
- 含实时数值的行（余额、分钟数、天数）。

#### F8 · 首用态（默认不执行）

若用户点头再做：`records.length===0 && !loading` 时，today 分区隐藏「今天的安排」与「最近记下的」两卡，替换为一块 `hub-card`：「从这里开始」+「记下第一件事，属性与金币会在你确认后出现。」+ 按钮「＋ 记一件事」（`/capture`）。有 1 条记录后恢复原样。**在此之前不要改。**

---

## 三、模块划分

```
┌─────────────────────────────────────────────────────────────┐
│ 壳层 shell        App.vue                                   │
│                   · personalTabs（导航唯一来源，两端共用）      │
│                   · 全局返回按钮（returnTarget + meta.title）  │
│                   router.js（路由与 meta：section / title）    │
│                   navigation.js（来源记忆，不改逻辑）           │
│                   daily-use.css / ui-layout.css（底栏栅格）    │
├─────────────────────────────────────────────────────────────┤
│ 页面层 pages      PageHub.vue       今天/计划/成长/奖励/我的    │
│                   SectionDetail.vue 各二级页（按 meta.detail）  │
│                   独立页：RecordList / DiaryView / PendingView │
│                          ReportHistory / ReviewView / ...     │
├─────────────────────────────────────────────────────────────┤
│ 提示层 hints      HintCard.vue   块级提示（已有）              │
│                   TipLine.vue    行级说明（新增）              │
│                   tips.css       行级样式（新增）              │
├─────────────────────────────────────────────────────────────┤
│ 偏好层 prefs      composables/useTipPrefs.js  单例缓存 + 读写  │
│                   PreferencesView.vue         开关与恢复入口   │
│                   ── HTTP ──▶ /api/experience-preferences      │
│ 后端              models/daily_use.py::ExperiencePreference   │
│                   routers/daily_use.py::preferences/save_      │
└─────────────────────────────────────────────────────────────┘
```

**依赖方向**：页面层 → 提示层 → 偏好层 → HTTP。禁止 `useTipPrefs` 直接操作 `localStorage` 当权威（只允许像 `HintCard` 那样用 `sessionStorage` 做"本次会话已看过"的辅助标记，且不得用它代替服务端状态）。

---

## 四、接口与数据结构设计

### 4.1 复用而不改的接口

| 接口 | 用途 | 本规格是否改 |
|---|---|---|
| `GET /api/projects?day=` | 今日安排数据（含 `entry`、`position`、`show_today`） | 否 |
| `GET /api/records?date=` | 今天页「最近记下的」 | 否 |
| `GET /api/me` | 账号与 `onboarding_completed` | 否 |
| `GET /api/experience-preferences` | 提示偏好 | **是，加一个字段** |
| `PUT /api/experience-preferences` | 保存提示偏好 | **是，加一个可选字段** |

### 4.2 变更：`experience-preferences`

**A. 数据模型**（`app/models/daily_use.py:19-26`）

```python
class ExperiencePreference(Base):
    __tablename__ = 'experience_preferences'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    suppressed:Mapped[list]=mapped_column(JSON,default=list)
    suppressed_lines:Mapped[list|None]=mapped_column(JSON,default=list,nullable=True)  # 新增
    return_disabled:Mapped[bool]=mapped_column(Boolean,default=False)
    review_snoozed_until:Mapped[datetime|None]=mapped_column(UTCDateTime,nullable=True)
```

- 类型 `JSON`，SQLite / PostgreSQL 均可 `compile`（`migrate_schema` 依赖 `column.type.compile(dialect)`）。
- **必须 `nullable=True`**：`migrate_schema` 加列时只加可空列、只回填标量默认值（`str/int/float/bool`，见 `database.py:68-76`），**JSON 列的 `default=list` 不会被回填**，老行会留 `NULL`。因此**所有读取点必须写 `row.suppressed_lines or []`**。
- 不新建表、不删列、不改 `suppressed` 语义。

**B. 请求/响应**

`GET /api/experience-preferences` →（无记录时返回默认对象，保持现有写法）
```json
{
  "version": 3,
  "suppressed": ["plans-help"],
  "suppressed_lines": ["journal.pure-flag", "growth.ability-note"],
  "return_disabled": false,
  "review_snoozed_until": null
}
```

`PUT /api/experience-preferences`
```json
{
  "request_key": "b3f1c1a2-...-uuid4",
  "expected_version": 3,
  "suppressed": ["plans-help"],
  "suppressed_lines": ["journal.pure-flag"],
  "return_disabled": false
}
```

**C. 校验规则**（`PreferenceIn`）

> `app/routers/daily_use.py` 现有导入为 `from typing import Literal` 与 `from pydantic import BaseModel,Field,model_validator`，需补 `Annotated`（`typing`）与 `StringConstraints`（`pydantic`），否则 `NameError`。

```python
LineId = Annotated[str, StringConstraints(pattern=r'^[a-z][a-z0-9-]*(\.[a-z0-9-]+){1,2}$', max_length=48)]

class PreferenceIn(WriteIn):
    suppressed:list[Hint]=Field(default_factory=list,max_length=6)
    suppressed_lines:list[LineId]=Field(default_factory=list,max_length=40)   # 新增
    return_disabled:bool=False
```

- 上限 40 条（现清单 6 条，留足余量；超限 422，不做静默截断）。
- 去重：写入时 `list(dict.fromkeys(...))`，与 `suppressed` 现有写法一致。
- **不要把行级 id 塞进 `suppressed`**：它是 `Literal` 白名单 + `max_length=6`，塞进去直接 422。

**D. 向后兼容（必做，否则会误清数据）**

`WriteIn` 继承自 `MutationIn`，且 `model_config = ConfigDict(extra='forbid')`。旧客户端（或未来忘记带字段的调用）只发 `suppressed` 时，`suppressed_lines` 会取默认 `[]` → **一把清空用户已关闭的 6 条**。因此：

```python
touched = 'suppressed_lines' in body.model_fields_set
...
row.suppressed_lines = list(dict.fromkeys(body.suppressed_lines)) if touched else (row.suppressed_lines or [])
```

- 显式传 `[]` = 清空（用户在偏好页点「恢复一般提示」走的就是这条）。
- 完全不传 = 保持原值。
- `suppressed` / `return_disabled` 维持现有"全量替换"语义不变（前端保存时必须回传现值，见 4.4）。

**E. 迁移与回滚**

- 加列：启动时 `migrate_schema` 自动执行，幂等，无需手写 SQL。执行后日志应出现 `[migrate] 已添加缺失列 experience_preferences.suppressed_lines (JSON)`。
- 本地 SQLite：`my-life-rpg/game_of_life.db` 在启动时自动加列；**先备份**再启动。
- 云端 PG：沿用现有 `ops/manage.py` 升级流程，不新增迁移目录。
- 回滚：代码回退后该列被忽略，不报错；数据保留，不清洗。

### 4.3 前端状态与组件契约

**`frontend/src/composables/useTipPrefs.js`**（单例，模块级缓存，全站一次 GET）

```js
import { ref } from 'vue'
import { api } from '../api'
const prefs = ref(null)        // { version, suppressed, suppressed_lines, return_disabled }
const loading = ref(false)
const error = ref('')
let inflight = null

async function ensure() {       // 幂等；多组件并发只发一次请求
  if (prefs.value) return prefs.value
  if (inflight) return inflight
  loading.value = true
  inflight = api.flow('/experience-preferences')
    .then(v => { prefs.value = { ...v, suppressed_lines: v.suppressed_lines || [] }; return prefs.value })
    .catch(e => { error.value = e.message; prefs.value = { version: 0, suppressed: [], suppressed_lines: [], return_disabled: false }; return prefs.value })
    .finally(() => { loading.value = false; inflight = null })
  return inflight
}
function hidden(id) { return (prefs.value?.suppressed_lines || []).includes(id) }
async function hide(id) {       // 成功返回 true；失败不改本地状态
  const p = await ensure()
  const next = [...new Set([...(p.suppressed_lines || []), id])]
  try {
    const saved = await api.flow('/experience-preferences', {
      expected_version: p.version, suppressed: p.suppressed || [],
      suppressed_lines: next, return_disabled: !!p.return_disabled
    }, 'PUT')
    prefs.value = { ...saved, suppressed_lines: saved.suppressed_lines || [] }
    return true
  } catch (e) { error.value = e.message; return false }
}
export function useTipPrefs() { return { prefs, loading, error, ensure, hidden, hide } }
```

**约定**
- `ensure()` 在 `App.vue` 登录完成处调用一次即可（也可由首个 `TipLine` 触发），**不要每个组件各自 GET**。
- 失败时**显示说明**而不是隐藏：宁可多显示一行字，也不能让内容凭空消失。
- `hide()` 失败：保持可见 + 在按钮 `title` 上显示"这次没保存成功，再试一次"。**不允许"看起来关掉了其实没落库"**。
- 不写 `localStorage` 当权威；若要做"本次会话不重复请求"，用模块级变量，不用持久化。

**`frontend/src/components/ui/TipLine.vue`**

```vue
<script setup>
import { computed, onMounted } from 'vue'
import { useTipPrefs } from '../../composables/useTipPrefs'
const props = defineProps({ id: { type: String, required: true } })
const tips = useTipPrefs()
const shown = computed(() => !tips.hidden(props.id))
onMounted(tips.ensure)
async function dismiss() { await tips.hide(props.id) }
</script>
<template>
  <p v-if="shown" class="tip-line">
    <span class="tip-line-text"><slot/></span>
    <button type="button" class="tip-line-close" aria-label="不再显示这行说明" title="不再显示这行说明" @click="dismiss">×</button>
  </p>
</template>
```

- 样式放 `frontend/src/components/tips.css`（或 `src/tips.css`，与现有 css 同级），在 `main.js` 里 `import` 于 `navigation.css` 之后。
- `.tip-line{display:flex;gap:8px;align-items:baseline}`；`.tip-line-close{border:0;background:none;color:var(--text-sub);opacity:.55;font-size:15px;line-height:1;min-width:28px;min-height:28px;cursor:pointer}`；`hover/focus-visible` 时 `opacity:1`、`color:var(--primary)`。**不使用 emoji 作图标**。
- 触控目标 ≥ 28×28（现有 `.text-button` 是 36 高，行级 × 允许更小，但不能低于 28）。

**`PreferencesView.vue` 增量**
- 保留现有 6 个块级开关与「恢复一般提示」。
- 新增一行只读统计：`已关闭 {{ (prefs.suppressed_lines||[]).length }} 行说明`，放在「不再自动提示」卡片底部 `muted` 段落里。
- 「恢复一般提示」按钮已有 `prefs.suppressed=[]` 逻辑，**追加 `prefs.suppressed_lines=[]`**，一并提交。

### 4.4 id 命名规范

- 形如 `<页面>.<短横线语义>`，小写，2 段（允许 3 段）：`journal.pure-flag`、`growth.ability-note`。正则见 4.2C。
- id 一旦发布**不得改名**（改名等于让用户已关闭的提示复活）。
- 新增 id 必须同时登记到本文档附录 B 与 `docs/DECISIONS.md`。

### 4.5 明确不新增的接口

- ❌ 不新增 `POST /api/hints/{id}/dismiss` 之类专用接口。现有 `PUT /experience-preferences` 已带 `request_key` 幂等 + `expected_version` 乐观锁 + 收据（`app/services/workflow_common.py`），新增接口会绕过 receipts 与版本控制。
- ❌ 不为手账新增后端接口（搜索走现有 `GET /api/records?q=`）。

---

## 五、技术约束

**前端**
1. Vue3 `<script setup>` + 组合式 API，与现有风格一致（不引入 Pinia；跨组件状态用模块级 `ref` 单例，与 `session.js` 同款）。
2. 路由 meta 只允许新增/修改 `section`、`title` 两个键；**不得**改 `router.js` 的守卫逻辑（`beforeEach` 里的 admin 重定向）。
3. 断点沿用 `1100px`（桌面栏）、`799px`（daily-use）、`640px`（navigation），**不新增断点**。
4. 颜色只用 `design-tokens.css` 的 CSS 变量（`var(--primary)`/`var(--text-sub)`/`var(--border)`/`var(--primary-soft)`），不写死色值。
5. 所有入口链接必须是 `<RouterLink>`（可键盘聚焦、可中键新开）；禁用 `@click` + `router.push` 实现导航。
6. 无障碍：`aria-current="page"` 由现有 `selected()` 逻辑给出，不改；`×` 按钮必须有 `aria-label`；不得只靠颜色区分状态。

**后端**
7. 只在 `app/models/daily_use.py` 与 `app/routers/daily_use.py` 内改动；不动 `services/`。
8. 写入必须走 `begin / version / finish` 三件套（`workflow_common.py`），**不得直接 `db.commit()`**。
9. 不得修改 `Hint` Literal 白名单（加 id 会让旧客户端 422）。
10. 新增字段必须有 pytest 覆盖（含"不带该字段不丢数据"这条）。

**工程**
11. `cd frontend && npm run build` 必须通过（Vite 零警告增量不算失败，但不得新增 `error`）。
12. `python -m pytest tests/test_daily_use_redesign.py -q` 必须仍全绿（现有断言 `suppressed` 往返，不得改断言迎合实现）。
13. 不得提交 `dist/`、`_shots*`、临时脚本；`.gitignore` 已覆盖的不再动。
14. 每个 commit 只带本项文件；跨项共用文件（如 `PageHub.vue`）在不同 commit 里分别 `git add` 同一文件是允许的，但要在 message 里写清本 commit 只改了哪几行。

---

## 六、开发步骤

> 顺序不可调换：A 改壳层，B 依赖 A 的入口位置，C 是独立子系统但依赖 B 的文案定稿（否则 tip 原文要改两遍）。

### 批次 A · 壳层（可单独上线，风险最低）

**commit 1 `feat(nav): 手账移出主导航，/journal 归今天分区并补返回`**
1. `App.vue:16` 删 journal 项。
2. `router.js:18` `/journal` → `{section:'today', title:'手账'}`。
3. `router.js:20` `/events/:id` → `{section:'today'}`。
4. `daily-use.css:3` `.mobile-nav` 6 列 → 5 列。
5. 自检：底栏/侧栏各 5 项且顺序为 今天·计划·成长·奖励·我的；`#/journal` 顶部出现「← 返回今天」；进手账后侧栏「今天」高亮；从手账点一条记录，详情页返回为「← 返回手账」。

**commit 2 `feat(today): 手账入口统一为搜索`**
1. `PageHub.vue:61` 链接文案 `手账 ›` → `搜索 ›`。

**批次 A 完成判据**：上述 5 条自检全绿 + `npm run build` 通过。

### 批次 B · 页面内收敛

**commit 3 `feat(today): 今日安排只显示未记录的两条`**（F3 全部内容，含 computed、角标移除、`全部 N 条`、完成态）

**commit 4 `refactor(copy): 统一二级页与入口命名`**（F4，按附表 A 一次性改完；一个 commit 便于整体回滚）

**commit 5 `refactor(nav): 删除重复入口与组件内自建返回`**（F5 四处）

**commit 6 `feat(empty): 空状态补说明与动作`**（F6 两处）

**批次 B 完成判据**：附表 A 每一行目标名在页面上可见且唯一；`grep -rn "账号 ›" frontend/src` 无命中；三个页面各只有一个返回按钮。

### 批次 C · 提示可关闭

**commit 7 `feat(prefs): 偏好表新增 suppressed_lines 字段与接口兼容`**
1. 模型加列（4.2A）。
2. `PreferenceIn` 加字段与校验（4.2C）。
3. `save_preferences` 加 `touched` 兼容逻辑（4.2D）；`GET` 响应补 `suppressed_lines`（缺省 `[]`）。
4. `tests/test_daily_use_redesign.py` 追加 3 条用例：
   - 带 `suppressed_lines` 保存后 GET 能读回；
   - **不带该字段 PUT 只改 `suppressed`，`suppressed_lines` 保持原值**（防回归的核心用例）；
   - 传 `[]` 能清空；非法 id（如 `Bad_ID`、超 40 条）返回 422。
5. 本地启动确认 `[migrate]` 日志出现新列。

**commit 8 `feat(hints): 行级说明句可逐条关闭`**
1. 新增 `composables/useTipPrefs.js`、`components/ui/TipLine.vue`、`tips.css`，`main.js` 引入 css。
2. 按附录 B 六条接入（用原文 grep 定位，逐一替换为 `<TipLine id="...">原文</TipLine>`，注意保留原有的 `class` 语义与 `<p>` 结构）。
3. `PreferencesView.vue` 加"已关闭 N 行说明"，并把 `suppressed_lines` 纳入「恢复一般提示」。
4. 自检：点 × → 刷新后仍不显示；换设备/换房间（新 session）仍不显示；偏好页计数 +1；点「恢复一般提示」全部回归。

**批次 C 完成判据**：pytest 全绿 + 6 条提示逐个可关可恢复 + 断网时提示仍显示且 × 不误报成功。

### 批次 D · 首用态（**默认不做**）

需用户明确点头后再做，`commit 9 feat(today): 无记录时的首用态`。

---

## 七、验收标准

### 7.1 功能验收（逐条打勾，每条附证据）

| 编号 | 验收项 | 判定方法 |
|---|---|---|
| A01 | 桌面侧栏 5 项，顺序 今天·计划·成长·奖励·我的 | 打开 `/` 截图，数项数与顺序 |
| A02 | 手机底栏 5 项，等分无空格 | 窗口宽 390px 截图，最后一项右边无空白格（关键：`repeat(5)` 生效） |
| A03 | `/journal` 顶部有「← 返回今天」 | 直接访问 `#/journal`，看按钮文案 |
| A04 | 手账处于导航高亮「今天」 | 进手账，看侧栏/底栏选中态 |
| A05 | 今天 → 手账 → 某条记录，详情返回为「← 返回手账」 | 三步点击，读按钮文案 |
| A06 | 今天页「最近记下的」右侧文案为「搜索 ›」，点击进手账 | 截图 + 点击 |
| A07 | 「今天的安排」无数字角标，右侧为「全部 N 条 ›」，N=今日计划总数 | 截图 + 与 `/projects` 返回条数比对 |
| A08 | 只显示 `entry` 为空的安排，最多 2 条 | 造 3 条计划、记录 1 条 → 首页应显示 2 条且不含已记录那条 |
| A09 | 今日计划全部记录后显示「今天的安排都记下了，剩下的时间交给休息。」 | 把全部计划都记录一次，刷新首页 |
| A10 | 无排期时显示「今天没有排期，按自己的节奏来。」 | 清空当天排期 |
| A11 | 附表 A 每条目标名在页面上可见，旧名在 `frontend/src` 中不再出现（除历史文案） | `grep -rn "<旧名>" frontend/src` 逐条核对 |
| A12 | 「我的」页只有一处账号安全入口 | 数链接 |
| A13 | 待处理/历史报告/睡前回顾各只有一个返回按钮 | 截图 |
| A14 | 公告页空态含"会有什么 + 谁发布"，无假按钮 | 截图 |
| A15 | 待处理空态含「去记一件事 ›」并跳 `/capture` | 点击 |
| A16 | 6 条提示句尾各有一个 ×，点击后消失 | 逐条点 |
| A17 | 关闭后刷新、重开浏览器仍不显示 | 关一条 → 刷新 → 复查 |
| A18 | 偏好页显示「已关闭 N 行说明」，N 与实际关闭数一致 | 关 2 条后看数字 |
| A19 | 「恢复一般提示」后 6 条全部回归，N 归 0 | 点击后刷新核对 |
| A20 | 断网/接口 500 时提示仍显示、点 × 不假装成功 | DevTools 断网后点 × |

### 7.2 回归验收（证明没改坏）

| 编号 | 验收项 | 判定方法 |
|---|---|---|
| R01 | `npm run build` 通过 | 构建日志 |
| R02 | `pytest tests/test_daily_use_redesign.py -q` 全绿 | 输出 |
| R03 | 金币/属性/判定/挑战/兑换任何数值未变 | 改动前后 `GET /api/coins`、`GET /api/attributes` 数值对照一致 |
| R04 | 我的页其余 9 条入口仍可点通 | 逐个点击无 404 |
| R05 | 管理端（`/admin/*`）导航未被影响 | 以 owner 账号登录，侧栏仍为 概览/账号/公告/站点/记录 |
| R06 | 手机端 5 个 tab 均可点、均有高亮 | 逐个点 |
| R07 | 未建档账号仍被强制进 `/onboarding` | 新账号登录 |

### 7.3 证据要求

- 每个 commit 附：改动文件清单（`git show --stat`）、关键页面截图（改前/改后各一张）、A 段自检项的打勾记录。
- C 批必须附 `[migrate]` 日志行 + pytest 用例名清单。
- **不接受**"已实现，请自查"式交付。

---

## 八、风险与回滚

| 风险 | 触发条件 | 预案 |
|---|---|---|
| 底栏 5 项挤成 6 列留空格 | 只改了 `App.vue` 未改 `daily-use.css:3` | A02 专门覆盖；改列数是 A 批必做项 |
| `/journal` 改 section 后，某些跳转丢失高亮 | 若将来有其他页面依赖 `section==='journal'` | 执行前 `grep -rn "meta.section" frontend/src` 确认只有 `App.vue` / `PageHub.vue` / `navigation.js` 消费 |
| 偏好保存把用户已关的 6 条清空 | 前端忘了回传 `suppressed` / 后端没做 `touched` 兼容 | 4.2D 兼容逻辑 + C 批第二条规定用例；上线前用真实账号先 GET 再 PUT 一次对照 |
| 提示关太多，用户忘记自己关过 | — | 偏好页常驻「已关闭 N 行说明」+ 恢复按钮，不做"隐藏式记忆" |
| 命名统一改到文案模板变量，影响多页 | 直接 sed 替换字符串 | 逐条 grep 唯一命中再改，不许批量 sed；一 commit 一变 |
| 迁移在 PG 上失败 | JSON 类型或可空约束不兼容 | 先在本地 SQLite 冒烟，再在 `backups/` 副本库跑一遍 `migrate_schema`，最后才动云端 |

**回滚粒度**：A/B 两项纯前端，回滚 = revert 对应 commit，无数据影响。C 批回滚后 `suppressed_lines` 列残留但被忽略，**不清洗数据**（符合审计只增不删）。

---

## 附表 A · 命名对照表

| # | 位置（文件） | 现名 | 目标名 | 备注 |
|---|---|---|---|---|
| 1 | `App.vue` 导航 | 手账 | *（移除，不入导航）* | 入口改由 F2 承担 |
| 2 | `PageHub.vue:61` 今天页入口 | 手账 › | 搜索 › | F2 |
| 3 | `RecordList.vue:29` 页标题 | 手账 | 手账 | **不变**（它是页面名，不是导航项） |
| 4 | `DiaryView.vue` PageHeader | 晚间日记 | 日记 | 入口按钮「写日记」已一致；"晚间日记"降级为记录类型名（`RecordList` 筛选项保留） |
| 5 | `ChallengeView.vue:517` h1 | 挑战与合同 | 挑战 | 页内 `section-links` 同步 |
| 6 | `PageHub.vue:71` 入口 | 挑战与原有合同 | 挑战 | 目标 `/challenges` |
| 7 | `ChallengeView.vue:596` | 奖励与休息 | 奖励 | 与导航项一致 |
| 8 | `AchievementsView.vue` 页标题 | 成就与里程碑 | 成就 | |
| 9 | `ReportHistory.vue` 页标题 | 历史报告 | 成长报告 | 与 `PageHub.vue:79` 入口一致 |
| 10 | `AttributePanel.vue` 入口 | 周期报告 → | 成长报告 → | 与 9 一致 |
| 11 | `PageHub.vue:83` 钱包卡 | 收支明细 › | 金币收支 › | 与 `router.js:65` title「金币收支」一致 |
| 12 | `PageHub.vue:75/76` 成长入口 | 查看变化历史 › / 全部 › | 属性变化历史 › | `router.js:59` title 已是「属性变化历史」 |
| 13 | `SettingsView.vue` 页标题 | 设置 | AI 与数据 | 与 `PageHub.vue:91` 入口一致 |
| 14 | `PageHub.vue:52` 写卡 | 今天发生了什么？ | **不变** | 首屏引导，保留 |
| 15 | 各页 PageHeader `description` | 文艺句 | **不变** | 只允许作副标题 |

> 改法统一为：**只改显示文案，不改路由路径、不改 `meta.title` 之外的标识**（附表第 9/12 项若 `meta.title` 已是目标名则只改组件内文案）。

## 附表 B · 行级提示清单（`TipLine`）

| id | 文件 | 现有原文（grep 用） | 现有容器 |
|---|---|---|---|
| `today.write-hint` | `PageHub.vue` | `一件小事，或一篇晚间日记。` | `<p>`（写卡内） |
| `journal.pure-flag` | `RecordList.vue:31` | `历史纯享标记与当前是否分析是两种设置。` | `<p class="muted">` |
| `growth.ability-note` | `PageHub.vue` | `展开查看游戏数值，也可以继续追溯变化。` | `<p class="hub-small-note">` |
| `growth.baseline` | `PageHub.vue` | `可以继续问卷，也可以先用未评估基线开始。` | `<p class="hub-small-note">` |
| `diary.same-day` | `DiaryView.vue` | `同一日期保存为同一原稿的新版，不新增第二篇。` | `<p class="muted">` |
| `calendar.dot` | `SectionDetail.vue` | `有圆点的日期留下过记录；点日期查看当天手账。` | `<p class="hub-small-note">` |

> 接入时保留原 `class`（`<TipLine>` 根元素已是 `<p class="tip-line">`，需要额外样式就传 `class` 让它合并，不要把内容套两层 `<p>`）。

## 附表 C · 变更文件清单

**前端（改）**：`App.vue`、`router.js`、`components/PageHub.vue`、`components/RecordList.vue`、`components/DiaryView.vue`、`components/ChallengeView.vue`、`components/AchievementsView.vue`、`components/ReportHistory.vue`、`components/ReviewView.vue`、`components/PendingView.vue`、`components/AnnouncementsView.vue`、`components/SettingsView.vue`、`components/AttributePanel.vue`、`components/SectionDetail.vue`、`components/PreferencesView.vue`、`daily-use.css`、`main.js`

**前端（新增）**：`composables/useTipPrefs.js`、`components/ui/TipLine.vue`、`tips.css`

**后端（改）**：`app/models/daily_use.py`、`app/routers/daily_use.py`、`tests/test_daily_use_redesign.py`

**不动**：`HomeView.vue`、`PlansView.vue`、`RewardsView.vue`（死代码）、`navigation.js`（除 F1 说明外）、`app/services/**`、`api.js`。
