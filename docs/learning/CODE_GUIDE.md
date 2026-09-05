# 项目代码详解 —— my-life-rpg 全代码教学

> **目标**：读完能 ①完全理解本项目全部代码 ②读懂他人写的类似代码 ③修改与复用。
> **读者假设**：会 Python 语法/HTTP 基础/SQL 增删改查/HTML-JS 基础；框架级概念（ORM、依赖注入、Vue 响应式等）用**概念卡**补齐。
> **代码基线**：v1.3（2026-09-05，commit `8603079`）。所有引用的文件/函数/行为均与仓库当前代码一一对应。
> **更新约定**：用户说"更新学习文档"时，按本次要求更新（新功能→补对应小节；重构→改对应讲解）。

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
└── services/          8 个服务（judge/llm/anchor/memory/onboarding/user/goal/backup）
frontend/src/
├── main.js            入口：创建 Vue 应用挂到 #app
├── api.js             全部后端接口的统一封装（唯一 fetch 出口）
├── App.vue            布局壳：健康检查横幅 + 9 个 tab 切换
└── components/        9 个页面组件（与 tab 一一对应）
```

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
| events | 生活事件 | `source` form/journal 双通道；`params` JSON 结构化参数；`content` 日记原文；`is_pure` 纯享记录（不判定） |
| ai_judgments | 判定记录 | `suggested_changes`/`final_changes` 双字段——建议值 vs 置信度加权后实际入账值；`status` pending/confirmed/adjusted/rejected 状态机 |
| judgment_logs | 判定审计 | action: create/confirm/supplement/dispute/rejudge/maintain/delete，全程可回溯 |
| goals | 目标 | `audit` JSON 记修改/取消/达成/失败流水 |
| anchors | 量化锚点库 | `calibrated_value` 用户校准值（NULL=用默认 base_value）——"科学但用户可调" |
| settings | KV 配置 | `hidden_attributes`/`disabled_attributes`（维度开关）、`gamification_modules`（模块开关）、`unreal_count`（不实计数）全塞这张表，避免加列 |

> **两个可迁移的设计习惯**：①所有业务表带 `user_id` 外键（单用户也无妨，多用户零返工）；②"当前值表 + 流水表"分离（账户余额思维）。

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

## 第 4 章 LLM 服务层（llm_service.py，147 行，全项目唯一碰 openai SDK 的地方）

```python
class LLMService:
    def _get_client(self):        # 惰性创建：没 key 直接抛 LLMError（友好提示）
    def chat(self, messages, temperature, json_mode):   # 单次对话→文本
        kwargs["response_format"] = {"type": "json_object"}  # json_mode 时强制 JSON 输出
    def chat_json(self, messages):  # chat + _parse_json
