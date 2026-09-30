# 项目代码详解 —— my-life-rpg 全代码教学

> **目标**：读完能 ①完全理解本项目全部代码 ②读懂他人写的类似代码 ③修改与复用。
> **读者假设**：会 Python 语法/HTTP 基础/SQL 增删改查/HTML-JS 基础；框架级概念（ORM、依赖注入、Vue 响应式等）用**概念卡**补齐。
> **代码基线**：**v1.6 已完成 + v1.7 计划中（2026-09-22，commit `379fd90`）**。所有引用的文件/函数/行为均与仓库当前代码一一对应。
> **本次更新范围（v1.3 → v1.6）**：新增 BYOK 双模型组、追问逐面/来源区分/置信度原因、重判链路统一（就地更新）、输出前维度硬校验、`chat_json` 重试、增量修订契约（`revision_notes`）、前端 composable 抽离（日期分组）与保留式反馈；**新增第 11 章「故障档案」（14 条 fix 提交的根因+实现全档）**。
> **更新约定**：用户说"更新学习文档"时，按本次要求更新（新功能→补对应小节；重构→改对应讲解）。
> **⚠️ 长期维护约定（2026-09-22 追加）**：**此后每次修复 bug 或排查异常，都要在第 11 章「故障档案」按五栏格式（现象→定位过程→根因→修复实现→防复发）建档**，并在索引表登记一行。这不是可选项——本章的价值完全依赖"当时就记"，事后补写会丢失定位过程与证据细节。

---

## 第 0 章 阅读前的 6 张概念卡

**卡1 · ORM 与 SQLAlchemy**：不用手写 SQL，把"表"映射成 Python 类、一行数据映射成一个对象。`Attribute` 类 ↔ `attributes` 表；`db.query(Attribute).filter(...)` ≈ `SELECT * FROM attributes WHERE ...`。改对象属性后 `db.commit()` 即写库。
**卡2 · 依赖注入（FastAPI `Depends`）**：路由函数参数写 `db: Session = Depends(get_db)`——每次请求时 FastAPI 自动调用 `get_db()` 造一个数据库会话塞进来，请求结束自动关闭。你不用手动管理连接生命周期。
**卡3 · Pydantic 校验**：`schemas/__init__.py` 里的 `EventCreate` 等类是"请求体说明书"——客户端 POST 的 JSON 自动按它校验/转类型，不合法直接 422，业务代码拿到的永远是干净数据。
**卡4 · Vue 响应式**：`ref(值)` 创建响应式数据，值变→页面自动更新；`computed(() => ...)` 是"依赖变化才重算的派生值"；`watch([a,b], fn)` 监听变化执行副作用（如存缓存）；`v-if`/`v-for`/`v-model` 分别是条件渲染/循环/双向绑定。
**卡5 · LLM API 调用模式**：OpenAI 兼容 SDK 的固定姿势——发一个 messages 数组（`system` 设定角色规则、`user` 给数据），返回 `resp.choices[0].message.content`。`temperature` 控制随机性（判定用 0.3 保证口径稳定）。
**卡6 · JSON 列**：SQLite 的 JSON 类型列存的是"JSON 字符串"，SQLAlchemy 自动帮你序列化/反序列化——Python 里当 dict/list 用。**坑**：用原生 sqlite3 直接读该列拿到的是字符串，需 `json.loads`（本项目诊断时踩过）。

---

## 第 1 章 全局架构

### 1.1 分层图（一条请求的旅程）

```
浏览器 (Vue3, :5173)
   │ fetch('/api/...')
   ▼
FastAPI 路由层  app/routers/*.py      ← 只做：参数校验、HTTP 语义、调服务、组装响应
   ▼
服务层        app/services/*.py      ← 只做：业务逻辑（判定/结算/记忆/锚点）
   ▼                                ↘ app/prompts/*.py（拼 LLM 消息）
模型层        app/models/__init__.py  ← ORM 表定义
   ▼
SQLite        game_of_life.db
```

**判断代码放哪层的口诀**：换 UI 要重写吗？不用 → 服务层。换数据库要重写吗？不用 → 路由层也不该碰 SQL 细节。跟大模型说话有关 → prompts + llm_service。

### 1.2 目录结构逐项说明

```
app/
├── config.py          全局配置（.env 读取，密钥/模型名/数据库路径）
├── constants.py       13 属性维度 + 中英文别名映射表
├── database.py        engine/SessionLocal/Base/get_db/轻量迁移 migrate_schema
├── main.py            FastAPI 实例 + 路由注册 + startup 初始化链 + /api/health
├── models/__init__.py 10 张表
├── schemas/__init__.py Pydantic 请求/响应模型
├── prompts/           6 个 LLM 提示词模板（judge/dispute/extract/memory/report/onboarding）
├── routers/           9 个路由模块（onboarding/events/judgments/attributes/goals/anchors/settings/export/report）
└── services/          9 个服务（judge/llm/**llm_config**/anchor/memory/onboarding/user/goal/backup）
frontend/src/
├── main.js            入口：创建 Vue 应用挂到 #app
├── api.js             全部后端接口的统一封装（唯一 fetch 出口）
├── App.vue            布局壳：健康检查横幅 + 9 个 tab 切换
├── composables/       **useDateGroups.js**（v1.6 抽出的日期分组逻辑，两处列表复用）
└── components/        9 个页面组件（与 tab 一一对应）
```

> **注意本节的两处变化（v1.3 → v1.6）**：① `services/` 从 8 个变 9 个，新增 `llm_config.py`（BYOK 配置解析层，见第 4 章）；② `frontend/src/` 下**新增 `composables/` 目录**——这是 Vue3 工程化的第一个信号：当两处以上的组件需要同一段**逻辑**（而非同一个外观）时，就抽 composable，见 8.4。

### 1.3 启动链（main.py 的 startup，全部幂等）

`uvicorn app.main:app` 后依次发生：
1. `Base.metadata.create_all` 建缺失的表（已存在则跳过）
2. `migrate_schema(engine)` 给已有表补模型新增的列（SQLite 的 `ALTER TABLE ADD COLUMN` + NULL 回填默认值）——解决"旧库文件没有新列导致 INSERT 报错"
3. `seed_anchors` 内置锚点幂等写入（按 name 去重）
4. `get_or_create_default_user` + `ensure_dimensions`（缺的维度以中性值 50 补建——维度从 6 扩到 13 时老用户无痛升级）
5. `backup_now()` 启动即自动备份
> **设计思想**：五步全部幂等（重复执行结果不变），所以崩溃重启、重复启动都安全。这是"自动化初始化"的通用范式。

---

## 第 2 章 数据模型层（models/__init__.py，10 张表）

```
users ──1:1── user_profiles
  └──1:N── attributes ──1:N── attribute_history
  └──1:N── events ──1:N── ai_judgments ──1:N── judgment_logs
  └──1:N── goals
anchors（全局共享）  settings（user_id+key 唯一）
```

| 表 | 职责 | 关键字段与设计意图 |
|----|------|--------------------|
| users | 用户（V1 只有 default） | M4 多用户的锚点 |
| user_profiles | 画像+引导会话态+游戏化 | `onboarding_state` JSON 持久化问卷进度（重启不丢）；`initial_attributes_snapshot` 初始面板快照；`long_term_memory` 五类记忆 JSON；`level/exp` 游戏化预留 |
| attributes | 属性当前值 | `UniqueConstraint(user_id,name)` 防重复；`current_value Float` 支持 -0.5 小数 |
| attribute_history | **append-only 点数流水** | 每次 delta 记 `value_after`（变动后值）+ reason/evidence——出错可对账、可回滚、可画趋势线 |
| events | 生活事件 | `source` form/journal 双通道；`params` JSON 结构化参数；`content` 日记原文；`is_pure` 纯享记录（不判定）。**`item_id` 为 v1.7 计划字段**（关联打卡项目清单，尚未实现） |
| ai_judgments | 判定记录 | `suggested_changes`/`final_changes` 双字段——建议值 vs 置信度加权后实际入账值；`status` pending/confirmed/adjusted/rejected 状态机；**`analysis`**（v1.1，分析过程推理链）；**`confidence_reason`**（v1.4，低置信度必填理由）；**`revision_notes`**（v1.6，重判增量修订说明） |
| judgment_logs | 判定审计 | action: create/confirm/supplement/dispute/rejudge/maintain/delete/invalidate，全程可回溯。**v1.5 起重判不再删旧日志**（只增不删） |
| goals | 目标 | `audit` JSON 记修改/取消/达成/失败流水 |
| anchors | 量化锚点库 | `calibrated_value` 用户校准值（NULL=用默认 base_value）——"科学但用户可调" |
| settings | KV 配置 | `hidden_attributes`/`disabled_attributes`（维度开关）、`gamification_modules`（模块开关）、`unreal_count`（不实计数）、**`llm_primary`/`llm_aux`**（v1.4 BYOK 双模型组）全塞这张表，避免加列 |

> **三个可迁移的设计习惯**：①所有业务表带 `user_id` 外键（单用户也无妨，多用户零返工）；②"当前值表 + 流水表"分离（账户余额思维）；③**新配置一律进 KV 表而不是加列**——`llm_primary`/`llm_aux` 就是这么加进来的，零迁移成本（详见第 4 章 BYOK）。

---

## 第 3 章 基础设施三件套

### 3.1 config.py —— pydantic-settings
`Settings(BaseSettings)` 类字段名自动对应环境变量（`deepseek_api_key` ↔ `DEEPSEEK_API_KEY`），从 `.env` 读。两个 property：`database_url`（显式 db_url 优先，否则拼 SQLite 路径——上云只改环境变量）、`llm_ready`（key 以 sk- 开头才算配置）。**可插拔**的落点就在这：换模型只改 .env 的 model/base_url，业务代码零改动。

### 3.2 database.py
```python
engine = create_engine(url, connect_args={"check_same_thread": False})  # SQLite 支持多线程
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
def get_db():           # 卡2 的依赖注入
    db = SessionLocal()
    try: yield db
    finally: db.close()
```
`migrate_schema` 的原理：用 `inspect(engine)` 拿已有表的列名集合，与 `Base.metadata.sorted_tables` 的模型列对比，缺的 `ALTER TABLE ADD COLUMN`（一律可空，绕开 SQLite 不能加 NOT NULL 列的限制），再把有 Python 默认值的 NULL 行回填。

