# 项目代码详解 —— my-life-rpg 全代码教学

> **2026-10-24 最新节点**：10月21日改版已于云端发布并完成外网检查，见[部署记录](../review/daily_use_public_2026-10-21/DEPLOYMENT_RESULT.md)。本轮根据手机实机反馈补修折叠、待办与属性展示等，仍为本地未发布改动，见[本轮记录](../USABILITY_REPAIRS_2026-10-24.md)及第21章；不能把以下早期“未实现/未上云”说明当作今天状态。

> **2026-10-21 最新学习节点**：已有云端使用后，进入“日常反馈 → 完整交互 Demo → 用户认可 → 新开发规格/Writer 任务书”。见[本轮规格](../DAILY_USE_REDESIGN_DEV_SPEC_2026-10-21.md)、[任务书](../WRITER_DAILY_USE_REDESIGN_2026-10-21.md)及第18章。Demo 的143项检查是本机脚本证据，新版正式业务尚未实现/发布；下方旧“未上云/未迁移”状态按原日期阅读。本轮没有重新登录云端验收。

> **2026-10-18 实施补记**：已按完整任务书完成本地代码和隔离验收，HEAD 仍为 `ec5259b`，改动尚未提交。后端119通过／2个真实PG跳过，前端构建通过；浏览器逐项及截图见[本轮交付](../FULL_SYSTEM_DELIVERY_2026-10-18.md)。下文“尚未实现”是当天文档准备阶段的历史状态，本轮实现说明见文末新增小节。未推送、未部署、未迁移真实旧库。

> **2026-10-18 学习进度更新**：项目已到“私有试用反馈 → 完整 Demo 确认 → 正式开发规格”阶段。当前代码核对 HEAD 为 `ec5259b`，新一轮尚未实现；[本轮开发规格](../FULL_SYSTEM_DEV_SPEC_2026-10-18.md)与[Writer 任务书](../WRITER_FULL_SYSTEM_2026-10-18.md)是接续入口。下文 10 月 13 日基线及当时备案／部署信息按历史阅读，不代表今天重新核验。

> **目标**：读完能 ①完全理解本项目全部代码 ②读懂他人写的类似代码 ③修改与复用。
> **读者假设**：会 Python 语法/HTTP 基础/SQL 增删改查/HTML-JS 基础；框架级概念（ORM、依赖注入、Vue 响应式等）用**概念卡**补齐。
> **当前代码基线（2026-10-13 补写）**：HEAD `ba7031e96a9c91a667eaeb28b4a0a4606f5f8a15`，运行包 `rr-20261010-ba7031e9-1463a8b6ca15`。已知云端证据截至 10 月 12 日，为邀请制私有试用；没有正式公网发布或迁移旧数据。本次只更新学习文档，没有重新验证服务器实时状态。
> **原笔记写到哪里**：第 1~10 章主体是 v1.6 的逐层讲解；后续局部修订和 B-17~B-19 已补到 10 月 8 日 v1.11。旧示例保留作演进记录，**不能把旧同步流程、明文 KV 模型配置、清库和启动顺序照搬到当前云端**。
> **本次更新范围**：校正历史说明；第 11 章补至 B-46，按五栏区分已修、现场修复和未修；新增第 13 章当前云端代码链路、第 14 章发布与运维、第 15 章试用审查与后续停点。代码来自本地只读核对，运行结果引用对应日期交付和用户截图，不用历史 PASS 冒充今天的新测试。
> **更新约定**：用户说"更新学习文档"时，按本次要求更新（新功能→补对应小节；重构→改对应讲解）。
> **⚠️ 长期维护约定（2026-09-22 追加）**：**此后每次修复 bug 或排查异常，都要在第 11 章「故障档案」按五栏格式（现象→定位过程→根因→修复实现→防复发）建档**，并在索引表登记一行。这不是可选项——本章的价值完全依赖"当时就记"，事后补写会丢失定位过程与证据细节。

---

**阅读导航**：初学者先读[业务路线图](BUSINESS_ROADMAP.md)的阶段 4~6，再读本文件第 13 章。想查故障怎么定位，读第 11 章；想理解这次服务器部署，读第 14 章。待讨论的产品意见统一在[试用反馈](../USER_TEST_FEEDBACK_2026-10-11.md)，不是已实现功能。

## 第 0 章 阅读前的 6 张概念卡

**卡1 · ORM 与 SQLAlchemy**：不用手写 SQL，把"表"映射成 Python 类、一行数据映射成一个对象。`Attribute` 类 ↔ `attributes` 表；`db.query(Attribute).filter(...)` ≈ `SELECT * FROM attributes WHERE ...`。改对象属性后 `db.commit()` 即写库。
**卡2 · 依赖注入（FastAPI `Depends`）**：路由函数参数写 `db: Session = Depends(get_db)`——每次请求时 FastAPI 自动调用 `get_db()` 造一个数据库会话塞进来，请求结束自动关闭。你不用手动管理连接生命周期。
**卡3 · Pydantic 校验**：`schemas/__init__.py` 里的 `EventCreate` 等类是"请求体说明书"——客户端 POST 的 JSON 自动按它校验/转类型，不合法直接 422，业务代码拿到的永远是干净数据。
**卡4 · Vue 响应式**：`ref(值)` 创建响应式数据，值变→页面自动更新；`computed(() => ...)` 是"依赖变化才重算的派生值"；`watch([a,b], fn)` 监听变化执行副作用（如存缓存）；`v-if`/`v-for`/`v-model` 分别是条件渲染/循环/双向绑定。
**卡5 · LLM API 调用模式**：OpenAI 兼容 SDK 的固定姿势——发一个 messages 数组（`system` 设定角色规则、`user` 给数据），返回 `resp.choices[0].message.content`。`temperature` 控制随机性（判定用 0.3 保证口径稳定）。
**卡6 · JSON 列**：SQLite 的 JSON 类型列存的是"JSON 字符串"，SQLAlchemy 自动帮你序列化/反序列化——Python 里当 dict/list 用。**坑**：用原生 sqlite3 直接读该列拿到的是字符串，需 `json.loads`（本项目诊断时踩过）。

---

## 第 1 章 全局架构（v1.6 本地版历史；当前架构见第 13 章）

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

### 1.3 启动链（本地兼容模式；2026-10-13 校正顺序）

`uvicorn app.main:app` 后依次发生：
1. `backup_now()` 先给已有本地库留迁移前副本
2. `Base.metadata.create_all` 建缺失的表（已存在则跳过）
3. `migrate_schema(engine)` 给已有表补列及回填默认值
4. `seed_anchors` 内置锚点幂等写入（按 name 去重）
5. `get_or_create_default_user` + `ensure_dimensions` 补默认用户和缺失维度
> **设计思想**：初始化应尽量幂等（重复执行不重复创建业务对象），但幂等不等于无须备份或故障测试；时机、异常与数据来源仍要单独核对。

**云端不同**：启动只检查显式 DB_URL、HTTPS origin、主密钥和 Alembic 版本，不自动建表/补列/创建默认用户/备份；先由独立 migrate 任务执行升级，再初始化账号。不要把上面本地自动迁移用于云端。

---

## 第 2 章 数据模型层（v1.6 的 10 表教学；当前增量见 13.2）

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
| events | 生活事件 | `source` form/journal、`params` 与原文。**当前 `item_id` 已实现**；另有正文版本、分析意图、发生时间、删除标记等；不可再当成 v1.7 计划字段 |
| ai_judgments | 判定记录 | `suggested_changes`/`final_changes` 双字段——建议值 vs 置信度加权后实际入账值；`status` pending/confirmed/adjusted/rejected 状态机；**`analysis`**（v1.1，分析过程推理链）；**`confidence_reason`**（v1.4，低置信度必填理由）；**`revision_notes`**（v1.6，重判增量修订说明） |
| judgment_logs | 判定审计 | action: create/confirm/supplement/dispute/rejudge/maintain/delete/invalidate，全程可回溯。**v1.5 起重判不再删旧日志**（只增不删） |
| goals | 目标 | `audit` JSON 记修改/取消/达成/失败流水 |
| anchors | 量化锚点库 | `calibrated_value` 用户校准值（NULL=用默认 base_value）——"科学但用户可调" |
| settings | KV 配置 | `hidden_attributes`/`disabled_attributes`（维度开关）、`gamification_modules`（模块开关）、`unreal_count`（不实计数）、**`llm_primary`/`llm_aux`**（v1.4 BYOK 双模型组）全塞这张表，避免加列 |

> **经验校正**：①业务对象显式归属用户，仍须查询过滤、写入引用验证与隔离测试，不能称“多用户零返工”；②当前值与流水分离，方便核账；③普通配置适合 KV，**敏感凭据和有独立生命周期的数据不能一律塞进 KV**。云端模型 Key 已移到专门的 `llm_credentials` 加密表，见 13.4。

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
本地开发前端 5173 调后端 8000 属跨域。当前代码仅允许 localhost/127.0.0.1:5173，云端仅允许配置的 `public_origin`，支持凭据。旧版 `allow_origins=["*"]` 已不是现状；CORS 也不能替代身份验证与 CSRF/Origin 检查。

---

## 第 4 章 LLM 服务层（v1.6 设计；当前云端差异见 13.4/13.6）

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

> 下表 `.env` 回退仅保留于本地模式；云端不使用平台公共 Key，读取本人 `LLMCredential`。主/辅组之间的用途回退仍存在，不代表一定使用设置页当前正在编辑的组。

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

## 第 6 章 核心业务链路精讲（v1.6 同步链路历史；当前入口见 13.5~13.7）

> 当前云端先保存文字，再提交持久分析任务；旧同步判定入口拒绝执行。确认与撤销仍须追到服务层学习，但要结合 v1.11 的事务、实际流水和版本校验。旧例中的“删除”不能读成当前物理删记录。

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

## 第 8 章 前端精讲（v1.6 组件演进；当前路由和状态见 13.9）

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

> 本章模式可对照**第 11 章**的故障档案学习；其中 v1.6 历史经验须结合当前云端边界，不能作为无条件规则。

1. **幂等初始化链**：本地先备份再建表/轻量迁移/种子；云端显式迁移，启动只核对版本（B-08/B-14/B-23）
2. **LLM 服务层单例 + 三级 JSON 容错 + 一次重试**：业务零直接依赖 SDK；重试只吃瞬时抖动，不掩盖系统错误（B-02/B-05）
3. **事实基准表（锚点库）**：LLM 判定类产品防口径漂移的标准解法
4. **建议→确认→生效**：AI 输出一律 pending，人确认才落账
5. **append-only 流水 + 反向回滚**：删除不改历史，账目永远可对（B-03）
6. **异常即协议**：服务层自定义异常，路由层翻译 HTTP 语义（B-11）
7. **prompt = 活的规格说明书**：每节堵一个真实 bug；改前查逃逸出口/默认值倾向/条款冲突；软提醒升级为**输出前硬校验步骤**（B-06/B-07/B-09/B-10）
8. **前端状态分档持久化**：localStorage（草稿）/ sessionStorage（**只存 id 的会话指针**）/ DB（业务数据）——**缓存指针不缓存副本**（B-03/B-04）
9. **枚举展示映射表**、**emit 通信**、**chart dispose**、**双端一致的业务拦截**（B-03：新增状态值要全局搜映射表）
10. **普通配置可用 KV，敏感对象需要专门生命周期**：v1.4 BYOK 曾借 KV 提前交付，云端凭据现已迁到加密模型；通用 GET 必须白名单（B-19/B-25）
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

以下是当前修改时的阅读路径，不是授权在真实数据上练习；结构/规则改变要先定方案，在独立测试库验证。

| 任务 | 步骤 |
|------|------|
| 加一个属性维度 | constants 的名称/别名、基线、模型提示、图表、导出等共同核对；云端用显式迁移/受控补数，不靠 API 重启自动补用户 |
| 加一条锚点 | 定义基准与依据；本地种子可幂等，云端通过受控初始化/迁移；区分内置模板与个人校准 |
| 调判定规则 | prompt、解析与业务护栏共同核对；事件/总结场景分开，先用合成样本和已获授权副本评测，不擅自重算历史 |
| 加一张表 | ORM＋Alembic＋归属保护＋导出/备份/导入引用审查；云端先显式迁移，启动只检查版本 |
| 加一个接口 | schema→认证/授权/版本/回执/事务→router→api.js→组件→HTTP 隔离回归；读操作不偷偷发奖 |
| 换 LLM 供应商 | 云端在批准供应商中配置本人主/辅组，切换供应商重新绑定 Key；扩大端点范围须审查出口保护，不是只改 .env |
| **加一个"AI 输出字段"** | prompt 输出契约→解析/数值或引用校验→存储模型/显式迁移→响应 schema→前端展示→导出及回归。是否需要新列先判断字段生命周期 |
| **改重判相关逻辑** | ⚠️ 先确认写入语义：必须**就地更新**（id 不变、审计只增不删）；涉及"AI 会不会改口"时同步检查增量修订契约那一节 |
| **加一个前端复用逻辑** | 判断逻辑还是外观——逻辑进 `frontend/src/composables/`，外观进 `components/`；页面级策略留在页面里 |
| **改 LLM 容错策略** | `llm_service.py` 的 `_parse_json`（解析）与 `chat_json`（重试）分开改；重试次数改动要考虑成本与重复执行风险 |

## 第 11 章 故障档案（Bug Ledger）—— 每个 bug 的根因与修复实现

> **为什么单独成章**：第 6 章的链路精讲讲的是"代码现在长什么样"，第 4 章的阶段 4 讲的是"业务教训是什么"，但**两者都没回答"出问题当时怎么定位的、改的是哪一行、为什么这么改"**。
> `git log` 里一条 `fix(A4): 实测发现并修复两个链路 bug`，三个月后你根本不知道是哪两个——本章就是把这类信息**固定成五栏格式**留档，可反查、可复现、可迁移。
>
> **五栏格式**：**现象**（用户/测试看到什么）→ **定位过程**（怎么找到的，证据是什么）→ **根因**（本质原因）→ **修复实现**（改哪个文件哪个函数、代码形态）→ **防复发**（怎么保证不再犯）。
>
> **收录范围**：**52 条**（B-81~B-83 见文末 v1.13.1 三条）。B-01~B-19 保留原档；B-20~B-46 补充 v1.11、发布复审、部署及私有试用。能核实的修复给出提交或交付文件；现场诊断和未实施意见明确标状态，**没有对应代码提交就不编造 hash**。同一根因涉及多项验收时合并建档，不把反馈数量等同于已修复数量。
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
| B-17 | 点一下"重置全部数据"就真删了全部真实记录与审计 | 危险操作无前置校验 | `3d26327` | 10-08 |
| B-18 | 删除一笔误提交，把自己的审计证据也一起删了 | 用物理删除实现"撤销" | `5dd763b` | 10-08 |
| B-19 | 打开设置页，响应体里带着模型 API Key 明文 | 通用接口无字段白名单 | `2e0ebcf` | 10-08 |

**本次续补索引（补写日期 2026-10-13；发生/证据日期见各档）**：

| 编号 | 问题 | 状态及主要依据 |
| --- | --- | --- |
| B-20 | 属性、金币、挑战/目标结算不在同一原子边界 | v1.11 已修；交付 18 项表及事务测试 |
| B-21 | 非有限值、别名重复与封顶建议污染入账 | v1.11 已修；`2118a26`、`5f42eee` |
| B-22 | 已入账仍能修改、旧响应覆盖、失败重试造新事件/缓存损坏 | v1.11 已修；`006b40d`、`b75bd79`、`a26309a`、`835e42a` |
| B-23 | 启动备份晚于迁移、备份错误路径或清理异常 | v1.11 已修；`e3c20a8` |
| B-24 | 浏览发启动资金、待结算删除及删除后追授 | A00 已修；`22ce20e` |
| B-25 | 换供应商沿用另一家的 Key | R01 已修；发布准备交付 |
| B-26 | 兑换响应未知时重新购买导致重复扣币 | R02 已修；真实 HTTP/合成 PG 回执验证 |
| B-27 | 导入只映射外键，遗漏 JSON/流水语义引用 | R03 已修合成场景；真实迁移未做 |
| B-28 | 模型持续慢速输出绕过单次 read timeout | R06 已修总截止；真实 Linux 边界仍待验 |
| B-29 | db 仅声明端口却被误判公网映射 | 运维复审已修；Publishers 样本 |
| B-30 | restic 临时容器 host 破坏保留分组 | 运维复审已修；真实本地合成仓库 |
| B-31 | 首页 200 掩盖 API/DB 故障、Caddy 内部路由暴露 | 运维复审已修；真实本机 Caddy |
| B-32 | Docker 29 跨存储后端外层 ID 不同 | `835ebc2` 已修 schema v2；目标校验通过 |
| B-33 | 官方 PostgreSQL 镜像缺省 User 触发校验失败 | `ba7031e` 已修；缺省 User 与生产导入验证 |
| B-34 | PG 密码末尾换行引起网络认证失败 | 现场修复通过；初始化 SQL 源修复未做 |
| B-35 | 私有网页不可达：隧道在，但浏览器走代理 | 定向探测支持代理路径问题；专用直连浏览器 |
| B-36 | SSH `Connection reset` | 断开已见；唯一根因未知，保活不能保证连接 |
| B-37 | 错误模型名可保存、连接测试反馈不明显 | F02/F03/F16，已定位，未实施 |
| B-38 | 同时显示不分析/待补充/请绑定模型 | F05/F09，条件取错，未实施 |
| B-39 | 单事件被追问全天生活面 | F07，旧 journal 规则诱因已核实，未实施 |
| B-40 | 测试记录与真实事件标为已合并 | F10，完整唯一根因未证实，未实施 |
| B-41 | 未评估 50 起点标“熟练” | F11，统一区间标签冲突，未实施 |
| B-42 | 详情页可能一直显示排队中 | F14，代码缺更新机制，云端时序未复现 |
| B-43 | 390px 金币 80 断成两行 | F15，本机浏览器复现，未实施 |
| B-44 | 原生确认框与大块金币吸顶不协调 | F13，代码与截图一致，方案待讨论 |
| B-45 | 导出遗漏关联/审计业务表 | P1-9 已修；`93bacb4`，当前又扩至格式 3 |
| B-46 | 配置挂载不回填、建档状态/成就追溯入口不一致 | P1-1/P1-4/P1-5 已修；云端 GET 语义再收紧 |
| B-47 | 金币金额是规则按档位算的，AI 只给 small/medium/large | 设计遗留：规则定钱、模型补理由 | `808fe9c` | 11-16 |
| B-48 | 改原文后「原文已变化」提示在标题下，滚到按钮就看不见 | 反馈与动作不同屏 | `4ee990d` | 11-16 |
| B-49 | 心愿定价必然 422，界面直接显示 Pydantic 的 loc/type/input | 前端把空串当数字发、错误未转译 | `88acec3` | 11-16 |
| B-81 | 商品加了 `pricing_mode` 列却没写 alembic 迁移，云端一上线商店页 500 | 云模式不走 `migrate_schema`，只加模型不算加列 | `ae32c85` | 11-17 |
| B-82 | 计时页按 demo 改了 CSS，界面却毫无变化 | `.timer-ring` 声明块少一个 `}`，后面整段被吞 | `8002e5b` | 11-17 |
| B-83 | 关掉自动定价后仍每天重估，打开却没反应 | 新列 `pricing_mode` 只读、旧列 `auto_pricing` 只写，两个开关脱钩 | `700ceb3` | 11-17 |
| B-84 | 同一个「今日已得」在设置页 28、在分析页 25 | 改口径只改了 `/api/trial`，页面真正读的是 `preview.used` | `46a0085` | 11-17 |