```

**`_parse_json` 三级容错**（面试级设计点）：
1. 去 markdown 围栏 `​```json ... ```​` 后直接 `json.loads`
2. 失败 → 正则提取首个 `{...}` 平衡块再解析（模型爱加说明文字）
3. 仍失败 → `_repair_curly_quotes`：模型偶尔用中文全角引号 `“”` 当 JSON 定界符。**位置感知修复**：看全角引号的前一个非空白字符——是 `{ [ , :` 就说明这个开引号在结构位，还原成半角 `"`；闭引号同理看后一个字符；字符串内部的引用则替换成 `「」` 不破坏内容；最后把结构位的全角逗号 `，` 转半角。
4. 全失败才抛 `LLMError`（路由层转 503）。

> **可迁移**：任何"LLM 返回结构化数据"的场景都值得抄这套容错链。业务层永远 `from app.services.llm_service import llm_service` 单例调用，不直接碰 SDK——换供应商只改这一处。

---

## 第 5 章 Prompt 层（app/prompts/，一功能一文件）

| 文件 | 用途 | 核心结构 |
|------|------|----------|
| judge.py | 事件判定（产品灵魂） | 13 节 system prompt（见下） |
| dispute.py | 反驳复核 | "客观复核员"：有据才调整，无据维持原判，绝不迎合；输出 conclusion=maintain/adjust |
| extract.py | 日记要素提取 | 从自然语言提 event_type/category/title/params，"只提取明确提到的，不臆造" |
| memory.py | 长期记忆压缩 | 五类摘要（目标/经历/性格/偏好/状态），增量合并不丢旧记忆 |
| report.py | 周报/月报 | 亮点/关注/建议/tone；关闭维度"温和关心不批评" |
| onboarding.py | 问卷出题+面板生成+补充评估 | AI 自评把握度 confidence，≥95 自动生成面板 |

**judge.py 的 13 节为什么这么排**（每节都在堵一个真实发生过的坑）：
1. 角色定位（引导者+科学客观底线）→ 2. 只判 13 维（防发散）→ 3. 任务三步 → 4. 上下文记忆使用规则（背景只参考不越权）→ 5. 事件去重（同天同件事才去重；不确定倾向正常判——防误伤）→ 6. 语义理解（"吃瘦肉很知足"归感恩不是营养）→ 7. 负面情绪减分规则（紧张→心理韧性）→ 8. **多属性联动+生活面覆盖自检**（判定前列作息/饮食/运动/学习/社交/情绪清单，漏面必须复核）→ 9. 锚点库注入 `{anchors}` → 10. 判定规则（delta∈[-5,5]、goal 规则、如实记录加诚信）→ 11. 累积效应（坚持上浮/频繁加重）→ 12. 真实性甄别（realistic 字段）→ 13. 客观性硬约束 + **追问触发规则**（journal 默认追问、form 不追问、信息不足禁止降 confidence 直接判定）+ 边际递减 + analysis 三步推理链 + 输出 JSON schema（含"严禁全角引号"的格式警告）。

> **写 prompt 的方法论**：每一节都对应一个"曾经出过的 bug"（负面不扣分→第7节；维度漏判→第8节；从不追问→第13节重写）。prompt 是活的规格说明书，出问题就加一节/改一节，并保持节间不矛盾。

`build_judge_messages` 把上下文**条件注入** user 消息：`【记录模式】`、`【当天已记录的事件】`（去重依据）、`【用户长期记忆】`、`【近期生活记录】`（7天10条）、`【近期同类事件频率】`、`【当前属性值】`（边际递减）、`【用户对追问的补充回答】`——有什么注什么，没有就不出现。

---

## 第 6 章 核心业务链路精讲（judge_service.py，544 行）

### 链路 A：提交日记 → 提取 → 判定（含追问）
```
前端 EventForm.submitJournal()
  → POST /api/events        (routers/events.create_event)
      source=journal → llm_service.chat_json(prompts.build_extract_messages(content))
      → 提取 event_type/category/title/params 落 events 表
  → POST /api/events/{id}/judge  (events.judge)
      → judge_service.judge_event(db, event, clarification="")
          1. 幂等处理：已有 confirmed → ValueError 拒绝；已有 pending/adjusted → 连审计一起删旧建新
          2. 组装上下文（锚点文本/记忆/频率/属性值/当天事件/维度开关）
          3. llm_service.chat_json → result
          4. result["realistic"]==False → _handle_unrealistic：计数、第3次起扣诚信、删事件、抛 ValueError
          5. result["needs_clarify"]==True → raise ClarifyNeededError(questions)
          6. _parse_changes：别名表规范化属性名（constants.ATTRIBUTE_ALIASES 防 AI 返回 "physical"）
             + delta 钳制 [-5,5] + 过滤 disabled 维度（双保险，prompt 已要求但代码再兜底）
          7. 建 AIJudgment(status=pending) + 审计 create + commit
      路由层异常翻译：ClarifyNeededError → 200 {"needs_clarify":true,"questions":[...]}
                      ValueError → 400；LLMError → 503
  → 前端：res.needs_clarify → 显示追问卡（clarifyEvent）→ 用户答 → judgeEvent(id, answer) 再进 3（可多轮）
```
**学习点**：①"异常即协议"——用自定义异常 `ClarifyNeededError` 在服务层控制流程，路由层翻译成 HTTP 响应；②**纵深防御**——prompt 说"不判关闭维度"+代码再过滤一遍，LLM 输出永远不可全信。

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
- supplement：原事件描述+`【用户补充信息】`重新走判定 → status=adjusted，审计 rejudge。
- dispute：换 dispute prompt（客观复核员）→ conclusion=adjust 时用 `_parse_changes` 覆盖建议（**空结果则保守维持原判**）；maintain 时审计 maintain。**返回值里带 conclusion/explanation 供前端弹窗提示**。

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
`maybe_update_memory`：距上次更新超 24h → 取近 30 天事件摘要 → memory prompt 增量合并旧记忆 → 存 `profile.long_term_memory`（JSON）。**失败静默返回 None**——记忆更新失败不影响判定主流程（优雅降级）。

### 链路 G：周报（routers/report.py）
纯 SQL 聚合（事件数/类别分布/属性变化/判定数/目标状态）→ 连同长期记忆与关闭维度塞给 report prompt → 返回结构化报告。**统计用代码、洞察用 LLM**——数字必须准确的部分不交给模型。

---

## 第 7 章 其余路由速览

- `attributes.py`：`GET /attributes` 返回面板+每项 `visibility`（show/hidden/disabled 三态，读 settings 表）；`GET /attributes/history` join 属性名给趋势图。
- `goals.py` + `goal_service.py`：CRUD + achieve（规划力+reward、关联属性+reward）/ fail（扣 penalty）/ cancel（只审计不结算），全部写 `goal.audit`。
- `anchors.py`：列表 + calibrate（calibrated_value，null 恢复默认）。
- `export.py`：`_collect` 聚合六类数据 → JSON 直返 / CSV（StringIO+csv.writer+BOM，`Response` 带 Content-Disposition 触发下载）；备份两个端点。
- `settings.py`：KV 读写 + 三类键的默认值兜底。
- `judgments.py`：判定列表（join 事件取标题）/详情/审计 logs/confirm/supplement/dispute。

---

## 第 8 章 前端精讲（frontend/src/）

### 8.1 api.js —— 唯一 fetch 出口
`request()` 统一处理：JSON 头、`resp.ok` 检查、`detail` 字符串/对象归一化为 Error message。所有接口按域分组导出（onboarding/events/judgments/...）。**收益**：换后端地址、加 token、统一 loading——都只改这一个文件。
`exportData` 是例外（要触发浏览器下载）：拿 blob → `URL.createObjectURL` → 动态 `<a download>` 点击。

### 8.2 App.vue —— 布局壳
`tabs` 数组驱动 9 个 tab 按钮；`activeTab` ref 控制 `v-if/v-else-if` 挂载对应组件（**非 router**，个人项目够用且零依赖）；onMounted 里 `checkHealth()` 探测 `/api/health` → 顶部绿/红横幅（解决"没连上后端"排查痛点的 UX 方案）；`!hasProfile` 时显示引导卡；EventForm 用 `@go-judgments` 事件让父组件切 tab（**子组件不直接操作父状态，通过 emit 通信**——卡4）。

### 8.3 EventForm.vue —— 双通道 + 三层状态持久化
- 双通道：`mode` form/journal 切换模板；表单提交组装 params；日记提交只传 content（后端提取）。
- **三层持久化**：①表单草稿 → localStorage（`watch([mode,form,...], save, {deep:true})` 自动存）；②判定结果/追问状态 → sessionStorage（`gol_last_judgment`，关标签即清，`restoreJudgeState()` 在 onMounted 恢复）——解决"切页结果丢失"；③清除分档：`reset()` 全清 vs `clearResult()` 只清结果留草稿。
- 追问两阶段：`clarifyEvent` 非空显示问题卡 → `submitClarify` 带 clarification 重判（后端可能继续追问，循环）。
- 结果卡展示 analysis 推理链 + `预计入账 delta×confidence`（透明展示加权）+ "去判定中心确认" emit。

### 8.4 JudgmentList.vue —— 判定中心
- `refreshAudit(id)` 独立函数 + `runAction` 成功后 `if (auditTarget===id) await refreshAudit(id)`——修复"操作后审计不刷新"；`removeEvent` 后主动收起审计面板。
- 低置信度：按钮 `:disabled="(j.confidence||0) < 0.8"` + 黄色提示条（与后端 400 拦截双保险）。
- `ACTION_LABEL`/`STATUS_LABEL` 字典把后端枚举翻译成人话——**枚举展示永远用映射表**，不要在模板里写三元判断链。

### 8.5 SettingsView.vue —— 状态机 + 紧凑 UI
三态真相：`hidden_attributes`/`disabled_attributes` 两个数组（settings 表）；`stateOf(name)` 派生三态；`setState` 同时更新两数组再连续 PUT（hidden 永远不含 disabled 的项，disabled 优先级高）。v1.3 UI：`changedAttrs` computed 只列非默认维度，其余收进 `<details>` 折叠，3 按钮→单 select。
另有：游戏化模块开关（MODULES 字典）、导出/备份/重置（双重 confirm）、周报。

### 8.6 AttributePanel.vue —— ECharts 三图
`Promise.all` 并发拉三份数据 → `nextTick()` 等 DOM 渲染后 init 三个 chart（radar 雷达/growth 折线/heatmap 日历热力图）；`visibleAttrs` computed 过滤 hidden；`onBeforeUnmount` dispose + 移除 resize 监听（**防内存泄漏的固定姿势**）；`radarChart && radarChart.resize()` 应对窗口变化。

---

## 第 9 章 可迁移的设计模式总结（本项目出产的通用件）

1. **幂等初始化链**：create_all + 轻量迁移 + 种子数据 + 默认记录 + 自动备份，重复启动安全
2. **LLM 服务层单例 + 三级 JSON 容错**：业务零直接依赖 SDK
3. **事实基准表（锚点库）**：LLM 判定类产品防口径漂移的标准解法
4. **建议→确认→生效**：AI 输出一律 pending，人确认才落账
5. **append-only 流水 + 反向回滚**：删除不改历史，账目永远可对
6. **异常即协议**：服务层自定义异常，路由层翻译 HTTP 语义
7. **prompt = 活的规格说明书**：每节堵一个真实 bug，改前查条款冲突与默认值倾向
8. **前端状态分档持久化**：localStorage（草稿）/ sessionStorage（会话结果）/ DB（业务数据）
9. **枚举展示映射表**、**emit 通信**、**chart dispose**、**双端一致的业务拦截**

## 第 10 章 常见修改任务手册（动手练）

| 任务 | 步骤 |
|------|------|
| 加一个属性维度 | constants.py 加名+别名 → user_service.ensure_dimensions 自动补建（重启生效）→ prompt 第2节 13 维列表同步改 |
| 加一条锚点 | anchor_service.BUILTIN_ANCHORS 追加一条（name/evidence 必填）→ 重启幂等写入 → 锚点库页可见、判定自动注入 |
| 调判定规则 | 只改 prompts/judge.py 对应节 → 注意与"客观性硬约束/追问规则"节是否冲突 → 用真实日记验证 |
| 加一张表 | models 加类 → schema.sql 同步 → 重启自动建表；已有表加列走 migrate_schema |
| 加一个接口 | schemas 加入参 → router 加函数 → main.py include_router（已有模块则免）→ api.js 加封装 → 组件调用 |
| 换 LLM 供应商 | 只改 .env（base_url/model/key），业务代码零改动 |

## 第 11 章 读懂他人代码的方法论（从本项目提炼）

1. **先跑起来再看**：start.bat 一键起 → 点一遍页面 → 每个功能对应到目录里的文件
2. **顺着一条请求读穿**：从 api.js 找到 fetch → 路由 → 服务 → 模型 → 数据库，一条链读完比十个文件乱翻有效
3. **先读 models**（数据结构是骨架）再读服务层（业务逻辑是血肉）
4. **看注释里的"为什么"**：本项目注释大量记录设计动机（如 migrate_schema 为什么要可空列）——这是最有价值的部分
5. **改之前先做只读实验**：查库、print、断点——证据先于猜测
6. **git log 当历史书读**：`git log --oneline` 83 个提交就是这个项目的演化史，每个 commit message 都是一个学习点
