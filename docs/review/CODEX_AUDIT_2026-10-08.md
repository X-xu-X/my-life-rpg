> 元信息：日期：2026-10-08；项目 HEAD commit：`4ae0ca56b843dfbf9002e058dc164dc3a55d184c`；模型型号：`gpt-6.1-sol`（来自审查时的会话记录）。编号说明：上一条完整原文为第 0～8 节，另含 P1-9 条目，没有独立第 9 节；以下保留原文编号和全部内容。

阶段 A 已完成。**当前数据库的账目核验通过；代码仍存在会导致半结算、重复入账、审计丢失和密钥明文回显的路径。**这些是需要修正的程序缺陷，不能据此声称真实库已经损坏。

本次没有修改、创建或删除文件，没有启动应用、调用模型、执行迁移或提交 Git。下面的代码均为供你挑选的修复建议，尚未实施。

## 0. 我读到了什么

项目根目录：

`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg`

### 目录树

按要求排除了 `frontend/node_modules`、`frontend/dist`、`__pycache__`、`backups`、`.git`、`_shots`、`frontend/package-lock.json`。`.venv` 是依赖环境，仅列目录，不展开。

```text
my-life-rpg/
├── .env
├── .env.example
├── .gitignore
├── .venv/
├── .run/
│   ├── backend-fastapi.run.xml
│   └── frontend-vite.run.xml
├── .workbuddy/memory/
│   ├── 2026-08-30.md
│   ├── 2026-08-31.md
│   ├── 2026-09-01.md
│   ├── 2026-09-02.md
│   ├── 2026-09-03.md
│   ├── 2026-09-05.md
│   ├── 2026-09-08.md
│   ├── 2026-09-09.md
│   ├── 2026-09-11.md
│   ├── 2026-09-22.md
│   ├── 2026-09-29.md
│   ├── 2026-09-30.md
│   └── MEMORY.md
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── constants.py
│   ├── database.py
│   ├── main.py
│   ├── models/__init__.py
│   ├── schemas/__init__.py
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── challenge.py
│   │   ├── dispute.py
│   │   ├── exemption.py
│   │   ├── extract.py
│   │   ├── judge.py
│   │   ├── memory.py
│   │   ├── onboarding.py
│   │   ├── report.py
│   │   ├── shop.py
│   │   └── subdimension.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── achievements.py
│   │   ├── anchors.py
│   │   ├── attributes.py
│   │   ├── challenges.py
│   │   ├── coins.py
│   │   ├── events.py
│   │   ├── exemptions.py
│   │   ├── export.py
│   │   ├── goals.py
│   │   ├── items.py
│   │   ├── judgments.py
│   │   ├── onboarding.py
│   │   ├── report.py
│   │   ├── settings.py
│   │   ├── shop.py
│   │   ├── stagnation.py
│   │   └── subdimensions.py
│   └── services/
│       ├── __init__.py
│       ├── achievement_service.py
│       ├── anchor_service.py
│       ├── backup_service.py
│       ├── challenge_service.py
│       ├── coin_service.py
│       ├── economy_service.py
│       ├── exemption_service.py
│       ├── goal_service.py
│       ├── item_service.py
│       ├── judge_service.py
│       ├── llm_config.py
│       ├── llm_service.py
│       ├── memory_service.py
│       ├── onboarding_service.py
│       ├── shop_service.py
│       ├── stagnation_service.py
│       ├── subdimension_service.py
│       └── user_service.py
├── docs/
│   ├── DECISIONS.md
│   ├── PRD.md
│   ├── WRITER_PROMPT.md
│   ├── DEV_PLAN_v1.3.md
│   ├── DEV_PLAN_v1.4.md
│   ├── DEV_PLAN_v1.5.md
│   ├── DEV_PLAN_v1.6.md
│   ├── DEV_PLAN_v1.7.md
│   ├── DEV_PLAN_v1.8.md
│   ├── DEV_PLAN_v1.9.md
│   ├── DEV_PLAN_v1.10.md
│   └── learning/
│       ├── BUSINESS_ROADMAP.md
│       └── CODE_GUIDE.md
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.vue
│       ├── api.js
│       ├── main.js
│       ├── styles.css
│       ├── components/
│       │   ├── AnchorsView.vue
│       │   ├── AttributePanel.vue
│       │   ├── ChallengeView.vue
│       │   ├── EventForm.vue
│       │   ├── GoalsView.vue
│       │   ├── ItemManager.vue
│       │   ├── JournalView.vue
│       │   ├── JudgmentList.vue
│       │   ├── Onboarding.vue
│       │   ├── SettingsView.vue
│       │   ├── TimelineView.vue
│       │   ├── ToastHost.vue
│       │   └── TodayCheckin.vue
│       └── composables/
│           ├── useDateGroups.js
│           └── useToast.js
├── sql/schema.sql
├── game_of_life.db
├── README.md
├── requirements.txt
├── start.bat
├── start-phone.bat
└── start.sh
```

### 实际读取的文档

沿用了本聊天前序已经完成的全文读取，并在本次重新核对了关键决策、实施记录和对应代码。

| 文档 | 文件总行数 | 阅读范围 |
|---|---:|---|
| [DECISIONS.md](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md) | 776 | 全文 |
| [PRD.md](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/PRD.md) | 317 | 全文 |
| [DEV_PLAN_v1.10.md](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DEV_PLAN_v1.10.md) | 767 | 全文 |
| [DEV_PLAN_v1.9.md](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DEV_PLAN_v1.9.md) | 496 | 全文 |
| [DEV_PLAN_v1.8.md](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DEV_PLAN_v1.8.md) | 711 | 全文 |
| [README.md](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/README.md) | 86 | 全文 |
| [WRITER_PROMPT.md](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/WRITER_PROMPT.md) | 65 | 全文 |
| [CODE_GUIDE.md](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/learning/CODE_GUIDE.md) | 1,065 | 目录及故障档案第 456–1049 行；其余章节未全文读 |

### 实际读取的代码

下面按绝对目录分组，括号为文件总行数。后端这些文件均已阅读全文。

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\app`**

`__init__.py`（1）、`config.py`（54）、`constants.py`（75）、`database.py`（76）、`main.py`（92）。

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\app\models`**

`__init__.py`（492）。

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\app\schemas`**

`__init__.py`（403）。

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\app\prompts`**

`__init__.py`（24）、`challenge.py`（225）、`dispute.py`（75）、`exemption.py`（108）、`extract.py`（33）、`judge.py`（288）、`memory.py`（36）、`onboarding.py`（199）、`report.py`（64）、`shop.py`（90）、`subdimension.py`（64）。

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\app\routers`**

`__init__.py`（1）、`achievements.py`（76）、`anchors.py`（45）、`attributes.py`（91）、`challenges.py`（169）、`coins.py`（41）、`events.py`（231）、`exemptions.py`（63）、`export.py`（149）、`goals.py`（109）、`items.py`（141）、`judgments.py`（282）、`onboarding.py`（71）、`report.py`（102）、`settings.py`（133）、`shop.py`（164）、`stagnation.py`（33）、`subdimensions.py`（78）。

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\app\services`**

`__init__.py`（1）、`achievement_service.py`（285）、`anchor_service.py`（437）、`backup_service.py`（63）、`challenge_service.py`（747）、`coin_service.py`（238）、`economy_service.py`（78）、`exemption_service.py`（422）、`goal_service.py`（129）、`item_service.py`（167）、`judge_service.py`（888）、`llm_config.py`（115）、`llm_service.py`（192）、`memory_service.py`（104）、`onboarding_service.py`（365）、`shop_service.py`（243）、`stagnation_service.py`（245）、`subdimension_service.py`（310）、`user_service.py`（40）。

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\frontend\src`**

`App.vue`（116）、`api.js`（199）、`main.js`（5）全文；`styles.css`（876）只统计行数，未全文读。

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\frontend\src\components`**

| 文件 | 总行数 | 阅读范围 |
|---|---:|---|
| App 所用的 `AttributePanel.vue` | 379 | 全文 |
| `ChallengeView.vue` | 914 | 全文 |
| `EventForm.vue` | 708 | 全文 |
| `JudgmentList.vue` | 515 | 全文 |
| `SettingsView.vue` | 439 | 全文 |
| `TodayCheckin.vue` | 353 | 全文 |
| `AnchorsView.vue` | 114 | 脚本 1–57 |
| `GoalsView.vue` | 168 | 脚本 1–99 |
| `ItemManager.vue` | 274 | 脚本 1–159 |
| `JournalView.vue` | 97 | 脚本 1–62 |
| `Onboarding.vue` | 413 | 脚本 1–274，并核对重置、成就展示模板 |
| `TimelineView.vue` | 276 | 脚本 1–172 |
| `ToastHost.vue` | 25 | 脚本 1–6 |

**`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg\frontend\src\composables`**

`useDateGroups.js`（73）、`useToast.js`（47）全文。

其他完整读取：`requirements.txt`（9）、`frontend/package.json`（19）、`frontend/vite.config.js`（21）、`frontend/index.html`（10）、`.env.example`（5）、`.gitignore`（37）、`start.bat`（129）、`start-phone.bat`（8）、`start.sh`（33）、`sql/schema.sql`（272）。Windows 启动脚本已按其实际编码读取。

### 数据库的只读核验

只读取 [game_of_life.db](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/game_of_life.db) 的字节，再反序列化到内存 SQLite；没有连接原库。读取前后文件大小和修改时间一致，没有非空 WAL 文件。查询只输出结构、计数和数值汇总。

结果：

- 17 张业务表实际存在。
- 事件 32、判定 32、属性流水 124、审计日志 86。
- 金币流水 3 笔；当前余额 **40**，流水合计 **40**，逐笔 `balance_after` 也正确。
- 嵌套快照中的 **12 个维度全部满足初始值＋流水＝当前值**。
- 诚信不在初始快照中；按代码明确的初始 50 计算，`50＋5.83＝55.83`，也一致。这里的基线来自规则，不能伪称来自快照。
- 未发现同事件多判定、悬空属性流水引用、悬空审计引用、悬空挑战引用。
- 未发现置信度越界、属性越界或同判定同属性累计绝对变化超过 5。
- 成就 0、豁免券 0、兑换记录 0；这些新路径尚不能用真实库证明已经运行正确。
- 日记来源事件 23 条，成就表仍为空，是成就追溯检查缺口的现实背景。

### 未读、不存在及限制

未读：`.env`、`.run` 两个 XML、`.workbuddy/memory` 13 个文件、旧施工计划 v1.3–v1.7、`BUSINESS_ROADMAP.md`、依赖库源码、完整 CSS，以及上表明确未全文读取的模板部分。没有输出日记正文或 API Key。

不存在：工作区内没有找到 `AGENTS.md`；项目没有 `.github`、`tests`、`conftest.py`、`pytest.ini`。

代码中没有找到：多用户认证、零 Key 免费模型、每日备份调度、生产静态前端挂载、访问密码、B1/C1/D3。这些分别属于后续范围或明确暂缓项。

所要求的七份意图材料已收齐。限制主要是文档内部存在新旧口径冲突，以及本次没有运行应用、浏览器、模型或故障注入测试。

## 1. 项目现状认定

### 技术栈、版本与工作区

- 后端：FastAPI、SQLAlchemy 2、Pydantic 2，默认 SQLite。
- 前端：Vue 3、Vite、ECharts 5，通过 `api.js` 调用 `/api`。
- 模型：OpenAI 兼容 SDK；统一出口 `llm_service`，默认 `deepseek-chat`、temperature 0.2；BYOK 分 primary/aux 两组。
- 单用户：内部解析 `username=default`。当前没有认证，符合本地阶段决定。
- HEAD：`4ae0ca56b843dfbf9002e058dc164dc3a55d184c`，2026-09-30，`feat(P2): 三页合并「今日盘点」+ 可视化重做（V1/V2/V3）`。
- 文档批次为 v1.10；后端与前端清单中的软件版本仍是 `0.1.0`，不能把它写成已有 v1.10 release tag。
- 审查的是当前工作区，包含原有未提交修改：`.gitignore`、`frontend/vite.config.js`、`start.bat`；未跟踪文件 `docs/DEV_PLAN_v1.10.md`、`start-phone.bat`。这些没有被本次改动。