### 3.3 CORS（main.py）
本地开发前端 5173 调后端 8000 属跨域，`CORSMiddleware(allow_origins=["*"])` 放行；注释里写明上云收紧——**技术债显式标注**是好习惯。

---

## 第 4 章 LLM 服务层（llm_service.py + llm_config.py，全项目唯一碰 openai SDK 的地方）

### 4.1 llm_service.py —— 调用与容错

```python
class LLMService:
    def _get_client(self, config):   # 惰性创建 + 按 (api_key, base_url) 缓存
    def chat(self, messages, temperature, json_mode):   # 单次对话→文本
        kwargs["response_format"] = {"type": "json_object"}  # json_mode 时强制 JSON 输出
    def chat_json(self, messages):  # chat + _parse_json + 失败自动重试 1 次（v1.5 A5）
```

**`_parse_json` 三级容错**（面试级设计点）：
1. 去 markdown 围栏 `​```json ... ```​` 后直接 `json.loads`
2. 失败 → 正则提取首个 `{...}` 平衡块再解析（模型爱加说明文字）
3. 仍失败 → `_repair_curly_quotes`：模型偶尔用中文全角引号 `“”` 当 JSON 定界符。**位置感知修复**：看全角引号的前一个非空白字符——是 `{ [ , :` 就说明这个开引号在结构位，还原成半角 `"`；闭引号同理看后一个字符；字符串内部的引用则替换成 `「」` 不破坏内容；最后把结构位的全角逗号 `，` 转半角。
4. 全失败才抛 `LLMError`（路由层转 503）。

**`chat_json` 的自动重试（v1.5 A5 新增，`470b714`）**：
```
chat_json → 拿到空返回 或 _parse_json 抛错
         → 等 ~1s（指数退避）→ 重试 1 次
         → 仍失败 → 抛 LLMError
```
**为什么只重试 1 次**：重试是为了吃掉**瞬时抖动**（网络、模型偶发空响应），不是为了掩盖**系统性错误**——如果两次都失败，说明 prompt 或模型本身有问题，继续重试只是浪费钱和时间。**只在"空返回/解析失败"时重试**，业务性失败（如模型明确返回 `realistic: false`）绝不重试。

> **可迁移**：任何"LLM 返回结构化数据"的场景都值得抄这套容错链（三级解析 + 一次重试）。业务层永远 `from app.services.llm_service import llm_service` 单例调用，不直接碰 SDK。

### 4.2 llm_config.py —— BYOK 双模型组（v1.4 新增，116 行）

这是 v1.4 最重要的架构升级。用户要求"自己配 API Key"，实现上不是加个输入框，而是抽象出**"用途 → 配置组"的解析层**。

**核心概念：模型槽位（slot）与用途（purpose）**

```python
SETTING_KEY_PRIMARY = "llm_primary"   # 主模型槽位（settings 表 KV）
SETTING_KEY_AUX     = "llm_aux"       # 辅助模型槽位
PURPOSE_JUDGE       = "judge"         # 判定用途（要质量）
PURPOSE_AUX         = "aux"           # 辅助用途（可省钱：记忆压缩/周报等）

@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    quality_note: str = ""   # 降级标注，一路传到前端
```

**解析优先级（`resolve_llm_config(db, user_id, purpose)`）**：

| 用途 | 优先级链 | 回退到辅助模型时 |
|------|---------|-----------------|
| `aux`（辅助） | `aux` → `primary` → `.env` | 静默回退（辅助任务质量要求低） |
| `judge`（判定） | `primary` → `aux` → `.env` | **显式标注**：`quality_note = "判定质量一般（使用辅助模型）"` |

全链缺失才抛 `LLMError`。

**读-显-存三态设计（密钥安全的关键）**：
- **读**：`read_group(db, user_id, setting_key)` → 缺失/未启用/字段不全一律返回 `None`（防御式解析）
- **显**：`mask_key(api_key)` → `sk-****末4位`。**接口永远不回显密钥全文**
- **存**：前端提交 `api_key="__KEEP__"` 哨兵值表示"沿用旧值"（用户只改了模型名没改 key 时），后端识别后跳过 key 更新；`settings.py` 另做 `model_changed` 检测用于提示上下文不兼容

> **可迁移（两条硬经验）**：①**凡是"用户自带凭据"的功能，都要单独设计读-显-存三态**——明文回显是安全红线，哨兵值是不覆盖的通用手法；②**降级必须可感知**——判定回退到辅助模型时 `quality_note` 会一路传到前端展示，静默降级是对信任的透支。

### 4.3 客户端缓存策略（v1.4 改）

`_get_client(config)` 从"全局单例"改为**按 `(api_key, base_url)` 元组缓存**——因为 BYOK 之后不同用户/不同用途可能用不同的 key 和端点，单一 client 不再够用。不传 config 时走 `.env`（兼容旧路径）。

---

## 第 5 章 Prompt 层（app/prompts/，一功能一文件）

| 文件 | 用途 | 核心结构 |
|------|------|----------|
| judge.py | 事件判定（产品灵魂） | **16 节** system prompt（见下） |
| dispute.py | 反驳复核 | "客观复核员"：有据才调整，无据维持原判，绝不迎合；输出 conclusion=maintain/adjust。**v1.6 起同样受增量修订契约约束** |
| extract.py | 日记要素提取 | 从自然语言提 event_type/category/title/params，"只提取明确提到的，不臆造" |
| memory.py | 长期记忆压缩 | 五类摘要（目标/经历/性格/偏好/状态），增量合并不丢旧记忆 |
| report.py | 周报/月报 | 亮点/关注/建议/tone；关闭维度"温和关心不批评" |
| onboarding.py | 问卷出题+面板生成+补充评估 | AI 自评把握度 confidence，≥95 自动生成面板 |

**judge.py 的 16 节为什么这么排**（每节都在堵一个真实发生过的坑）：
1. 角色定位（成长引导者 + 科学客观底线，"引导 ≠ 迎合"）→ 2. 只判 13 维（防发散）→ 3. 任务三步 → 4. 上下文记忆使用规则（背景只参考不越权）→ 5. 事件去重（同天同件事才去重；不确定倾向正常判——防误伤）→ 6. 语义理解（"吃瘦肉很知足"归感恩不是营养）→ 7. 负面情绪减分规则（紧张→心理韧性）→ 8. **多属性联动 + 生活面覆盖自检**（判定前列作息/饮食/运动/学习/社交/情绪清单，漏面必须复核）→ 9. 锚点库注入 `{anchors}` → 10. 判定规则（delta∈[-5,5]、goal 规则、如实记录加诚信）→ 11. 累积效应（坚持上浮/频繁加重）→ 12. 真实性甄别（realistic 字段）→ 13. 客观性硬约束 → 14. **追问引导**（journal 默认追问、form 不追问、按生活面逐面追问、信息不足禁止降 confidence 直接判定）→ 15. 边际递减 → 16. 分析过程要求（analysis 三步推理链）+ **记录来源区分** + **重判增量修订契约** + 输出 JSON schema（含 `confidence_reason`、`revision_notes`、"严禁全角引号"的格式警告）。

**v1.3 → v1.6 期间新增/强化的四节**（重点理解这几节，它们是产品可信度的来源）：
- **输出前维度硬校验（v1.5 B2）**：在输出 JSON 之前增加一个**强制自检步骤**——"对照生活面清单，确认每个有事实依据的维度都被评分"。**为什么要用"硬校验"而不是"提醒"**：prompt 里的软性提醒容易被模型忽略，写成输出前的**编号检查步骤**（"第一步…第二步…"）能显著提高遵守率。同时服务层 `_parse_changes` 仍做过滤兜底——**prompt 是软约束，代码是硬约束，两层都要**。
- **记录来源区分（v1.4）**：要求 AI 在判定中区分**用户主动提及**与**追问后引导想起**的内容，后者的加点应更保守。**解决的是"AI 把追问套出来的信息当主动性证据"**——如果不区分，用户越配合 AI 追问，加点越多，等于奖励"被问出来的回忆"，逻辑不成立。
- **置信度原因 `confidence_reason`（v1.4）**：置信度低于 0.95 时**强制填写理由**。这是"让模型为不确定性负责"的通用手法——不给理由的低置信度等于没说。
- **重判增量修订契约（v1.6，见 6.6 详解）**：要求 AI 在重判时**逐条声明每个维度的处置方式**（保留/调整/撤销 + 依据），不相干维度**逐字保留原文**。

> **写 prompt 的方法论**：每一节都对应一个"曾经出过的 bug"（负面不扣分→第7节；维度漏判→第8节+硬校验；从不追问→第14节重写；重判改口→增量修订契约）。prompt 是活的规格说明书，出问题就加一节/改一节，并保持节间不矛盾。**改 prompt 前必做三查**：查逃逸出口、查默认值倾向、查条款冲突。

### 5.1 `build_judge_messages` 的条件注入

把上下文**条件注入** user 消息——有什么注什么，没有就不出现：

| 注入块 | 来源函数 | 作用 |
|--------|---------|------|
| `【记录模式】` | event.source | 区分 form/journal（决定是否追问） |
| `【当天已记录的事件】` | `_today_events_context` | 事件去重依据（同天同件事不重复加事实分） |
| `【用户长期记忆】` | profile.long_term_memory | 五类摘要背景 |
| `【近期生活记录】` | `_recent_events_context` | 近 7 天 10 条，提供近期状态背景 |
| `【近期同类事件频率】` | `_recent_same_category_count` | 近 30 天同类计数 → 累积效应 |
| `【当前属性值】` | `_attribute_context` | 边际递减依据 |
| `【用户对追问的补充回答】` | clarification 参数 | 追问后重判的输入 |
| **`【此前判定（基准）】`** | **`_prior_snapshot(judgment)`** | **v1.6 新增：重判时的基准快照，增量修订契约的载体** |
| **`【此前追问与用户回答】`** | **`clarify_history`** | **v1.4 新增：让重判知道之前问过什么、用户答了什么（避免重复问）** |
| `用户画像背景` | `_profile_context` | basic_profile 摘要 |


---

## 第 6 章 核心业务链路精讲（judge_service.py，~620 行）