> **B-17~B-19 的来源**是一次**外部只读审计**（Codex，2026-10-08，`docs/review/CODEX_AUDIT_2026-10-08.md`）——它不是在"跑测试"时发现的，而是**拿项目自己写下的红线去逐条量代码**量出来的。这三条的共同特征是：**它们都不是功能坏了，而是"某个安全性设计只在主路径上实现了"**。这是本项目第一次系统性地做"红线 vs 实现"对照，值得单独记住。

---

### 2026-10-18 实施故障索引（接 B-46）

| 编号 | 现象 | 当前结论 |
| --- | --- | --- |
| [B-47](#b47) | 找回邮箱响应正文相同，已绑定邮箱仍因同步 SMTP 更慢 | 持久统一受理＋worker重试，假邮件已验 |
| [B-48](#b48) | 周一草稿出现在周二，晚回覆盖当前日期 | 复合草稿键＋读取代次保护，真实Vue验证 |
| [B-49](#b49) | 只过滤原文仍可能把旧记忆／派生字段交给模型 | 服务端统一来源边界，捕获各用途payload |
| [B-50](#b50) | 多来源重复结算、重分段改写再领、过早撤销共享属性 | 稳定事实／显式关系／整组原子确认及最后来源回滚 |
| [B-51](#b51) | 取消问答导出后，游戏附件又把内容带回来 | 附件复用同一投影；四格式响应与下载验证 |
| [B-52](#b52) | 新券可能沿用上一次手填实际秒数 | 来源独立额度＋新会话清草稿，25／30／25验证 |
| [B-53](#b53) | 问卷确认后资金正确，建档字段却丢失 | 余额入口refresh前flush，原子一次建档回归 |
| [B-54](#b54) | 新坚持奖励领取后，旧自动入口仍可能再发同等奖励 | 共享等价身份；新试用只发现、不自动授奖 |

### 2026-10-19 独立审查修复索引

| 编号 | 现象 | 当前结论 |
| --- | --- | --- |
| [B-55](#b55) | 旧清单关闭后任意项目名称仍进入回顾模型 | N01：旧任意 key 排除，仅保留无正文状态计数 |
| [B-56](#b56) | 取消历史，JSON 表附件仍带旧原文 | N02：记录和附件共用所选投影，四格式完整响应验证 |
| [B-57](#b57) | 计划名称写45分钟，页面实际开始30分钟 | N03：版本化预计时长与服务端开始快照，20／45及刷新验证 |
| [B-58](#b58) | 先记录后建档的首记领取返回500 | N04：变更资格前409，资格保留并引导选起点 |
| [B-59](#b59) | 娱乐使用一小时和三小时，定价模型消息完全相同 | N05：近30天实际确认秒数／日分布，购买另列且不强制涨价 |
| [B-60](#b60) | 无历史旧计划设为明天改时长后，今天入口消失 | R01：首次编辑先保留旧基线，再追加未来版本 |
| [B-61](#b61) | 2026-10-21：模型独立测试失败，但用户报告定价可成功 | 本轮已修预算/安全诊断和分类；真实供应商原响应及语义仍NOT_RUN |
| [B-62](#b62) | 问卷评估使用了错误builder输入格式 | 已修；AI面板/合法资金范围回归 |
| [B-63](#b63) | 价格撤权晚回返回500而非可恢复冲突 | 已修；失败审计、零商品、409 |
| [B-64](#b64) | 回归刷新跳题、旧缓存无版本 | 已修；真实Vue/API草稿恢复 |
| [B-65](#b65) | 用途服务存在但事件/报告未完整接入 | 已修；四用途实际消息捕获 |
| [B-66](#b66) | 同步分析结果未知可重复付费 | 已修当前带UUID路径；真实PG并发待验 |
| [B-67](#b67) | 项目编辑将服务器timezone回传，严格输入拒绝 | 已修显式表单字段；真实两类页面保存 |
| [B-68](#b68) | 打开编辑隐式改期、间隔基准与生效混用 | 已修独立effective_from；历史/日期回归 |
| [B-69](#b69) | 每日同UUID只重放首三项，后续项目饥饿 | 已修有限续批/未知槽/公平队列 |
| [B-70](#b70) | 共用项目页漏接照顾清单配置、排序与移除 | 已修共用入口；旧原文/事实/结算保持 |
| [B-71](#b71) | 首次部分完成在事件flush前缺非空结果字段 | 已修创建时初始化outcome/facts；真实页面回归 |

### 2026-10-24 手机使用反馈补修索引

| 编号 | 现象 | 当前结论 |
| --- | --- | --- |
| [B-72](#b72) | 新版事实已确认，首页仍显示待处理 | 本地已修：按当前事实组确认状态退出待办，零奖励也覆盖 |
| [B-73](#b73) | 计划表单全展开，手机弹窗长且排序数字难懂 | 本地已修：默认折叠、四项首屏列表、原子上移/下移与固定操作栏 |
| [B-74](#b74) | 停用奖励仍混在主列表 | 本地已修：移除入口与归档列表，旧券与流水保留 |
| [B-75](#b75) | 首次分析失败但找不到当时报错 | 原因待核实；本地补任务历史与安全错误说明，不虚构失败原因 |
| [B-76](#b76) | 内容日期仍显示浏览器混合分段占位 | 10月22日本地补修；手账筛选遗漏原生日期框，尚未发布 |

### 2026-11-11 发布流程补修索引

| 编号 | 现象 | 当前结论 |
| --- | --- | --- |
| [B-77](#b77) | 第二次云端发布拿不到彩排通行证 | 已修：一次性补发断言挡所有后续发布；探针通用化为只读恢复校验，专项断言留 git 历史 |

### 2026-11-11 事实合并口径索引

| 编号 | 现象 | 当前结论 |
| --- | --- | --- |
| [B-79](#b79) | 每天记录的「阅读」都被问是不是同一次行动 | 已修：跨天不再进入合并候选，只在同一内容日内比较；选已有事件的列表默认只列当天 |
| [B-80](#b80) | 「是否同一次行动」一出现就无法继续分析和入账 | 已修：关系核对改为可选，默认按另一次行动继续；旧 `unresolved` 记录也不再被卡住 |


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

### B-17 · 点一下"重置全部数据"就真删了全部真实记录与审计

**来源** 外部审计（Codex）· **文件** `services/onboarding_service.py`、`routers/onboarding.py`、`SettingsView.vue`、`Onboarding.vue`

**现象**：设置页有一个"重置全部数据"按钮，点下去会**直接物理删除**事件、判定、审计日志、属性流水、目标；**不备份、不走删除接口**，而且**不清理金币、挑战、兑换等关联状态**——于是留下了"金币余额还在、但产生它的记录全没了"的悬空状态。另一个"重新建档"（普通 reset）更隐蔽：它允许重新生成面板，**用新值覆盖当前值与初始快照，却保留旧属性流水**，直接破坏了本项目最核心的账目恒等式「初始快照 + Σ delta = 当前值」，还可能**再发一次启动资金**。

**定位过程**：审计者的做法值得学——它没有去"跑"这个按钮，而是**把项目红线列出来，逐条在代码里找出路**。第一步定位到 `reset_all_data()` 的实现是 `for model in (JudgmentLog, AIJudgment, AttributeHistory, Event, Goal): db.query(model)...delete()`，与红线「禁止物理删除」正面冲突。第二步反查 `_generate_panel()`，发现它**没有任何"是否已建档"的前置检查**，于是"重新建档"可以覆盖快照。第三步对照真实库：`attribute_history` 已有 124 条流水——**只要点一次，恒等式就永久坏掉**。

**根因**：**开发期的便利功能没有在开发期结束时退役。** `reset-all` / 重建面板是为"反复调试问卷流程"造的脚手架，上线后忘了拆。更深的问题是**服务层没有任何前置断言**——所有防线都在"用户不会去点那个按钮"这个假设上。

**修复实现**（v1.11 P0-1）：
1. 新增 `_assert_unbuilt_profile()`：已有 `onboarding_completed` / `initial_attributes_snapshot` / 任何 `attribute_history` → 抛 `ValueError`。
2. `reset_all_data()` 直接抛错停用；`reset_onboarding()` 改为**只清问卷状态，不碰真实数据**。
3. `_generate_panel()` **在第一条模型调用之前**插入同一断言——**防止绕过路由直接调 service**。
4. 路由层捕获 → 409。前端**移除**两个按钮（不只是隐藏）。

**防复发**：
- **"能为调试而清库"的能力，上线前必须逐个拆掉。** 检查项：所有 `db.query(X).delete()` 的批量调用点，问一句"这是调试脚手架还是业务需求"。
- **服务层要有自己的防线**，不能只靠路由或前端约束。任何"破坏性操作"的 service 入口都应有前置断言。
- **真实数据的存在本身就是一道防线**：本库已有 124 条流水，任何"重建基线"的操作都不再安全。**新功能上线时应重跑一遍这类断言。**

**施工验收（2026-10-08）**：`3d26327`；内存库 17 表计数/基线/余额前后不变，两个重置接口 409，直接生成被拒。详见 `docs/review/V1_11_DELIVERY_2026-10-08.md` 与 `tests/test_v1_11_safety.py`。

---

### B-18 · 删除一笔误提交，把自己的审计证据也一起删了

**来源** 外部审计（Codex）· **文件** `services/judge_service.py:828`（`delete_event`）

**现象**：`delete_event()` 的行为自相矛盾——它**先写一条 `delete` 审计留痕**（表示"我要删了"），**紧接着把该判定的全部审计日志和判定记录物理删除**（`db.query(JudgmentLog)...delete()` + `db.delete(judgment)`）。结果是：**删除操作把自己的证据消灭了**——事后只有一条"删除事件"的日志，看不出**曾经判定过什么、加了多少分**。更隐蔽的第二个问题：回滚用的值是 `judgment.final_changes or judgment.suggested_changes`——**当实际入账为空时（例如属性已 100 封顶、实际加 0），它会回退到"名义建议值"**，于是删除一个"实际没加分"的事件，反而**倒扣了 5 分**。

**定位过程**：审计者的手法是**读代码的"意图声明"再对照实现**。这个函数的第一行注释写着"全程留痕"、"历史入账流水保留，与回滚流水形成完整账目"——**说明作者本意是要保留审计的**。但往下读 5 行就是 `JudgmentLog...delete()`。**注释和代码在同一个函数里打架，这就是 bug 的定位信号。**

第二个问题更典型：`final_changes or suggested_changes` 这个 `or` 写法的本意是"没有最终值就用建议值兜底"，但**没有考虑"final_changes 是空列表"这种情况**——空列表在 Python 里是 falsy，于是 `or` 走到右边，用了建议值。**这是"用 or 做默认值"的经典陷阱。**

**根因**：两处。① **用物理删除实现"撤销"语义**——这正是 v1.5 B-03 立下的铁律禁止的做法（B-03 的教训在同一个文件的同一个章节）。② **回滚依据取错了数据源**——应该用"真实发生过的流水"，而不是"当初建议改多少"。

**修复实现**（v1.11 P0-5）：
1. `Event` 新增 `is_deleted` 布尔列（启动迁移补列 + 回填 `False`，不重建表）。
2. 删除改为**逻辑删除**：条件 UPDATE 抢占 `is_deleted`，判定状态改 `"deleted"`，**一行都不删**。
3. 回滚改为**汇总真实 `attribute_history` 流水**（按 `attribute_id` 累加 delta），再反向 + 夹取——**彻底不用建议值**。
4. ⚠️ **必须给 10 处消费点加 `Event.is_deleted.is_(False)` 过滤**（判定上下文、热力图、周报、成就计数、连续日记、券的近期事件、打卡统计、记忆摘要、子维关联…）——**这是本条真正的难点：漏一处，用户就会看到"删掉的事件还在影响 AI 判断"**。这与 B-16 是同一类错误。

**防复发**：
- **"删除"这个词要拆成两件事问：用户想不想看到它？数据该不该消失？** 前者是逻辑删除，后者是物理删除。对真实数据，**默认答案是前者**。
- **回滚必须依据"真实发生的流水"，不是"当初的意图"。** 凡是形如 `X or Y` 取值的写法，都要问：**X 为空（`[]` / `0` / `""` / `None`）时会发生什么？** 空列表是 falsy 这一点，在本项目已经坑过一次。
- **引入"全局过滤条件"（如 `is_deleted`）时，必须 `grep` 出该表所有读取点逐个收敛**——这是 B-16 的教训，本条再次踩到，**说明"加过滤列"是本项目的高发风险动作**。

**施工验收（2026-10-08）**：`5dd763b`；封顶 +0 不反扣，真实 +2 反向回滚，15 个直接消费者及报告计数逐个核验，审计只增不减。详见 `docs/review/V1_11_DELIVERY_2026-10-08.md` 与 `tests/test_v1_11_safety.py`。

---

### B-19 · 打开设置页，响应体里带着模型 API Key 明文

**来源** 外部审计（Codex）· **文件** `routers/settings.py:18`（`get_settings`）

**现象**：`GET /settings` 的实现是一行 `result = {r.key: r.value for r in rows}`——**把 `settings` 表的全部内容原样吐出去**。而 BYOK 的模型配置（含 `api_key`）**就存在这张表里**。于是：**用户只是正常打开一次设置页，浏览器响应体里就带着明文 API Key**。同一条路径下 `POST /settings` 接受**任意 key** 并原样回显——意味着它可以绕过专门的 BYOK 校验接口直接改模型配置，也能覆盖 `stagnation_checks` 之类的内部审计记录。

**定位过程**：这条和 B-17 同源——**红线是"BYOK 的 GET 绝不明文"，项目也确实实现了掩码**（`llm_config.mask_key()`，有专门的 `/llm-config` 接口做掩码读取）。审计者没有去看那个实现，而是去**找还有没有别的接口能读到同一张表**——于是找到这个"通用设置接口"。**关键动作是问："这份数据还有几条出路？"**

**根因**：**"通用 KV 接口"和"敏感配置表"共用了同一张表。** 开发时把 `settings` 当成了"什么都能放的配置袋"，后来 BYOK 图省事也放进去，但**通用接口的白名单从来没建**——它假设"`settings` 表里的东西都是可以公开的"。

**修复实现**（v1.11 P0-8）：
1. 定义 `PUBLIC_SETTING_KEYS = {gamification_modules, hidden_attributes, disabled_attributes}` —— **只有这三个是公开的**。
2. GET 加 `.filter(Setting.key.in_(PUBLIC_SETTING_KEYS))`。
3. POST 非白名单 key → 400「该设置只能由专用接口修改」。
4. 写值加**类型校验**（`gamification_modules` 的值必须 `type(v) is bool`，**刻意不用 `isinstance`**——否则 `True`/`1` 会混过）。

**防复发**：
- **敏感数据和普通配置不能共用一张"通用读写表"。** 如果非要共用，**通用接口必须默认拒绝，用白名单放开**（fail-closed），而不是默认全开。
- **掩码实现只保护了它自己那条路径。** 检查项：**同一种敏感数据，全项目有几条读取路径？** `grep` 一下 Key 的字段名/表名，把所有出口列出来。
- **类型校验用 `type(v) is bool` 而不是 `isinstance(v, bool)`**——这是 Python 的一个经典坑（`isinstance(1, int)` 为真，而 `isinstance(True, int)` 也为真；`bool` 是 `int` 的子类）。
- 这条同时是**上云硬前置**：本地自用风险低，但一旦上云，任何访客打开设置页都能拿到 Key。

**施工验收（2026-10-08）**：`2e0ebcf`；实际 `llm_primary/llm_aux` 测试 Key 不出现在通用 GET/JSON，POST 内部键 400，专用 GET 掩码。详见 `docs/review/V1_11_DELIVERY_2026-10-08.md` 与 `tests/test_v1_11_safety.py`。

---

### B-20 · 部分成功的结算：属性变了，金币或终态却没变

**现象**：v1.11 审查发现结算与发币提交边界分散；双请求可能同时结算，挑战/目标终态也可能被重复处理。

**定位过程**：顺着 confirm、金币 grant、目标终态和挑战接受/结算/退缩/到期逐个找 commit；测试在发币等写点注入异常，并发执行同一动作，比对属性、流水、余额、审计和终态。

**根因**：一次用户操作被拆成多个事务，且“先读状态再写”不能抵御竞争。停滞扣分与冷却若分开提交，也会重复扣分。

**修复实现**：用户锁、条件认领、原子余额更新、统一提交；停滞冷却同事务，可选补课失败以 savepoint 隔离。补课押金按奖励派生，历史不重定价。证据见 [v1.11 交付](../review/V1_11_DELIVERY_2026-10-08.md)，相关提交 `2c6a7a3`、`889587c`、`59f16c1`、`6438142`、`d561974`。

**防复发**：任何“扣币＋建券”“属性＋日志＋奖励”都先画事务边界，故障注入后必须全回滚；SQLite 结果不能替代 PG 竞争测试。

### B-21 · AI 输出“是数字”还不够：有限值、聚合与真实增量

**现象**：NaN/Infinity/超大整数、布尔值和重复别名可能穿过宽松解析；建议 +5 与封顶实际 +1 不一致。

**定位过程**：构造边界值，同一维度用中文/别名重复提交，检查最终属性及历史流水，而非只看接口返回。

**根因**：类型转换不等于业务数值合法；逐条夹取与最后聚合不一致；模型建议被误当成实际入账。

**修复实现**：严格有限数值/整数范围校验、规范化维度、按最终 Attribute.id 聚合后夹取、记录实际 delta；禁用父维同时阻止子维。`2118a26`、`5f42eee`。

**防复发**：每个外部数值入口都验证类型、范围、方向和归属；回滚只读真实流水，不读模型意图。

### B-22 · 重试、旧版本与缓存损坏共同考验状态边界

**现象**：保存成功但模型失败后重试可能另建事件；已确认结果仍能修改；较早模型响应可能覆盖新正文；损坏日期缓存使页面无法正常挂载。

**定位过程**：分别模拟 create 成功/judge 失败、判定中编辑、两次提交、已确认再补充，以及非法 JSON/数组/存储异常。

**根因**：把保存与分析当成一个不可分动作；写回缺版本前置条件；把浏览器缓存当可靠数据源。

**修复实现**：保存身份复用、已入账冻结、未确认编辑失效化、写回版本核对、缓存防御解析。`006b40d`、`b75bd79`、`a26309a`、`835e42a`；云端继续升级为 UUID 回执和持久任务。

**防复发**：按“已保存但未分析”“结果未知”“旧响应晚到”分别测试；不能用清空草稿来消除冲突。

### B-23 · 备份必须拿到迁移前的正确数据库

**现象**：旧启动链先补列再备份；备份可能跟默认文件名走，或被 mkdir/cleanup 异常打断。

**定位过程**：将 engine 指向临时独立库，检查备份实际目标与列；同秒备份、目录/连接/清理故障分别测试。

**根因**：备份时机、数据库来源和异常边界没有绑定真实运行配置。

**修复实现**：`e3c20a8`，本地按实际 engine 在线备份，置于迁移前、名称去碰撞、保护失败清理；云端另走 PG 运维流程。

**防复发**：检查副本保存的是“改之前”结构；恢复到独立库验证，绝不为演练删除真实原库。

### B-24 · GET 与生命周期旁路：浏览、删除也可能意外发奖

**现象**：A00 发现浏览金币可能发启动资金、accepted 挑战关联事实可被删除、删除事实后仍可能追授成就。

**定位过程**：把查询、删除、追授与挑战生命周期联合检查，对比全表及流水，不只测试 confirm 主入口。

**根因**：初始化/发奖混进读取路径；删除和追授各自不知道对方状态。

**修复实现**：`22ce20e` 拦截待结算关联删除、收紧启动资金与追授；云端进一步要求 GET 不发币、不结算、不调用模型，奖励用显式 POST。

**防复发**：列出所有会改变余额的调用者；状态变化要盘点消费点和旁路，而非只修一个按钮。

### B-25 · 切换供应商时，旧密钥不能悄悄跟过去

**现象**：复审发现换 provider 后保留旧密文可能将 A 家 Key 发给 B 家端点。

**定位过程**：用两家合成凭据验证保留/替换/清空及停用分支，替身记录请求目标与 Key 归属，不使用真实 Key。

**根因**：把“沿用 Key”视为无条件行为，没有绑定供应商身份。

**修复实现**：`credentials.save_config` 换供应商且启用须新 Key；停用换供应商清旧密文，同供应商才可保留。见 [发布准备 R01](../RELEASE_READINESS_DELIVERY_2026-10-10.md)。

**防复发**：配置测试同时断言请求发给谁、用谁的凭据、配置版本是否仍当前；不能只断言 HTTP 成功。

### B-26 · 请求超时，不等于这次兑换没发生

**现象**：服务端扣币建券成功，但响应在网络中丢失；前端若当失败重新生成购买，就再次扣币。

**定位过程**：真实前端逻辑→HTTP→隔离 PG，故意丢已提交响应、重载页面、双击，并模拟成功后的列表刷新失败。

**根因**：“结果未知”与“明确失败”混在一起；重试换了操作身份或正文。

**修复实现**：账号专属持久 UUID＋原 body＋版本；查回执或重发原请求，未知时阻止新购买，成功与刷新失败分开。R02 与 `useRedemption.js`。

**防复发**：同次动作不换 UUID；明确第二次购买才换身份。幂等只保证本地业务效果，不承诺模型供应商恰好计费一次。

### B-27 · 数据导入不只是 INSERT：JSON 里也藏着对象关系

**现象**：新库分配新 ID，普通外键虽映射，`params._challenge_id`、金币 ref_id、审计嵌套数组却可能还指旧对象。

**定位过程**：合成目标先占用序列，故意让新旧 ID 不同；检查引用指向、普通数字不变及异常时全事务回滚。

**根因**：数据库约束只能看普通外键，无法理解 JSON/多态 ref_type 的业务含义。

**修复实现**：`ops/import_references.py` 显式语义登记，缺映射/跨用户阻断，不按任意整数替换。见 [引用登记](../IMPORT_REFERENCE_REGISTRY_2026-10-10.md)。真实旧库尚未正式预检/导入。

**防复发**：生产者新增引用字段时同步登记和测试；条数相同不能证明迁移正确。

### B-28 · 持续滴答的响应，可以一直躲过 read timeout

**现象**：替身供应商不断返回小块，单次读取始终没超时，模型调用却一直不结束。

**定位过程**：R06 用真实子进程制造慢块返回，观察父进程总截止、锁释放及后续任务能否继续。

**根因**：read timeout 限制相邻读取的等待，不是整个调用总耗时。

**修复实现**：可终止单次调用子进程、父进程总截止、SDK 隐式重试关闭和统一两次预算；租约/版本检查防止旧结果写回。Windows 合成验证通过，Linux 父死亡信号与目标真实故障仍须对应证据。

**防复发**：区分连接、读取、总截止、重试预算和租约五种时限，不承诺取消能追回已产生的费用。

### B-29 · EXPOSE 5432 并不等于宿主机开放 5432

**现象**：Compose ps 的 Publishers 有记录，就被预检判成数据库公网映射。

**定位过程**：对照 null、空、EXPOSE-only、PublishedPort=0 及真实 IPv4/IPv6/回环映射样本。

**根因**：把声明端口与宿主机发布端口混用。

**修复实现**：仅 db 的合法整数 PublishedPort>0 判为宿主映射，异常形状阻断。见 [运维复审](../OPS_REVIEW_FIXES_2026-10-10.md)。

**防复发**：读取工具结构化输出前弄清字段含义；不要靠字符串出现“5432”作安全结论。

### B-30 · 临时容器名变了，备份保留策略也跟着失效

**现象**：每次 ops 容器 host 不同，restic 按 host 分组，旧快照分散后不能按同一部署正确保留。

**定位过程**：替换容器身份检查命令，真实本地合成 restic 仓库 35→9 快照；其他部署/标签的两份保留，check 通过。

**根因**：用短命执行容器身份代表长期部署身份。

**修复实现**：稳定 BACKUP_ID→RESTIC_HOST，backup/forget 显式 host，并按 host,tags 分组。7 日＋4 周是自然日/周最新快照并集，不是固定 11 份。

**防复发**：把执行者与资产身份分开；历史随机 host 快照不能擅自归并/删除。真实异地恢复与失败通知尚未验收。

### B-31 · 首页能打开，后端却已经坏了

**现象**：停止 API 或制造 DB 连接失败，静态首页仍是 200；真实 Caddy 又暴露 request_body 语法和内部路由排序问题。

**定位过程**：官方工具校验后在回环 HTTPS 运行真实 Caddy→隔离 API，分别停 API、让 DB 失败，检查首页、就绪入口、内部路由及假通知接收器。

**根因**：把静态页面存活当应用就绪；Caddy 指令默认排序与书写顺序不同。

**修复实现**：监测首页和 `/service-status`；后者转发 `/api/ready` 的只读 SELECT 1，严格核对 JSON；合法多行 request_body，route 明确顺序，内部健康/docs 等 404。运维复审本机通过。

**防复发**：健康检查随依赖链设计；本机假通知到达不是用户的真实通知配置已经可用。

### B-32 · Docker 29 导入成功，镜像外层 ID 却变了

**现象**：同一镜像包跨 classic/containerd 存储导入，外层 `.Id` 变化导致旧校验误报。

**定位过程**：比较 docker save 配置原始字节、标签、平台与观察 ID；CI 加入双向存储矩阵，目标机另校验已安装镜像。

**根因**：把存储后端观察值当稳定内容身份。

**修复实现**：`835ebc2` 的 schema v2 用原始配置 JSON SHA256，observed_id 只诊断；核对平台、用户与标签，目标 verify 流式保存已安装镜像而非只读输入 TAR。

**防复发**：旧清单拒绝并重建同次源码/镜像包；不能改 checksum、拼接新脚本或降级 Docker 绕过。详见 [身份修复交付](../DOCKER29_IMAGE_ID_COMPAT_DELIVERY_2026-10-11.md)。

### B-33 · 官方 PostgreSQL 没写 User，不等于镜像损坏

**现象**：真实 Docker CLI 模板直接访问缺省 Config.User 失败；合成矩阵写了 USER，未覆盖官方镜像形状。

**定位过程**：检查可选字段语义；加入缺省/null/空值/错误类型样本，真实 Linux 缺省 USER 矩阵和当次实际 PG containerd 导入。

**根因**：工具模板和测试都假设 User 键一定存在。

**修复实现**：`ba7031e` 改 `json(index .Config "User")`；比较时规范合法空值，原始摘要不变，应用仍必须 10001:10001，PG 身份不跳过。

**防复发**：合成样本保留，但还须使用真实部署产物。见 [PG 缺省用户交付](../POSTGRES_DEFAULT_USER_FIX_DELIVERY_2026-10-11.md)。

### B-34 · 本机 psql 成功，跨容器还是密码错误

**现象**：API 报 gol_app 密码认证失败；loopback 下两种密码读取都 PASS，`-h db` 下去末尾换行 FAIL、保留原文件 PASS。

**定位过程**：查询 `pg_hba_file_rules` 发现 loopback 是 trust、容器网络是 scram-sha-256；再比较两种读取方式，只输出 PASS/FAIL，不打印秘密。

**根因**：`deploy/init-app-role.sql` 的 `trim(text)` 默认只移除空格，没有剥末尾换行；应用读取会 strip，双方密码字节不一致。trust 连接不验证密码，前一结果不能反证密码正确。

**修复实现**：现场用明确空白集合 trim 并 ALTER ROLE，跨网络认证通过，迁移到 b004_reports；**仓库初始化 SQL 仍是旧 trim，源修复待实施**。没有删卷或重新生成密码。

**防复发**：初始化与应用读取约定一致；新增带换行样本并在 scram 网络连接验证。当前笔记只记录修复方向，不直接修改 SQL。

### B-35 · 浏览器错误先查路径：SSH 在监听，也可能绕到代理

**现象**：专用浏览器报 ERR_CONNECTION_ABORTED，用户以为要重启网站。

**定位过程**：本机只读检查发现 SSH 监听 127.0.0.1:443、系统代理开启；指定域名解析及不走代理的 curl 得到 200 ready。默认 curl 另有私有证书吊销检查失败，诊断时只放宽吊销查询，保留证书链校验。

**根因**：证据支持浏览器代理路径影响私有回环请求，不能把所有连接错误都归到服务崩溃。

**修复实现**：独立 Edge profile 加 no-proxy-server 与 lifexp.cn→127.0.0.1 解析规则；不关闭浏览器 TLS 安全，不修改全局代理。

**防复发**：依次分清本机监听、代理、转发、证书信任和应用就绪；不要一遇网页失败就重建容器。

### B-36 · SSH 被重置：有故障现象，还没有唯一根因

**现象**：用户截图 `client_loop: send disconnect: Connection reset`。

**定位过程**：核对原命令未启用协议保活；没有读取服务端日志或复现具体网络断开过程。

**根因**：**未确定**，可能网络、休眠、中间设备或服务器端重置；不能直接断言是空闲超时。

**修复实现**：给出 ServerAliveInterval=30、ServerAliveCountMax=3，并以 `ssh -G` 核对参数；这是缓解和失联检测，不是已证明的根治，也不自动重连。完整命令见私有试用审查。

**防复发**：频繁发生再按日志定位；公开上线后普通访问不应依赖这条个人 SSH 通道。

### B-37 · 保存配置、模型可用、测试反馈，是三个状态

**现象**：用户填错模型名仍可保存；测试连接点了不知结果，也不清楚当前绑定什么。

**定位过程**：核对 save_config 仅校验名称非空/长度；测试接口实际调用已保存的组；页面反馈位置及共享 busy 状态见 F02/F03，字段回填不等于摘要清楚。

**根因**：缺少“已保存但未验证/验证失败/可用”的明确呈现；保存不承诺供应商存在该模型。没有证据说按钮从不发请求。

**修复实现**：**未实施**。候选是就近结果、明确测试对象、主辅/回退展示和配置指南；不擅自每次保存就付费调用模型。

**防复发**：未来测试覆盖错误模型、无额度、错误 Key、未保存编辑及主辅切换；先商定验证触发和费用语义。

### B-38 · “不分析”“待补充”“请绑定模型”同时出现

**现象**：记录已主动分析并返回追问，仍显示保存时不分析和绑定提示。

**定位过程**：RecordDetail 的不分析取历史 intent；绑定提示只看 !judgment，未查有效模型；待补充阶段恰好可没有判定。

**根因**：把历史选择、当前任务与配置可用性当成同一个状态；固定教学文案也重复展示。

**修复实现**：**未实施**，F05/F09 待定；不能为改文案就篡改 is_pure 或历史选择。

**防复发**：未来建立当前任务状态展示表，分别覆盖未配置、已排队、待补充、就绪、失败和手动改意图。

### B-39 · 记录一个部署事件，为什么问我昨晚几点睡

**现象**：用户只记录项目部署，AI 却追问睡眠、三餐、运动等全天事项。

**定位过程**：Composer 用 source=journal；judge prompt 沿用“日记＝逐生活面覆盖”旧规则。

**根因**：记录入口含义已变，提示词场景定义未同步；不是只凭换模型可以解释的问题。

**修复实现**：**未实施**。用户明确单事件围绕事件问，全天回忆留给晚上总结；提醒清单/总结 AI 如何开启仍待讨论。

**防复发**：同一文本分别走事件/总结场景验证；睡眠事件可以追问睡眠，不能一刀切禁止健康分析。

### B-40 · 测试文字被标“已合并”：先分清标签与数据操作

**现象**：真实部署事件与同日“部署测试”标成已合并；理由又承认是否同一件事不确定。

**定位过程**：近期上下文含测试记录；模型返回 merged_with，解析器整理字符串，页面据此展示；未见物理合并证据。

**根因**：上下文候选和语义验证需要复核，**唯一根因未证实**；提示词虽写“不确定倾向独立”，并不保证模型遵守。

**修复实现**：**未实施**。待商定可能相关/疑似重复/用户确认的差别，不擅自排除所有不分析记录或取消去重。

**防复发**：用测试描述、真实事实、同一事实补充和独立相似事实做评测；关联展示不能代替后端结算安全检查。

### B-41 · 50 是游戏起点，为什么变成了能力“熟练”

**现象**：选择未评估基线后，多个 50 维度直接标熟练。

**定位过程**：constants 的 40≤值<60→熟练，attributes 路由对所有 baseline_kind 用同一映射，前端直接显示。

**根因**：数值区间标签表达了能力判断，与未评估起点含义冲突。

**修复实现**：**未实施**，F11；隐藏/换标签/游戏等级区别待商定，不重置数值，不改旧已评估历史。

**防复发**：展示规则要携带数据来源与基线类型；游戏分数不是精密能力测量。

### B-42 · worker 完成了，详情页却可能还显示排队

**现象**：静态审查发现任务提交后只立即读取一次，之后可能停在旧状态。

**定位过程**：RecordDetail 只在 mounted/操作/冲突时 load；PendingView 每 5 秒读取。未在实际云端复现特定完成时序。

**根因**：异步后端接上了，但详情页缺定时更新或订阅机制。

**修复实现**：**未实施**，F14；不能将所有排队问题都归因于它。

**防复发**：未来让 worker 延迟完成，检查详情页终态、按钮和错误同步；卸载/退出后停止读取并拒绝旧账号响应。

### B-43 · 没有整页横向溢出，金币仍然会断行

**现象**：390×844 本机 Edge 真实页面中 80 断成上 8 下 0，金币也竖排。

**定位过程**：人工查看 `docs/review/private_test_2026-10-12/mobile-shop.png`，与整体宽度自动断言对照。

**根因**：金币区局部空间分配不足，金额缺适当完整展示约束；整体 overflow 断言没覆盖局部可读性。

**修复实现**：**未实施**，F15；与吸顶区一起商定布局。

**防复发**：检查金额、按钮、长中文、字号放大及实机；模拟尺寸不冒充手机蜂窝验收。

### B-44 · 确认框靠浏览器顶部，余额卡片还挡内容

**现象**：用户截图原生兑换确认框与页面不协调；大金币栏吸顶占据表单空间。

**定位过程**：ChallengeView 使用 window.confirm；styles 的 coin-bar sticky/top/z-index 与截图一致。

**根因**：浏览器管理原生框外观；大内容块吸顶造成信息与滚动冲突。

**修复实现**：**未实施**，F13；页面对话框和紧凑/不吸顶余额只是候选。

**防复发**：调整外观仍保留花费确认、键盘焦点、进行状态及原请求重放机制，不以 UI 改动删掉交易保护。

### B-45 · JSON 有事件，不代表导出了完整个人业务关系

**现象**：旧导出遗漏部分游戏化表、关联 ID 和审计，无法完整离线对照。

**定位过程**：按模型逐表对照输出，测试日期/嵌套快照/删除行，检查敏感信息排除。

**根因**：只维护旧字段列表，新增模型没同步进入导出契约。

**修复实现**：`93bacb4` 补 v1.11 的 17 表；当前 format_version=3 又加入个人回顾/报告/任务等，继续排除凭据和会话。CSV 仍只含事件。

**防复发**：新模型同时决定导出/迁移/隐私边界；导出并不自动意味着实现了对应全量恢复工具。

### B-46 · “状态”不能只凭占位数值、页面挂载或读取副作用猜

**现象**：设置没回填已有模型；13 个占位维度被误当已建档；历史达到成就条件却没追溯，另有重复追授路由。

**定位过程**：真实浏览器查看表单回填，测试未完成/已完成建档，并用 23 篇合成日记比较成就与金币。

**根因**：挂载未加载专用配置；用属性存在替代显式完成字段；成就发现/授予的入口职责不统一。

**修复实现**：`d9f6a99` 加载配置；`4b2eca3`/`861d208` 用 onboarding_completed；`67cf8a0` 修当时追溯和重复入口。**云端后续收紧 GET 不发奖，当前以显式写入口为准**，不能照旧档把读墙授币当现状。

**防复发**：状态读权威字段，初始化/查询/发奖分开；配置字段已回填仍需处理 F16 的绑定摘要体验。

### 本章小结：原 19 个 bug 的历史类型分布

把 19 条按**根因类型**归类，能看出 bug 的"高发地带"：

| 根因类型 | 条数 | 涉及 bug | 预防手段 |
|---------|------|---------|---------|
| **规则/prompt 边界不清** | 4 | B-06、B-07、B-09、B-10 | 正负场景对称走查；判据收敛到单一维度；角色描述必带边界约束 |
| **多入口/多数据源不同步** | 3 | B-01、B-04、B-19 | 盘点所有入口，核对参数与副作用对等；**敏感数据找全部读取路径** |
| **写库语义错误** | 3 | B-03、B-17、B-18 | "更新/撤销"必用 update / 逻辑删除，**禁止"先删后建"**；拆掉调试脚手架 |
| **对模型输出的格式假设** | 2 | B-05、B-13 | LLM 输出永远不可全信；异常时先看 prompt 示例本身 |
| **迁移不完整** | 2 | B-12、B-14 | 迁移 = 结构变更 + 数据回填 |
| **外部依赖无容错** | 1 | B-02 | 韧性六问 |
| **辅助功能阻断主流程** | 1 | B-08 | 启动链每步问"失败该不该阻断" |
| **幂等缺失** | 1 | B-11 | 创建型接口必问"重复调用会怎样" |
| **外部库隐式语义（静默丢数据）** | 1 | B-15 | 日期/枚举参数写全格式；用"像素/条数"量化对照预期 |
| **新增/变更过滤条件后消费点漏收敛** | 1 | B-16 | 加过滤条件 → `grep` 出该表所有读取点，逐个判断 |

**四条最值得记住的**：
1. **多入口是 bug 的温床**（B-01/B-03/B-04/B-19）——同一个业务动作有几个入口？**同一份敏感数据有几条读取路径？** 它们的代码路径、参数、副作用一致吗？
2. **修复方案本身要评估副作用**（B-11 → B-03 这一对）——"删旧建新"图省事，代价是三重连锁伤害；**"物理删除"是同一个坑的第二次出现**（B-18）。
3. **LLM 相关 bug 一半在 prompt、一半在容错**（B-05/B-06/B-07/B-09/B-10/B-13）——改 prompt 前先问"规则的边界在哪、正负场景都覆盖了吗"
4. **红线不会自己生效，得有人拿它去量代码**（B-17/B-18/B-19）——这三条**首先由只读审计发现，当时功能测试没有覆盖**；后来可并且已经补入回归。共同形态是安全设计只在主路径实现了，旁路仍开放。每次立下一条红线，都要回答“可能在哪些地方被绕过”，再把可验证的条件写成测试。

---


### 2026-10-18 实施故障补记

<a id="b47"></a>

### B-47 · 找回受理与真实投递是两个生命周期

**现象**：审查R01说明，已绑定账号等待SMTP，未知邮箱立即返回。

**定位过程**：沿公开恢复请求读到同步发信调用，并用假Mailer观察公开响应前是否有send。

**根因**：只统一JSON正文，仍把外部网络等待留在已知账号分支。

**修复实现**：所有邮箱先写MailDelivery后返回accepted；worker解析账号、持久租约／有限重试，加密保存同一个单次token，SMTP等待不持有数据库事务。

**防复发**：同时测试已知／未知不调SMTP、重启后重试不换token、过期／消费后不能再用；真实收件另验。

<a id="b48"></a>

### B-48 · 跨日期草稿需要身份边界与异步边界

**现象**：同一schedule在换日后仍显示上一日输入，甚至可能用错所属日。

**定位过程**：检查drafts键和load异步回包；在编译Vue里做A→B→A及延迟旧日期响应。

**根因**：日程ID不是一次安排的完整身份；旧请求并不知道页面已换到新日期。

**修复实现**：账号命名空间＋local_date:schedule_id复合键，同步写缓存；load清旧卡片、递增读取代次并核对当前日期／卸载状态；恢复旧请求用原path和payload。

**防复发**：既验草稿内容，也验晚回后的日期／卡片；保存未完成只锁定该次，不造事实或成功奖励。

<a id="b49"></a>

### B-49 · 不交给AI必须涵盖所有派生内容

**现象**：原文可过滤，但旧长期记忆、判定摘要、属性依据或挑战标题仍可能含私密片段。

**定位过程**：逐个检查实际chat_json构造入口，用PRIVATE哨兵放入原文和未知派生数据并捕获请求。

**根因**：把“有摘要”误当“可继续向外发送”；来源和许可版本没有绑定。

**修复实现**：ai_context统一记录许可／版本／背景；模型流程查询过滤，旧无来源派生隔离；发送前、回写前重检。长期补充的AttributeHistory也只用有合法来源的依据。

**防复发**：新增任何模型用途都必须参加payload测试；UI可见不等于出站许可；不能承诺撤回已发出的内容。

<a id="b50"></a>

### B-50 · 一个文档不等于一个事实，撤销也不等于删证据

**现象**：日记重述多件已做的事，简单整篇结算会重复；撤销一份原文还可能回滚别的来源支撑的属性。

**定位过程**：用白天英语／跑步＋晚间绘画构造多事实；再测试两个来源关联后的先后撤销和日记改写。

**根因**：原文身份、事实身份、建议与结算身份混为一谈。

**修复实现**：FactFragment／FactBundle／FactNote保留来源，沿用唯一FactSettlement；关系由用户核对，改写后新片段强制核对旧事实；整组在同一事务确认。最后存活来源撤销才反向属性，旧钱及账目不删除。

**防复发**：验证事件数不因拆分增加；故障注入不得半组账；同UUID回放原结果；真实PG竞争还须另验。

<a id="b51"></a>

### B-51 · 导出选项必须作用到全部输出路径

**现象**：取消包含问答后，可读文件的game附件曾直接全表收集，又夹回问答。

**定位过程**：从readable select追到game=_collect，看同一个选项是否在附件路径生效。

**根因**：主记录和游戏附件各自维护投影，隐私范围出现两套规则。

**修复实现**：可读附件复用JSON v5同一筛选；递归剔除未选问题快照，独立控制问卷／反馈。保留HTML转义、CSV公式防护和新格式导入拒绝。

**防复发**：四种后端响应都用哨兵验证，并从实际Vue触发下载、核对字节；不要只检查下载按钮存在。

<a id="b52"></a>

### B-52 · 独立券不仅是独立剩余额度

**现象**：第一张30分钟使用5分钟后，新券应30分钟且本次0；手填实际秒数也不能沿用上一段300秒。

**定位过程**：对照TimeSession.source_id、VoucherAllowance与前端seconds草稿，截图新券状态。

**根因**：持久额度已分开，但组件里的手填结束数据仍跨会话复用。

**修复实现**：券额度按redemption独立存；新会话以开始快照确定可用量，切换active.id清除seconds／说明，当前计时用时间差。结束先预览再确认，人工修正走追加差额。

**防复发**：同时验第一剩25、新券30、继续旧券25、本次0、暂停刷新、重复更正净0，不只看一个数字。

<a id="b53"></a>

### B-53 · ORM refresh可能覆盖尚未flush的业务字段

**现象**：无AI问卷确认时，余额已发但建档状态／初始快照可能没留下。

**定位过程**：跟踪问卷confirm到coin_service，发现余额入口会refresh同一UserProfile。

**根因**：以为修改ORM对象就已经写进当前事务；refresh重新载入数据库覆盖了未flush字段。

**修复实现**：在调用余额入口前flush建档／属性字段；未建档校验放在赋值前；基线、启动资金及回执仍由外层事务一次提交。

**防复发**：用新Session重新读取建档状态、13维和资金；重复UUID／新UUID都不能二次建档，不能仅断言接口返回成功。

<a id="b54"></a>

### B-54 · 固定和动态成就需要跨入口共享身份

**现象**：试用候选确认后，旧coins/check-streak或目录自动检查可能再发同一坚持奖励。

**定位过程**：枚举全部发奖入口，比较DynamicAward.equivalence_key、Achievement.code及旧CoinLedger.reason。

**根因**：各入口幂等只防自己的重试，没有表达“不同入口其实是同一个里程碑”。

**修复实现**：等价日记固定奖励使用fixed:journal_streak_N；试用模式旧自动入口只发现候选，退出试用后旧入口也检查历史等价身份。额度满不丢候选，忽略的等价项不重推。

**防复发**：测试固定先领／动态先领和切规则后旧入口；名称、窗口、规则版本改变不能重置终身领取身份。

证据统一见[本轮交付](../FULL_SYSTEM_DELIVERY_2026-10-18.md)和 `tests/test_full_system.py`；本轮未提交，所以不编造commit编号。

<a id="b55"></a>
### B-55 · 兼容旧数据也是模型许可边界的一部分

**现象**：没有开启关注项名称授权，甚至旧清单已关闭，日记回顾消息仍含自定义旧名称。

**定位过程**：独立审查用私密 sentinel 保存到 LifeChecklist.entries 的 key，再截获实际回顾消息；追到 review_context.capture 中另一条未过滤的兼容 map。

**根因**：将“状态字典”的所有字段都当作无正文元数据；实际 key 是用户可自由填写的文字，新 CareConfig 许可没有覆盖旧路径。

**修复实现**：移除旧 entries 原样出站，只发清单 ID／版本／启用状态及 recorded／skipped／not_recorded 计数；当前 CareItem 名称仍须当前启用、到期与名称授权。旧数据本人可见、可导出。

**防复发**：新配置缺省／未授权／授权 × 旧清单启用／关闭，同时截获日记和逐事实两条模型消息。不要只断言 focus_items 为空，要搜索完整消息中的私密文字。

<a id="b56"></a>
### B-56 · 选项必须约束同一文件中的第二份数据

**现象**：JSON records.revisions 为空，完整响应的 tables.diary_revisions 却仍有旧原稿；Markdown 没有同样泄漏。

**定位过程**：建立旧／新两版日记并关闭历史，检索完整导出响应，确认 _collect 全量表仅按事件ID筛选，绕开了 readable_export 的历史投影。

**根因**：记录列表和表附件各自过滤，某一投影正确不能保证整个下载文件正确；旧会话、分析和派生快照也有同类风险。

**修复实现**：select 选定当前版本会话、分析、补充和事实；project_record_tables 从同一结果生成所有记录表附件，无历史时不挂回历史过程快照。可读格式的游戏附件也复用该路径。

**防复发**：JSON／Markdown／HTML／CSV、游戏附件开／关均检索整个响应；旧正文、问答、分析、片段分别用 sentinel，既验证排除旧值，也验证当前值和打开历史后的旧值可读。

<a id="b57"></a>
### B-57 · 隐藏API参数不等于用户能配置计划

**现象**：正式计划表单没有分钟数；计划即使名为45分钟，计时页面只传ID，服务端默认30分钟。

**定位过程**：对照 Demo、ScheduleIn、保存 rule 和 TimerView 的真实请求；复现配置45分钟被422，页面启动却为1800秒。

**根因**：计时API单独支持 planned_minutes，日程模型与页面没有保存和传递它，名称中的数字不能作为合同。

**修复实现**：分钟数进入版本化 rule／history，表单、卡片及计时入口展示；服务端检查本人日程、来源版本、当前生效时长，开始时将规则和分钟数写入合同快照。旧缺省30；已接受旧请求按原回执重放。

**防复发**：验证20／45、非法分钟、旧来源版本／他人来源、未来生效修改与刷新恢复；实际Vue表单保存45后应启动2700秒，未来改20不能把当前会话也改掉。

<a id="b58"></a>
### B-58 · 资金底线还需要可恢复的业务入口

**现象**：允许新账号先记录，但首记领取直接返回500；底层没有发错币，用户却不知道如何继续。

**定位过程**：采用试用规则、保存记录、不建档即领取，追到 coin_service.grant 的未建档 ValueError；原测试都先建档，所以没走到该分支。

**根因**：资金服务拒绝未建档结算是必要保护，上层未将其表达为“资格保留，先选择起点”的业务状态。

**修复实现**：首记、节日、动态成就、事实及有金币差额的计时，在资格或账目变更前 require_baseline 返回409；首页显示首记资格保留及 /me 入口，仍允许先记录和使用独立基础额度。

**防复发**：先记→重复失败→建档→原UUID领取→重放，检查资格版本、额度、流水及80＋3余额；同时枚举其他新增发币入口，不能只让首记路由不再500。

<a id="b59"></a>
### B-59 · 模型建议质量之前，先检查模型有没有收到区别

**现象**：相同购买记录、实际娱乐3600和10800秒，两次完整定价消息完全一样；旧 prompt 还要求按多次兑换涨价。

**定位过程**：固定购买／余额／阶段，只改变已确认计时秒数，截获消息对比；发现只有累计计时段数，没有实际秒数和日期窗口，且混入计划计时。

**根因**：购买、标记兑现与真实使用是不同事实。只补一句“购买不等于使用”无法弥补缺少的上下文，也无法消除旧强制涨价规则。

**修复实现**：pricing_activity 分列近30天购买和已确认结束的娱乐用量，以当前结算值给秒数、每日分布、最近及前一7天；计划／窗口外／未确认排除。明确结算日口径，不猜跨午夜分配；prompt 不再按购买次数强制涨价。

**防复发**：实际消息验证买而未用为0、3600／10800可区分、修正后取600、近期回落与前周分别呈现、计划和旧用量不改消息。合成payload通过只证明信息齐全，真实模型的建议质量仍另验。

本轮证据见[2026-10-19修复交付](../FULL_SYSTEM_FIXES_DELIVERY_2026-10-19.md)与 `tests/test_review_repairs.py`。原交付和独立审查保留，不将后来修复倒写成上一轮已经正确。

<a id="b60"></a>
### B-60 · 读取回退不能代替首次编辑前的快照保留

**现象**：合成旧计划无分钟字段且history为空，原先当天可按30分钟开始；设置明天45分钟后，今天timing变null、计时返回409。真实旧库是否存在这种记录未核对。

**定位过程**：独立复审R01用旧结构复现；新增回归在修复前明确失败于“未来修改后当天timing不能为null”。检查发现保存只追加明天的新版本并覆盖旧rule。

**根因**：读取层只在history为空时回退到当前rule。首次编辑后history非空，唯一旧规则也已被覆盖，未来生效前没有可用快照。

**修复实现**：save_schedule首次编辑空历史的已有行时，先以原版本记录当前已知规则、名称、启用状态和目标，标记legacy_baseline，再追加新版本；均在原写事务中完成。已有正常历史和新建计划沿原逻辑，回执重放不重复追加。

**防复发**：验证今天30／明天45、已开始合同不变、刷新及当天重新开始、版本校验、旧目标保留和同UUID重放；另验原显式20分钟与停用状态不被未来编辑覆盖。用合成数据验证兼容，不推定真实库受影响。详见[补修交付](../LEGACY_PLAN_HISTORY_FIX_2026-10-19.md)。

---

<a id="b61"></a>
### B-61 · 独立连通测试与业务请求可以有不同结果（本轮已修）

**现象**：用户配置模型后独立测试显示 MODEL_INVALID_RESPONSE；随后明确说“建议涨降价”能返回新报价。不能据测试红字就认定 Key、全部模型请求或实际业务都失败。

**定位过程**：按[反馈F01/F10](../DAILY_USE_FEEDBACK_2026-10-21.md)核对 settings 的 `/llm-config/test`、model_runner、错误映射与 reward-quotes→shop_service→chat_json。测试固定短提示与8 token；无数据库/网络的模拟复现表明空正文、HTTP400被归同类，reasoning存在但正文空、结束为length时，runner丢失结束原因。用户业务成功是用户报告，未获取该次原始供应商响应。

**根因**：已证实的是测试输出预算过窄的风险、诊断元数据丢失和错误分类过粗。截断并非已证实的唯一线上原因；独立测试的请求模式和业务JSON不同，二者成功/失败可以共存。

**修复实现**：本次只有诊断、Demo与[正式修复规格第3节](../DAILY_USE_REDESIGN_DEV_SPEC_2026-10-21.md#3-ux01ux04模型诊断摘要和可选辅助配置)，未修正式模型调用。Writer W1需按供应商协议有限预算/短答模式、受控finish_reason/用量、空/截断/请求拒绝/超时分类和配置版本复核落地。禁止把思考全文当正文或改历史状态伪造通过。

**防复发**：A01/A02覆盖短答、仅其他输出无正文、截断、HTTP400/401/429、超时、测试中换配置与真实业务JSON。模型替身可验证分类和脱敏，真实供应商需单列验收；不能拿Demo模拟测试成功冒充接口已修好。

**2026-10-21 实施补记**：`model_diagnostics.py`保留受控finish_reason、HTTP状态、用量及空正文/其他输出布尔值；runner和进程边界继续传递这些字段。测试1024 token、仅官方DeepSeek端点关闭思考；截断/空输出/400参数/网络等分类分开，测试结果仍绑定保存配置版本。新A01及原TrialP1模拟矩阵通过。没有取得用户当次真实响应，不能宣布已证实线上唯一根因或真实模型质量通过。

<a id="b62"></a>
### B-62 · 初始评估传入了聊天格式而非问答格式

**现象**：基础整体分析不再补题后，生成属性面板触发KeyError。

**定位过程**：扩展问卷真实服务测试，沿`questionnaire.evaluate`进入`prompts.build_panel_messages`，发现后者读取question/answer。

**根因**：新调用者误用role/content构建旧builder所需的问答对，早期全跳过中性夹具没有走模型面板分支。

**修复实现**：从本次实际题目快照/补题取文本，与本人授权答案组成question/answer；历史保留真实题目。AI资金合成150用例证明没有落回固定80。

**防复发**：A07/A08覆盖不补题、有限补题、面板确认与相同UUID回放，不只验证中性出口。

<a id="b63"></a>
### B-63 · 报价撤权晚回必须失败存档并返回受控冲突

**现象**：模型返回期间撤销个人背景用途，原检查抛ValueError导致500，界面难以恢复。

**定位过程**：在真实价格服务的模型替身里用另一Session撤权，查看商品、报价状态和HTTP结果。

**根因**：出站边界已经拒绝来源变化，但新增报价路由没有将该异常转换为业务冲突/持久失败。

**修复实现**：回滚模型结果，锁profile把原running报价标failed，映射CONTEXT_CHANGED并返回409，不创建商品或覆盖有效价格。

**防复发**：A22同时检查409、失败存档和零新商品；价格应用继续核对用途/模型/日/商品/经济快照。

<a id="b64"></a>
### B-64 · 自动保存了答案也要恢复题目位置，旧缓存不能覆盖新版本

**现象**：真实浏览器刷新回归向导，已输入文字虽在服务器，页面跳到下一题，用户像是丢了草稿。

**定位过程**：真实Vue/ASGI日志显示PUT成功，刷新GET也返回答案；当前步骤由“首个空题”重新推导。

**根因**：本机草稿未保存step，问卷/回归缓存还未绑定服务器基线版本。

**修复实现**：缓存题目位置和version；只有与服务器相同基线才恢复本机内容，保存成功更新版本与缓存；防止旧设备缓存默默回盖新答案。切账号仍沿epoch隔离。

**防复发**：浏览器真实输入、等待自动保存、刷新断言同题同文字；问卷也同样验证，后端版本冲突仍拒绝覆盖。

<a id="b65"></a>
### B-65 · 个人用途服务存在不等于每条模型链路已接入

**现象**：新增四用途实际消息捕获发现，事件逐事实payload缺少允许用于judge的长期信息；报告也需要独立接入新的report背景。

**定位过程**：为四用途分别设置独特合成背景，在真实worker/报告/价格路径捕获chat_json的messages，逐个检查应有/不应有标记。

**根因**：事件事实路径只有本篇sources；报告旧builder仅引用已证实的派生记忆，新增背景服务没有被调用。

**修复实现**：普通事件事实context增加judge用途背景，日记保留按CURRENT用途采集；报告追加report用途背景并在模型晚回复核ai_context。未授权用途/原文/无来源派生内容不放行。

**防复发**：A04四用途实际出站消息文件留档，必须“该有的存在”和“其他用途/私密不存在”同时成立；不能只用敏感词不存在证明功能接全。

<a id="b66"></a>
### B-66 · 同步分析未知结果重发可能再次调用模型

**现象**：阶段/说明/报告等同步请求在供应商返回前网络断开，单靠最终回执无法证明是否已经付费。

**定位过程**：模型替身抛超时后以相同UUID重发，检查调用计数；最终回执尚未产生时仍需中间状态。

**根因**：回执与最终业务同事务是必要条件，但不能覆盖事务外付费调用已经发生的区间。

**修复实现**：b025新增model_dispatches按账号/操作/UUID唯一，完成配置和输入校验后先提交发送标记，再在事务外调用；原最终回执仍与业务原子提交。报告UI发送稳定UUID，未知结果有恢复入口。问卷/报价已有专用运行状态，异步分析已有持久任务，不重复造第二条业务账。

**防复发**：A03模拟同UUID超时后重发只调一次、新主动分析可用、成功结果回执重放；跨进程唯一约束拒绝并发重复。真实PG双连接仍NOT_RUN，旧本地无UUID报告兼容API不宣称具备该保证，云端缺UUID直接拒绝。

<a id="b67"></a>
### B-67 · 读取模型不是编辑写入模型

**现象**：新项目管理页打开已有项目改名，计划/照顾来源都返回422，窗口不能保存。

**定位过程**：独立审查实际编译页面捕获body.timezone extra_forbidden；沿ProjectManager发现edit展开整个rule，save又展开整份表单。

**根因**：服务器读模型包含timezone等上下文字段，严格写模型不能直接照单回传。

**修复实现**：editable和allowedBody显式取可编辑字段；服务器继续extra=forbid，版本和回执不放宽。长表单定向初始焦点到名称并滚到窗口顶端，兑换确认默认行为保持。

**防复发**：真实页面按新建→重新打开→改名/分类/停用→保存→刷新检查两类来源；捕获实际字段无timezone且HTTP200，另以非法字段证明服务器仍422。窄屏编辑与原确认焦点回归。

<a id="b68"></a>
### B-68 · 排期起算日与规则生效日不能混用

**现象**：未来一次性项目打开编辑后日期从下周变今天；若仅修422，会导致普通改名携带隐式改期。

**定位过程**：独立审查发现展开原rule后又start:localDate()；再检查history选版本与interval取模，均使用rule.start。

**根因**：同一字段承担一次日期/间隔锚点和修改生效边界；只允许今天或未来修改又迫使前端覆盖原锚点。

**修复实现**：原start保留，另传显式effective_from，顶层历史按生效日选版本，due仍按原start。旧历史无新字段按旧语义解释，缺历史先捕获已知基线；今天计时继续读今天有效快照。

**防复发**：两来源未来一次性、历史间隔和历史每日的真实页面验收；旧部分/未完成与事件ID不变；旧空历史计划明天改名今天仍能计时。新JSON语义不能仅用旧代码回退读新库，恢复须用一致备份。

<a id="b69"></a>
### B-69 · 有限首批不等于覆盖全部项目

**现象**：每日复用一个UUID，反复进入只重放首三项；后面奖励可能长期没有检查，首次空队列也可能锁住当天机会。

**定位过程**：独立HTTP复现6项首批3项、同UUID仍3项、不同UUID才再3项；与页面每日缓存组合后缺少续批机会。

**根因**：把结果已知的成功回执当作全天操作，限流没有配套遍历/公平协议。

**修复实现**：队列返回has_more和剩余预算，已知接收后才续批，每次进入最多4个POST/每天10项，GET轮询不续排；未知UUID独立持久槽保留，旧成功键可恢复后退役。按最近已检查/定价日优先未覆盖者，失败也算当天已检查，不自动重试。

**防复发**：6项两批、13项日上限、次日未覆盖3项优先、失败不自动重试；真实双标签各次新进入及刷新，10项只10次假供应商调用；辅助测试核对未知UUID恢复、多个槽和旧键兼容。真实PG并发仍另验。

<a id="b70"></a>
### B-70 · 页面合并要保留旧设置和管理语义

**现象**：CareConfig关闭后旧care.today为空，新首页仍显示；原position排序、移除和零项隐藏也遗漏。

**定位过程**：独立页面/HTTP对比旧care与projects门面，发现新读路径只看项目开关，编辑不回填position。

**根因**：替换页面时只合并项目表单，没有接上原清单配置、排序和归档入口。

**修复实现**：门面返回care_config/position/removed及show_today，首页按原选择和有效当次分类展示。共用页维护显示、排序、停用和软移除，移除历史可勾选查看；旧ai_allowed保留。来源ID/事件/结果/结算不搬表，显式更正从原状态开始。

**防复发**：关闭/零项隐藏、2/40顺序、改名保留40、移除后原事件/结果/余额/已结算流水不变，双来源换分类保留skipped/partial。实际页面验证而不只构造合法API。

<a id="b71"></a>
### B-71 · 事件创建的flush会提前插入未完成的结果行

**现象**：新增首次部分完成用例，保存返回500；先报outcome非空失败，补齐后又发现facts缺省。

**定位过程**：R4分类历史用例和真实页面同时复现，查看SQL发现新PlanOccurrence在创建事件的db.flush时一并写入，结果字段在后续代码才赋值。

**根因**：依赖“稍后赋值”，忽略同一Session的flush会同步所有待写对象；missed分支不创建事件，早期测试没触发该提前插入。

**修复实现**：构造结果行时即初始化outcome=body.outcome、facts={}；后续填真实内容，仍与事件和回执同事务提交，不放宽数据库约束。

**防复发**：新8项复合用例及真实页面实际保存partial、再编辑项目、核对原结果与事件ID；全系统171项执行169通过/2真实PG未运行。首次失败日志单独留档，不能用最终表面按钮存在替代写库路径。

<a id="b72"></a>
### B-72 · 新流程的完成状态不能继续只看旧判定表

**现象**：用户已确认属性/金币分析，主页还显示待处理；属性建议和实际到账点数也不够清楚。

**定位过程**：顺着 HomeView → pending → FactAnalysis → FactBundle，发现 pending 只检查 AIJudgment.status；零奖励确认不一定创建判定。另对照 judge_service.confirm，实际属性还受既有置信度加权及上限影响。

**根因**：把“有已确认旧判定”当成唯一完成信号；把模型原始建议当作实际变化展示。

**修复实现**：新版记录按当前内容/许可版本的事实组和最新事实任务判定待办；已确认退出，主动重新分析仍能进入。已确认组只读关联实际结算判定的 final_changes，用来展示真正入账数值。首页回到可见时重新读取，提交分析后更新待处理摘要。

**防复发**：覆盖零奖励、有奖励、确认后重分析及+1建议以0.9置信度实际+0.9；读取展示不改余额。云端尚未发布本修复。

<a id="b73"></a>
### B-73 · 可编辑不代表初次进入就要铺开全部表单

**现象**：手机和桌面项目内容全部铺开；照顾自己也要求预计分钟；排序通过填整数，弹窗要滑很长。

**定位过程**：检查 ProjectManager 模板、共享 ConfirmDialog 和实际390像素编译页面；每行直接挂结果输入，表单把次要日期、排序字段全部放在主路径。

**根因**：数据复用后直接复用整套表单，没有区分浏览摘要与主动编辑。原焦点收集也不能可靠判断关闭的原生 details 子节点是否可见。

**修复实现**：记录与历史默认折叠，列表首批四项；照顾自己使用可选note小字，沿规则JSON及历史保存。上移/下移通过整组版本校验、用户锁和回执原子提交，仅调整显示顺序。次要日期/目标按需展开，操作栏固定，焦点陷阱只包含实际可见控件及summary。

**防复发**：跨plan/care排序重放、冲突及原历史不变；手机操作栏可达；关闭表单不丢数据；覆盖普通及管理员各入口横向布局。桌面模拟不能代替小米浏览器实机验收。

<a id="b74"></a>
### B-74 · 从当前列表移除与删除历史证据需要分开

**现象**：奖励只有停用按钮，停用后仍占主列表，积累后冗余。

**定位过程**：RewardShop遍历所有items，后端DELETE原本就是停用，旧兑换记录仍引用奖励身份。

**根因**：后端保留历史的行为没有对应前端归档展示；不能用物理删商品来解决列表长度。

**修复实现**：新增明确移除确认，关闭自动价格检查；主列表只展示启用奖励，已移除/停用项放在默认关闭区域并可恢复。带版本的DELETE请求通过原回执机制重放，保留原无请求体旧入口兼容。

**防复发**：购买后移除、UUID重放、余额与旧券完全一致、实际页面移除与恢复；不重定价旧券。

<a id="b75"></a>
### B-75 · 不能用之后的成功反推第一次失败原因

**现象**：用户报告第一次分析失败，之后成功，但找不到当时报错。

**定位过程**：已询问错误文字，用户确认找不到；本地没有这次云端任务错误证据，不能据此认定超时或供应商不兼容。

**根因**：首次失败根因待核实；当前页面只展示最新一次任务，重试后此前错误不易回看。

**修复实现**：本地把现有最近20条事实分析任务的时间/状态/安全错误编号与受控中文说明放入折叠历史；正在分析持续显示明确状态。未改成自动无限重试，也未采集Key、供应商原文或隐藏思考。

**防复发**：安全错误说明只用已知分类，未知错误不回显任意原始异常。需用户更新后查看失败任务编号；本条不标为真实故障已定位或已修复。

<a id="b76"></a>
### B-76 · 修复一个日期入口不等于所有同名入口已替换

**现象**：上线后用户仍在“内容日期”看到yyyy/mm/日。

**定位过程**：导出已经使用完整文本日期；手账RecordList仍使用input type=date。

**根因**：上一轮修复范围只覆盖导出；原生分段占位由浏览器决定。

**修复实现**：10月22日本地改为默认“全部日期”的文本框，复用真实日期校验及清除入口，内容日期筛选语义不变。

**防复发**：有效日期参数、非法日期不发请求、清除筛选和桌面/窄屏验证；这处改动与本轮一起仍待发布。

### B-77 · 发布彩排被“上次补发”卡死：一次性脚本不能当长期门票

**commit** 通用化提交（2026-11-11）· **文件** `ops/rehearse_reward_repair.py`（删）、`ops/rehearse_public_update.py`（增）、`ops/rehearse-public-update.sh`、`ops/update-public.sh`

**现象**：11 月 11 日准备第二次云端发布（纯 UI 改动，无迁移）时，发现强制彩排 `rehearse-public-update.sh` 必然失败——`update-public.sh` 没有 `ISOLATED_PG_REHEARSAL_PASS` 就拒绝切换，而彩排本身跑不过。

**定位过程**：读 `ops/rehearse_reward_repair.py` 第 23 行硬编码 `inspect_source(db, '旭旭仔', 3, 35, 24)`、第 36 行 `assert result['coins_added'] == 24`；事件 35 已于 10-25 在生产补发（`CLOUD_UPDATE_2026-10-25.md` 记录余额 55→79），恢复副本带既有回执；`repair_confirmed_rewards.py` 的 `RequestReceipt` 幂等保护遇“同请求键、不同方案摘要”抛 `DIFFERENT_PLAN_ALREADY_APPLIED`。git 历史确认这套彩排脚本 10-25 才首次入库，仅跑通过一次，本就是一次性设计。

**根因**：**把“本次发布专属的业务断言”写进了“所有发布的通用门槛”**。探针注释自称 mechanism test，实际混入了只对 10-25 那次补发成立的断言；脚本过期后没人删，成为永久路障。

**修复实现**：删一次性探针，新增通用只读探针直接复用 `cloud_update_snapshot.capture()`（只读事务 + 连接目标三元组强制校验 + b025 + 表/序列计数 + 凭据解密），断言面收敛为“备份能恢复、角色能读、凭据能解”；外壳的隔离网络、独立卷、生产容器不变自证原样保留。本地以假模块跑通三分支（环境守卫/只读 PASS/空恢复拒绝）。

**防复发**：① 写“门槛类”脚本时区分通用检查与当次专项断言，专项断言用参数化或独立文件，不硬编码业务实体；② 一次性运维脚本在任务完成后标注“用过即废”或直接删除，需要时从 git 历史找回；③ 发布流程文档（CLOUD_UPDATE）同步记录门槛的校验字段契约，改探针前先核对切换脚本消费哪些字段。

### B-79 · 每天重复的安排被当成“上一次的那件事”

**commit** 同天口径提交（2026-11-11）· **文件** `app/services/fact_analysis.py`、`tests/test_fact_same_day_scope.py`

**现象**：用户把「阅读」设成每日安排，当天记录完，分析结果里出现「这条内容是在重述已有行动，还是另一次行动？」两个按钮。第二天再记，又问一次，天天都问。

**定位过程**：前端只有 `item.decision==='unresolved'` 才渲染这个问句（`EventFactAnalysis.vue` 第 77 行），顺着它找到 `fact_analysis.generate()` 的 `needs_review=bool(candidate or options or proposal.relation!='new')`。再看送进模型的候选集 `known`：取的是**最近 100 条事实、不限日期**，且每条只带 `fact_id/event_id/excerpt`——**没有日期**。模型看到的是一堆一模一样的「阅读30分钟」，没有任何时间线索，只能按字形相似判 `relation='uncertain'`；而 `relation!='new'` 本身就等于弹窗。提示词里那句“已知事实可能来自同一天不同活动……不确定标uncertain”更是直接鼓励模型标不确定。用户既有的口径（`docs/DESIGN_REVIEW_SUMMARY_2026-11-05.md` 验收表：“同一天两次阅读、连续两天同书同分钟 → 真正独立的活动不误合并”）从未落到代码里。

**根因**：**把“去重”做成了“跨天全文查重”**。同一次行动的判断本来就是当天范围内的问题：每日重复的安排，每天都是独立的一次行动，昨天那次与今天这次没有任何合并价值。代码把三个月历史塞给模型还不给日期，等于逼模型按字面猜，再把猜测变成一次人工追问。

**修复实现**：① 新增 `content_day(event)`——`occurred_on` 优先，否则按 `timezone_at_capture` 换算本地日，取不到返回 `None` 且不与任何日期相等；② `known` 只收**同一内容日**、且排除本文事件自身的 fragment，并带上 `day` 字段；③ 硬兜底：模型给的 `related_event_id`/`related_fact_id` 若不在当日集合 `same_day` 内，直接丢弃为 `None`（不报错、不弹窗）；④ `needs_review` 的 `relation!='new'` 分支加上 `and same_day` 门槛——当天没有可比事实时，“不确定”降级为新的一次行动；⑤ 提示词写明 known_facts 只含同一内容日、每天重复安排各自 `relation=new`、不跨天比较；⑥ 同一口径延伸到「选一条已有事件」的选择器：`GET /event-options` 无关键词时只返回**与当前记录同一天**的记录（`day` 跟随该记录的发生日，缺省今天；老数据按 `occurred_at` 落在当日兜底），只有输入关键词才跨天检索——首屏不再铺几个月前的记录，补记前天的事也仍然能关联到前天的记录。

**防复发**：① 凡是“是不是同一件事”的判断，候选集必须自带比较范围（同一天/同一事件）和日期字段，不给范围就是让模型瞎猜；② 让模型“谨慎”的措辞要和人工介入成本对齐——标 uncertain 会直接弹窗打扰用户，不能一边鼓励不确定一边强制追问；③ 用户口头的业务口径要落成可执行的断言，`tests/test_fact_same_day_scope.py` 固定跨天同文本 `candidate_fact_id is None` 且 `decision=='keep'`；同天候选后来由 B-80 进一步改成不阻断主流程。

### B-80 · 「是否同一次行动」变成分析与入账的强制闸门

**文件** `app/services/fact_analysis.py`、`app/routers/analysis.py`、`frontend/src/components/EventFactAnalysis.vue`、`frontend/src/components/FactAnalysis.vue`、`tests/test_fact_same_day_scope.py`

**现象**：分析结果一出现“这条内容是在重述已有行动，还是另一次行动？”，用户就无法继续查看属性与金币预览，也不能确认入账；即使不想关联，也没有一条不受阻的主流程。

**定位过程**：`EventFactAnalysis.vue` 在 `unresolved` 时自动展开核对区，并在已有预览时禁用主按钮；后端 `preview()` 把所有 `unresolved` 项排除在 `eligible` 之外，`confirm()` 再主动抛 409；`/pending` 还把这种建议标成 `needs_input`。四层代码共同把一个模型猜测变成了强制人工步骤。

**根因**：**把辅助去重误当成主流程的前置条件**。模型只是提出“可能相同”的候选，并没有足够事实替用户做决定；但系统却让候选拥有否决分析、属性、金币和待办状态的能力。

**修复实现**：① 新生成建议一律以 `decision='keep'` 继续，候选仅保留给主动合并；② 预览不再因 `unresolved` 排除属性与金币，确认接口删除对应 409，因此旧草稿也能直接继续；③ 待办不再把关系候选算作 `needs_input`；④ 前端不自动展开关系核对、不禁用主按钮，只在明细里保留“是同一次行动”的显式去重入口；⑤ 同一来源改写且已有结算的特殊场景默认不重复发奖，但整组仍可确认，用户明确选择“另一次行动”后才可作为新事实结算。

**防复发**：辅助判断不得默认拦截“保存→分析→预览→确认”主链路；只有用户明确选择的合并或跳过才能改变结算资格。回归测试同时覆盖“新同天候选可直接结算”和“旧 `unresolved` 草稿可直接结算”，避免只修新数据、旧页面仍卡死。

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

---

## 第 13 章 从 v1.11 到邀请制云端：当前代码怎样连起来

本章按 `ba7031e` 的源码讲解。不要把交付文件里的“当时未运行”直接改成“永久未完成”，也不能把后来的某次通过覆盖掉旧失败证据。每轮结果保留版本和环境。

### 13.0 补齐 v1.7~v1.10：游戏化模块接在什么位置

旧逐层讲解停在 v1.6，之后的功能不能只记版本名；先按“对象→操作→结算”找到入口：

| 模块 | 主要服务 | 该懂的关系与边界 |
| --- | --- | --- |
| 自建打卡项目 | `item_service.py` | CheckinItem 定义项目，Event.item_id 关联事实；次数/日期统计来自记录，不等于另造一份日记 |
| 目标 | `goal_service.py` | Goal 记录目标与审计，达成/失败是终态动作；重复结束不能再发同一份点数 |
| 金币与行情 | `coin_service.py`、`economy_service.py` | 前者写余额/流水，后者只读行情快照；模型定价建议不能直接绕过账户写入口 |
| 挑战 | `challenge_service.py` | 候选/档位→接受与押金→事实/判定→用户结算；接受后不能任意换档，退缩/到期也有生命周期 |
| 商店与奖励券 | `shop_service.py` | 商品价格与兑换券是两个对象；兑换扣币建券，兑现不再次收取购买价 |
| 成就 | `achievement_service.py` | 累计规则与 AI 发现型建议不同；唯一 code/状态避免重复授予，删除后不能靠重授刷奖励 |
| 豁免券 | `exemption_service.py` | 有时间/作用边界，按历史事件发生时段判断命中；不是删除真实负面事实或随意抹掉历史 |
| 满级子维度 | `subdimension_service.py` | 主维 parent_id 层级、提议后用户选；图表/活动统计要区分主子维，负向落点仍须按实际规则核对 |
| 停滞觉察 | `stagnation_service.py` | 没记录不等于没行动；用户回答、冷却、可选补课挑战分开，不能自动凭空扣分 |

**以 v1.10 AI 定价为例**：模型先读当前余额、近期收支与物价区间，给挑战/商品价格建议；服务再验证合法性，用户主动接受/购买后才改账。更换定价方式不能给历史商品和已接受挑战悄悄重定价。它与用户新提的“普通事件主线加成”不是同一个功能，当前普通事件仍用旧 2 币规则。

可以用四个问题读任一模块：哪个是原事实？哪个是模型建议？哪个动作改变账户？重复/取消/异常时，状态与流水是否仍一致？B-20~B-24 是这些模块上线后真正付出的工程成本。

### 13.1 先认识三个独立动作：保存、分析、入账

```text
文字 → POST events → Event 原文＋保存回执 → 已保存
                       ↓ 用户主动选择现在/稍后分析
                 AnalysisJob → worker → 追问或 AIJudgment 建议
                                                 ↓ 用户确认
                           属性＋实际流水＋金币＋审计＋回执，同事务提交
```

**为什么分开**：原文是用户的劳动成果，不应该因为模型欠费、超时或 JSON 错误而消失。模型输出是候选解释，不能直接成为已结算事实。用户确认后再改账，也才有明确的撤销依据。

**对照场景**：你写“今天完成部署”。API 先保存这句话；worker 可能要求补充，原文仍然存在；你补充后得到建议，再确认才产生属性/金币流水。没有 Key 仍可保存和回看；“稍后”不自动排队；“现在”在保存成功后另外提交任务。

**从哪里读**：`frontend/src/components/RecordComposer.vue` → `frontend/src/api.js` → `app/routers/events.py`；分析看 `app/routers/analysis.py`、`app/services/analysis_jobs.py`、`app/worker.py`；确认/撤销看 judgments/events 路由与 `judge_service.py`。云端旧同步 judge/supplement/dispute 入口拒绝执行，不能用旧教程绕过任务预算。

### 13.2 模型从 17 表扩展为“业务＋身份＋派生过程”

| 模型位置 | 新增或演进的数据 | 为什么不能只存在前端变量里 |
| --- | --- | --- |
| `app/models/__init__.py` | 原 17 核心表；用户角色/时区/密码哈希、事件 content_version/analysis_intent/is_deleted 等 | 业务主体、实际账目和原文必须持久保留 |
| `app/models/access.py` | AuthSession、Invitation、RecoveryToken | 会话可撤销、邀请/恢复码可一次性消费 |
| 同上 | LLMCredential、AnchorOverride | 模型凭据每人独立；内置锚点只读，校准写个人覆盖 |
| 同上 | RequestReceipt、EventDerivation | 响应丢失可查操作结果；派生信息可指出源事件版本 |
| `app/models/analysis.py` | AnalysisJob、ModelUsage | 浏览器关闭后任务仍在；预算与租约不是某个标签页独有 |
| 同上 | DailyReview、ReviewLink、GrowthReport | 日回顾和报告可回看原来源，避免伪造新事件/重复奖励 |

**三个数据层的区别**：Event 是当时写下的事实；AIJudgment/报告是对事实的派生理解；AttributeHistory/CoinLedger 是确认后真实发生的变动。显示“已合并”不等于两个 Event 被物理合并；显示建议 +0.5 也不等于已经入账 +0.5。

### 13.3 local/cloud：同一项目，两种明确的启动契约

`app/config.py` 用 `run_mode: Literal['local','cloud']`，拼错模式要启动失败。`app/main.py` 的 `init_db` 分支如下：

| 本地兼容模式 | 云端模式 |
| --- | --- |
| 默认 SQLite，先在线备份再自动补列/种子/默认用户 | 显式 PostgreSQL URL、HTTPS origin 和密钥文件 |
| 为既有单用户使用保留兼容入口 | 通过真实会话识别用户，不回退默认用户 |
| 旧轻量迁移 | 独立 `alembic upgrade head`；API 仅检查头是否匹配 |
| 可保留个人 `.env` 模型回退 | 无平台公共 Key 回退，必须本人绑定 |

Alembic 四版为 `a001_legacy` → `a002_identity` → `b003_analysis` → `b004_reports`。迁移工具描述结构怎样演进，不等于已经导入旧日记。API 启动检查数据库版本，是为了避免“源码已经更新，库却少列”时还接收用户写入。

`deploy/entrypoint.py` 从秘密文件建立应用数据库连接；`deploy/init-app-role.sql` 给空 PG 卷初始化应用角色。当前换行密码缺陷见 B-34：现网手动修复与源代码初始化缺陷必须分开记。

### 13.4 身份、授权与个人模型凭据

**认证：证明你是谁。** `auth_service.py` 用 Argon2 验证密码；登录生成随机令牌，数据库只存摘要，浏览器持有 `__Host-gol_session` Secure/HttpOnly Cookie。写请求检查 Origin 和 CSRF token；退出撤销会话。登录不是每次都重新注册。

**授权：证明这件事你能做。** `current_user` 把 user_id 放入请求对应 Session；`owned_repository.py` 过滤查询并检查写入外键归属，不能靠前端隐藏别人的按钮。owner 的邀请码接口另有 `require_owner`。用户 ID 出现在请求中，不代表调用者就有权限操作它。

**邀请与找回的当前边界**：邀请仅用于新注册，默认 72 小时、一次性；没有邀请码无法注册，已有账号正常登录。后台有 owner 邀请生成接口，前端没有对应入口。忘记密码用一次性恢复码；邮箱/手机号/QQ/微信找回、登录后主动改密码、公告后台都尚未实现，不能把用户提供的证书邮箱当成已绑定账号邮箱。

**为什么哈希密码，却加密模型 Key？** 登录只需比较是否匹配，不需要还原密码；调用供应商必须拿到原 Key，所以 `credentials.py` 用 Fernet 加密，密钥文件留在数据库之外，以 key_id 管版本。数据库丢失能从备份恢复；若主密钥同时丢了，恢复的密文也无法解密。

**配置的四层含义**：

1. `LLMCredential` 存本人 primary/aux 组、provider/model、密文及配置版本。
2. `credentials.save_config` 处理保留/替换/清空和换供应商约束；GET 只回掩码，不回 Key 全文。
3. `resolve_llm_config` 根据用途选组：judge 优先 primary，aux 用途优先 aux；允许组间回退，云端不回退平台 `.env`。
4. `assert_current` 在结果写回时复查版本，旧配置发出的结果不能覆盖新配置状态。

供应商当前固定三家；`PinnedTransport` 检查 HTTPS 主机、DNS 公网 IP、连接固定及 SNI，不跟随重定向，不读系统代理。扩大供应商范围不只是给下拉框加一项。模型名的合法格式与供应商是否真有此模型也是两种验证；F02/F03/F16 的体验问题仍未解决。

### 13.5 UUID 回执与版本：防重复和防旧数据各管一件事

**概念卡 · 幂等**：同一次操作收到两遍，业务效果只有一次。当前回执按 `(user_id, operation, request_key)` 唯一，保存输入指纹和结果快照。

`app/services/receipts.py` 的结构很小，值得自己读：`MutationIn` 携带 request_key/expected_version；`replay` 查已完成结果，同 UUID 异正文 409；`record` 在**同一业务事务**写回执。不能先提交扣币、后另一个事务写回执，否则中间崩溃仍有空窗。

**概念卡 · 乐观版本**：操作前说明“我基于哪个版本”。若你打开价格 30 的商品，别人/另一设备已改到 40，不能无提示按旧页面结算。版本冲突拒绝的是过时依据；UUID 回执解决的是重复发送。它们不能互相替代。

```text
操作 UUID=甲，正文=兑换奶茶 → 已提交但响应丢失
再次 UUID=甲，正文保持原样 → 返回原回执，不再扣币
再次 UUID=甲，却改成兑换电影 → 409，阻止身份混用
用户明确再买一杯，UUID=乙 → 一笔新的购买
```

前端 `useRedemption.js`、`useExemptionPurchase.js` 保存账号专属操作信息；成功后的列表刷新失败要提示读取问题，不能把已经成功的购买重新做一次。切换账号时旧草稿、请求和迟到响应不能流进新账号。

### 13.6 后台任务、租约与费用预算

**概念卡 · 持久队列**：任务保存在数据库。页面关闭并不删除任务；worker 是独立进程，定期领取任务处理。

阅读 `analysis_jobs.py` 时先看三个函数：

- `submit`：校验事件/判定版本、用户、已有活动任务、追问 job ID、配置可用性；同请求返回已有任务，异正文拒绝。
- `claim`：PG 协调领取、锁行，赋予随机 lease_token 和 240 秒租约；过期任务按剩余预算重排或失败，活动任务有唯一约束。
- `process`：调用前校验，供应商等待不占写事务；写回前再次校验租约、事件是否删改、判定版本与配置版本；建议、日志、任务终态一起提交。

**租约像限时工作证**：旧 worker 卡住后任务被接管，新 worker 拿到新 token；旧 worker 晚回来，不能只凭 job ID 写结果。取消、编辑、换 Key 后也要拒绝迟到写回。

**任务状态与判定状态不是同一回事**：queued/running/needs_input/ready/failed/cancelled/superseded 描述处理过程；pending/adjusted/confirmed 等描述业务判定。任务 ready 只表示有建议，不表示已经发币。详情页缺自动更新是 F14，不能因后台设计正确就认为前端状态一定及时。

当前控制：SDK 隐式重试 0、总尝试预算 2、单次总截止 90 秒、连接超时 5 秒、每用户每天 30 次预算；实际请求串行还有进程/PG 锁。预算按尝试预留，取消后供应商可能仍计费，不能宣传“绝不重复计费”。worker 有心跳及周期维护，不是只看容器进程存在就证明每个任务成功。

### 13.7 事务与账本：把一次用户动作完整地落地

`transactions.lock_profile` 通过更新用户 profile 取得数据库锁，是每用户写入串行的共用入口；服务还会锁具体对象或用条件更新认领状态。统一锁顺序可减少互相等待；`rollback_on_error` 出错回滚，但实际提交边界仍由业务入口负责。

**一个兑换事务**：锁用户 → 校验商品/版本 → 原子扣余额 → 建兑换券 → 写金币流水 → 写回执 → commit。任一必需步骤失败，全部 rollback。兑现券是消费已买到的权利，不再扣一次购买价。

**一个确认事务**：校验判定与版本 → 聚合合法维度 → 记录实际属性增量/审计 → 计算现有奖励 → 写回执 → commit。当前普通事件净增为正时固定奖励 2 币；用户提出主线目标加成，但还没有规则或实现。

**一个撤销事务**：逻辑删除 Event，保留判定/原文/审计；按实际属性流水反向，已发金币按现规则保留。它不是清除所有痕迹。未来若改金币规则，需要另行讨论，不能倒改历史账。

**查完整策略**：[业务写路由策略](../BUSINESS_WRITE_POLICY_2026-10-10.md)列出实际入口、版本/回执/锁/模型边界。不同写入口有不同协议；不要宣称所有新建对象都跨不同 UUID 自动去重，也不要把 ORM 自动归属过滤当成所有 raw SQL 都自动安全。

### 13.8 基线、日界、日回顾与报告来源

**基线不是测量**：未评估用户主动选择 13 维各 50、启动 80 币，是游戏起点。默认创建 13 个占位维度不等于已建档；完成状态是 onboarding_completed。已选基线不能再用问卷覆盖；旧 40 币不补差。F11 的“熟练”标签仍与这层含义冲突。

**时间不是单个字符串**：云端统一 UTC 持久化，用户 timezone 决定日界。`time_service.date_range` 把某本地日期转换为查询范围；一天不总是 24 小时，历史合成测试包含夏令时 23/25 小时。occurred_at 是发生时间，created_at 是保存时间，不应为了隐藏控件就混为一个字段。

**回顾只关联原事实**：DailyReview 按用户/日期/保存时区唯一；ReviewLink 保存事件版本。手写回顾不生成新事件、不重复发奖，也不要求模型 Key；当前路由不调用 AI，不能称已有完整“AI 睡前总结”。多设备编辑用整数版本冲突，保留输入再比较。

**报告保留当时的来源**：GrowthReport 存 payload 和 provenance；来源后来编辑、删除或不可用时要说明，不能默默把报告引用换成最新正文。报告是派生历史，不应成为新的生活事实再拿来赚币。

### 13.9 当前前端：导航、状态和布局分别由谁负责

| 阅读顺序 | 文件/职责 | 学习时要问的问题 |
| --- | --- | --- |
| 入口与路由 | `main.js`、`router.js`、`App.vue` | 四主导航如何把详情/旧页归到相应区域？懒加载何时加载？ |
| 身份与请求 | `session.js`、`api.js` | Cookie/CSRF、退出中断、旧账号响应在哪里处理？ |
| 日常原文 | RecordComposer/List/Detail、HomeView | 草稿、已保存、后台任务、判定建议是不是被混为一谈？ |
| 待处理与回顾 | PendingView、ReviewView | 怎样回到未完成任务，怎样保存同一天的回顾？ |
| 成长与设置 | AttributePanel、MyView、SettingsView | 模型摘要、游戏基线、旧功能入口如何呈现？ |
| 操作复用 | useRedemption/useExemptionPurchase/useToast/useDateGroups | 哪些是业务协议，哪些只是显示反馈？ |
| 样式层 | design-tokens.css、ui-layout.css、styles.css | 颜色语义、断点、局部金额/按钮和长内容各由哪层约束？ |

Vue 的响应式只在数据变化后重绘；worker 完成不会自动跨网络改变浏览器 ref。需要主动读取或订阅，这就是 F14 的原理。CSS 断点已区分桌面侧栏和窄屏导航，但自适应不是只判断 User-Agent，更不是“有媒体查询＝手机体验已验收”。

10 月 10 日 UI 精修保留了保存/交易/账号隔离协议；不要为改弹窗外观重写回执逻辑，也不要为页面不溢出把所有横向内容强行藏起来。F13/F15/F20 说明信息层级、局部断行与页面长度仍需实际体验核对。

### 13.10 自己动手读代码的练习（不操作真实数据）

1. 画出“保存成功但模型失败”的数据状态，说明为什么只重试分析。
2. 找到 Invitation 的 token_hash、consumed_at 和生成路由，解释为何没有前端按钮却有后端能力。
3. 在 receipts.py 找到唯一键与异正文 409，写出两次购买和同次重试的区别。
4. 在 analysis_jobs.process 的 validate 中标出取消、编辑、换 Key、过期工作证各靠哪条检查挡住。
5. 对照导出器的模型列表，解释为什么日记 CSV 不含金币明细，而 JSON 包含。

练习只需读代码/画图；不要运行生产删除、初始化、导入或付费模型调用来“验证理解”。

---

## 第 14 章 从代码到服务器：离线发布、私有 HTTPS 与数据保护

### 14.1 先分清六个东西

| 名称 | 它记录什么 | 不代表什么 |
| --- | --- | --- |
| Git commit | 一次源码历史状态 | 已上传或已部署 |
| push | 把提交上传远端 | 自动更新服务器 |
| Actions run | 某次工作流实际执行 | run 成功就已完成业务验收 |
| 源码包＋RELEASE_MANIFEST | 固定源码文件与摘要 | 当前已安装镜像正确 |
| 镜像包＋images manifest | 构建出的镜像配置/角色/平台/用户 | API/DB 已健康 |
| BUILD_RECEIPT/目标检查 | 哪次构建、哪些核验实际完成 | 自动恢复、公网与真机全部通过 |

本次离线工作流在 `.github/workflows/build-deployment-bundle.yml`；`ops/package_release.py` 固定源码，`build-images.sh` 构建/导出镜像，`verify_package.py` 核对源码，`image_identity.py` 核对镜像。不要在服务器上临时改一个脚本后继续声称运行同一个已验发布包。

**概念卡 · 哈希**：同样字节得到同样摘要，用于发现变化，不是知道数据含义。源码 SHA、镜像配置 SHA、数据库备份 SHA 分属不同对象。一个通过不能替代另外两个。

当前镜像身份 schema v2 四角色 api/web/ops/postgres；配置摘要取原始字节，不能解析重排 JSON 后再算。标签/平台/User 另校验；observed_id 只作诊断。verify-archive 只查输入包，目标 verify 要查实际已安装镜像。B-32/B-33 是这套边界从真实部署中学到的修正。

### 14.2 Compose 中每个服务干什么

| 服务 | 职责与生命周期 |
| --- | --- |
| db | PostgreSQL 数据；命名卷持久化，不发布宿主机数据库端口 |
| migrate | 一次性显式升级 Alembic 结构，成功后退出 |
| api | HTTP 认证、保存、读取和业务写入口 |
| worker | 后台模型任务及周期维护，独立心跳 |
| caddy | 静态前端、反向代理、HTTPS；证书数据另存卷 |
| ops | 按需备份/恢复/运维，不等于一直运行的业务服务 |

`restart: unless-stopped` 用于长期服务；健康检查与依赖顺序帮助启动，不证明所有长期故障会自动恢复。命名卷与独立秘密目录让容器重建后数据继续存在；仍须实际主机重启演练，不能只看 YAML 得出“永远不用维护”。

服务器内存约 1.6 GiB、swap 2 GiB。健康截图显示一次空闲时刻资源可用，只能作观察起点。`ops/observe-resources.sh` 的持续窗口、模型请求高峰、备份临时磁盘及日志轮转都需另验，不能拿一次 free -h 作容量保证。

### 14.3 回环监听、SSH 本地转发和 HTTPS 名称

**回环地址** `127.0.0.1` 表示当前机器自己。服务器 127.0.0.1:8443 与你电脑的 127.0.0.1:443 不是同一个端口空间。SSH `-L 本机地址:本机端口:远端目标:远端端口` 把两者连接起来。

```text
Windows 专用 Edge 访问 https://lifexp.cn
  ├─ 专用解析规则：lifexp.cn → Windows 127.0.0.1
  ├─ 本机 443 由 SSH 监听
  └─ SSH → 服务器 127.0.0.1:8443 → Caddy 容器 443
```

仍用域名访问是为了 HTTPS 名称和应用 origin 一致，不是偷偷修改公网 DNS。内部 CA 根证书已下载并校验后用于该私有测试；公开证书仍未启用。证书文件不是私钥文件，主密钥/SSH 私钥都不应贴进截图或 Git。

**执行位置是命令的一部分**：Windows PowerShell 的 `$env:USERPROFILE`、`Get-FileHash`、`&` 不能直接粘到服务器 Bash。此前备份下载脚本贴错终端产生语法错误，后来在 `PS C:\Users\19687>` 下执行才成功。以后命令块标出“本机 PowerShell / 服务器 Bash / 容器内”，并看提示符确认。

实际重连命令与保活解释集中在 [私有试用审查](../PRIVATE_TEST_REVIEW_2026-10-12.md)，不在多处复制可能过时的操作指令。公网开放前，所有服务器 Compose 操作都应同时使用 base 和 private override；只用 base 会恢复公开端口映射，不能随手切换。

### 14.4 健康与 TLS 分层验证

`/api/health` 表示进程能响应；`/api/ready` 执行 DB SELECT 1；Caddy 对外只提供 `/service-status` 转发就绪检查，内部健康/docs 路由按设计隐藏。已知截图 ready、未登录事件 401、内部端点 404，分别证明依赖就绪、认证拦截和路由边界。

它们都不能证明真实账号登录、日记保存、模型调用、账目一致和备份恢复已全部完成。TLS 证书可信也不代表应用业务健康，首页 200 更不能替代数据库检查，见 B-31。

**本次进度**：包/镜像及运行目录校验、DB 认证现场修复、b004_reports、owner、db/api/worker/caddy 私有启动已有用户证据。备案仍审核，公开 DNS/端口/证书切换、电脑关机后手机访问仍待执行；不需要把这句话读成“今天已远程检查仍 Healthy”。

### 14.5 三种“保存一份”的边界

| 材料 | 适合用途 | 关键限制 |
| --- | --- | --- |
| JSON 个人导出 | 留存个人业务结构、审计与关系，当前 format_version=3 | 不含登录会话/密码哈希/模型密钥，不是整机恢复包 |
| CSV 事件导出 | 表格查看事件，UTF-8 BOM，9 列 | 不包含完整金币、成就与判定结构 |
| PG dump＋配套恢复材料 | 恢复数据库并核账；秘密配置/密钥单独保护 | 归档可读不等于恢复成功；缺主密钥不能解密凭据 |

用户希望适合本地阅读的事件日记，Markdown/HTML/PDF 如何提供仍待商定，本轮没有新导出按钮。现有 JSON 并不只有日记，也含金币、成就等个人业务；也不能写成“所有服务器数据全导出”。

首次云备份目录 `lifexp-db-backup-20261011T150955Z` 已生成、归档可读、下载并核 SHA；它早于后来部分测试操作，需后续新鲜备份。自动异地备份、保留、失败通知及真实隔离恢复尚待验证。此前本机合成恢复成功只能作工具能力证据。

### 14.6 旧数据迁移：先保全，再证明，最后切换

主候选是项目根 `game_of_life.db`；32 事件/32 判定/124 属性历史等定位证据及指纹见 [旧数据定位](../LEGACY_DATA_LOCATION_2026-10-12.md)。本次不重新读取用户正文、不启动本地应用触发迁移、不复制/清洗/导入真实库。

当前工具 `ops/import-sqlite.py` 先预检完整性/外键/语义引用和源哈希，再向 PostgreSQL 导入；`apply` 会拒绝非空目标账号，包括已有基线/凭据等情况。**当前 owner 已有测试数据，不是可以直接导入的空目标**。是否新建日常账号、旧数据归哪个账号，需用户商定。

后续顺序：确定源和身份 → 一致冻结备份 → 只读预检并处理发现项 → 独立库试导入 → 逐关系/基线/流水/余额核对 → 再决定正式切换。原数据库及备份始终保留。历史交付记载过一条悬空引用，定位轮没有重跑 foreign_key_check，不能编造“已修复”或自动补造丢失事实。

---

## 第 15 章 当前验收结论、产品讨论与下一轮学习

### 15.1 这一轮究竟测到了什么

10 月 12 日隔离审查使用临时 SQLite、合成账号、模拟模型与真实编译 Vue/本机 FastAPI：111 项中 100 通过、11 跳过、0 失败/错误；Vite 610 模块构建通过；桌面 1440×1000/手机尺寸 390×844 各 14 页，共 28 图。没有请求真实供应商，没有用当前云账号跑破坏性/并发用例。

跳过的是 9 PG、1 Caddy、1 restic 集成，不算通过。早期交付中对应环境有部分独立验证，保留各自版本和范围，不能把它们移植成这轮实测。构建仍有图表大分包提示；通过构建不等于弱网加载已优化。

页面没有整体横向溢出和捕获异常，不代表每个控件都好用。人工查看才发现金币 80 断行；静态代码审查发现详情没有自动更新。证据在 `docs/review/private_test_2026-10-12/`，完整说明见 [审查记录](../PRIVATE_TEST_REVIEW_2026-10-12.md)。

用户云端截图另证明：owner 登录；记录保存/读取、AI 追问及建议；未评估基线与 80 币；确认后智力 50.4、金币 82；奶茶兑换消耗 30 后余额 52、一张待兑现券；数据库备份下载校验通过。**券已兑现、重新登录后的余额/属性保持、回顾刷新后保存**仍按审查 A1~A3 待补，不从截图内容自行推断完成。

### 15.2 产品意见怎样进入下一轮，而不提前改程序

| 反馈组 | 已知结论 | 仍需商定 |
| --- | --- | --- |
| F01~F04、F16 | 配置保存≠模型可用，测试/绑定摘要不清楚，缺新用户帮助 | 验证触发、费用、供应商扩展与指南入口 |
| F05~F10、F14 | 状态条件、单事件/日总结范围、重复说明、关联语义有问题 | 生活提醒、日期补记、总结 AI、去重确认和状态更新方式 |
| F11/F12 | 未评估显示熟练不合适；用户希望金币向当前主线倾斜 | 标签含义、主线定义/切换/加成；未授权重算历史 |
| F13/F15/F18/F20 | 原生框、吸顶金额、窄屏断行和长页面影响体验 | 桌面/手机信息层级与关键入口，不是全站一律折叠 |
| F17/F19 | 需要本地日记留存，关注 App/微信小程序 | 导出格式及内容范围、渠道优先级和实际工作量 |
| F21~F24 | 邀请后端存在而 UI 缺；恢复只靠码，缺主动改密；提出独立管理身份 | 邀请范围、邮箱等恢复、管理员/普通账号、公告及管理权限 |

**管理员想法的学习点**：可以共享登录页面，由后端角色决定管理入口；“独立管理员账号”不等于要复制一套登录系统。管理员发布公告/改站点设置与开发者改代码是不同层次。不能默认管理员能读他人日记、查看模型 Key 或随意改金币。以上都是讨论方向，账号/后台/公告未创建。

**App 想法的学习点**：API 能复用，不表示 UI、身份、下载和系统权限都能直接搬。现有 manifest 不等于已实现完整 PWA；原生壳和微信小程序各有适配成本。当前只记录方向，不替用户决定框架或购买服务。

**历史约定要有时间语境**：原来的 journal 逐面追问、PWA 预想、只 commit 不 push，都解释当时为什么这么做；用户现在的明确意见或具体授权优先。笔记不能用旧规则反过来要求用户按过去的想法使用产品。

### 15.3 接下来的停点：知道没完成什么，也是学习成果

1. **私有试用收束**：沿用已有证据，一次性补必要主流程；不反复要求制造同样错误或付费调用。
2. **讨论反馈并写正式方案**：F01~F24 先商定；尤其主线激励、生活提醒、账号恢复与管理、日记导出和多端范围。
3. **独立运维验证**：初始化密码源修复、新备份、真实隔离恢复/密钥、异地备份/通知、资源与重启持久化；不拿 YAML 或脚本存在当通过。
4. **旧数据迁移**：选源、冻结、预检、试导入、对账、账号归属和正式切换，不覆盖当前测试账号碰运气。
5. **公开访问**：以实际备案结果为条件之一，再核 DNS/端口/公开证书/配置，电脑关机后手机蜂窝验收。

这不是今天已经批准执行的清单。本轮只补学习文档，没有提交/推送、改产品、创建 Issue、生成邀请、发布公告、迁移或公开上线。

### 15.4 新增概念的自测题

- 为什么保存按钮成功不能用 AI 分析成功来定义？
- 身份认证、资源授权、CSRF 和 CORS 分别拦截什么问题？
- request_key、expected_version、lease_token 分别处理重复、过时与失去执行权的哪种风险？
- 同一镜像为什么外层 ID 能变，原始配置摘要却可用来验证身份？
- localhost 的 trust 密码测试为什么会误导排障？
- 下载备份并核哈希后，还缺哪些证据才能宣称恢复可用？
- 同样是 50，为什么“游戏起点”和“能力熟练”不能直接划等号？
- 哪些新反馈是已定位缺陷，哪些是新需求，哪些仍然不能确定根因？

回答时先用自己的话，再找对应源码与故障档案。能说明证据与限制，比记住一串部署命令更能帮助你独立维护下一个项目。


## 第 16 章 从完整 Demo 确认到可实施规格（2026-10-18）

本章记录设计与交接进度，不是新功能实现报告。第二版完整 Demo 的 36 个模块、207 项检查说明本机预览覆盖；当前真实源码仍从 `ec5259b` 接续，不能拿这些预览数字代替数据库／worker／真实模型验收。

### 16.1 一份原文与一件事实为什么不是同一个东西

白天写“读完英语文章”，晚上日记同时写了英语阅读、跑步和新的绘画。一篇日记是一个文档，可以引用三个事实；英语和跑步可能已经奖励，绘画才是新增。需要保存“原文及版本 → 片段 → 事实身份 → 判断／结算”的关系，原文完整保留，奖励按事实去重。

旧 `EventFact.event_id` 唯一适合事件单事实，不能靠解除日记拒绝就支持整篇多事实。后续 Writer 需要扩展关联结构和逐事实结算，保留现有唯一账本／事务；无需造三条用户没写过的事件。理解区别后，才能解释为什么“同一篇日记重新分析”不应再领奖。

### 16.2 “不交给 AI”为什么需要处理派生数据

页面隐藏按钮只影响交互。如果 worker、周期报告或记忆服务后来仍取到原文，或者取到包含该原文的摘要，实际并未实现用户选择。正确规格应记录许可及来源版本，在任务发送前和返回后检查；派生摘要要知道来自哪里，以便许可改变后隔离或重建。旧分析作为本人历史保留，并不等于可以继续向模型发送。

两个常见测试：私密 A 与允许 B 同一天，捕获 B 及所有后续用途的实际出站 payload；任务排队后关闭许可，检查发送／晚回是否仍能生效。字段存在不是这两种行为已经正确的证据。

### 16.3 接下来怎样验收 Writer

[主规格第 15 节](../FULL_SYSTEM_DEV_SPEC_2026-10-18.md#15-验收矩阵)提供 V01～V22。先看每项实现证据，再区分假模型可验证的权限／事务与真实模型才能验证的语义质量。独立 PG、真实邮件、手机实机缺环境写 NOT_RUN；不能因有前端截图就写“全部完成、可以上线”。

本次没有修正式程序，所以不新增一个声称已修复的故障档案。Writer 真正修复 R01～R07 后，按第 11 章五栏约定补故障案例和索引，并更新本章中的设计到实际代码位置。


## 第 17 章 完整规格落到真实系统（2026-10-18 实施）

第16章记录当时设计交接；这一章记录实际代码。新链路是：本人原文／版本和逐篇许可 → 队列快照 → 事实片段／独立问答或补充 → 模型建议存档 → 程序预览金额与额度 → 用户确认 → 事实结算／属性流水／金币／回执同事务。页面“已保存”“分析排队”“建议就绪”“已入账”是四种状态，不能合成一个成功提示。

| 顺着请求读代码 | 应当学会解释的问题 |
| --- | --- |
| `RecordComposer.vue` → events → `trial_rules.qualify` | 为什么只保存也有首记资格，却没有行动奖励？ |
| `analysis_jobs.py` → `ai_context.py` → `fact_analysis.py` → fact_bundles | 内容、许可、配置和租约各自防止哪一种晚回？ |
| `DiaryView.vue` → diary／review_context／diary_review | 为什么回答另存，下一轮要重新采集来源，而不是覆盖原文？ |
| `PlanAgenda.vue` → PlanSchedule／PlanOccurrence | 为什么日期与日程共同标识一次结果，“部分”不能直接设成50%？ |
| `reward_quotes.py` → shop_service → accept／redeem | 为什么模型建议不立刻创建商品，购买价与实际使用必须分开？ |
| `timers.py` → TimeSession／VoucherAllowance／coin_service | 为什么离线不能证明超时，修正只能退真实旧扣款？ |
| `questionnaire.py` → profile／attributes／startup资金 | 为什么建档校验、flush、refresh和外层commit顺序会影响结果？ |
| export／readable_export → importer | 为什么完整存档和一键恢复不是同一个承诺？ |

新增迁移 b010～b024，旧迁移不改。隔离验收后端119通过、2真实PG跳过；真实Vue构建、浏览器下载／多端尺寸截图记录在交付文件。本人模型、真实SMTP、独立PG及手机实机尚未验，不能凭代码或合成截图宣称可公网发布。本地一键启动新增等待API就绪后启动worker的启动器；本轮没有启动真实旧库验证该启动器。


## 第 18 章 日常使用反馈怎样变成下一轮开发协议（2026-10-21）

用户已经在使用云端旧版本。本轮从真实电脑反馈开始，先登记 F01～F22，再制作涵盖全部主要模块的本机完整 Demo；用户表示“看了大概，感觉还可以”，才进入正式规格和 Writer 交接。当前本地核对 HEAD 为 `7eb96f6`；本轮新功能尚未正式实现或上线，不将前轮服务器状态当作本轮新验收。

### 18.1 交互认可与真实实现分别证明什么

Demo 的 143 项浏览器检查和 19 张截图证明预览的操作链路、桌面/窄屏布局和实际本地导出能工作。脚本里的关键词评分、固定延迟、模拟登录、个人比例和问答不能证明真实模型质量、账号认证、数据库并发或邮件送达。正式实现必须对照[新规格 A01～A33](../DAILY_USE_REDESIGN_DEV_SPEC_2026-10-21.md#16-正式验收矩阵)重新提供 API/worker/数据库/编译 Vue 的证据；没有条件的外部项写 NOT_RUN。

### 18.2 三个容易误写的业务边界

- **一题一屏与逐题分析不同**：前者是展示，后者是模型调用时机。本次要求先完成较充分基础题，再整体分析，按本人缺口有限补题，预览确认一次。自动保存答案不等于自动送给供应商，跳过也不等于授权。
- **AI 自动改价与自动花钱不同**：自动化接管的是有效报价应用，购买仍由本人确认。旧报价晚回要检查配置/来源/商品/日期；展示23币时不能暗扣27。已购券的价格和剩余时间与今天商店新价是不同资源。
- **原文保存、首记资格与行动结算不同**：原文无论是否分析都可保存；每日首记3币独立；低于0.8的事实暂不写行动币和属性。一篇日记可同时有旧事实、待补充事实和达标新事实，不能按整篇平均分一次授奖。

### 18.3 页面合并为什么先写数据保留协议

计划与照顾自己可共用编辑，但完成/部分/未完成和轻记录/跳过不是完全相同的语义。安全整合先用稳定身份、类型、当次日期和旧快照连接历史，再调整呈现，不把全部旧表复制进一张“新计划表”。同理，成就集中成长不是删除旧成就，阶段目标归计划不是按同名吞掉另一条目标，去掉熟练标签也不是重算属性。

### 18.4 怎样让后来的实现者接得上

[Writer 任务书](../WRITER_DAILY_USE_REDESIGN_2026-10-21.md)说明 W0～W6、现有未提交改动、哪些旧方案被替代、哪些暂缓，以及交付报告应列哪些证据。PRD/DECISIONS/README 的最新入口同步更新，避免另一位 agent 只读旧文档又做回人工接受价格。模型测试诊断按第11章 B-61 留五栏记录，明确“已定位”和“正式待修”的差别；真正修复后再补实现和验收。

本章是规格阶段学习记录。未执行新业务迁移、真实模型或发信，未提交/推送/部署，也未通过聊天工具向 Writer 派发任务。


## 第19章 正式日常改版的请求和数据边界（2026-10-21）

第18章是设计阶段，这一章是实际实现。沿`App/router`进入Home/Plans/Rewards/My，再沿`ProjectManager→projects门面→原计划/照顾表`理解界面合并与身份保留；沿`QuestionnaireView→questionnaire→真实题目快照/一次资金`理解背景和评估不同；沿`RewardShop→pricing_checks→worker→reward_quotes.apply_quote→shop.redeem`理解自动改价和主动花钱不同。

`personal_context.background(purpose)`只送相应用途本人信息，`ai_context.background`签名包括其版本和真实唯一主线，防止旧响应在许可/目标变化后生效。`model_dispatch`记录是否发送，不充当成功结果；成功仍在业务表和RequestReceipt同事务。原文保存、模型建议、资金确认三种状态分别由页面明确显示。

本轮证据用编译Vue、真实FastAPI/worker和临时SQLite，供应商响应与测试时钟合成；四格式是真的API响应下载，不是预制Demo文件。浏览器1440/390、200%核心文本、焦点及键盘缩小视口通过只能证明桌面模拟环境；真实PG、模型语义、SMTP、生产TLS和手机仍NOT_RUN。完整映射及可重跑命令见[交付报告](../DAILY_USE_REDESIGN_DELIVERY_2026-10-21.md)。


## 第20章 独立审查为什么能在109项浏览器通过后找到四处问题（2026-10-21）

原测试覆盖了新建项目，却未覆盖“读取已有rule再写回”；覆盖单个价格，却没超过3项；首页按默认开关验过，没有关闭/零项/原排序夹具。这次[补修](../DAILY_USE_REDESIGN_FIXES_DELIVERY_2026-10-21.md)把边界补成状态转换，不以增加相似按钮断言来凑数。

顺着读：ProjectManager.allowedBody → projects门面 → plans/care独立生效历史；RewardShop → pricingSweep未知槽 → pricing_checks有限队列/次日公平；CareConfig → show_today → 首页隐藏与归档查看。读模型、写模型、排期锚点、修改生效日、结果身份、显示设置和AI授权分别承担不同职责。

新的页面验收真实点击并捕获请求，数据库和模型仍合成；双标签证明正常入口去重/预算行为，不等于独立PG两连接。schema无需新revision也不代表可以单独回退旧代码解释新的effective_from历史。外部PG升级、模型语义、SMTP/手机及生产发布保持未验状态，不用本地自验覆盖独立审查结论。


## 第21章 手机反馈怎样转成可验证的页面与状态修复（2026-10-24）

先区分三类问题：待办漏退出是完成状态错误；长页面和数字排序是信息组织问题；首次模型失败是证据不足的线上异常。不能把它们一起归结为“模型没接好”，也不能只收起表单却不修状态接口。

阅读路径：`HomeView → analysis.pending → FactBundle`理解完成状态；`FactAnalysis → fact_bundles.bundles → FactSettlement/AIJudgment.final_changes`理解建议与实际属性；`ProjectManager → projects.reorder → begin/finish`理解跨来源显示顺序的原子性；`RewardShop → shop.DELETE → RequestReceipt`理解隐藏当前商品和保留历史权益。note保存在原规则JSON里，不为这次UI增加表或迁移。

页面保留记录输入、计时和待确认分析等当前任务；把历史、长依据、已保存问答及配置表单改为用户主动展开。首页钱包/待处理/日记合并快捷入口，今日片段收起且可去手账回看。问卷仍一道一道作答，不为了减少高度而隐藏必要确认。

完整检查和限制见[本轮补修记录](../USABILITY_REPAIRS_2026-10-24.md)。本轮是本地修复，未提交、推送或重新部署；原线上提交仍为21b7dbae。真实供应商首次失败原因及手机实机最终验收均待补证据。


## 22. 2026-10-25：从页面 Demo 到可发布版本

本轮用户确认新版层级、分析修复和事件35补发一起发布。先在独立工作树整合正式接口，移除体验账号文案和演示外壳，原 Demo 保留。普通事件只显示原文和属性/金币两块，依据、权限、补充和历史按需打开；一级页只提供摘要和二级入口。

B-77：属性和金币都为0不一定是模型没连上。事件35已有成功响应，实际根因是行动币误依赖可选娱乐配置，加上未登记属性被静默丢弃。修复需同时覆盖提示词、类型/名称校验、预览和确认，不能只给界面补一个数字。事件36复测则定位到effort格式错误；只对不影响核心资格的可选标记做保守降级，可信度、属性和来源仍严格校验。

B-78：预览是确认时的历史，实际结果是账。补发保留旧0币预览，同时追加流水、修正原ActionAward与原判定实际属性；详情通过真实FactSettlement关联显示实际入账。重复点击不应通过删除重建结算解决，而应使用同一事故回执防止重复发放。

联合本地验证：193项后端中191通过、2个真实PG专项未运行；正式构建配实际API的99项浏览器检查通过。390宽度模拟不等于实机。云端更新还需精确提交制品、独立PG恢复演练、最终备份、逐步切换与真实模型验收；截至本节准备时尚未切换或补发。部署步骤见CLOUD_UPDATE_2026-10-25.md。

<a id="b81"></a>

### B-81 · 加了列却没写迁移，云端上线即 500

**现象**：本地一切正常；按现有链路发一版，云端 `/api/shop/items` 直接 500，商店整页打不开。v1.13 的 `ShopItem.pricing_mode` 在本地由 `migrate_schema` 补上，云端没有这一列。

**定位过程**：先看 `app/main.py:100-116`——云模式只校验 `alembic_version == heads` 就 `return`，**`migrate_schema()` 只在不走云的分支里执行**；再看 `alembic/versions/` 止于 `b025_daily_use`，`grep pricing_mode alembic/versions/` 为空；`alembic heads` 仍输出 `b025_daily_use`，说明迁移链压根不知道这列存在。

**根因**：把「模型加字段」当成「schema 已升级」。SQLite 本地启动会把缺失列补上，正好掩盖了缺口；云端没有这层兜底，只能在第一次 `SELECT` 时报 `UndefinedColumn`。

**修复实现**：`b026_pricing_mode`（`server_default='once'` 保证老行非空，同一次 upgrade 里 `UPDATE ... WHERE auto_pricing IS TRUE` 回填）+ `b027_suppressed_lines`（`experience_preferences` 漏列，属遗留老债，顺手补齐）。**回填语句统一写 `IS TRUE`**，PG 不接受 `boolean = integer`。

**防复发**：**加列必查 `alembic/versions/`**，`alembic heads` 必须是单一 head；本地验证要拿真实库副本跑 `DB_FILE=_tmp_x.db`，不能只看「本机能启动」。

<a id="b82"></a>

### B-82 · CSS 少一个花括号，改了跟没改一样

**现象**：计时页按 demo 加了居中卡、圆环、44px 大字，截图出来和改前完全一样，但 `vite build` 成功、控制台无报错。

**定位过程**：`python -c "s=open('daily-use.css').read(); print(s.count('{'), s.count('}'), s.count('.timer-ring{'))"` → `{` 134 个、`}` 133 个、`.timer-ring{` 出现 **2** 次。顺着行号看，第 52 行 `.timer-ring{...border-radius:50` 没有闭合，紧接着整段又被重复了一遍。

**根因**：浏览器遇到未闭合的声明块，会把后面所有内容都当成该块的一部分吞掉，于是 `.timer-card` / `.timer-head` / `.timer-ring-inner` 等规则**全部不生效**；构建工具不校验 CSS 语法，所以安静通过。

**修复实现**：删掉重复且未闭合的那半段（`8002e5b`），保留完整一份；花括号配平与选择器去重写成断言。

**防复发**：**改 CSS 必须起本地服务截图核对**，验收标准是「看到图」，不是「构建成功」；顺手把配平/去重断言贴进验收命令。

<a id="b83"></a>

### B-83 · 两个开关各写一半，谁也不听谁的

**现象**：调旧接口关掉自动定价，第二天奖励还是被重估；反过来开启后，商品永远不进价格队列。

**定位过程**：读 `app/routers/shop.py` 找到 `pricing_permission()` 只写 `item.auto_pricing`；读 `app/services/pricing_checks.py` 发现入队条件只看 `item.pricing_mode`。前端早已改成调 `PATCH /pricing-mode`，旧的 `permission()` 成了没人调的死代码。

**根因**：v1.13 引入 `pricing_mode` 时选择「双写保平安」，但**读取只走新列**，写入却还有一条只写旧列的老路径。同一语义有了两个真源，任何一边没同步就是静默失效。

**修复实现**：删掉 `POST /shop/items/{id}/automatic-pricing` 整个路由与 `AutomaticPricingIn`、删前端 `permission()`；新建奖励一律 `auto_pricing=False`；停用/移除也把 `pricing_mode` 写回 `once`（否则恢复后当晚又进重估队列）。`auto_pricing` 列保留但明确标注**只写不读**。

**防复发**：**同一语义只能有一个真源**；为兼容保留的旧字段必须显式标注「只写不读」，并在删除入口时连前端调用一起清掉，不留点了没反应的按钮。

### B-84 · 「今日已得」在设置页 28、在分析页 25

**现象**：同一天、同一句「今日已得 N 币」，设置页（手账规则）显示 28，写完日记的分析页显示 25。差额正好是当日首记的 3 币。

**定位过程**：先看设置页的数据来源——`app/routers/trial.py:26` 已经改用 `coin_service.day_total()`（全口径：手账 + 首记 + 挑战 + 成就）。再看分析页：`FactAnalysis.vue:57` 与 `EventFactAnalysis.vue:78` 读的都是 `group.preview.used`，而 `preview.used` 来自 `app/services/fact_analysis.py:200` 的 `trial_rules.cap_used()`——那个函数只 `sum(ActionAward)`。`:138` 喂给模型的 `today_coins` 是同一个旧口径。

**根因**：v1.13.1 的 P2-4 只改了**报障的那一个接口**。这个数字有三个出口（`/api/trial`、`preview.used`、prompt 里的 `today_coins`），改了其中一个，另外两个继续输出旧值，于是「同一个词两个数」——正是这一版要消灭的那类不一致，自己又造了一次。

**修复实现**：`preview.used` 与 `today_coins` 都换成 `coin_service.day_total(db,user,day)`；`trial_rules.cap_used()` 全仓已无引用，直接删掉（保留只会留下第三个口径的隐患）。回归用例 `tests/test_v1131_today.py::test_analysis_preview_uses_the_same_total_as_settings_page` 把「两处都是 28」钉住——在此之前全仓没有一条用例断言过 `preview.used`。

**副作用（预期）**：`confirm()` 有「`bundle.preview != preview(...)` 就 409」的一致性校验，所以**改口径前生成、还没确认的草稿**会在下次预览时要求重新生成一次。与 F4 升 `rule_version` 时同样的效果。

**防复发**：改「某个数字的口径」时，先按**字段名**在整个仓库 grep 一遍所有出口（接口、preview、prompt 注入都算），不要只改当前页面报上来的那一条。同一个词出现在两处，就必须来自同一个函数。