### 代码规模

| 模块 | 文件数 | 行数 |
|---|---:|---:|
| 后端根模块 | 5 | 298 |
| ORM | 1 | 492 |
| Schema | 1 | 403 |
| Prompt | 11 | 1,206 |
| Router | 18 | 1,979 |
| Service | 19 | 5,069 |
| **后端合计** | **55** | **9,447** |
| Vue 组件 | 13 | 4,675 |
| Composable | 2 | 120 |
| App/API/main/CSS | 4 | 1,196 |
| **前端源码合计** | **19** | **5,991** |
| **源码总计** | **74** | **15,438** |

行数包含空行和注释，不是可执行语句数量。

### 17 张表

依据 [ORM](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/models/__init__.py:40)，并与内存库结构核对：

| 表 | 职责 |
|---|---|
| users | 默认用户与后续用户预留 |
| user_profiles | 问卷、画像、嵌套初始快照、金币余额 |
| attributes | 主维度与 `parent_id` 子维度 |
| attribute_history | 属性实际变动流水 |
| checkin_items | 打卡项目、频率、目标关联 |
| events | 生活记录、发生时间、纯享、挑战来源 |
| ai_judgments | 当前建议、置信度、实际入账、成就建议 |
| judgment_logs | 判定审计，`judgment_id NOT NULL` |
| goals | 目标、奖励、扣分、状态与审计 |
| anchors | 科学锚点与校准 |
| settings | 显示/判定开关、BYOK、停滞记录等 |
| coin_ledger | 金币流水与逐笔余额 |
| challenges | 候选、接受、押金、结果、结算 |
| shop_items | 现实奖励及 AI 定价 |
| redemptions | 兑换与兑现状态 |
| achievements | 成就解锁，用户＋code 唯一 |
| exemptions | 日期时段券、价格、购买惩罚、使用状态 |

### 对外接口

路由文件注册 **73 个方法/路径组合，其中一个重复**；加健康检查后是 74 次注册、73 个唯一组合。统一前缀 `/api`，见 [main.py:47](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/main.py:47)。

| 模块 | 实际接口 |
|---|---|
| 健康 | `GET /health` |
| 引导 | `/onboarding/status`、`questions`、`answer`、`supplement`、`supplement/confirm`、`reset`、`reset-all` |
| 事件 | `POST/GET /events`，`GET /events/heatmap`，`POST /events/{id}/judge`，`GET/PUT/DELETE /events/{id}` |
| 判定 | 列表、详情、logs、confirm、supplement、dispute、achievement |
| 属性 | `GET /attributes`、`GET /attributes/history` |
| 目标 | 列表、创建、详情、修改、achieve、fail、cancel |
| 打卡项目 | 列表、stats、创建、修改、toggle、删除 |
| 金币/成就 | `GET /coins`、`GET /achievements` |
| 挑战 | 列表、current、generate、accept、variant、complete、settle、abandon |
| 商店 | 商品 CRUD、`POST /shop/items/{id}/reprice`、redeem；兑换列表、fulfill |
| 豁免券 | `GET/POST /exemptions` |
| 子维度 | 列表、propose、accept、dismiss |
| 停滞 | 查询、`POST /stagnation/{name}/answer` |
| 锚点 | 查询、calibrate |
| 配置 | `GET/POST /settings`、`GET/PUT /llm-config` |
| 数据 | export、backup、backup/list、report |

重复项是 `POST /judgments/{judgment_id}/achievement`，分别存在于两个 router。

关键依赖声明：FastAPI `>=0.110`、Uvicorn `>=0.29`、SQLAlchemy `>=2.0`、Pydantic `>=2.6`、pydantic-settings `>=2.2`、python-dotenv `>=1.0`、OpenAI `>=1.30`；前端 Vue `^3.4.0`、ECharts `^5.5.0`、Vite `^5.2.0`。这里认定的是声明范围，没有核验已安装版本。

## 2. 两层核对

### 表 A：意图 vs 代码

| 意图条目 | 代码实际状态 | 落差 | 出处 | 认定 |
|---|---|---|---|---|
| 单用户 default，当前不做认证 | 默认用户统一解析，无注册登录 | 符合当前阶段 | [DECISIONS:14](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:14)；[user_service:10](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/user_service.py:10) | 已完成 |
| 固定默认判定口径，双模型组互回退 | primary/aux 按配置可用性回退，再用 `.env` | 这是配置缺失回退；模型调用失败不会自动换另一组 | [DECISIONS:55](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:55)；[llm_config:77](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/llm_config.py:77) | 已完成 |
| 零 Key 免费模型 | 全部无 Key 时抛 LLMError/503 | 文档明确仅部分实现，不应包装成已完成 | [DECISIONS:56](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:56)；[llm_config:104](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/llm_config.py:104) | 部分完成 |
| 一事件一现行判定，重判 id 不变 | pending/adjusted 普通重判就地更新；invalidated 被排除 | 编辑后重判新 id；并发首判没有唯一约束或写入互斥 | [DECISIONS:136](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:136)；[judge_service:441](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:441) | 部分完成 |
| 审计只增不删 | 普通修订追加；删除事件删除所有关联审计 | 删除路径直接违反红线 | [DECISIONS:137](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:137)；[judge_service:875](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:875) | 部分完成 |
| confidence＜0.8，后端400、前端禁用 | 普通确认拦截；挑战吞掉异常继续结算；空建议直接确认 | 挑战入口与普通入口不一致；None/异常数值也未严防 | [DECISIONS:73](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:73)；[challenge_service:544](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/challenge_service.py:544) | 部分完成 |
| 单次单属性绝对变化≤5，范围0–100 | 普通 parser 逐条夹取，普通落账记录实际 delta | 重复属性可累计超过5；画像补充、目标金额未统一限制 | [DECISIONS:27](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:27)；[judge_service:304](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:304)；[onboarding_service:289](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/onboarding_service.py:289) | 部分完成 |
| 完全关闭维度不判定、不入账 | 普通首判过滤 disabled | confirm 不重新检查；挑战和复核路径不统一 | [DECISIONS:61](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:61)；[judge_service:495](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:495) | 部分完成 |
| 科学锚点、拒绝不实事件 | 普通判定和反驳注入锚点 | 挑战完成 prompt 未注入锚点、没有 realistic 合约 | [WRITER:29](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/WRITER_PROMPT.md:29)；[challenge_service:459](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/challenge_service.py:459) | 部分完成 |
| 唯一金币写入口、禁止透支 | 除创建画像置0，余额赋值只在 grant | grant 使用读旧值再覆盖；一次性发币仅先查后写 | [coin_service:61](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/coin_service.py:61)；[coin_service:130](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/coin_service.py:130) | 部分完成 |
| AI 定价＋快照；押金0.6派生 | 正常挑战、商店路径已采用；快照不列逐件商品 | 停滞补课挑战仍直接用旧表：35奖励/20押金，应为21 | [DECISIONS:443](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:443)；[stagnation_service:224](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/stagnation_service.py:224) | 部分完成 |
| 成就自然追溯，下次打开点亮发币 | 行为后有检查；成就墙GET只展示 | 打开应用/成就墙本身不检查。真实库23篇日记、成就0 | [DECISIONS:725](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:725)；[achievements router:25](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/achievements.py:25) | 部分完成 |
| 豁免按事件发生时间命中 | 普通首判、补充、反驳有 hook | expired 券不能保护补录；挑战完成/退缩未统一使用 | [DEV_PLAN:544](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DEV_PLAN_v1.10.md:544)；[exemption_service:156](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/exemption_service.py:156) | 部分完成 |
| 子维度AI提议、多选、阈值95 | 已有相应表字段、接口、服务和面板 | 满级主维冻结与“13维可跌”存在口径冲突，见第7节 | [DECISIONS:729](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:729)；[subdimension_service:117](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/subdimension_service.py:117) | 已完成，存在决策冲突 |
| 三页合并今日盘点、9 tabs、进度不自动达成 | App、TodayCheckin、GoalsView 已接入 | 设置仍保留第二个项目管理入口，最新记录明确保留 | [DECISIONS:734](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:734)；[App:31](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/frontend/src/App.vue:31) | 已完成 |
| 三图重做、正确calendar范围、五处主维过滤 | range 使用完整起止日期；五处均有 parent_id IS NULL | 未发现这两项代码覆盖遗漏；未实测浏览器渲染 | [AttributePanel:234](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/frontend/src/components/AttributePanel.vue:234)；五处 service 查询 | 已完成 |
| BYOK GET绝不回显明文 | 专用 `/llm-config` 掩码 | 通用 `/settings` 返回包含明文Key的所有Setting | [DECISIONS:57](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:57)；[settings router:23](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/settings.py:23) | 部分完成 |
| 真实数据禁止未经备份批量清理 | 有在线整库备份、自动补列 | reset-all直接批量删除；普通reset允许覆盖旧基线 | [onboarding_service:332](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/onboarding_service.py:332) | 部分完成 |
| JSON导出全部数据 | 导出旧六类实体 | 缺画像基线、审计、金币、挑战、成就、券和完整层级字段 | [export router:40](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/export.py:40) | 部分完成 |
| 游戏化扩展模块可开关 | 设置能保存四个开关 | 没找到已交付模块消费这些开关的实现 | [WRITER:33](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/WRITER_PROMPT.md:33)；[SettingsView:232](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/frontend/src/components/SettingsView.vue:232) | 代码中不存在实际接线 |
| M4上云自用、B1/C1/D3 | 没找到对应生产部署或新功能实现 | 与当前范围一致，单列后续门槛 | [DECISIONS:156](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:156) | 未开始 |

### 表 B：记录 vs 代码

| 记录怎么写 | 代码实际是什么 | 性质 |
|---|---|---|
| “审计只增不删，旧审计连带删除根因已移除”，[DECISIONS:137](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:137) | 删除事件仍在 [judge_service:884](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:884) 批量删日志 | **错误：适用范围写得过宽** |
| “disabled维度过滤建议并拦截入账”，[DECISIONS:61](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:61) | 首判过滤存在；confirm无重新检查，其他入口不统一 | **错误：缺少入账拦截** |
| “GET绝不返回Key明文”，[DECISIONS:57](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:57) | `/llm-config`正确，`/settings`泄漏 | **错误：通用接口旁路** |
| v1.9记录“AI金额不用、从参数表派生” | v1.10正常路径使用AI金额 | **过时，已被新决策推翻** |
| “已达成成就下次打开正常发币”，[DECISIONS:725](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:725) | 打开成就墙只调用wall，没有check_and_grant | **记录提到但代码不存在该触发点** |
| 启动备份“失败不影响启动”，[main:83](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/main.py:83) | mkdir在try外；失败清理unlink也未保护 | **错误：存在未覆盖异常路径** |
| SQL与ORM保持一致，[DECISIONS:21](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/docs/DECISIONS.md:21) | SQL只有15张表，缺成就、券及层级新字段 | **过时** |
| WRITER只从.env读Key、BYOK留到M4 | BYOK双组已经交付 | **过时** |
| 停滞问询写settings，不写无judgment_id审计 | 实现确实如此 | **一致** |
| B15 calendar使用完整日期；B16五处主维过滤 | 代码均有对应修复 | **一致** |
| 9 tabs、Today复用组件、设置保留ItemManager | 代码对应 | **一致** |
| 历史实施记录里的31事件、122流水等计数 | 当前32事件、124流水；历史计数有时间背景 | **历史快照，不能当当前计数，也不能据此判错** |

## 3. P0 —— 必须修的问题

P0 的依据是会破坏明确的数据、资金、判定或密钥约束。以下代码是完整替换函数，或标明位置的替换块；每项都独立交代所需上下文。若选中多项涉及同一函数，阶段 B 必须合并这些约束。

### P0-1【关闭真实数据的危险重置，禁止重新建档覆盖已有基线】