### 链路 A：提交日记 → 提取 → 判定（含追问）
```
前端 EventForm.submitJournal()
  → POST /api/events        (routers/events.create_event)
      source=journal → llm_service.chat_json(prompts.build_extract_messages(content))
      → 提取 event_type/category/title/params 落 events 表
  → POST /api/events/{id}/judge  (events.judge)
      → judge_service.judge_event(db, event, clarification="", clarify_history=[])
          1. 幂等处理：已有 confirmed → ValueError 拒绝重判
                       已有 pending/adjusted → **就地更新（v1.5 A1，id 不变）** ⚠️
          2. 组装上下文（锚点/记忆/频率/属性值/当天事件/维度开关/clarify_history/prior_judgment）
          3. resolve_llm_config(db, user_id, PURPOSE_JUDGE) → 拿 BYOK 配置（可能带 quality_note 降级标注）
          4. llm_service.chat_json → result
          5. result["realistic"]==False → _handle_unrealistic：计数、第3次起扣诚信、删事件、抛 ValueError
          6. result["needs_clarify"]==True → raise ClarifyNeededError(questions)
          7. _parse_changes：别名表规范化属性名（constants.ATTRIBUTE_ALIASES 防 AI 返回 "physical"）
             + delta 钳制 [-5,5] + 过滤 disabled 维度（双保险，prompt 已要求但代码再兜底）
          8. 新建路径：AIJudgment(status=pending) + 审计 create + commit
             重判路径：**更新原 judgment 的字段**（不动 id）+ 审计 rejudge（带 payload）+ commit
      路由层异常翻译：ClarifyNeededError → 200 {"needs_clarify":true,"questions":[...]}
                      ValueError → 400；LLMError → 503
  → 前端：res.needs_clarify → 显示追问卡（clarifyEvent）→ 用户答 → judgeEvent(id, answer) 再进 2（可多轮）
```

> **⚠️ v1.5 关键修复点（务必理解）**：v1.3 及之前，重判是**"删旧判定 + 建新判定"**。这导致三个连锁问题：① **审计断裂**（把 create 之后的日志一起删了，历史消失）② **judgment id 漂移**（前端 sessionStorage 存的 id 失效，出现"预览的是旧判定"）③ **维度漂移**（两次判定输出的维度集合不一致，用户看到点数莫名变动）。
> **修复（`bc4929f`）**：重判一律**就地更新原判定对象**——`id` 不变、`status` 重置为 pending、`suggested_changes`/`analysis`/`confidence_reason`/`revision_notes` 全部覆盖写，**审计只增一条 rejudge 不删任何日志**。
> **可迁移铁律**：**同一个业务对象的多条操作入口，必须走同一套写入语义。**"更新"就该是 update，不要图省事用"先删后建"——它会让 id 稳定性、审计完整性、缓存有效性同时失守。

**学习点**：①"异常即协议"——用自定义异常 `ClarifyNeededError` 在服务层控制流程，路由层翻译成 HTTP 响应；②**纵深防御**——prompt 说"不判关闭维度"+代码再过滤一遍，LLM 输出永远不可全信；③**上下文要带历史**——`clarify_history` 让重判知道"之前问过什么"，避免重复追问同一个问题。

### 链路 B：确认入账（confirm）
```
低置信度拦截：confidence < 0.8 → ValueError（前端同步禁用按钮，双端一致）
逐条 suggested_changes：
    实际 delta = 原始 delta × confidence          # 置信度加权
    attr.current_value += delta                   # _ensure_attribute 不存在则以 50 兜底创建
    写 AttributeHistory(delta, value_after, reason="xxx（置信度 90% 加权）", evidence)
judgment.status="confirmed"; final_changes=applied; 审计 confirm
```

### 链路 C：补充/反驳（supplement / dispute）
- supplement：原事件描述 + `【用户补充信息】` + **`clarify_history`** + **`prior_judgment`** 重新走判定 → status=adjusted，审计 rejudge（v1.5 起同样就地更新）。
- dispute：换 dispute prompt（客观复核员）→ conclusion=adjust 时用 `_parse_changes` 覆盖建议（**空结果则保守维持原判**）；maintain 时**用 `revision_notes` 承载"维持理由"**（v1.6），审计 maintain。**返回值里带 conclusion/explanation 供前端弹窗提示**。

### 链路 D：删除回滚（delete_event，账目守恒）
```
对该事件全部判定：
    status==confirmed → 按 final_changes 逐条反向扣回 + 写 AttributeHistory(delta=-delta,
                          reason="事件删除回滚（原判定：…）")   # 流水保留，账目可对
    审计 delete（留痕）→ 物理删 JudgmentLog → 删 AIJudgment
最后删事件本身
```
**学习点**：删除也走"反向流水"而不是抹掉历史——任何时候 `sum(attribute_history.delta)` 都等于当前属性值减初始值，这是可审计系统的通用做法。

### 链路 E：Onboarding 问卷（onboarding_service.py）
```
POST /onboarding/questions → start_questions：已完成→锁定提示；有会话→恢复；
    无会话 → _evaluate（LLM 出题+自评把握度）→ 存 onboarding_state
POST /onboarding/answer → answers 追加进 conversation → _evaluate
    confidence ≥ 95 → _generate_panel：LLM 生成面板 → 写 initial_attributes_snapshot 快照
    → basic_profile 沉淀问答 → attributes 表逐项落值 → 标记 completed → 清空会话态
补充长期信息：supplement_profile（AI 综合画像+流水客观评估）→ pending_adjustment 暂存
    → confirm_adjustment 确认后才生效（写流水）——用户保留最终控制权
reset_onboarding（保留数据重建档）/ reset_all_data（全清，双确认在前端）
```
**学习点**：**会话态存数据库而非内存/前端**——多轮问卷中断、重启服务都能恢复；"生成建议→用户确认→才生效"是 AI 决策类功能的可信度关键。

### 链路 F：长期记忆（memory_service.py）
`maybe_update_memory`：距上次更新超 24h → 取近 30 天事件摘要 → memory prompt 增量合并旧记忆 → 存 `profile.long_term_memory`（JSON）。**失败静默返回 None**——记忆更新失败不影响判定主流程（优雅降级）。**v1.4 起该调用走 `PURPOSE_AUX` 配置**（记忆压缩属于辅助任务，可用便宜的模型）。

### 链路 G：周报（routers/report.py）
纯 SQL 聚合（事件数/类别分布/属性变化/判定数/目标状态）→ 连同长期记忆与关闭维度塞给 report prompt → 返回结构化报告。**统计用代码、洞察用 LLM**——数字必须准确的部分不交给模型。同样走 `PURPOSE_AUX`。

### 链路 H：重判增量修订契约（v1.6 新增，本项目最精细的一次 prompt 工程）

**问题**：v1.5 统一了重判链路（就地更新），但没解决**语义层面**的退化——重判时如果 AI 只盯着新增信息，会把上次已判定的维度"忘记"（漏判）或"改口"（无依据地改分数）。用户看到的就是"我只是补充了一句，结果好几个维度的分都变了"。

**方案：基准快照 + 逐条处置声明**

```
judge_event 检测到已有 pending/adjusted 判定
  → _prior_snapshot(judgment)  # 把上次判定的 suggested_changes 压成"基准快照"
  → 注入 user 消息的【此前判定（基准）】块
  → prompt 中的「重判增量修订契约」节要求 AI：
       ① 逐维度声明处置方式：保留 / 调整 / 撤销
       ② 不相干的维度**逐字保留原文**（不改措辞、不改分数）
       ③ 撤销必须有依据（用户补充的哪句话推翻了哪条依据）
  → 输出 JSON 增加 revision_notes 字段承载这些声明
  → 服务层 _parse_revision_notes 解析 → 存 ai_judgments.revision_notes
  → 前端 JudgmentList/EventForm 展示"本次重判的修订说明"
```

**dispute 链路特别处理**：当 dispute 的结论是 `maintain`（维持原判）时，**用 `revision_notes` 承载"维持理由"**——这样"驳回"也是一个有解释的动作，而不是一个沉默的按钮。

> **可迁移（这是本项目最值得抄的一条）**：**当 AI 需要"多次改写同一个对象"时（重判、润色、重构、配置迭代），不要指望它记住上次的结论——把上次结果作为显式基准注入，并要求它逐条声明处置方式（保留/调整/撤销+依据）。**
> 为什么有效：①"保留"是默认动作，声明它成本极低，但**声明这个动作本身会强迫模型审视每一个维度**（防漏判）②"撤销需说明依据"堵住了模型随意改口③用户能看到"哪些变了、为什么变"，透明性大幅提升。这套契约适用于任何多轮改写的场景。


---

## 第 7 章 其余路由速览

- `attributes.py`：`GET /attributes` 返回面板+每项 `visibility`（show/hidden/disabled 三态，读 settings 表）；`GET /attributes/history` join 属性名给趋势图。
- `goals.py` + `goal_service.py`：CRUD + achieve（规划力+reward、关联属性+reward）/ fail（扣 penalty）/ cancel（只审计不结算），全部写 `goal.audit`。**v1.7 计划**：与打卡项目的"计划内"类型联动展示进度。
- `anchors.py`：列表 + calibrate（calibrated_value，null 恢复默认）。
- `export.py`：`_collect` 聚合六类数据 → JSON 直返 / CSV（StringIO+csv.writer+BOM，`Response` 带 Content-Disposition 触发下载）；备份两个端点。
- `settings.py`：KV 读写 + 三类键的默认值兜底。**v1.4 新增 BYOK 两个端点**：`get_llm_config`（掩码回显 `sk-****末4位`）/ `put_llm_config`（识别 `__KEEP__` 哨兵值不覆盖旧 key、`model_changed` 检测）。
- `judgments.py`：判定列表（join 事件取标题，**排除 invalidated**；Python 内分组统计 `last_input` 与 `rejudge_counts`）/详情/审计 logs/confirm/supplement/dispute。**v1.5 起列表额外返回 `last_user_input`（上次用户输入）与 `rejudge_count`（重判次数）**——前端因此能展示"你上次说的是什么"和"这条改过几次"。
- `events.py`：`create_event`（journal 走 extract；**L52-56 的"结构化打卡必须指定事件类型"400 分支为 v1.7 计划要移除项**）/ `list_events`（pure/q/date 过滤）/ `get_heatmap` / `judge` / `get_event` / `update_event`（作废旧判定为 `invalidated` 并审计 `invalidate`）/ `delete_event`。


---

## 第 8 章 前端精讲（frontend/src/）

### 8.1 api.js —— 唯一 fetch 出口
`request()` 统一处理：JSON 头、`resp.ok` 检查、`detail` 字符串/对象归一化为 Error message。所有接口按域分组导出（onboarding/events/judgments/...）。**收益**：换后端地址、加 token、统一 loading——都只改这一个文件。
`exportData` 是例外（要触发浏览器下载）：拿 blob → `URL.createObjectURL` → 动态 `<a download>` 点击。

### 8.2 App.vue —— 布局壳
`tabs` 数组驱动 9 个 tab 按钮；`activeTab` ref 控制 `v-if/v-else-if` 挂载对应组件（**非 router**，个人项目够用且零依赖）；onMounted 里 `checkHealth()` 探测 `/api/health` → 顶部绿/红横幅（解决"没连上后端"排查痛点的 UX 方案）；`!hasProfile` 时显示引导卡；EventForm 用 `@go-judgments` 事件让父组件切 tab（**子组件不直接操作父状态，通过 emit 通信**——卡4）。

### 8.3 EventForm.vue —— 双通道 + 三层状态持久化
- 双通道：`mode` form/journal 切换模板；表单提交组装 params；日记提交只传 content（后端提取）。
- **三层持久化**：①表单草稿 → localStorage（`CACHE_KEY='game_of_life_event_draft'`，`watch([mode,form,...], save, {deep:true})` 自动存）；②判定结果/追问状态 → sessionStorage（`JUDGE_CACHE_KEY='gol_last_judgment'`，关标签即清）——解决"切页结果丢失"；③清除分档：`reset()` 全清 vs `clearResult()` 只清结果留草稿。
- **⚠️ v1.5 A3 的关键修正（"单一数据源"）**：sessionStorage 里**只存 `judgmentId` + clarify 态，不再存判定内容快照**。`restoreJudgeState()` 拿着 id 去 **DB 拉现行判定**；如果该判定已被作废（`invalidated`）则设 `previewStale=true` 提示"此判定已失效"。
  > **为什么这条重要**：存快照看似省一次请求，实则制造了**两个真相来源**——DB 里的判定被重判更新了，sessionStorage 里还是旧的，用户看到的是"幽灵数据"。**缓存只缓存指针（id），不缓存副本（内容）**，是前端状态管理的一条硬规矩。
- 追问两阶段：`clarifyEvent` 非空显示问题卡 → `submitClarify` 带 clarification 重判（后端可能继续追问，循环）。
- 结果卡展示 analysis 推理链 + `confidence_reason`（v1.4，低置信度理由）+ `revision_notes`（v1.6，重判修订说明）+ `预计入账 delta×confidence`（透明展示加权）+ "去判定中心确认" emit。

### 8.4 JudgmentList.vue + useDateGroups.js —— 判定中心与"逻辑复用"

**（a）useDateGroups.js（v1.6 抽出的 composable，73 行）**

判定中心与手账本都需要"按日期分组折叠"，且规则完全一致（今天/昨天/本周更早/更早，以**本周一 0 点**为界；默认只展开"今天"；展开状态存 localStorage）。v1.6 之前这段逻辑在两处组件里各写一遍，v1.6 把它抽成 composable：

```js
export function useDateGroups(items, { storageKey, getTime = (item) => item.created_at }) {
  const GROUPS = [
    { key: 'today',     label: '今天' },
    { key: 'yesterday', label: '昨天' },
    { key: 'thisweek',  label: '本周更早' },
    { key: 'earlier',   label: '更早' },
  ]
  // expanded 从 localStorage 读（默认 { today: true }），toggleGroup 切换并回写
  return { groups, expanded, toggleGroup }
}
```

> **组件 vs composable 的选型**（Vue3 工程化的核心判断）：**复用的是逻辑还是外观？** 逻辑→composable（无需模板、无需 props/emit 协议，参数直接传）；外观→组件。本项目 `App.vue`/`EventForm.vue` 是组件（有 UI），`useDateGroups` 是 composable（只有计算）。
> **注意一处刻意的不对称**：搜索时两个页面都要"强制展开全部组"，但这**不写进 composable**——由各消费者自己在模板里叠加判断（`groupIsOpen(g) => searching.value || expanded[g.key]`）。因为"搜索要不要强制展开"是**页面级的产品决策**，不是分组逻辑本身；把这种决策塞进通用件会让它变成"什么都要管"的上帝函数。

**（b）JudgmentList.vue（判定中心，408 行）**
- **保留式反馈状态机（v1.6）**：三个状态 ref 各司其职——`actionSuccess`（成功，保留式）、`actionError`（v1.4，就近错误）、`disputeResult`（v1.5，反驳结论弹窗）。核心是 `runAction(id, fn, okMsg)`：**失败保留用户输入并显示错误，成功也保留输入并显示成功文案**。操作区的成功态是**整体替换**（把按钮换成"✓ 已确认"文字），避免用户看到按钮还能点而重复提交。
- **v1.3 修复续存**：`refreshAudit(id)` 独立函数 + `runAction` 成功后 `if (auditTarget===id) await refreshAudit(id)`——修复"操作后审计不刷新"；`removeEvent` 后主动收起审计面板。
- 低置信度：按钮 `:disabled="(j.confidence||0) < 0.8"` + 黄色提示条（与后端 400 拦截双保险）。
- `ACTION_LABEL`/`STATUS_LABEL` 字典把后端枚举翻译成人话（**含 `invalidated: '已作废'`**）——**枚举展示永远用映射表**，不要在模板里写三元判断链。
- **v1.4~v1.6 新增展示项**：`revision_notes`（重判修订说明）、`last_user_input`（上次你输入的内容）、`rejudge_count`（重判了几次的 tag）、`myInputOpen`（展开看自己的原始输入）。
- **v1.6 日期分组**：`groupedJudgments` 用 `useDateGroups` + `storageKey: 'gol_judgment_group_expand'`。
- ⚠️ **代码质量提示**：L302 之后模板缩进异常（v1.6 嵌套重构遗留），不影响运行但影响可读性，是后续可以清理的技术债。

### 8.5 TimelineView.vue —— 手账本时间线（v1.6 折叠版，153 行）
与判定中心同构：`useDateGroups(filteredEvents, { storageKey: 'gol_timeline_group_expand' })`。
- **摘要行**：时间 + 标题 + 类别 tag + **`changeSummary`**（把判定点数变化压成一行，如 `体能 +1 · 智力 +0.5`，无加点则显示"无加点"）——**折叠态要给出足够的信息密度**，否则用户必须逐条展开，折叠就失去意义。
- **展开态**：content / params / 判定明细 / analysis。
- **搜索强制展开**：`groupIsOpen`/`itemIsOpen` 在 `searching` 为真时返回 true（同 8.4 的不对称设计）。

### 8.6 SettingsView.vue —— 状态机 + 紧凑 UI（v1.3 整合 + v1.4 扩展）
三态真相：`hidden_attributes`/`disabled_attributes` 两个数组（settings 表）；`stateOf(name)` 派生三态；`setState` 同时更新两数组再连续 PUT（hidden 永远不含 disabled 的项，disabled 优先级高）。v1.3 UI：`changedAttrs` computed 只列非默认维度，其余收进 `<details>` 折叠，3 按钮→单 select。
**v1.4 新增 BYOK 配置区**（本次新增 140 行，占该文件近一半）：主/辅模型两组输入（key/base_url/model），key 输入框显示掩码且聚焦时可覆盖；保存时未改动的 key 传 `__KEEP__`；模型名变更时提示"模型切换会影响判定口径一致性"。这一区是**"前端做安全边界"的典型**——掩码回显不是后端一个人的事。
另有：游戏化模块开关（MODULES 字典）、导出/备份/重置（双重 confirm）、周报。

### 8.7 AttributePanel.vue —— ECharts 三图
`Promise.all` 并发拉三份数据 → `nextTick()` 等 DOM 渲染后 init 三个 chart（radar 雷达/growth 折线/heatmap 日历热力图）；`visibleAttrs` computed 过滤 hidden；`onBeforeUnmount` dispose + 移除 resize 监听（**防内存泄漏的固定姿势**）；`radarChart && radarChart.resize()` 应对窗口变化。

---

## 第 9 章 可迁移的设计模式总结（本项目出产的通用件）

> 本章的每一条都**能追溯到第 10 章的具体 bug**——括号里标了来源，可以对照着看"抽象出这条模式的代价是什么"。

1. **幂等初始化链**：create_all + 轻量迁移 + 种子数据 + 默认记录 + 自动备份，重复启动安全（B-08/B-14）
2. **LLM 服务层单例 + 三级 JSON 容错 + 一次重试**：业务零直接依赖 SDK；重试只吃瞬时抖动，不掩盖系统错误（B-02/B-05）
3. **事实基准表（锚点库）**：LLM 判定类产品防口径漂移的标准解法
4. **建议→确认→生效**：AI 输出一律 pending，人确认才落账
5. **append-only 流水 + 反向回滚**：删除不改历史，账目永远可对（B-03）
6. **异常即协议**：服务层自定义异常，路由层翻译 HTTP 语义（B-11）
7. **prompt = 活的规格说明书**：每节堵一个真实 bug；改前查逃逸出口/默认值倾向/条款冲突；软提醒升级为**输出前硬校验步骤**（B-06/B-07/B-09/B-10）
8. **前端状态分档持久化**：localStorage（草稿）/ sessionStorage（**只存 id 的会话指针**）/ DB（业务数据）——**缓存指针不缓存副本**（B-03/B-04）
9. **枚举展示映射表**、**emit 通信**、**chart dispose**、**双端一致的业务拦截**（B-03：新增状态值要全局搜映射表）
10. **配置进 KV 表而不是加列**（v1.4 BYOK 的 `llm_primary`/`llm_aux`）：零迁移成本，功能可以"插队"提前交付
11. **凭据读-显-存三态**（v1.4）：掩码回显 + `__KEEP__` 哨兵值不覆盖 + 变更检测——用户自带密钥类功能的通用骨架
12. **降级可感知**（v1.4）：`quality_note` 随响应传到前端展示——静默降级是信任透支
13. **多入口同一写入语义**（v1.5）：同一对象的多个操作入口必须走同一套写库逻辑；**绝不用"先删后建"实现"更新"**（B-01/B-03）
14. **AI 多轮改写的增量修订契约**（v1.6，本项目最精细的一次 prompt 工程）：注入基准快照 + 要求逐条声明处置（保留/调整/撤销+依据）+ 不相干项逐字保留 + 结构化落库（`revision_notes`）供用户审阅
15. **逻辑复用抽 composable，外观复用抽组件**（v1.6）：判断标准是"复用的是逻辑还是外观"；页面级产品决策不塞进通用件
16. **保留式反馈**（v1.6）：成功/失败都保留用户输入——用户的劳动成果不该因为一次操作而消失
17. **辅助功能不得阻断主流程**（B-08）：启动链每步都要问"失败该不该阻断"；能静默降级的就静默
18. **迁移 = 结构变更 + 数据回填**（B-12/B-14）：只加列不留回填，历史行就是 NULL；标量默认值要显式 UPDATE
19. **规则要收敛到单一判据，且"不确定时"要选好默认倾向**（B-06）：多判据叠加会让边界情况指数增长
20. **能用自然终止信号就不要用硬阈值**（B-09）：追问用"信息足够/用户不愿谈/问题重复"，重试才用固定次数（成本场景）