- **维度：**工程。
- **位置：**[onboarding_service.py:332](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/onboarding_service.py:332)、[routers/onboarding.py:62](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/onboarding.py:62)。
- **现象：**reset-all直接删除事件、判定、审计、属性流水和目标；不备份、不走删除接口，而且不清理金币、挑战、兑换等关联状态。普通reset则允许重新生成面板，覆盖当前值与初始快照，却保留旧属性流水。
- **依据：**

```python
for model in (JudgmentLog, AIJudgment, AttributeHistory, Event, Goal):
    db.query(model).filter(model.user_id == user.id).delete()

profile.onboarding_completed = False
# 后续 _generate_panel:
profile.initial_attributes_snapshot = {"attributes": panel, ...}
attr.current_value = value
```

- **影响：**点击设置页“重置全部数据”可丢失真实记录和审计；重新问卷会破坏基线＋流水恒等式，并可能再次发启动资金。
- **意图对齐：**符合数据红线和“首次建档一次性”方向。建议撤掉两个面向已建档用户的重置按钮；未完成、无历史的新问卷仍可重开。
- **修复方案：**服务层禁止批量清空，允许重置前检查是否已有基线或流水；生成面板前重复检查，防止直接调用绕过。相关 ORM 类已在此 service 导入。

```python
def _assert_unbuilt_profile(db: Session, profile: UserProfile) -> None:
    has_history = (
        db.query(AttributeHistory.id)
        .filter(AttributeHistory.user_id == profile.user_id)
        .first()
        is not None
    )
    if (
        profile.onboarding_completed
        or profile.initial_attributes_snapshot
        or has_history
    ):
        raise ValueError("已有角色基线或属性流水，不能重新建档；请使用补充长期信息。")


def reset_onboarding(db: Session) -> dict:
    user = get_or_create_default_user(db)
    profile = _get_profile(db, user)
    _assert_unbuilt_profile(db, profile)
    profile.onboarding_state = {}
    profile.pending_adjustment = {}
    db.commit()
    return {"status": "ok", "message": "未完成的问卷已重置。"}


def reset_all_data(db: Session) -> dict:
    raise ValueError("真实数据清空入口已停用；批量清理必须先整库备份并走事件删除接口。")
```

在 `_generate_panel()` 第一条配置/模型调用之前插入：

```python
_assert_unbuilt_profile(db, profile)
```

将两个重置路由完整替换为：

```python
@router.post("/onboarding/reset")
def reset_onboarding(db: Session = Depends(get_db)):
    try:
        return onboarding_service.reset_onboarding(db)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/onboarding/reset-all")
def reset_all(db: Session = Depends(get_db)):
    raise HTTPException(status_code=409, detail="真实数据清空入口已停用。")
```

前端移除 `SettingsView` 的 reset-all 操作区和 `Onboarding` 已建档态的重建按钮；不要只隐藏前端而留下可用的清库 service。

- **影响范围：**onboarding service、router、设置页、角色档案页。
- **是否改动数据模型：**否。
- **是否改动对外接口：**是，危险操作明确返回409。
- **是否引入新依赖：**否。
- **验证方式：**在有基线和属性流水的内存库调用两个重置入口及 `_generate_panel`，均被拒绝；17表计数、快照、属性值、金币完全不变。空白未完成问卷仍可重置。
- **预估改动量：**大，完整移除交互涉及4个文件；后端止损本身约30–50行。

### P0-2【判定、属性流水、金币和挑战终态必须一次提交】

- **维度：**架构。
- **位置：**[judge_service.py:680](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:680)、[routers/judgments.py:152](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/judgments.py:152)、[challenge_service.py:524](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/challenge_service.py:524)。
- **现象：**confirm先commit属性，路由再发金币；金币失败只rollback第二段。挑战也先确认属性，再退押金/发奖励。挑战吞掉低置信度异常继续结算，空建议甚至绕过confidence检查。挑战来源判定还能从普通确认入口获得日常金币，随后挑战settle因confirmed而失败。
- **依据：**

```python
judgment = judge_service.confirm(db, judgment)  # 内部已commit
try:
    coin_service.reward_event_confirm(...)
    db.commit()
except Exception:
    db.rollback()

# challenge:
except ValueError:
    judgment.status = "adjusted"
    db.commit()
# 随后仍退押金、发奖励、改终态
```

- **影响：**发币失败后留下已确认但少币的记录，重试又被状态拦住；挑战留下属性已入账但押金未返的状态；低信判断可改资金及终态。
- **意图对齐：**符合统一入账和置信度拦截。累计成就可在主事务完成后单独检查；基础日常奖励、押金和挑战奖励必须和主状态同事务。
- **修复方案：**

先给 service `confirm` 增加内部事务参数，默认保持旧调用兼容：

```python
def confirm(
    db: Session, judgment: AIJudgment, *, commit: bool = True
) -> AIJudgment:
```

在该函数取得user后、任何属性写入前，加入数据库状态抢占，防止两个请求同时结算：

```python
claimed = (
    db.query(AIJudgment)
    .filter(
        AIJudgment.id == judgment.id,
        AIJudgment.user_id == user.id,
        AIJudgment.status.in_(("pending", "adjusted")),
    )
    .update({"status": "confirmed"}, synchronize_session=False)
)
if claimed != 1:
    raise ValueError("该判定已入账或已作废，不能确认。")
db.refresh(judgment)
```

将函数末尾commit替换为：

```python
db.flush()
if commit:
    db.commit()
    db.refresh(judgment)
return judgment
```

普通确认路由完整替换为下列函数。现有 `_get_judgment`、`coin_service`、`achievement_service` 和 `Event` 均已存在：

```python
@router.post("/judgments/{judgment_id}/confirm")
def confirm(judgment_id: int, db: Session = Depends(get_db)):
    judgment = _get_judgment(db, judgment_id)
    if judgment.status == "confirmed":
        raise HTTPException(status_code=409, detail="该判定已确认入账。")

    event = db.get(Event, judgment.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="事件不存在。")
    if event.origin == "challenge":
        raise HTTPException(status_code=409, detail="挑战判定请从挑战页确认结算。")

    user = get_or_create_default_user(db)
    try:
        judgment = judge_service.confirm(db, judgment, commit=False)
        coins_gained = coin_service.reward_event_confirm(
            db, user, judgment, event_title=event.title or ""
        )
        db.commit()
        db.refresh(judgment)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    unlocked = []
    try:
        for row in achievement_service.check_and_grant(db, user):
            unlocked.append({
                "code": row.code, "name": row.name,
                "icon": row.icon, "coin_reward": row.coin_reward,
            })
    except Exception:
        db.rollback()

    return {
        "status": judgment.status,
        "final_changes": judgment.final_changes,
        "coins_gained": (
            coin_service.EVENT_CONFIRM_REWARD if coins_gained is not None else 0
        ),
        "balance": coin_service.balance(db, user),
        "unlocked_achievements": unlocked,
        "achievement_suggestion": judgment.achievement_suggestion or {},
    }
```

挑战 `settle()` 完整替换。金额规则沿用现在的done/partial/excused/retreated，不新增上限：

```python
def settle(
    db: Session, user: User, challenge: Challenge,
    final_status: str = "settled",
) -> dict:
    if final_status not in ("settled", "abandoned", "expired"):
        raise ValueError("不支持的挑战终态。")
    if not challenge.judgment_id:
        raise ValueError("请先提交完成自述。")

    try:
        claimed = (
            db.query(Challenge)
            .filter(
                Challenge.id == challenge.id,
                Challenge.user_id == user.id,
                Challenge.status == "accepted",
            )
            .update({"status": final_status}, synchronize_session=False)
        )
        if claimed != 1:
            raise ValueError("该挑战已结算或当前不可结算。")
        db.refresh(challenge)

        judgment = db.get(AIJudgment, challenge.judgment_id)
        if judgment is None:
            raise ValueError("挑战判定不存在。")

        # 空建议同样必须检查置信度和判定状态。
        judge_service.confirm(db, judgment, commit=False)
        applied_changes = judgment.final_changes or []
        outcome = challenge.outcome or "retreated"
        if outcome not in VALID_OUTCOMES:
            raise ValueError("挑战结果不合法。")

        coins_delta = 0
        if outcome in RETAIN_OUTCOMES:
            coin_service.grant(
                db, user, challenge.deposit,
                source="challenge_refund",
                reason=f"挑战「{challenge.title}」退回押金",
                ref_type="challenge", ref_id=challenge.id,
            )
            coins_delta += challenge.deposit
            if outcome == "done":
                coin_service.grant(
                    db, user, challenge.coin_reward,
                    source="challenge_reward",
                    reason=f"完成挑战「{challenge.title}」奖励",
                    ref_type="challenge", ref_id=challenge.id,
                )
                coins_delta += challenge.coin_reward
        else:
            coin_service.grant(
                db, user, 0, source="challenge_forfeit",
                reason=f"挑战「{challenge.title}」未完成，押金不退",
                ref_type="challenge", ref_id=challenge.id,
            )

        challenge.resolved_at = datetime.now()
        db.commit()
        db.refresh(challenge)
    except Exception:
        db.rollback()
        raise

    unlocked = []
    try:
        for row in achievement_service.check_and_grant(db, user):
            unlocked.append({
                "code": row.code, "name": row.name,
                "icon": row.icon, "coin_reward": row.coin_reward,
            })
    except Exception:
        db.rollback()

    return {
        "challenge_id": challenge.id,
        "outcome": outcome,
        "explanation": challenge.outcome_note,
        "coins_delta": coins_delta,
        "balance": coin_service.balance(db, user),
        "applied_changes": applied_changes,
        "unlocked_achievements": unlocked,
    }
```

同时修正三个事务收尾点：

1. `complete()`第501行的commit移到第507行 `_log()`之后，否则create审计未提交。
2. `_make_retreat_judgment()`第646行commit也移到其 `_log()`之后；已有 `challenge.judgment_id` 时复用，不能再次新建：

```python
if challenge.judgment_id:
    existing = db.get(AIJudgment, challenge.judgment_id)
    if existing is None:
        raise ValueError("挑战引用的判定不存在。")
    return existing
```

3. `expire_stale()`不得在settle失败后强行写expired；失败回滚并保留待处理状态：

```python
if not ch.judgment_id:
    _make_retreat_judgment(db, user, ch, "到期未完成")
db.refresh(ch)
try:
    settle(db, user, ch, final_status="expired")
except ValueError:
    db.rollback()
```

前端/API补齐拦截：

```python
# routers/challenges.py 的 _out() 返回字典新增：
"judgment_confidence": j.confidence if j else None,
"judgment_confidence_reason": j.confidence_reason if j else "",
```

```javascript
// ChallengeView.vue 脚本新增：
function canSettle(c) {
  const confidence = Number(c.judgment_confidence)
  return ['pending', 'adjusted'].includes(c.judgment_status)
    && Number.isFinite(confidence)
    && confidence >= 0.8
    && confidence <= 1
}
```

将挑战结算按钮改为：

```html
<button class="btn small primary"
        :disabled="anyBusy || !canSettle(c)"
        @click="settle(c)">
  {{ isBusy(`settle-${c.id}`) ? '入账中…' : '确认结算' }}
</button>
```

普通判定卡的确认按钮增加 `v-if="j.origin !== 'challenge'"`，挑战卡显示“请在挑战页结算”。

- **影响范围：**judge/challenge service、judgments/challenges router、两个判定前端。
- **是否改动数据模型：**否。
- **是否改动对外接口：**是，挑战响应增加置信度字段；普通确认拒绝挑战来源。
- **是否引入新依赖：**否。
- **验证方式：**在金币grant处注入异常，属性、属性流水、confirm审计、金币流水、挑战终态应全部回滚；相同判定/挑战两个并发请求至多一次成功；confidence0.79及空建议0.79均400且资金不变；挑战不拿日常2币；create日志确实保存。
- **预估改动量：**大，约150–220行，超过3个文件。

### P0-3【金币原子增减，并锁住启动资金和日记里程碑的一次性发放】

- **维度：**功能。
- **位置：**[coin_service.py:97](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/coin_service.py:97)、[onboarding_service.py:186](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/onboarding_service.py:186)。
- **现象：**grant读余额后覆盖；启动资金和streak先查后写没有并发保护。GET coins可在建档之前先发80，问卷完成随后不检查就再次发AI启动资金。
- **依据：**

```python
current = int(profile.coins or 0)
new_balance = current + int(delta)
profile.coins = new_balance

# onboarding:
coin_service.grant(db, user, initial_coins, source="onboarding_bonus")
```

- **影响：**并发覆盖可能让流水和余额不一致，两个扣款都通过旧余额检查；先访问金币再建档会多发启动资金。当前真实库没有这些坏账。
- **意图对齐：**符合grant唯一入口、禁止透支、一次性启动资金；不追溯调整历史合法40币，也不增设经济上限。
- **修复方案：**在coin service增加 `from sqlalchemy import func`；完整替换grant，保留外部签名及“不commit”的约定：

```python
def grant(
    db: Session, user: User, delta: int, source: str,
    reason: str = "", ref_type: str | None = None,
    ref_id: int | None = None,
) -> int:
    if type(delta) is not int:
        raise ValueError("金币变动必须是整数。")
    if source not in SOURCES:
        raise ValueError("未知的金币流水来源。")

    profile = _profile(db, user)
    db.flush()
    current_expr = func.coalesce(UserProfile.coins, 0)
    affected = (
        db.query(UserProfile)
        .filter(
            UserProfile.user_id == user.id,
            current_expr + delta >= 0,
        )
        .update(
            {UserProfile.coins: current_expr + delta},
            synchronize_session=False,
        )
    )
    if affected != 1:
        db.refresh(profile, attribute_names=["coins"])
        raise InsufficientCoins(
            f"金币不足（需 {abs(delta)} 币，当前 {int(profile.coins or 0)} 币）"
        )

    db.refresh(profile, attribute_names=["coins"])
    new_balance = int(profile.coins or 0)
    db.add(CoinLedger(
        user_id=user.id, delta=delta, balance_after=new_balance,
        source=source, reason=reason,
        ref_type=ref_type, ref_id=ref_id,
    ))
    db.flush()
    return new_balance
```

在coin service增加一次性发放锁，使用现有画像行，不加表：

```python
def _lock_oneoff_account(db: Session, user: User) -> UserProfile:
    profile = _profile(db, user)
    db.flush()
    db.query(UserProfile).filter(
        UserProfile.user_id == user.id
    ).update({UserProfile.id: UserProfile.id}, synchronize_session=False)
    db.refresh(profile)
    return profile


def grant_startup_bonus_if_needed(
    db: Session, user: User, amount: int | None = None,
    reason: str = "",
) -> bool:
    profile = _lock_oneoff_account(db, user)
    if amount is None and not profile.onboarding_completed:
        return False

    exists = db.query(CoinLedger.id).filter(
        CoinLedger.user_id == user.id,
        CoinLedger.source == "onboarding_bonus",
    ).first()
    if exists is not None:
        return False

    value = STARTUP_BONUS if amount is None else amount
    if type(value) is not int or value <= 0:
        raise ValueError("启动资金必须是正整数。")
    grant(
        db, user, value, source="onboarding_bonus",
        reason=reason or f"角色档案建立，发放启动资金 {value} 币",
    )
    return True
```

在 `check_journal_streak()`取得streak之前插入：

```python
_lock_oneoff_account(db, user)
```

使“查询是否已发”和grant处在同一持锁事务。现有GET coins末尾commit保留。

将 `_generate_panel()`原第186–200行整体替换：

```python
user = db.get(User, profile.user_id)
if user is None:
    raise ValueError("用户不存在。")
coin_service.grant_startup_bonus_if_needed(
    db, user, amount=initial_coins,
    reason=f"角色档案建立，获得启动资金 {initial_coins} 币 —— {initial_coins_reason}",
)
db.commit()
```

这样快照、属性、完成状态和启动资金一起提交；即使历史上已发过启动资金，也不再次发放。

- **影响范围：**coin service、onboarding service及所有现有grant调用方。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否。
- **是否引入新依赖：**否。
- **验证方式：**并发两次扣款且余额只够一次，至多一次成功；并发加币后余额等于流水和；每笔balance_after正确；建档前GET coins不发启动资金；建档与GET并发仅一笔bonus；streak并发仅一次。异常必须整笔回滚。
- **预估改动量：**大，约90–130行。

### P0-4【锁住已入账判定，编辑后的重判复用原id，并防止并发首判重复】

- **维度：**功能。
- **位置：**[judge_service.py:687](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:687)、[judge_service.py:750](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:750)、[routers/events.py:195](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/events.py:195)。
- **现象：**supplement/dispute不检查已入账状态；supplement把confirmed改成adjusted，没有冲回旧流水，随后可再确认。编辑把未确认判定invalidated，judge_event又排除invalidated并新建id。首判仅先查后建，没有并发保护。
- **依据：**

```python
judgment.suggested_changes = changes
judgment.status = "adjusted"
db.commit()
# 没有冲回已有 final_changes

AIJudgment.status.in_(["pending", "adjusted"])
```

- **影响：**直接调用API可重复入账；旧预览id与新id分裂；编辑已确认正文还会让当前文字与旧评分证据不对应。
- **意图对齐：**符合一事件一现行判定、审计保留。**建议暂时禁止已入账内容修订，会收紧原来可编辑正文的行为，需要第7节确认。**若要支持已确认修订，应另做反向流水流程。
- **修复方案：**给supplement/dispute加入口检查，并在LLM返回后再次用数据库状态条件抢占：

```python
def _require_reviewable(
    db: Session, judgment: AIJudgment, *, lock: bool = False
) -> None:
    if lock:
        count = db.query(AIJudgment).filter(
            AIJudgment.id == judgment.id,
            AIJudgment.status.in_(("pending", "adjusted")),
        ).update(
            {AIJudgment.status: AIJudgment.status},
            synchronize_session=False,
        )
        if count != 1:
            raise ValueError("该判定已入账或已作废，不能修订。")
        db.refresh(judgment)

    if judgment.status not in ("pending", "adjusted"):
        raise ValueError("仅未入账的现行判定可以补充或反驳。")
    if db.query(AttributeHistory.id).filter(
        AttributeHistory.judgment_id == judgment.id
    ).first() is not None:
        raise ValueError("该判定已有入账流水，不能再次修订入账。")
```

两个函数在写入用户操作log之前调用：

```python
_require_reviewable(db, judgment)
```

两个函数在 `llm_service.chat_json()`返回后、修改judgment之前调用：

```python
_require_reviewable(db, judgment, lock=True)
```

对应两个router增加ValueError→400，并rollback：

```python
except ValueError as exc:
    db.rollback()
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

普通judge_event应读取同事件全部判定，不只pending/adjusted；本库目前没有重复，可以安全复用原id。新增以下 helper，LLM调用前记录输入，返回后取得事件写锁并重新核对：

```python
def _event_fingerprint(event: Event) -> tuple:
    return (
        event.event_type, event.category, event.source,
        event.title, event.content, event.item_id,
        event.occurred_at, event.is_pure, event.origin,
        json.dumps(event.params or {}, ensure_ascii=False, sort_keys=True),
    )


def _current_for_write(db: Session, event: Event, user, fingerprint) -> AIJudgment | None:
    count = db.query(Event).filter(
        Event.id == event.id, Event.user_id == user.id
    ).update({Event.title: Event.title}, synchronize_session=False)
    if count != 1:
        raise ValueError("事件已不存在。")
    db.refresh(event)
    if getattr(event, "is_deleted", False):
        raise ValueError("事件已删除。")
    if _event_fingerprint(event) != fingerprint:
        raise ValueError("判定期间事件已被编辑，请重新判定。")

    rows = db.query(AIJudgment).filter(
        AIJudgment.event_id == event.id,
        AIJudgment.user_id == user.id,
    ).populate_existing().all()
    if len(rows) > 1:
        raise ValueError("该事件存在历史多判定，需先人工确认现行记录。")
    current = rows[0] if rows else None
    if current is not None:
        if current.status == "confirmed":
            raise ValueError("该事件已入账，不能再次判定。")
        if db.query(AttributeHistory.id).filter(
            AttributeHistory.judgment_id == current.id
        ).first() is not None:
            raise ValueError("该事件已有入账流水，不能再次判定。")
    return current
```

具体接入点：

```python
# judge_event 原来的current查询：
current = db.query(AIJudgment).filter(
    AIJudgment.event_id == event.id,
    AIJudgment.user_id == user.id,
).order_by(AIJudgment.id.desc()).first()

# 传给prompt的基准：被编辑作废或拒绝的旧结果不作为增量底稿。
prior_judgment = (
    _prior_snapshot(current)
    if current is not None and current.status in ("pending", "adjusted")
    else None
)

# 自己追加 clarification 并flush之后、调用模型之前：
fingerprint = _event_fingerprint(event)

# 模型返回之后、处理输出和新建/更新判定之前：
current = _current_for_write(db, event, user, fingerprint)
```

将原confirmed拒绝文案改为“该事件已入账，不能再次判定”，删除“可以用补充信息调整”的错误引导。

编辑接口在修改字段前，先对Event做同样的写锁，并拒绝已有判定入账流水或confirmed的事件；未确认的编辑继续追加invalidate日志，不删除判定。前端应展示该限制，不能继续提示“旧判定全部作废”却保留已确认分数。

- **影响范围：**judge service、events/judgments router、判定卡编辑交互。
- **是否改动数据模型：**否；使用现有行写锁，不新增唯一索引或重建表。
- **是否改动对外接口：**是，已入账修订/编辑返回明确拒绝。
- **是否引入新依赖：**否。
- **验证方式：**confirmed→supplement/dispute/再次confirm，属性和流水均不变；pending→编辑→重判id不变、日志增加；并发首判最终只有一条；判定期间编辑正文，旧响应被拒绝。
- **预估改动量：**大，约100–150行，超过3个文件。

### P0-5【删除事件必须保留审计，并按真实入账流水回滚】

- **维度：**工程。
- **位置：**[judge_service.py:828](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:828)。
- **现象：**先写delete审计，随后删掉全部审计及判定。回滚还使用 `final_changes or suggested_changes`：实际入账为空时会错误回退到名义建议。不实事件直接物理删Event，可能留下已有判定或诚信扣分引用。
- **依据：**

```python
for item in judgment.final_changes or judgment.suggested_changes:
    ...