## 第 10 章 常见修改任务手册（动手练）

| 任务 | 步骤 |
|------|------|
| 加一个属性维度 | constants.py 加名+别名 → user_service.ensure_dimensions 自动补建（重启生效）→ prompt 第 2 节 13 维列表同步改 |
| 加一条锚点 | anchor_service.BUILTIN_ANCHORS 追加一条（name/evidence 必填）→ 重启幂等写入 → 锚点库页可见、判定自动注入 |
| 调判定规则 | 只改 prompts/judge.py 对应节 → 注意与"客观性硬约束/追问规则/增量修订契约"节是否冲突 → 用真实日记验证 |
| 加一张表 | models 加类 → sql/schema.sql 同步 → 重启自动建表；已有表加列走 migrate_schema |
| 加一个接口 | schemas 加入参 → router 加函数 → main.py include_router（已有模块则免）→ api.js 加封装 → 组件调用 |
| 换 LLM 供应商 | 全局：只改 .env（base_url/model/key）；**单用户：设置页 BYOK 主/辅两组**（v1.4） |
| **加一个"AI 输出字段"** | 五处联动：`prompts/judge.py` 输出 schema 加字段 → `models/__init__.py` 加列（可空）→ `sql/schema.sql` 同步 → `judge_service` 解析写入 → `schemas/__init__.py` 响应模型暴露 → 前端组件展示。**漏一处就静默失效**（如 `revision_notes` 就是这么加的） |
| **改重判相关逻辑** | ⚠️ 先确认写入语义：必须**就地更新**（id 不变、审计只增不删）；涉及"AI 会不会改口"时同步检查增量修订契约那一节 |
| **加一个前端复用逻辑** | 判断逻辑还是外观——逻辑进 `frontend/src/composables/`，外观进 `components/`；页面级策略留在页面里 |
| **改 LLM 容错策略** | `llm_service.py` 的 `_parse_json`（解析）与 `chat_json`（重试）分开改；重试次数改动要考虑成本与重复执行风险 |

## 第 11 章 故障档案（Bug Ledger）—— 每个 bug 的根因与修复实现

> **为什么单独成章**：第 6 章的链路精讲讲的是"代码现在长什么样"，第 4 章的阶段 4 讲的是"业务教训是什么"，但**两者都没回答"出问题当时怎么定位的、改的是哪一行、为什么这么改"**。
> `git log` 里一条 `fix(A4): 实测发现并修复两个链路 bug`，三个月后你根本不知道是哪两个——本章就是把这类信息**固定成五栏格式**留档，可反查、可复现、可迁移。
>
> **五栏格式**：**现象**（用户/测试看到什么）→ **定位过程**（怎么找到的，证据是什么）→ **根因**（本质原因）→ **修复实现**（改哪个文件哪个函数、代码形态）→ **防复发**（怎么保证不再犯）。
>
> **收录范围**：全部 14 条 `fix` 提交（按时间倒序）。每条都标注 commit hash，可直接 `git show <hash>` 看原始 diff。
> **用法**：出问题时先查索引表找同类现象 → 看对应条目的"定位过程"学怎么查 → 对照"防复发"检查是否还有其他地方犯同样的错。

### 索引表

| # | 现象一句话 | 根因类型 | commit | 日期 |
|---|-----------|---------|--------|------|
| B-01 | 补充/追问后 AI"失忆"，维度漂移、置信度虚低被拦截 | 多入口不同步 | `5f9e2be` | 09-09 |
| B-02 | 判定偶发失败，用户白填一遍表单 | 外部依赖无重试 | `470b714` | 09-09 |
| B-03 | 重判后审计消失、id 失效、点数莫名变动 | 写库语义错误 | `bc4929f` | 09-09 |
| B-04 | 操作后审计轨迹不刷新，要关掉重开才更新 | 前端未重拉 | `5cfa6ca` | 09-05 |
| B-05 | 判定随机解析失败（模型输出全角引号） | 输出格式假设 | `5c34c3e` | 09-05 |
| B-06 | 当天首次提到的负面行为被误判为"重复记录" | 规则过度泛化 | `cd9f4ca` | 09-03 |
| B-07 | 负面行为重复记录被去重、负面情绪不减分 | 规则缺失 | `fe28d0b` | 09-03 |
| B-08 | 备份清理失败导致启动中断 | 辅助阻断主流程 | `6dd6c8e` | 09-03 |
| B-09 | 追问在第 2~3 轮被硬性截断，漏掉可复盘内容 | 规则僵化 | `4bb2e6f` | 09-02 |
| B-10 | 追问语气偏软，出现"迎合式"判定倾向 | 定位条款不完整 | `4b26500` | 09-02 |
| B-11 | 同一事件出现双判定记录 | 幂等缺失 | `d55cde3` | 09-01 |
| B-12 | 新列 `is_pure` 为 NULL，下游 schema 校验失败 | 迁移不完整 | `5d3965a` | 08-31 |
| B-13 | onboarding 问卷报 JSON 解析失败 | 模板变量转义 | `9a1ae4d` | 08-30 |
| B-14 | 模型加列后旧库 INSERT 报 `no column named xxx` | 无迁移机制 | `e7cb967` | 08-30 |
| B-15 | 热力图只渲染了最近一周（日期参数被静默截断） | 外部库隐式语义 | 见 P2 commit | 09-30 |
| B-16 | 子维度混进雷达图、变成独立条目 | 新增层级后漏收敛消费点 | `00519df` | 09-30 |

---

### B-01 · 补充/追问后 AI"失忆"，维度漂移、置信度虚低被拦截

**commit** `5f9e2be`（v1.5 A4，2026-09-09）· **文件** `routers/judgments.py`、`services/judge_service.py`

**现象**：用户补充信息后重判，AI 把"此前追问中已回答过的面"当成未提及——同一件事的维度集合与上次不一致（维度漂移），置信度虚低（实测 **0.9 → 0.72，跌破 0.8 被拦截**）。同时判定中心不显示用户自己填的补充内容。

**定位过程**：对比 `judge_event` 与 `supplement` 两条链路的参数传递，发现 `judge_event` 传了 `clarify_history`，而 `supplement` **没传**——AI 手上没有"之前问过什么、用户答了什么"，自然当作首次看到。

**根因**：**同一条判定链路的两个入口，参数传递不对等**。追问流程的用户回答存在 `event.params["_clarify_history"]`，但只有追问入口会读它。

**修复实现**：
1. `supplement()` 中补上历史注入——这是核心修复：
```python
# v1.5 A4 修复：补充重判同样注入追问历史，避免 AI"失忆"
clarify_history = list((event.params or {}).get("_clarify_history") or [])
messages = prompts.build_judge_messages(
    ...
    clarify_history=clarify_history,
    previous_changes=judgment.suggested_changes,  # v1.5 B2：重判不丢维度
)
```
2. `judge_event()` 的 `rejudge` 审计 payload 增加 `clarification` 字段（把用户完整回答写进审计，供"我的补充"展示）：
```python
payload={
    "suggested_changes": changes, "analysis": judgment.analysis, "summary": summary,
    "clarification": clarification.strip(),  # v1.5 A4：完整回答入审计
}
```
3. `list_judgments()` 里把"追问流程的用户回答"也识别为 `last_input`（原先只认 `supplement`/`dispute` 两种 action）：
```python
elif log.action == "rejudge" and isinstance(log.payload, dict) and log.payload.get("clarification"):
    last_input[lid] = {
        "action": "supplement",
        "detail": str(log.payload["clarification"]),
        "created_at": log.created_at,
    }
```

**防复发**：**凡是"同一业务动作的多个入口"，逐个核对参数传递是否对等**（这是 B-03 同源问题，见该条的"多入口一致性审查"）。判断标准：如果某个入口缺了另一个入口有的上下文，AI 的行为就会出现"入口差异"。

---

### B-02 · 判定偶发失败，用户白填一遍表单

**commit** `470b714`（v1.5 A5，2026-09-09）· **文件** `services/llm_service.py`

**现象**：用户填了一长段日记点提交，返回"AI 服务不可用"——重试一次就成功了。

**定位过程**：`backlog` 记录了"LLM 偶发空返回"问题（v1.4 回写时登记）。检查 `chat_json` 发现**单次调用、无重试**：模型返回空字符串或 JSON 解析失败时直接抛 `LLMError`。

**根因**：**外部依赖没有容错层**。LLM 服务的瞬时抖动（空响应、格式偶发异常）是常态，而代码假设了"每次调用都成功"。

**修复实现**：`chat_json` 改为**最多 2 次尝试**，只对"空返回/解析失败/结果无有效字段"重试，退避 1s：
```python
last_error: Exception | None = None
for attempt in range(2):
    if attempt == 1:
        time.sleep(1.0)  # 指数退避：第 1 次重试前等待 ~1s
    raw = self.chat(messages, temperature=temperature, json_mode=True, config=config)
    if not raw or not raw.strip():
        last_error = LLMError("模型返回内容为空"); continue
    try:
        result = self._parse_json(raw)
    except LLMError as exc:
        last_error = exc; continue
    if not isinstance(result, dict) or not result:
        last_error = LLMError("模型返回 JSON 无有效字段"); continue
    return result
raise LLMError("AI 服务偶发抖动，已自动重试仍失败，请稍后重试。" f"（{last_error}）")
```