_log(db, judgment.id, user.id, "delete", ...)
db.query(JudgmentLog).filter(...).delete()
db.delete(judgment)
db.delete(event)
```

- **影响：**删除操作把自身证据也消灭；100封顶导致实际加0时，删除可能反而扣分；保留下来的历史流水可能引用已不存在的父记录。
- **意图对齐：**符合审计只增不删及真实流水回滚。这里不把“禁止删除数据库文件”曲解成“所有行都不能删除”；保留父记录是为了满足审计和外键语义。
- **修复方案：**推荐逻辑删除，保留现有DELETE接口的用户行为。Event新增：

```python
is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
```

由现有启动迁移补列并回填False，不重建、不删列。替换delete service，用真实历史而非建议值：

```python
def delete_event(db: Session, event: Event) -> None:
    user = get_or_create_default_user(db)
    try:
        claimed = db.query(Event).filter(
            Event.id == event.id,
            Event.user_id == user.id,
            Event.is_deleted.is_(False),
        ).update({"is_deleted": True}, synchronize_session=False)
        if claimed != 1:
            raise ValueError("事件已删除或不存在。")

        judgments = db.query(AIJudgment).filter(
            AIJudgment.event_id == event.id,
            AIJudgment.user_id == user.id,
        ).all()
        ids = [j.id for j in judgments]
        histories = (
            db.query(AttributeHistory).filter(
                AttributeHistory.user_id == user.id,
                AttributeHistory.event_id == event.id,
                AttributeHistory.judgment_id.in_(ids),
            ).all()
            if ids else []
        )
        totals = {}
        for row in histories:
            totals[row.attribute_id] = totals.get(row.attribute_id, 0.0) + row.delta

        reversed_changes = []
        for attribute_id, total in totals.items():
            attr = db.query(Attribute).filter(
                Attribute.id == attribute_id,
                Attribute.user_id == user.id,
            ).populate_existing().first()
            if attr is None:
                raise ValueError("原流水对应的属性不存在，不能猜测回滚。")
            before = attr.current_value
            after = round(_clamp_attribute_value(before - total, attr.max_value), 2)
            actual = round(after - before, 2)
            if actual == 0:
                continue
            attr.current_value = after
            db.add(AttributeHistory(
                user_id=user.id, attribute_id=attr.id,
                event_id=event.id, judgment_id=None,
                delta=actual, value_after=after,
                reason="事件删除回滚：按原始实际入账流水反向处理",
                evidence="误提交兜底",
            ))
            reversed_changes.append({
                "attribute_id": attr.id, "name": attr.name, "delta": actual,
            })

        for judgment in judgments:
            judgment.status = "deleted"
            _log(
                db, judgment.id, user.id, "delete",
                detail=f"事件逻辑删除（event_id={event.id}）",
                payload={
                    "source_history_ids": [h.id for h in histories],
                    "reversed_changes": reversed_changes,
                },
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
```

业务查询必须明确排除逻辑删除。**不能只改删除函数。**在以下已有Event查询的filter中加入同一个条件：

```python
Event.is_deleted.is_(False)
```

必须覆盖的消费点已经枚举：

| 文件 | 函数 |
|---|---|
| events router | list_events、get_heatmap；judge/get/update/delete 的 `db.get` 后检查is_deleted |
| judgments router | list_judgments的Event join；普通confirm取Event后检查 |
| report router | generate_report |
| achievement service | _metrics的journal和event计数 |
| coin service | _journal_days |
| exemption service | _recent_events |
| item service | count_in_period、period_count_map、build_stats |
| judge service | _recent_same_category_count、_recent_events_context、_recent_24h_context、_today_events_context；supplement/dispute取Event后检查 |
| memory service | _events_summary |
| subdimension service | _related_events |

判定列表同时排除 `AIJudgment.status == "deleted"`。完整JSON归档和数据库备份则应保留删除记录，不将逻辑隐藏误当成彻底遗忘。

不实事件处理至少必须保留Event，拒绝已有现行判定，并追加审计；不能留下可确认的旧pending：

```python
# _handle_unrealistic 开头，取得/复用同事件判定：
rejected = db.query(AIJudgment).filter(
    AIJudgment.event_id == event.id,
    AIJudgment.user_id == user_id,
).order_by(AIJudgment.id.desc()).first()
if rejected is None:
    rejected = AIJudgment(
        event_id=event.id, user_id=user_id,
        suggested_changes=[], final_changes=[],
        confidence=0.0, status="rejected",
    )
    db.add(rejected)
    db.flush()
rejected.status = "rejected"
rejected.confidence = 0.0
rejected.summary = f"拒绝判定：{reason}"
_log(
    db, rejected.id, user_id, "reject",
    detail=reason, payload={"event_id": event.id},
)

# 保留原不实计数及诚信实际流水处理；删除原来的 db.delete(event)。
# 诚信流水可以关联 rejected.id，不能伪造空judgment_id审计。
db.commit()
raise ValueError(msg)
```

DELETE router捕获ValueError、rollback并返回409。UI解释“从业务列表移除并冲回点数，审计保留”。

- **影响范围：**Event模型、judge service、事件router及上表读取者。
- **是否改动数据模型：**是，仅新增布尔列。
- **是否改动对外接口：**删除路径/响应形状不变；重复删除明确拒绝，删除语义改为保留审计。
- **是否引入新依赖：**否。
- **验证方式：**100分属性建议＋2但实际0，删除后仍100且无错误扣分；有实际加点时写反向实际流水；原判定、所有旧日志及delete日志保留；重复删除不重复回滚；列表/热力图/计数不含删除事件；备份/完整归档仍含记录。
- **预估改动量：**大，约150–220行，涉及多个消费文件。封顶/触底后的历史撤销口径另见第7节。

### P0-6【模型数值与入账聚合必须统一校验，不能把异常值或重复维度当合法结果】

- **维度：**功能。
- **位置：**[llm_service.py:172](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/llm_service.py:172)、[judge_service.py:304](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/judge_service.py:304)、[onboarding_service.py:172](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/onboarding_service.py:172)。
- **现象：**json.loads允许NaN/Infinity，`1e309`也可成为inf；confidence直接float且不校验0–1；None在confirm按1处理。changes逐条限制5，但同属性两条仍能合计10。初始面板接受未知名字和越界值；补充画像直接用无限制delta。
- **依据：**

```python
confidence=float(result.get("confidence", 0.0))
conf = judgment.confidence if judgment.confidence is not None else 1.0

for item in raw_changes:
    delta = float(item.get("delta", 0.0))
    cleaned.append({"name": name, "delta": _clamp_delta(delta)})
```

- **影响：**confidence2会放大积分；重复＋5可同次加10；错误面板可能创建任意维度或污染基线；模型返回结构错误时产生500。
- **意图对齐：**符合LLM不可信、单属性单次≤5和0–100；不添加经济金额上限，不替换AI定价。
- **修复方案：**

在llm service新增严格解码函数，并将 `_parse_json()`中的两处 `json.loads(...)`替换成它；原捕获范围从JSONDecodeError扩展为ValueError/RecursionError：

```python
import math


def _strict_json_loads(text: str):
    def reject_constant(value):
        raise ValueError(f"非法JSON数值：{value}")

    def check(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("模型返回了非有限数值。")
        if isinstance(value, dict):
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    result = json.loads(text, parse_constant=reject_constant)
    check(result)
    return result
```

在judge service新增 `import math`，替换数值parser：

```python
def _finite_float(raw, fallback=0.0):
    if isinstance(raw, bool):
        return fallback
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return value if math.isfinite(value) else fallback


def _parse_confidence(raw) -> float:
    value = _finite_float(raw, 0.0)
    return value if 0.0 <= value <= 1.0 else 0.0


def _parse_changes(raw_changes, extra_names=None) -> list[dict]:
    if not isinstance(raw_changes, list):
        return []
    grouped = {}
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        name = _normalize_attribute_name(str(item.get("name", "")), extra_names)
        if name is None:
            continue
        delta = _finite_float(item.get("delta"), None)
        if delta is None:
            continue
        entry = grouped.setdefault(name, {
            "name": name, "delta": 0.0, "reasons": [], "evidences": [],
        })
        entry["delta"] += _clamp_delta(delta)
        if item.get("reason"):
            entry["reasons"].append(str(item["reason"]))
        if item.get("evidence"):
            entry["evidences"].append(str(item["evidence"]))

    return [{
        "name": entry["name"],
        "delta": round(_clamp_delta(entry["delta"]), 2),
        "reason": "；".join(dict.fromkeys(entry["reasons"])),
        "evidence": "；".join(dict.fromkeys(entry["evidences"])),
    } for entry in grouped.values()]
```

所有首判、补充、反驳的confidence赋值使用 `_parse_confidence`；挑战用 `judge_service._parse_confidence`，不再把非法/缺失置信度默认为0.85。

confirm必须在状态抢占后刷新judgment，再检查：

```python
conf = _parse_confidence(judgment.confidence)
if conf < CONFIDENCE_CONFIRM_MIN:
    raise ValueError("判定置信度不足或不合法，请补充信息后重新判定。")
```

confirm先规范化，再按**实际写入Attribute.id**聚合，避免多个子维度回流同一主维后再次突破5。替换原逐条即时写入循环为：

```python
attrs = db.query(Attribute).filter(
    Attribute.user_id == user.id
).populate_existing().all()
by_name = {a.name: a for a in attrs}
by_id = {a.id: a for a in attrs}
child_names = {a.name for a in attrs if a.parent_id is not None}
disabled = _get_disabled_attributes(db, user.id)
changes = _parse_changes(judgment.suggested_changes, child_names)
targets = {}

for item in changes:
    attr = by_name.get(item["name"])
    if attr is None:
        continue
    parent = by_id.get(attr.parent_id)
    if attr.name in disabled or (parent and parent.name in disabled):
        continue

    target, note = subdimension_service.resolve_write_target(db, user, attr)
    parent = by_id.get(target.parent_id)
    if target.name in disabled or (parent and parent.name in disabled):
        continue
    group = targets.setdefault(target.id, {
        "attr": target, "delta": 0.0, "reasons": [], "evidences": [],
    })
    group["delta"] += item["delta"] * conf
    group["reasons"].append(item["reason"] + note)
    group["evidences"].append(item["evidence"])

applied_changes = []
for group in targets.values():
    attr = group["attr"]
    before = _finite_float(attr.current_value, None)
    if before is None:
        raise ValueError("属性已有非法数值，需人工核查。")
    delta = round(_clamp_delta(group["delta"]), 2)
    after = round(_clamp_attribute_value(before + delta, attr.max_value), 2)
    actual = round(after - before, 2)
    if actual == 0:
        continue
    reason = "；".join(dict.fromkeys(group["reasons"])) + f"（置信度 {conf:.0%} 加权）"
    evidence = "；".join(dict.fromkeys(group["evidences"]))
    attr.current_value = after
    db.add(AttributeHistory(
        user_id=user.id, attribute_id=attr.id,
        event_id=judgment.event_id, judgment_id=judgment.id,
        delta=actual, value_after=after, reason=reason, evidence=evidence,
    ))
    applied_changes.append({
        "name": attr.name, "delta": actual,
        "reason": reason, "evidence": evidence,
    })
```

保留原来的final_changes赋值和confirm日志；任何校验失败由事务拥有者rollback。

初始面板不能自行发明缺失维度的评分。新增解析并在 `_generate_panel`替换原 `panel = result.get(...)`：

```python
from app.constants import ATTRIBUTE_DIMENSIONS
from app.services import judge_service


def _parse_initial_panel(raw) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("初始面板格式不合法。")
    panel = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("初始面板条目不合法。")
        name = judge_service._normalize_attribute_name(str(item.get("name", "")))
        if name is None:
            continue
        if name in panel:
            raise ValueError("初始面板含重复维度。")
        value = judge_service._finite_float(item.get("value"), None)
        if value is None:
            raise ValueError("初始面板含非法数值。")
        panel[name] = {
            "name": name,
            "value": round(max(0.0, min(100.0, value)), 2),
            "reason": str(item.get("reason", "")),
        }
    panel["诚信"] = {
        "name": "诚信", "value": 50.0,
        "reason": "诚信按行为判定，首次建档从50起步。",
    }
    if any(name not in panel for name in ATTRIBUTE_DIMENSIONS):
        raise ValueError("初始面板缺少标准维度，请重新生成。")
    return [panel[name] for name in ATTRIBUTE_DIMENSIONS]
```

画像补充确认，在循环前将raw adjustments替换为规范化结果，并删除“未知名字新建50分属性”的分支：

```python
attrs = db.query(Attribute).filter(Attribute.user_id == user.id).all()
adjustments = judge_service._parse_changes(
    adjustments, {a.name for a in attrs if a.parent_id is not None}
)
disabled = judge_service._get_disabled_attributes(db, user.id)
adjustments = [a for a in adjustments if a["name"] not in disabled]
```

其循环中 `attr is None` 时跳过；继续以实际delta写流水。启动资金parser的异常捕获增加OverflowError。

- **影响范围：**llm/judge/onboarding/challenge service；目标金额另有独立边界约束。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否；非法模型结果变为可解释的拒绝/重试。
- **是否引入新依赖：**否，math为标准库。
- **验证方式：**NaN、Infinity、1e309、bool、字符串delta、非数组changes、非dict条目、重复别名、confidence缺失/2/-1均不会污染库；同一最终落点的两条＋5累计≤5；99＋5实记＋1；禁用后确认旧建议也不加点；初始快照与实际写入值相同。
- **预估改动量：**大，约150–220行，超过3个文件。

### P0-7【目标终态不能相互切换重复发分，规划力不能奖励两次】

- **维度：**功能。
- **位置：**[goal_service.py:66](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/goal_service.py:66)、[schemas:219](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/schemas/__init__.py:219)。
- **现象：**achieve只防同为achieved，fail只防同为failed；可achieve→fail→achieve。related_attribute若为规划力，达成时规划力加两次。reward/penalty没有有限值、符号、5分边界。
- **依据：**

```python
if goal.status == "achieved":
    return goal, []
_apply_delta(..., "规划力", goal.reward, ...)
if goal.related_attribute:
    _apply_delta(..., goal.related_attribute, goal.reward, ...)
```

- **影响：**同一目标可循环结算；用户创建reward100或未知属性会造成大额加点或新维度。
- **意图对齐：**符合目标一次结算、单属性≤5、固定13主维。重新开启终态目标若是产品需求，应单独定义逆向结算，不沿用现在的状态切换。
- **修复方案：**新增数据库条件状态转换helper：

```python
def _claim_goal(db: Session, goal: Goal, target: str) -> bool:
    affected = db.query(Goal).filter(
        Goal.id == goal.id,
        Goal.user_id == goal.user_id,
        Goal.status == "active",
    ).update({"status": target}, synchronize_session=False)
    db.refresh(goal)
    if affected == 1:
        return True
    if goal.status == target:
        return False
    raise ValueError("该目标已结束，不能再次结算或修改。")
```

各函数入口完整替换原状态判断：

```python
# achieve_goal：
if not _claim_goal(db, goal, "achieved"):
    return goal, []

# fail_goal：
if not _claim_goal(db, goal, "failed"):
    return goal, []

# cancel_goal：
if not _claim_goal(db, goal, "cancelled"):
    return goal

# update_goal：先取得active写锁，后修改字段。
_claim_goal(db, goal, "active")
```

关联奖励判断改为：

```python
if goal.related_attribute and goal.related_attribute != "规划力":
```

Schema字段改为：

```python
# GoalCreate
reward: float = Field(2.0, ge=0, le=5, allow_inf_nan=False)
penalty: float = Field(-1.0, ge=-5, le=0, allow_inf_nan=False)

# GoalUpdate
reward: float | None = Field(None, ge=0, le=5, allow_inf_nan=False)
penalty: float | None = Field(None, ge=-5, le=0, allow_inf_nan=False)
```

service `_apply_delta`也必须保护旧库对象，不能仅靠新请求Schema。在任何属性创建/修改前插入：

```python
import math
from app.constants import ATTRIBUTE_DIMENSIONS_SET

if name not in ATTRIBUTE_DIMENSIONS_SET:
    raise ValueError("目标关联属性必须是标准主维度。")
if isinstance(delta, bool):
    raise ValueError("目标点数不合法。")
try:
    delta = float(delta)
except (TypeError, ValueError, OverflowError) as exc:
    raise ValueError("目标点数不合法。") from exc
if not math.isfinite(delta) or abs(delta) > 5:
    raise ValueError("目标单次属性变化必须在-5到5之间。")
```

achieve还检查reward非负，fail检查penalty非正。创建/修改关联属性时，用 `ATTRIBUTE_DIMENSIONS_SET` 拒绝非空未知名字；不新增属性行来“修复”错误输入。

router使用下列包装函数，四处service调用都经过它：

```python
def _run_goal_action(db: Session, action, *args):
    try:
        return action(db, *args)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
```

例如：

```python
goal, applied = _run_goal_action(db, goal_service.achieve_goal, goal)
goal, applied = _run_goal_action(db, goal_service.fail_goal, goal)
goal = _run_goal_action(db, goal_service.cancel_goal, goal)
goal = _run_goal_action(db, goal_service.update_goal, goal, data)
```

- **影响范围：**goal service、schema、goal router。
- **是否改动数据模型：**否。
- **是否改动对外接口：**是，非法数值422、非法终态动作409。
- **是否引入新依赖：**否。
- **验证方式：**achieve→fail→achieve不能新增流水；并发achieve仅一次；关联规划力只加一次；unknown/NaN/Inf/100/反符号金额被拒；取消不改点数。
- **预估改动量：**大，约80–110行。

### P0-8【通用设置接口不得回显或改写BYOK及内部审计设置】

- **维度：**工程。
- **位置：**[settings router:18](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/settings.py:18)。
- **现象：**GET全部Setting.value，包含明文API Key；POST接受任意key并原样回显，能绕过专用BYOK校验，也能覆盖停滞冷却等内部记录。
- **依据：**

```python
result = {r.key: r.value for r in rows}
return {"key": body.key, "value": body.value}
```

- **影响：**正常打开设置页就可能在响应中收到Key明文；无需上云即可违反已定掩码红线。
- **意图对齐：**符合现有BYOK方向。当前不要求去掉数据库BYOK存储，也不引入认证。
- **修复方案：**通用接口限定为三个实际公开设置；内部key和模型配置只走专用服务。完整替换两函数：

```python
from app.constants import ATTRIBUTE_DIMENSIONS_SET

PUBLIC_SETTING_KEYS = frozenset({
    "gamification_modules", "hidden_attributes", "disabled_attributes",
})


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    rows = db.query(Setting).filter(
        Setting.user_id == user.id,
        Setting.key.in_(PUBLIC_SETTING_KEYS),
    ).all()
    result = {
        "gamification_modules": {m: False for m in GAMIFICATION_MODULES},
        "hidden_attributes": [],
        "disabled_attributes": [],
    }
    result.update({row.key: row.value for row in rows})
    return result


@router.post("/settings")
def upsert_setting(body: SettingIn, db: Session = Depends(get_db)):
    if body.key not in PUBLIC_SETTING_KEYS:
        raise HTTPException(status_code=400, detail="该设置只能由专用接口修改。")

    value = body.value
    if body.key == "gamification_modules":
        if (
            not isinstance(value, dict)
            or set(value) - set(GAMIFICATION_MODULES)
            or any(type(v) is not bool for v in value.values())
        ):
            raise HTTPException(status_code=400, detail="模块开关格式不合法。")
    else:
        if (
            not isinstance(value, list)
            or any(not isinstance(v, str) for v in value)
            or set(value) - ATTRIBUTE_DIMENSIONS_SET
        ):
            raise HTTPException(status_code=400, detail="属性开关格式不合法。")
        value = list(dict.fromkeys(value))

    user = get_or_create_default_user(db)
    row = db.query(Setting).filter(
        Setting.user_id == user.id, Setting.key == body.key,
    ).first()
    if row is None:
        row = Setting(user_id=user.id, key=body.key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    return {"key": body.key, "value": value}
```

- **影响范围：**settings router及设置页公开配置读取。
- **是否改动数据模型：**否。
- **是否改动对外接口：**是，GET不再包含内部配置；任意key写入400。
- **是否引入新依赖：**否。
- **验证方式：**放入含测试Key的primary/aux设置，GET settings不出现配置或Key；GET llm-config仍掩码；POST内部key被拒，记录不变；合法三个公开设置正常读写；JSON导出也没有Key。
- **预估改动量：**中，约50–75行。

### P0-9【挑战也要遵守科学判定和豁免；过期券仍应保护其有效时段内的补录事件】

- **维度：**功能。
- **位置：**[challenge_service.py:459](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/challenge_service.py:459)、[exemption_service.py:156](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/exemption_service.py:156)。
- **现象：**挑战完成调用单独prompt，缺锚点、子维度上下文、disabled与realistic校验。普通券按occurred_at判断，但expired被排除：先打开券列表使其过期，再补录昨日事件，就失去原时段保护。挑战退缩扣分也没有统一券hook。
- **依据：**

```python
build_completion_messages(
    challenge_title=..., challenge_description=...,
    challenge_attributes=..., note=..., today_events_context=...,
)
Exemption.status.in_(["active", "used"])
```

- **影响：**同一生活行为从普通记录和挑战入口得到不同科学约束；是否先读过券列表会改变历史事件的扣分。
- **意图对齐：**符合科学底线、当前券“负向一律归零”以及按事件发生时间命中。购券能否保护购券之前的行为暂不更改，留第7节确认。
- **修复方案：**保留一次LLM调用，扩展现有完成消息，不新增模型调用。在challenge service增加json导入及锚点导入，在messages建立后、chat_json前插入：

```python
import json
from app.services.anchor_service import format_anchors_text

disabled = judge_service._get_disabled_attributes(db, user.id)
messages[0]["content"] += """
额外硬约束：
1. 依据下方真实锚点判定，不得迎合用户或虚构科学依据。
2. 必须输出 realistic 布尔值、realistic_reason 字符串。
3. 不科学或明显不实的描述，realistic=false，不给正向结果。
4. confidence 必须为0到1；信息不足不能自行给高置信度。
5. 禁用主维度及其子维度不得给分。
6. 已拆分维度可以使用下方列出的合法子维度名。
"""
messages[1]["content"] += (
    "\n【科学锚点】\n" + format_anchors_text(db)
    + "\n【主维度现状】\n" + judge_service._attribute_context(db, user.id)
    + "\n【子维度上下文】\n" + judge_service._subdimension_context(db, user)
    + "\n【禁用维度】\n" + json.dumps(sorted(disabled), ensure_ascii=False)
)
```

模型返回后、任何判定commit之前：

```python
if result.get("realistic") is not True:
    db.rollback()
    raise ValueError(
        "挑战自述未通过真实性校验："
        + str(result.get("realistic_reason", "请补充可验证的真实细节。"))
    )

confidence = judge_service._parse_confidence(result.get("confidence"))
changes = judge_service._parse_changes(
    result.get("affected_attributes"),
    subdimension_service.child_name_set(db, user),
)
changes = _apply_outcome_changes(changes, outcome, challenge)
```

此处需要在challenge service的既有service导入中加入 `subdimension_service`。之后按标准主维及子维父级过滤disabled。

最终confirm仍重新应用券，以覆盖挑战完成、主动放弃和到期退缩。替换原 `changes = judgment.suggested_changes`：

```python
event = db.get(Event, judgment.event_id)
if event is None:
    raise ValueError("判定对应的事件不存在。")
changes, exemption_hit = _apply_exemption(
    db, user, event, judgment.suggested_changes or []
)
```

confirm审计payload同时保存原建议、实际变化与命中券：

```python
payload={
    "raw_changes": judgment.suggested_changes,
    "applied_changes": applied_changes,
    "exemption": exemption_hit,
}
```

如果入账函数先规范化再聚合，则在规范化后、聚合前应用上述hook，不能随后又从raw重新解析覆盖豁免结果。

历史券命中修复：

```python
# find_active 的状态条件改为：
Exemption.status.in_(["active", "used", "expired"])

# mark_used：
def mark_used(db: Session, row: Exemption) -> None:
    if row.status in ("active", "expired"):
        row.status = "used"
        row.used_at = datetime.now()
        db.flush()
```

仍由 `window_of(row)` 和事件occurred_at判断有效性；“expired”仅表示现在已过时段，不表示过去时段内失效。

- **影响范围：**challenge/judge/exemption service、挑战完成prompt上下文。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否；非法真实性结果返回400。
- **是否引入新依赖：**否。
- **验证方式：**捕获挑战messages确认含真实锚点/主子维/disabled；不科学自述不产生可入账结果；券有效时段内的事件，无论先读券列表与否、是否次日补录，都得到相同豁免；挑战retreated负点被券归零，正点和金币规则不变。
- **预估改动量：**大，约80–120行，多个文件。挑战补充自述与outcome同步修订仍需第7节明确交互。

## 4. P1 —— 值得做的优化

按投入与收益排序，覆盖体验、工程、功能、架构。

### P1-1【设置页挂载时真正加载已有模型配置】

- **维度：**体验。
- **位置：**[SettingsView.vue:259](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/frontend/src/components/SettingsView.vue:259)。
- **现象：**定义了loadLLMConfig，但首次挂载只调用load/loadBackups。
- **依据：**

```javascript
onMounted(() => {
  load()
  loadBackups()
})
```

- **影响：**已绑定模型仍显示未配置，enabled/base_url/model不回填，保存可能带入错误默认状态。
- **意图对齐：**符合已交付BYOK。
- **修复方案：**完整替换挂载块：

```javascript
onMounted(() => {
  load()
  loadBackups()
  loadLLMConfig()
})
```

- **影响范围：**SettingsView。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否。
- **是否引入新依赖：**否。
- **验证方式：**已有primary/aux配置时首次打开即显示configured、正确端点与开关；Key输入框仍为空，仅placeholder掩码。
- **预估改动量：**小，1行。
- **为什么值得做：**成本极低，修复每天可见的误导。
- **不做会怎样：**用户可能反复绑定Key或误关原有组。

### P1-2【损坏的日期折叠缓存不能让两个历史页面无法挂载】

- **维度：**工程。
- **位置：**[useDateGroups.js:17](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/frontend/src/composables/useDateGroups.js:17)。
- **现象：**初始化直接JSON.parse，读缓存没有try；写缓存反而有保护。
- **依据：**

```javascript
const expanded = ref(JSON.parse(localStorage.getItem(storageKey) || 'null') || { today: true })
```

- **影响：**一个损坏缓存就能让手账本或判定中心setup抛错。
- **意图对齐：**符合现有折叠状态持久化。
- **修复方案：**替换初始化：

```javascript
let initialExpanded = { today: true }
try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || 'null')
  if (saved && typeof saved === 'object' && !Array.isArray(saved)) {
    initialExpanded = saved
  }
} catch {
  initialExpanded = { today: true }
}
const expanded = ref(initialExpanded)
```

- **影响范围：**共享composable及两个消费者。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否。
- **是否引入新依赖：**否。
- **验证方式：**缓存为非法JSON、null、数组及合法对象时，页面均可挂载，合法折叠状态保持。
- **预估改动量：**小，约10行。
- **为什么值得做：**一次修复两个核心历史页面。
- **不做会怎样：**用户看到空白页，数据虽然还在，但无正常入口。

### P1-3【补课挑战押金也必须由奖励乘0.6派生】

- **维度：**功能。
- **位置：**[stagnation_service.py:224](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/stagnation_service.py:224)。
- **现象：**补课挑战直接取旧表的reward35/deposit20。
- **依据：**

```python
reward, deposit = challenge_service.coin_params("weekly", difficulty)
```

- **影响：**同一应用出现两种押金比例。
- **意图对齐：**符合新押金铁律；此小修不自行决定补课挑战是否也应调用AI定价。
- **修复方案：**

```python
reward, _ = challenge_service.coin_params("weekly", difficulty)
deposit = challenge_service.derive_deposit(reward)
```

- **影响范围：**stagnation service。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否。
- **是否引入新依赖：**否。
- **验证方式：**新生成奖励35的补课挑战押金为21；历史已接受挑战不重新定价。
- **预估改动量：**小，2行。
- **为什么值得做：**极低成本修正明确数值合同。
- **不做会怎样：**旧兜底表继续决定非标准押金。

### P1-4【是否建档应读onboarding_completed，不能用属性数量判断】

- **维度：**功能。
- **位置：**[App.vue:37](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/frontend/src/App.vue:37)。
- **现象：**启动已ensure_dimensions创建13个中性维度，App却以attributes.length＞0当已建档。
- **依据：**

```javascript
hasProfile.value = attrCount.value > 0
```

- **影响：**新库也被当成已有角色，首次引导提示失真。
- **意图对齐：**符合一次性问卷建档。
- **修复方案：**完整替换refreshProfile：

```javascript
async function refreshProfile() {
  try {
    const [data, status] = await Promise.all([
      api.getAttributes(),
      api.getOnboardingStatus(),
    ])
    attrCount.value = data.attributes?.length || 0
    hasProfile.value = !!status.completed
  } catch (e) {
    console.warn('获取角色状态失败', e)
  }
}
```

- **影响范围：**App；两个API helper已经存在。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否。
- **是否引入新依赖：**否。
- **验证方式：**有13个seed维度但completed=false时显示未建档；完成后显示已建档。
- **预估改动量：**小，约10行。
- **为什么值得做：**修正新用户进入产品时的基本状态。
- **不做会怎样：**中性占位面板继续伪装成AI建档结果。

### P1-5【成就墙触发自然追溯，并删除重复的追授路由】

- **维度：**架构。
- **位置：**[routers/achievements.py:24](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/achievements.py:24)、[routers/judgments.py:188](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/judgments.py:188)。
- **现象：**成就墙GET只展示；同一个追授POST存在两个不同处理器，响应和重复处理行为不同。
- **依据：**

```python
return achievement_service.wall(db, user)
# 两个文件均注册：
@router.post("/judgments/{judgment_id}/achievement")
```

- **影响：**旧达成项不自然点亮；路由顺序决定实际执行谁。
- **意图对齐：**遵从最新DECISIONS“自然追溯”，不采纳旧施工计划“不补发”的过时口径。
- **修复方案：**保留judgments router中现有canonical追授处理器；将achievements router完整收敛为：

```python
from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import achievement_service
from app.services.user_service import get_or_create_default_user

router = APIRouter()


@router.get("/achievements")
def list_achievements(db: Session = Depends(get_db)):
    user = get_or_create_default_user(db)
    try:
        achievement_service.check_and_grant(db, user)
    except IntegrityError:
        # 并发请求可能已先解锁；唯一约束保证没有重复发币。
        db.rollback()
    return achievement_service.wall(db, user)
```

这是有意使成就墙查询执行既定的惰性追溯，不新增调度器。若要求“打开应用首屏就发”，App挂载后还应调用现有 `api.getAchievements()`；单看墙才发的时机需你选择。

- **影响范围：**achievements router；如要求首屏触发，再涉及App。
- **是否改动数据模型：**否。
- **是否改动对外接口：**路径不变，去除重复注册；GET增加既定惰性授予副作用。
- **是否引入新依赖：**否。
- **验证方式：**23篇日记且没有成就的副本首次检查解锁7篇档，下一次不重发；余额增加等于新增成就流水；追授POST只注册一次，忽略不发币。
- **预估改动量：**中，删除重复实现并接入检查约20–50行有效变更。
- **为什么值得做：**修复已承诺却缺少触发点的功能，同时消除两个入口维护。
- **不做会怎样：**用户历史努力不被兑现；后续可能改到实际不执行的处理器。

### P1-6【今日盘点重试AI失败时复用已经保存的事件】

- **维度：**体验。
- **位置：**[TodayCheckin.vue:130](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/frontend/src/components/TodayCheckin.vue:130)。
- **现象：**createEvent成功、judgeEvent失败后保留草稿；再次提交又createEvent。
- **依据：**

```javascript
const event = await api.createEvent(...)
const res = await api.judgeEvent(event.id)
// catch仅保留草稿，没有保存event.id
```

- **影响：**模型失败重试制造重复生活记录，影响计数、频率和未来判定上下文。
- **意图对齐：**符合一条真实记录对应一条事件，保持“两阶段录入＋判定”。
- **修复方案：**完整替换submitOne。记录已保存内容与eventId，只重试同一内容；busy入口防重复：

```javascript
async function submitOne(it) {
  const previous = rowState.value[it.id] || {}
  if (previous.busy) return false

  const text = (drafts.value[it.id] || '').trim()
  if (!text) {
    setRow(it.id, { err: '请先写一句话' })
    return false
  }

  setRow(it.id, { busy: true, err: '', ok: false })
  try {
    let eventId = previous.savedText === text ? previous.eventId : null
    if (!eventId) {
      const event = await api.createEvent({
        item_id: it.id, source: 'form', content: text,
        params: {}, is_pure: false,
      })
      eventId = event.id
      setRow(it.id, { eventId, savedText: text })
    }

    const res = await api.judgeEvent(eventId)
    const okMsg = res.needs_clarify
      ? '已记录，AI 有疑问（去判定中心补充）'
      : '已记录并判定'
    setRow(it.id, {
      busy: false, ok: true, err: '', eventId: null, savedText: '',
    })
    drafts.value = { ...drafts.value, [it.id]: '' }
    await load()
    flash(`「${it.name}」${okMsg}`)
    return true
  } catch (e) {
    setRow(it.id, {
      busy: false, err: `记录可能已保存，可重试判定：${e.message}`, ok: false,
    })
    toast.error(`「${it.name}」${e.message}`)
    return false
  }
}
```

该方案只解决同一页面内重试。跨刷新待判记录入口属于第5节构想。EventForm同样需要保存create成功的eventId，且不能在判定成功前直接清除草稿；不能把它的create成功当成整条处理完成。

- **影响范围：**TodayCheckin；若一并处理自由记录，则扩展EventForm两条提交函数。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否。
- **是否引入新依赖：**否。
- **验证方式：**create成功后让judge失败，重试时create调用次数仍为1；双击仅一条；成功后行统计更新；用户改文字时创建新事件且旧记录仍可见。
- **预估改动量：**中，今日盘点约40–60行；加自由记录则大。
- **为什么值得做：**LLM失败是已存在的正常分支，重试不应变成重复记录。
- **不做会怎样：**用户越重试，日记越重复。

### P1-7【停滞扣分与冷却记录同事务，并计入子维度活动】

- **维度：**架构。
- **位置：**[stagnation_service.py:56](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/stagnation_service.py:56)、[stagnation_service.py:180](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/stagnation_service.py:180)。
- **现象：**扣分先commit，冷却最后另commit；只查主属性id，忽略其子维度活动；answer未知名字会创建50分属性。
- **依据：**

```python
db.commit()                  # 先提交扣分
challenge = _build_restart_challenge(...)
checks[name] = now.isoformat()
_set_checks(...)              # 再提交冷却
```

- **影响：**冷却写入失败时重试可能重复扣0.3；满级用户持续练子维仍被问“停滞”；直接请求可创建未知维度。
- **意图对齐：**保留“只问不自动扣、用户确认才扣”、settings审计位置，不引入日历衰减。
- **修复方案：**answer进入后先锁现有UserProfile行，再检查合法主维；不建未知属性：

```python
db.query(UserProfile).filter(
    UserProfile.user_id == user.id
).update({UserProfile.id: UserProfile.id}, synchronize_session=False)

attr = db.query(Attribute).filter(
    Attribute.user_id == user.id,
    Attribute.name == name,
    Attribute.parent_id.is_(None),
).populate_existing().first()
if attr is None or name in _disabled_attributes(db, user.id):
    raise ValueError("该主维度不存在或已关闭判定。")
```

将 `_set_checks()`和 `_build_restart_challenge()`中的commit改为flush；answer第180行commit也改flush。补课挑战创建用savepoint保护，避免可选创建失败破坏已准备的扣分/冷却事务：

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

替换 `_last_activity()`，加入SQLAlchemy的or_导入：

```python
from sqlalchemy import or_


def _last_activity(db: Session, user_id: int, attribute_id: int):
    ids = db.query(Attribute.id).filter(
        Attribute.user_id == user_id,
        or_(
            Attribute.id == attribute_id,
            Attribute.parent_id == attribute_id,
        ),
    )
    row = db.query(AttributeHistory.created_at).filter(
        AttributeHistory.user_id == user_id,
        AttributeHistory.attribute_id.in_(ids),
    ).order_by(AttributeHistory.created_at.desc()).first()
    return row[0] if row else None
```

- **影响范围：**stagnation service。
- **是否改动数据模型：**否。
- **是否改动对外接口：**路径不变，未知/禁用维度400。
- **是否引入新依赖：**否。
- **验证方式：**冷却写失败时扣分也回滚；并发/重复回答只扣一次；拒绝未知名称且attributes仍13；最近有子维度流水时主维不被视为无活动；回答“做了没记”不产生扣分。
- **预估改动量：**中，约40–70行。
- **为什么值得做：**一个服务内就能修复确认语义、重试和新层级的衔接。
- **不做会怎样：**用户会被误问，失败重试存在重复扣分风险。

### P1-8【备份应覆盖实际数据库路径，迁移前留副本，并保护失败清理】

- **维度：**工程。
- **位置：**[backup_service.py:17](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/backup_service.py:17)、[main.py:66](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/main.py:66)。
- **现象：**备份使用db_file而非实际engine URL；目录创建在try外；秒级文件名可能重名；启动备份发生在迁移之后。
- **依据：**

```python
db_path = Path(BASE_DIR / settings.db_file)
BACKUP_DIR.mkdir(exist_ok=True)  # try外
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
# main先create_all/migrate，再backup
```

- **影响：**覆盖database_url后可能备错库；失败仍可能影响启动；同秒备份覆盖；没有迁移前原始副本。
- **意图对齐：**符合真实数据保护；不增加每日调度，后者属于M4。
- **修复方案：**完整替换backup_now，保留现有_cleanup：

```python
from contextlib import closing
from uuid import uuid4
from app.database import engine


def backup_now() -> Path | None:
    if engine.url.get_backend_name() != "sqlite":
        return None
    database = engine.url.database
    if not database or database == ":memory:":
        return None

    dest = None
    try:
        db_path = Path(database).resolve()
        if not db_path.exists():
            return None
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest = BACKUP_DIR / f"game_of_life_{stamp}_{uuid4().hex[:8]}.db"
        with closing(sqlite3.connect(str(db_path))) as src:
            with closing(sqlite3.connect(str(dest))) as dst:
                src.backup(dst)
    except Exception:
        if dest is not None:
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
        return None

    try:
        _cleanup()
    except OSError:
        pass
    return dest
```

将main现有的backup调用移到create_all/migrate之前。新库不存在时无旧数据可备份，创建后仍可手动备份；已有库备的是迁移前副本。

- **影响范围：**backup service、main启动顺序。
- **是否改动数据模型：**否。
- **是否改动对外接口：**否。
- **是否引入新依赖：**否。
- **验证方式：**指向另一SQLite文件时备份该文件；同秒两次得到不同文件；mkdir/连接/清理失败不泄漏异常；旧schema升级前副本保留旧列结构且完整可读。
- **预估改动量：**中，约35–55行。
- **为什么值得做：**提高真实数据恢复能力，而非依赖“迁移绝不会出错”。
- **不做会怎样：**备份路径与运行库可能脱节，事故后缺少迁移前状态。

### P1-9【JSON导出补齐基线、审计和v1.10经济数据，继续排除Key】

- **维度：**功能。
- **位置：**[export.py:40](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/export.py:40)、[SettingsView.vue:384](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/frontend/src/components/SettingsView.vue:384)。
- **现象：**界面写“全部数据”，实现只有旧六类；attributes没有id，历史却只给attribute_id。
- **依据：**

```python
"attributes": [{"name": a.name, "value": a.current_value, ...}],
"attribute_history": [{"attribute_id": h.attribute_id, ...}],
```

- **影响：**导出无法完整关联历史，也无法重算基线和余额；不包含新功能资产。
- **意图对齐：**符合个人数据可带走；不导出BYOK，不增加自动导入/重建数据库功能。
- **修复方案：**保留旧导出字段兼容下载，原 `_collect`重命名 `_collect_legacy`，新增完整表区。以下代码完整：

```python
from datetime import date
from app import models


def _encode_export(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _encode_export(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode_export(v) for v in value]
    return value


def _export_row(row):
    return {
        column.name: _encode_export(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _collect(db: Session, user_id: int) -> dict:
    result = _collect_legacy(db, user_id)
    table_models = (
        models.UserProfile, models.Attribute, models.AttributeHistory,
        models.CheckinItem, models.Event, models.AIJudgment,
        models.JudgmentLog, models.Goal, models.CoinLedger,
        models.Challenge, models.ShopItem, models.Redemption,
        models.Achievement, models.Exemption,
    )
    tables = {}
    for model in table_models:
        rows = db.query(model).filter(model.user_id == user_id).order_by(model.id).all()
        tables[model.__tablename__] = [_export_row(row) for row in rows]

    user = db.get(models.User, user_id)
    tables["users"] = [_export_row(user)] if user else []
    tables["anchors"] = [
        _export_row(row) for row in db.query(models.Anchor).order_by(models.Anchor.id).all()
    ]
    safe_settings = (
        "gamification_modules", "hidden_attributes", "disabled_attributes",
        "stagnation_checks", "unreal_count",
    )
    tables["settings"] = [
        _export_row(row)
        for row in db.query(models.Setting).filter(
            models.Setting.user_id == user_id,
            models.Setting.key.in_(safe_settings),
        ).order_by(models.Setting.id).all()
    ]
    result["format_version"] = 2
    result["tables"] = tables
    return result
```

完整表区保留逻辑删除记录；业务列表隐藏条件不能误用于这一区。嵌套快照直接保留原结构，不把attributes误转成平铺基线。

- **影响范围：**export router、导出说明。
- **是否改动数据模型：**否。
- **是否改动对外接口：**是，JSON增加format_version和tables，旧字段保留。
- **是否引入新依赖：**否。
- **验证方式：**用导出重算40币余额与各维基线＋流水；通过id关联历史；17表区完整；全文搜索测试Key不存在；CSV事件导出仍可用。
- **预估改动量：**中，约50–75行。
- **为什么值得做：**使“全部数据”成为可验证的交付，而非只有展示记录。
- **不做会怎样：**用户拿到的JSON缺少恢复或核账所需上下文。

## 5. 功能构想——可选，明确非必须

本节不是待办，也不属于本轮必须实施。

| 构想 | 要解决的问题 | 为什么现在缺 | 大致做法 | 工作量 |
|---|---|---|---|---|
| 待判记录入口 | 模型失败后记录已保存，但用户不知道如何继续 | 创建事件与判定分两步，多个输入页各自维护临时状态 | 在今日盘点展示“已保存、待判定”，按已有event id补判；不重新创建事件 | 中到大，约80–150行 |
| 只读账目体检 | 用户需要知道数据是否一致，不靠人工审查 | 当前没有核账接口；导出也缺完整基线 | 按嵌套快照、真实delta、金币流水给出只读检查结果；只报差异，不自动修账 | 中，约60–100行 |
| 奖励兑现备注 | 兑换成功不等于现实奖励已落实 | redemption目前只有状态和兑现时间 | 兑现时允许记一句实际奖励体验；不兑换属性点、不引入徽章商品 | 小到中 |

B1/C1/D3不在这里建议开工，仍保持暂缓。

## 6. 建议不要做的事

- **不要清洗或“修正”当前数据库。**本次恒等式和引用检查正常，没有证据需要回填真实账目。历史启动资金40币不能因新规则80–200就被自动补齐。
- **不要通过删库、重建表、删列解决迁移。**保留create_all＋migrate_schema补列路线；新增约束前先检查历史数据。
- **不要把删除改成“删旧判定再建新判定”。**这会破坏id和审计，正是已有决策禁止的方式。
- **不要把COIN_TABLE重新升为正常定价权威，也不要加经济奖励上限。**本轮只修解析与金额一致性。
- **不要用全局商品id唯一流水阻止重复兑换。**同一现实奖励可以购买多次；网络重试幂等需要独立请求标识，不能把合法第二次购买一起封死。
- **不要把所有行为副作用绑成一个巨大事务。**基础积分、基础币、押金与挑战终态同事务；累计成就作为后续可重试检查即可。
- **不要展开注册、登录、JWT、多用户权限、排行榜、日历衰减、分组免扣、徽章商店、每档独立挑战卡、标题前缀识别。**
- **不要重报已修的calendar简写与五处parent过滤为P0。**代码已经覆盖；浏览器实测可以验证渲染，不能把已看到的修复忽略掉。
- **不要现在给四个旧游戏化开关扩建一套业务开关系统。**其当前文案“开启后对应入口才出现”缺少实现。建议先将这组开关标为“尚未接入已交付模块”并禁用操作，避免用户误以为控制已生效；删除还是接线应人工定夺。
- **建议砍掉真实环境的reset-all和已建档重建按钮。**它们的测试便利远小于数据损失代价。
- **不要直接拿旧sql/schema.sql初始化真实SQLite。**它是过时的迁移参考，当前事实以ORM和实际库为准。

### 超出当前阶段：M4上云自用的必要门槛

以下是上云前必须补齐的现有缺口，**不混入本轮P0/P1，也不建议现在开展多用户认证**。

| 门槛 | 当前证据 | 上云自用前的具体处理 |
|---|---|---|
| 访问密码 | [main.py:47](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/main.py:47)注册业务API，无访问校验 | 给静态页及全部业务/导出/备份接口加单一访问密码保护；不开放注册 |
| 同源生产部署 | [main.py](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/main.py)无前端静态挂载 | 构建Vue并由后端提供；SPA回退不得吞掉`/api`错误 |
| CORS | [main.py:40](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/main.py:40)为`["*"]` | 同源部署移除不必要跨域，或仅列明确域名；CORS不能替代访问密码 |
| Key环境变量 | [settings router:83](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/routers/settings.py:83)仍允许写数据库BYOK | 云端自用改为环境变量主导；停用云端Key编辑，并单独安排旧Key迁出，不盲删用户settings |
| HTTPS | 项目没有生产TLS配置 | 在实际部署入口配置HTTPS，密码、日记和Key不经明文HTTP |
| 每日备份与恢复 | [backup_service.py](C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg/app/services/backup_service.py)只有启动/手动备份 | 每日调度、备份失败通知、至少一次恢复验证；备份不能挂到公开静态目录 |
| 私密文件暴露 | 单库包含日记、画像、明文BYOK | 发布目录只提供构建资源；`.env`、数据库、backups、导出中间文件不得通过静态路径访问 |

## 7. 需要你确认的

以下无需现在逐条回答；它们是你挑选阶段B工作时需要定口径的项目。

1. **已确认事件能否补充、反驳和编辑？**最小稳定方案是已入账后冻结正文和判定。若允许修订，必须定义“反向旧实际流水→同id重新判定→重新确认”的流程，以及金币是否调整。
2. **满级主维是否还能下降？**新施工计划写主维100后冻结，当前日常判定会把满级主维的负向变化也转给最低子维；这与本次“13维一律可涨可跌”存在冲突。不能默默选一边。
3. **挑战低置信度是否锁住整笔结算？**本报告推荐400、保留accepted/pending，不先发奖励。若希望只退押金但暂不记属性，需要明确新的部分结算状态，不能吞异常后假装完整结算。
4. **挑战如何补充自述？**目前complete拒绝已有judgment，普通supplement又不会同步challenge.outcome。需要决定允许在挑战页原id重判，还是限定普通判定中心只能查看挑战，不能单独修订。
5. **购券能否追溯到购买之前、同一有效时段内的行为？**目前没有`created_at≤occurred_at`限制。补录和“出事后买券”需要区分。
6. **HH:MM结束时间怎样解释？**全天目前结束23:59:00，23:59:30不命中；相邻时段又都包含12:00。建议统一半开区间，但这是产品口径，未在P0里擅改。
7. **删除事件后金币是否撤销？**现状只回滚属性，日常奖励、成就奖励和挑战经济状态不会全部撤销。不能为了追求表面一致而偷偷改金币规则。
8. **历史撤销遇到后续封顶/触底怎么办？**反向实际流水再夹取能保持账目恒等式，但不保证恢复到“从来没有该事件”的反事实值。若需要后者，要按时间重放并处理后续判定，代价明显更大。
9. **成就追溯时机和连续日记口径。**是打开应用就检查，还是打开成就墙检查？连续天数目前取最近连续段，不是历史最长段；“曾经达成7天”与“当前连续7天”不同。
10. **补课挑战是否也是AI主导定价？**当前固定模板直接走兜底表；押金比例可先按明确规则修正，定价是否属于例外需要记录。
11. **两个项目管理入口与四个未接线开关。**最新记录明确保留双入口，施工计划原先要求移出设置；不要由执行者自行删掉。开关应保留占位、接线还是移除，也应先定。
12. **经济无上限的存储边界。**不能另设游戏经济上限；但SQLite整数仍有存储能力边界。若AI给出超出可存储范围的金额，应定义明确解析失败，而非任意截断成某个奖励上限。

## 8. 给下一棒的建议顺序

如果只能做三条，我建议选 **P0-1、P0-2、P0-5**：先封住会直接清空真实数据或覆盖基线的重置入口；再让属性、金币、押金与挑战终态成为可回滚的一次结算；最后修复删除事件会抹掉审计和错误反向扣分的问题。这三条优先保护不可轻易恢复的数据与结算证据。当前真实库核账正常，下一棒应在内存库或副本验证这些触发条件，不能用真实生活记录造故障数据，也不要先做历史清洗。

**阶段 A 到此结束。没有进入阶段 B，等待你指定要实施的条目。**