**关键设计边界**（这三条是"重试"的通用规矩）：
- **只重试 1 次**：两次都失败说明是系统性错误（prompt 或模型问题），继续重试只是烧钱烧时间
- **只对"空/解析失败"重试**：模型明确返回的业务结论（如 `realistic: false`）绝不重试
- **重试必须幂等安全**：docstring 明确写了"重判均为就地更新"——因为重试会重复执行 `chat_json`，如果下游是非幂等写入就会产生脏数据

**防复发**：**每个外部依赖都要过"韧性六问"**（阶段 5）：超时？重试？重试几次？降级？降级可见？失败后用户输入还在？

---

### B-03 · 重判后审计消失、id 失效、点数莫名变动 ⭐ 最有价值的一条

**commit** `bc4929f`（v1.5 A1，2026-09-09）· **文件** `routers/events.py`、`routers/judgments.py`、`services/judge_service.py`

**现象**（用户实测反馈，三条并发）：
1. 重判后**审计轨迹里 create 之后的记录全没了**
2. **前端预览显示的是旧判定**（SessionStorage 存的 id 失效）
3. **点数莫名变动**（前后两次判定的维度集合不一致）

**定位过程**：**没有直接改代码，先读 `judge_service.py` 比对两条链路的写入方式**，发现：
- `judge_event`（重判入口）：`db.query(JudgmentLog).filter(...).delete()` + `db.delete(j)` —— **删旧建新**
- `supplement`（补充入口）：原地修改现有对象的字段 —— **就地更新**

**根因**：**同一业务对象（判定）的两条入口用了两种写库语义**。"删旧建新"带来三重连锁伤害：

| 伤害 | 机理 | 用户看到的现象 |
|------|------|---------------|
| 审计断裂 | `JudgmentLog` 被连带删除 | 审计轨迹只剩一条 create |
| id 漂移 | 新判定换 id，前端仍持有旧 id | 预览显示旧判定 / 审计面板拉不到 |
| 维度漂移 | 两次 LLM 输出的维度集合本就不保证一致，旧基线又没了 | 点数莫名变动 |

**修复实现**（四处协同）：

1. `judge_event()` —— 查询现行判定（单数 `.first()`），不再删除：
```python
# v1.5 A1：现行判定（不删除，重判时就地更新）；invalidated 归档判定不参与
current = (db.query(AIJudgment).filter(
    AIJudgment.event_id == event.id, AIJudgment.user_id == user.id,
    AIJudgment.status.in_(["pending", "adjusted"]),
).first())
```
2. `judge_event()` —— 分支处理，重判走"就地更新 + 审计 rejudge"：
```python
if current is not None:
    current.suggested_changes = changes
    current.analysis = result.get("analysis", [])
    current.summary = summary
    current.confidence = float(result.get("confidence", 0.0))
    current.confidence_reason = str(result.get("confidence_reason", ""))
    current.status = "adjusted"
    judgment = current
    db.flush()
    _log(db, judgment.id, user.id, "rejudge", detail=rejudge_detail, payload={...})
else:
    judgment = AIJudgment(...); db.add(judgment); db.flush()
    _log(db, judgment.id, user.id, "create", ...)
```
3. `update_event()` —— 编辑事件时旧判定**不物理删除**，改 `status="invalidated"` + 审计 `invalidate`：
```python
for j in stale:
    j.status = "invalidated"
    db.flush()
    judge_service._log(db, j.id, event.user_id, "invalidate",
        detail="事件被编辑，旧判定作废归档（判定结果不再可信，需重新判定）",
        payload={"event_id": event.id})
```
4. `list_judgments()` —— 列表排除归档判定，成为唯一数据源：
```python
.filter(AIJudgment.user_id == user.id, AIJudgment.status != "invalidated")
```
5. 前端两个组件的 `STATUS_LABEL` 补 `invalidated: '已作废'`（枚举新增必须同步映射表）。

**防复发（三条）**：
- **"更新"就该是 update**：绝不用"先删后建"实现更新——它会让 id 稳定性、审计完整性、缓存有效性同时失守
- **新增状态值时全局搜索映射表**：`invalidated` 加进 status 枚举后，`JudgmentList.vue` 和 `TimelineView.vue` 两处 `STATUS_LABEL` 都要改（漏一处前端显示原始英文）
- **多入口一致性审查**（方法论化）：拿到"数据不对劲"类反馈，先问——*这个操作有几个入口？各自代码路径一样吗？产生的副作用（审计、id、缓存）一样吗？*

---

### B-04 · 操作后审计轨迹不刷新，要关掉重开才更新

**commit** `5cfa6ca`（v1.3，2026-09-05）· **文件** `components/JudgmentList.vue`

**现象**：在判定中心点"确认/补充/反驳"后，如果审计面板正开着，里面的轨迹不更新——必须关掉再打开才看到新记录。

**定位过程**：先查后端写入点（`_log` 在四个 action 里都调了，**数据是齐的**）→ 排除后端 → 再看前端 `runAction`：只 `await load()` 重拉了列表，**没重拉审计**。

**根因**：**前端刷新范围不完整**——列表数据刷新了，但审计数据是独立接口，没被触发。

**修复实现**：把审计拉取**抽成独立函数**（可复用），并在操作成功后条件刷新：
```javascript
async function refreshAudit(id) {
  // v1.3：审计拉取独立成函数，供操作成功后同步刷新（无需关闭重开）
  try { auditLogs.value = await api.getJudgmentLogs(id) }
  catch (e) { error.value = e.message }
}

async function runAction(id, fn, okMsg) {
  try {
    const res = await fn()
    await load()
    // v1.3：若该判定的审计面板正展开，同步刷新轨迹
    if (auditTarget.value === id) await refreshAudit(id)
    return res
  } catch (e) { error.value = e.message }
}
```
另外 `removeEvent` 后主动收起审计面板（避免残留已删判定的轨迹）：
```javascript
await api.deleteEvent(eventId)
auditTarget.value = null; auditLogs.value = []   // v1.3：判定消失，收起审计面板
```

**防复发**：**一次操作若影响多个数据源，要盘点全部需刷新的接口**。这里的信号是"数据是分开的接口"——判定列表一个接口、审计日志另一个接口，只刷一个必然不同步。

---

### B-05 · 判定随机解析失败（模型输出全角引号）

**commit** `5c34c3e`（v1.3，2026-09-05）· **文件** `services/llm_service.py`

**现象**：判定**随机**失败，报"无法解析为 JSON"。同一份日记重试可能就成功。

**定位过程**：抓取失败样本，发现模型偶尔用中文全角引号 `“”` 充当 JSON 的字符串定界符（如 `“属性”: “体能”`）。

**根因**：**对模型输出格式的假设太乐观**。原 `_parse_json` 只做两级容错（去 markdown 围栏 → 提取 `{...}` 块），没考虑"定界符被替换"这种变形。

**修复实现**：新增 `_repair_curly_quotes`，做**位置感知修复**——关键在于区分"结构位的引号"（应还原成 `"`）和"字符串内容里的引号"（应替换成 `「」` 不破坏内容）：
```python
@staticmethod
def _repair_curly_quotes(text: str) -> str:
    out = []
    for i, ch in enumerate(text):
        if ch in "“”":
            # 向前找非空白字符 → prev
            j = i - 1
            while j >= 0 and text[j] in " \t\r\n": j -= 1
            prev = text[j] if j >= 0 else ""
            # 向后找非空白字符 → nxt
            k = i + 1
            while k < len(text) and text[k] in " \t\r\n": k += 1
            nxt = text[k] if k < len(text) else ""
            if ch == "“" and prev in "{[,:，":   out.append('"')   # 结构位开引号
            elif ch == "”" and nxt in "]},:，":  out.append('"')   # 结构位闭引号
            else: out.append("「" if ch == "“" else "」")          # 内容里的引用
        else:
            out.append(ch)
    fixed = "".join(out)
    fixed = re.sub(r'"\s*，\s*"', '","', fixed)   # 结构位全角逗号
    return fixed
```
`_parse_json` 改为**候选列表逐个尝试**（原逻辑 → 括号块 → 全角修复版）：
```python
candidates = []
if match: candidates.append(match.group(0))
if "“" in text or "”" in text:
    candidates.append(cls._repair_curly_quotes(text))
for candidate in candidates:
    try: return json.loads(candidate)
    except json.JSONDecodeError: continue
raise LLMError(...)
```
（这是 v1.5 A5 重试机制的前身——先修解析，再加重试，两层兜底。）

**防复发**：**prompt 里已写"严禁全角引号"的格式警告，但代码仍要兜底**——LLM 输出永远不可全信（对应第 6 章"纵深防御"）。

---

### B-06 · 当天首次提到的负面行为被误判为"重复记录"

**commit** `cd9f4ca`（2026-09-03）· **文件** `prompts/judge.py`

**现象**：日记里**第一次**提到"今天熬夜了"，但 AI 判定为"这是重复记录"→ 不去重也不减分。

**定位过程**：逐条读去重规则，发现上一版（B-07）的修法引入了**"正面/负面"两套判据**，反而让规则变复杂、边界更模糊。

**根因**：**规则过度泛化 + 用"正负属性"当去重判据**。去重的本质是"同一件事被记录两次"，与"这件事是正面还是负面"**无关**。用正负性做判据，就会在"当天首次提到的负面行为"上出错。

**修复实现**：**把判据收敛为唯一一条中性规则**——
```diff
-- 去重**只针对正面事件**：若当天已记录过某件正面的事…但负面行为绝不去重…
-- 判断是否"同一件事"：看时间、动作、场景是否一致；不确定时，正面倾向不重复加、负面倾向正常减。
+- 去重的唯一标准：**同一天、同一件事、且已经判定过**，才不重复判定。
+- 关键约束：必须严格是「同一天」的「同一件事」才去重：
+  - 跨天的类似事件不是"重复"，应正常判定；
+  - 当天没有记录过、日记首次提到的事（无论正面还是负面，如日记首次提到"熬夜"），不是"重复"，应正常判定。
+- 不确定是否"同一件事"时，倾向正常判定（而不是倾向去重）。
```

**防复发**：**规则要收敛到"单一判据"，不要用派生属性（正/负）当条件**。多判据叠加会让边界情况指数增长。另外注意"不确定时的默认倾向"——这里选"倾向正常判定"，因为误去重的代价（漏加分/漏减分）大于误判定的代价。

---

### B-07 · 负面行为重复记录被去重、负面情绪不减分

**commit** `fe28d0b`（2026-09-03）· **文件** `prompts/judge.py`

**现象**（两条并发，用户实测 ②④）：
- 连续两天记录"熬夜"，第二天被去重 → 不减分
- 日记写"答辩前紧张到做不下事" → **不减分**（AI 只加不加）

**定位过程**：读 prompt 发现 ①去重规则写的是"不要重复给事实性分数"，未区分正负，导致负面行为也被吞 ②**根本没有"负面情绪减分"这一节**——prompt 只写了正面维度的归因示例。

**根因**：①规则的**负面场景未覆盖**（只考虑了正面事件被重复记录，没想到负面行为的"重复"是"问题持续"而非"重复记录"）②**缺失整节规则**（负面情绪/状态完全没写）。

**修复实现**：
1. 去重节明确正负分流（后被 B-06 进一步收敛为中性规则）：
```diff
+- 去重**只针对正面事件**…
+- **负面行为绝不去重**：熬夜、抽烟、酗酒…即使当天或近期已有类似记录，**每次出现都应正常减分**（频繁可累积加重）。负面行为的"再次出现"是"问题持续/加重"，不是"重复记录"。
```
2. **新增一整节**「负面情绪与状态」：
```diff
+## 负面情绪与状态（务必遵守）
+- 用户描述负面情绪/心理状态时（紧张、焦虑…），要给对应维度减分：
+  - 应对压力能力不足、情绪波动 → 心理韧性减分
+  - 负面情绪本身、不开心 → 幸福感减分
+  - 严重到影响正常生活/学习/睡眠 → 健康、规划力等也酌情减分
+- 客观如实：不要因为"温和"而回避减分，该减就减；但幅度与描述严重程度匹配。
```

**防复发**：**审查判定规则时，正负场景都要走一遍**。"这个规则在正面事件上对吗？在负面事件上对吗？"——本项目多处 bug 都是"只考虑了正面"（去重、追问、锚点）。**新增一节规则时，同步检查是否需要对称的负面版本**。

---

### B-08 · 备份清理失败导致启动中断

**commit** `6dd6c8e`（2026-09-03）· **文件** `services/backup_service.py`

**现象**：启动失败。日志指向备份清理环节删除旧文件时报错。

**定位过程**：`_cleanup()` 里 `f.unlink()` 未捕获异常——文件被占用或无权限时直接抛出，冒泡到启动链。

**根因**：**辅助功能没有降级路径**。备份清理是"锦上添花"的功能，却能让整个应用起不来。

**修复实现**：删除失败静默吞掉异常：
```python
def _cleanup() -> None:
    """保留最近 BACKUP_KEEP 份，删除更旧的（删除失败静默，不影响启动）。"""
    files = sorted(BACKUP_DIR.glob("game_of_life_*.db"))
    for f in files[:-BACKUP_KEEP] if len(files) > BACKUP_KEEP else []:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass  # 删除失败（如文件占用/权限）不影响主流程
```

**防复发**：**辅助功能不得阻断主流程**。启动链上的每一步都要问："这步失败了，应用该不该起得来？"（答：备份清理、记忆更新、锚点种子——都不该阻断；建表、迁移——应该阻断）。本项目 `maybe_update_memory` 也是同一原则（失败静默返回 None）。

---

### B-09 · 追问在第 2~3 轮被硬性截断，漏掉可复盘内容

**commit** `4bb2e6f`（2026-09-02）· **文件** `prompts/judge.py`

**现象**：用户写到一半的日记，AI 追问两轮后就"不再问了"，仍有一些值得回顾的内容没被引导出来。

**定位过程**：prompt 里有明确的硬性上限："累计追问不要超过 2~3 轮"。

**根因**：**用"数量上限"管理交互节奏，而不是用"价值判断"**。轮数上限是拍脑袋定的固定阈值，与"还有没有值得复盘的内容"这个真正的判据脱节。

**修复实现**：删掉轮数上限，改成**基于价值 + 多重终止条件**：
```diff
-- 用户补充回答后，若信息仍不足以支撑判定、且仍值得回顾，请继续追问（needs_clarify 仍为 true）；但累计追问不要超过 2~3 轮，若已问过类似问题或用户明显不愿多谈，就基于现有信息完成判定。
+- 不设固定的追问轮数上限：只要你觉得"还有值得用户回忆复盘的内容"，就可以继续温和地追问；直到信息已足够、或用户明显不愿多谈、或问题已重复，再基于现有信息完成判定。
```
**终止条件从"1 个硬阈值"变成"3 个自然信号"**：信息足够 / 用户不愿多谈 / 问题重复。

**防复发**：**能用"自然终止信号"表达的就不要用"硬性阈值"**。固定阈值的问题是不会随场景调整——但反过来，如果确实需要阈值（如成本控制），要在注释里写清"为什么是这个数"。**同时注意**：这条与 B-02 的"只重试 1 次"不矛盾——重试是成本控制场景（需硬阈值），追问是交互体验场景（宜价值判断）。

---

### B-10 · 追问语气偏软，出现"迎合式"判定倾向

**commit** `4b26500`（2026-09-02）· **文件** `prompts/judge.py`、`docs/DECISIONS.md`

**现象**：确立了"AI 是成长引导者"的定位后，判定开始**偏向鼓励**——该提醒的不提醒、该减分的不减分。

**定位过程**：读 prompt 首段，发现定位条款只强调了"温和引导"，**没有设客观底线**。

**根因**：**定位条款不完整**。"引导者"是个容易被模型过度解读为"让用户开心"的角色——缺少反向约束时，模型会自然滑向迎合。

**修复实现**：在首段直接写入"温和是语气，科学客观是底线"的对立统一表述：
```diff
-JUDGE_SYSTEM_PROMPT = """你是「游戏人生」的成长引导者。加点、提醒、复盘、建议——这些都是你引导用户走向更好的方式。…
+JUDGE_SYSTEM_PROMPT = """你是「游戏人生」的成长引导者——加点、提醒、复盘、建议都是你引导用户走向更好的方式。**但你的引导必须建立在科学与客观之上**：加点严格依据量化锚点库与科学标准，客观如实、不迎合、不夸大（**温和是语气，科学客观是底线，两者缺一不可**）。…
```
同步更新 `docs/DECISIONS.md` 的核心设计理念节，把"引导 ≠ 迎合"写成四条落地原则。

**防复发**：**给 LLM 设定角色时，角色描述必须包含"边界约束"**。只写"你要温和"会让模型牺牲准确性；要写成"温和的是语气，准确是底线"这类**明确的优先级表述**。另外，产品理念变更要**同时更新 prompt 和 DECISIONS.md**——只改 prompt 会让理念在文档里失传。

---

### B-11 · 同一事件出现双判定记录

**commit** `d55cde3`（2026-09-01）· **文件** `routers/events.py`、`services/judge_service.py`

**现象**：判定中心出现"同一事件的两条判定记录"。

**定位过程**：`judge_event` 无任何前置检查，重复调用就重复建记录。

**根因**：**缺幂等保护**。判定接口被重复触发（用户重复点击、前端重试）时没有防护。

**修复实现**：
1. 已入账（confirmed）拒绝重判：
```python
existing_confirmed = (db.query(AIJudgment).filter(
    AIJudgment.event_id == event.id, AIJudgment.user_id == user.id,
    AIJudgment.status == "confirmed",
).first())
if existing_confirmed:
    raise ValueError("该事件已确认入账。如需重新判定，请删除该事件后重新记录，或用「补充信息」调整。")
```
2. 未确认判定（pending/adjusted）先清理再新建（**注：这一版仍是"删旧建新"，其副作用在 B-03 才被发现并改为就地更新**）
3. 路由层补 `ValueError → 400` 的异常翻译：
```python
except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc))
```

**防复发**：**所有"创建资源"的接口都要问：重复调用会怎样？** 加幂等保护；同时服务层的业务拒绝（ValueError）必须在路由层翻译成 4xx，否则会变成 500。
> **⚠️ 这条与 B-03 的关联**：B-11 的修复引入了"删旧建新"，B-03 才暴露了它的副作用。**这是本项目最典型的一对"修 bug 引入 bug"案例**——教训是：修复时选的方案要评估副作用，特别是像"删除"这种破坏性操作。

---

### B-12 · 新列 `is_pure` 为 NULL，下游 schema 校验失败

**commit** `5d3965a`（2026-08-31）· **文件** `database.py`

**现象**：加了轻量迁移（B-14）后列能加上了，但这些新列在**已有行**里是 NULL。`is_pure=None` 导致下游 Pydantic schema 校验失败。

**定位过程**：`ALTER TABLE ADD COLUMN` 对已有行的取值是 NULL——SQLite 不会用 ORM 的 Python 默认值去回填已存在的行（ORM 默认值只在应用层 INSERT 时生效）。

**根因**：**迁移只做了"加列"，没做"数据回填"**。模型层有 Python 标量默认值（`is_pure=False`）的列，历史行仍是 NULL。

**修复实现**：新增列后，对有 Python 标量默认值的列做 NULL 回填（**对已存在列同样执行，幂等**）：
```python
# 标量默认值 NULL 回填（对已存在列同样执行，幂等）
arg = getattr(column.default, "arg", None)
if isinstance(arg, (bool, int, float, str)):
    default_val = 1 if arg is True else (0 if arg is False else arg)
    with engine.begin() as conn:
        conn.execute(
            text(f'UPDATE "{table.name}" SET "{column.name}" = :v WHERE "{column.name}" IS NULL'),
            {"v": default_val},
        )
```
注意 `bool → 1/0` 的转换（SQLite 无原生 bool）。

**防复发**：**迁移 = 结构变更 + 数据回填，两者缺一不可**。设计迁移时问：①列加上了吗？②**已有数据符合新约束吗**？另注意只对**标量默认值**回填——`default=callable`（如 `datetime.now`）或 `server_default` 不属于此列。

---

### B-13 · onboarding 问卷报 JSON 解析失败

**commit** `9a1ae4d`（2026-08-30）· **文件** `prompts/onboarding.py`

**现象**：Onboarding 问卷接口报 JSON 解析失败。

**定位过程**：看 prompt 模板，发现输出格式示例里写的是 `{{ ... }}`——**双大括号**。

**根因**：**模板转义遗留**。写 prompt 时误以为要按 Python `.format()` 规则转义大括号，但本项目用的是 `str` 常量 + 变量拼接（不是 `.format()`），所以双括号被**原样发给模型**。模型照着示例输出 `{{...}}`，JSON 解析自然失败。

**修复实现**：把 4 个 prompt（`QUESTION_SYSTEM_PROMPT`/`PANEL_SYSTEM_PROMPT`/`SUPPLEMENT_SYSTEM_PROMPT`/`PANEL_DISPUTE_SYSTEM_PROMPT`）的输出格式示例统一改回单括号：
```diff
-{{
+{
   "questions": ["问题1", "问题2", ...],
   ...
-}}
+}
```

**防复发**：**确认 prompt 的拼接机制再决定是否转义**。判断规则：用 `.format()` / f-string → 需要转义；用 `str` 常量 + 拼接 / `%` → 不需要。**这类 bug 的特征是"模型严格照抄了示例格式"**——所以调试 LLM 输出异常时，第一步看 prompt 里的示例本身对不对。

---

### B-14 · 模型加列后旧库 INSERT 报 `no column named xxx`

**commit** `e7cb967`（2026-08-30）· **文件** `database.py`、`main.py`

**现象**：新增字段（如 `ai_judgments.analysis`）后，本地已有的 SQLite 文件启动报错 `no column named analysis`。

**定位过程**：`Base.metadata.create_all` **只建缺失的表，不给已有表加列**——这是 SQLAlchemy/SQLite 的标准行为，但对开发期频繁改模型很不友好。

**根因**：**没有迁移机制**。开发期反复加字段，每次都要手删数据库（丢数据）或手写 ALTER。

**修复实现**：新增 `migrate_schema(engine)`，启动链第二步调用——
```python
def migrate_schema(engine) -> None:
    """轻量迁移：为已存在的表补充 ORM 模型新增的缺失列（仅 ADD COLUMN，不删列、不改类型）。"""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # 新表交给 create_all 处理
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_cols:
                continue
            col_type = column.type.compile(engine.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
            with engine.begin() as conn:
                conn.execute(text(ddl))
            print(f"[migrate] 已添加缺失列 {table.name}.{column.name} ({col_type})")
```
启动链接入（`main.py`）：
```python
Base.metadata.create_all(bind=engine)
migrate_schema(engine)  # 为已有表补充模型新增的缺失列（如 ai_judgments.analysis）
```
**关键设计**：新增列**一律可空**——绕开 SQLite "不能 ALTER TABLE 添加 NOT NULL 无默认值列"的限制，且不破坏已有数据。（这是**务实的技术选型**：本地单用户项目不需要 Alembic 的完整能力，100 行内解决 80% 痛点；上云时再换 Alembic。）

**防复发**：**开发期就要有迁移机制，不要等到上生产**。判断标准：只要你的数据"有保留价值"（哪怕只是测试数据），手删数据库就会开始疼。**顺序很重要**：`create_all`（建新表）→ `migrate_schema`（补旧表列）→ 种子数据 → 备份。

---

### B-15 · 热力图只渲染了最近一周（ECharts `calendar.range` 的日期格式陷阱）

**现象**（v1.10 P2-2）：热力图改版后，库里有 20 天记录、API 也返回 19 条数据，
但画面上**只有最近两天着色**，其他位置一片空白。

**定位过程**（这套排错顺序值得学）：
1. 先排除**数据层**：直接打 `GET /api/events/heatmap` → 19 条、日期分布正确 → 数据没问题
2. 再**量化 DOM 现象**：在页面里用 `getImageData` 统计 canvas 中"蓝色像素"的总数与横向分布
   —— 只有 2773 像素（≈3 格），而 19 格应有 ~14000 像素 → 确认是渲染层丢数据
3. 临时 `console.log` 打出图表入参 → `range: ['2026-06','2026-09']`、`n: 19`
4. **假设验证**：把 range 换成完整日期 `['2026-06-01','2026-09-30']` → 着色像素跳到 **14476**（≈16 格）→ 命中

**根因**：ECharts 的 `calendar.range` 把 `'2026-09'` 这类 `YYYY-MM` 字符串按**月初**解析，
日历实际只覆盖到 9 月 1 日，**超出范围的数据点被静默丢弃**——不报错、不警告，图看上去"正常"。

**修复**（`AttributePanel.vue::renderHeatmap`）：
```js
// ❌ 被解析成月初 → 9/2 之后的数据全丢
range: [`${fmt(start)}`, `${fmt(end)}`]     // ['2026-06', '2026-09']
// ✅ 完整日期
range: [rangeStart, rangeEnd]               // ['2026-06-01', '2026-09-30']
```

**防复发**：遇到"图表看起来对、其实少了一半数据"的问题，**先用像素 / 数据量做量化对照**
（预期格数 × 单格像素 ≈ 实际着色像素），比肉眼盯图快得多；
并且**日期类参数一律写全**（`YYYY-MM-DD`），不要依赖库对 `YYYY-MM` 的隐式解释。

---

### B-16 · 新增属性层级后，子维度混进雷达图并成了独立条目

**现象**（v1.10 P1-3）：创建子维度后，属性面板**条形列表尾部多出两个 0/100 的条目**
（"算法解题""工程实现"），**雷达图轴数从 13 涨到 15**——与设计直接冲突（文档明确"子维度不上雷达图"）。

**根因**：`attributes` 表新增 `parent_id` 后，**所有"取全部属性"的查询都变成了"取主 + 子"**。
`GET /api/attributes` 只是直接入口，此外还有 5 处"主维度上下文"消费点：
judge 的 `_attribute_context`、challenge 的短板上下文、shop / exemption 的属性上下文、stagnation 的停滞巡检。

**修复**：逐个消费点补 `Attribute.parent_id.is_(None)`——
子维度只在属性面板**缩进展示**，数值上雷达图 / 趋势图，语义上进 prompt 上下文。

**防复发**（通用）：**给一张表新增"层级 / 分类"列时，必须把该表的全部读取点列一遍**，
逐个回答"这里要不要包含子项"。别靠记忆，直接搜：
```bash
grep -rn "query(Attribute)" app/     # 列出所有读取点，逐个判断
```
这是"多入口不同步"（B-01 / B-04 同类）在新维度上的再现——**新增一个层级 = 新增一类入口**。

---

### 本章小结：16 个 bug 的类型分布（这是最有价值的部分）

把 16 条按**根因类型**归类，能看出 bug 的"高发地带"：

| 根因类型 | 条数 | 涉及 bug | 预防手段 |
|---------|------|---------|---------|
| **规则/prompt 边界不清** | 4 | B-06、B-07、B-09、B-10 | 正负场景对称走查；判据收敛到单一维度；角色描述必带边界约束 |
| **多入口/多数据源不同步** | 2 | B-01、B-04 | 盘点所有入口，核对参数与副作用对等；盘点一次操作影响几个接口 |
| **写库语义错误** | 1 | B-03 | "更新"必用 update，禁止"先删后建"；新增状态值全局搜映射表 |
| **外部依赖无容错** | 1 | B-02 | 韧性六问 |
| **对模型输出的格式假设** | 2 | B-05、B-13 | LLM 输出永远不可全信；异常时先看 prompt 示例本身 |
| **迁移不完整** | 2 | B-12、B-14 | 迁移 = 结构变更 + 数据回填 |
| **辅助功能阻断主流程** | 1 | B-08 | 启动链每步问"失败该不该阻断" |
| **幂等缺失** | 1 | B-11 | 创建型接口必问"重复调用会怎样" |
| **外部库隐式语义（静默丢数据）** | 1 | B-15 | 日期/枚举参数写全格式；用"像素/条数"量化对照预期 |
| **新增层级后消费点漏收敛** | 1 | B-16 | 加层级列 → `grep` 出该表所有读取点，逐个判断是否含子项 |

**三条最值得记住的**：
1. **多入口是 bug 的温床**（B-01/B-03/B-04）——同一个业务动作有几个入口？它们的代码路径、参数、副作用一致吗？
2. **修复方案本身要评估副作用**（B-11 → B-03 这一对）——"删旧建新"图省事，代价是三重连锁伤害
3. **LLM 相关 bug 一半在 prompt、一半在容错**（B-05/B-06/B-07/B-09/B-10/B-13）——改 prompt 前先问"规则的边界在哪、正负场景都覆盖了吗"

---

## 第 12 章 读懂他人代码的方法论（从本项目提炼）

1. **先跑起来再看**：start.bat 一键起 → 点一遍页面 → 每个功能对应到目录里的文件
2. **顺着一条请求读穿**：从 api.js 找到 fetch → 路由 → 服务 → 模型 → 数据库，一条链读完比十个文件乱翻有效
3. **先读 models**（数据结构是骨架）再读服务层（业务逻辑是血肉）
4. **看注释里的"为什么"**：本项目注释大量记录设计动机（如 migrate_schema 为什么要可空列）——这是最有价值的部分
5. **改之前先做只读实验**：查库、print、断点——证据先于猜测
6. **git log 当历史书读**：`git log --oneline` **106 个提交**就是这个项目的演化史；`git log --grep="^fix"` 的 14 条在第 11 章有完整存档，可以直接对照
7. **同一功能找所有入口**（B-01/B-03 教训的方法论化）：看到"重判"别只看 `judge_event` 一处——`supplement`/`dispute`/`update_event` 都可能在同一条链上。**多入口是 bug 的温床，读代码时主动盘点入口数量**
8. **区分"计划中的字段"与"已实现字段"**（v1.7 现状）：读文档时注意标注——`events.item_id`、`checkin_items` 表属 v1.7 计划，代码中尚不存在；`merged_with` 同理。**看代码为准，看文档为辅**
9. **读代码时同步建"故障意识"**：看到 `.delete()` 先问"这个删除会连带什么"；看到外部调用先问"失败/超时/返回畸形怎么办"；看到"更新"先问"是原地改还是删旧建新"——**第 11 章的 14 个 bug 就是这三类问题的实例集合**
10. **改 prompt 前先做三查**：查逃逸出口、查默认值倾向、查条款冲突；**改完正负场景对称走查一遍**（B-06/B-07 都栽在"只考虑正面"）



