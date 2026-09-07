# 开发计划 DEV_PLAN v1.4（backlog 精修 + AI 接入架构）

> 交付对象：实现者（writer）。开工前先读 `docs/PRD.md`（v1.2）、`docs/DECISIONS.md`（决策与 backlog 全文）、`docs/WRITER_PROMPT.md`（总工作指令）。本文档是本轮（v1.4）的唯一范围依据，与 PRD 冲突处以本文档为准。

## 本轮范围总览（用户 2026-09-07 确认）

| 批次 | 内容 | 层 |
|------|------|-----|
| A | 追问收紧（温和逐面）+ 主动/引导来源区分 + 置信度原因 | prompt + 少量后端/前端 |
| B | 判定中心补充/反驳交互修复 | 纯前端 |
| C | AI 接入架构：BYOK 设置页 + 判定/辅助双模型 + 免费兜底 | 后端为主 + 设置页 |

属性"显示/判定"开关**不在本轮**——已核实 v1.3 批次 C 完成（DECISIONS 已补记勾选），勿重复实现。

---

## 批次 A：判定体验（prompt 层）

### A1 追问收紧：温和逐面

**问题**：当前免问条件是"日记已充分展开（作息/事件/情绪/感受均有呈现）"（`app/prompts/judge.py` 追问引导节）。用户实测反馈：日记只写重要的事，字数多 ≠ 面面俱到——当天做了约 10min 拉伸忘写，AI 因"看起来充分"免问，事件流失。判定#12 也只覆盖 3 维（跑步/作息/饮食面有，学习面未提未问）。

**方案**（改 `app/prompts/judge.py`「追问引导」节触发规则）：
- 日记模式（journal）首轮默认 `needs_clarify=true` 保留，但免问判断从"整篇是否充分"改为"**逐生活面核对**"：核心生活面（作息/饮食/运动/学习工作/社交/情绪感受）逐一检查——凡**未提及或描述含糊**的面，就值得针对性提问引导回忆（如"今天有动一动吗？哪怕拉伸几分钟也算"）。
- **温和约束（防骚扰）**：每轮 1~3 问，优先挑"当天情境下最可能有事发生、且对加点最有价值"的 1~3 个面问（如日记写了学习没写运动 → 优先问运动）；**问过即止，不穷举**——同一面已问过、用户已答"没有/没做"，不再重复。
- 用户明确表示"没什么了/不想多谈"→ 立即停止追问，基于现有信息判定。
- 保留现有条款：只看本篇日记原文判断、不因系统背景信息跳过追问、打卡（form）不追问。
- 输出格式注释同步更新：needs_clarify 的判定规则描述改为"逐面核对后仍有未提及/含糊的核心面 → true"。

**验收**：
- 简略日记 → 追问且问题针对未提及的面（如只写了学习 → 问运动/作息）
- 长但缺面的日记（字数多、只有 3 个生活面）→ **仍追问**缺失面（这是本项核心，必须实测这条）
- 各面都写全的日记 → 可直接判定，要素解析中说明"逐面核对均已覆盖"
- 用户答"没了" → 下一轮不再追问，直接出判定

### A2 主动记录 vs 引导想起的来源区分（标注 + AI 自斟酌）

**问题**：用户主动写进日记的事说明下意识更关注；AI 追问"想起来"的事性质不同，当前判定不区分。

**方案**：
- `app/prompts/judge.py` 加权推导节加规则：用户消息中【原文日记】部分的内容为**主动提及**（反映用户自发关注），【用户对追问的补充回答】/【用户补充信息】部分为**引导想起**（完整性兜底）。AI 可据此对主动提及内容的权重适度倾斜（幅度自定），**但必须在加权推导中说明倾斜理由**；引导想起的内容正常判定、不额外加权。
- 保持客观底线：倾斜是"适度微调"，禁止仅为迎合用户而夸大主动内容加分。
- 无需改数据模型与前端——区分体现在 analysis 加权推导的文字中。

**验收**：构造一条日记 + 追问补充（补充里含"其实还拉伸了 10 分钟"）→ 重判后加权推导中能看到"主动提及/引导想起"的区分表述与理由，拉伸项加分未被夸大。

### A3 置信度原因（confidence_reason，每次都给）

**问题**：判定#13 初始置信度 78%（<80% 拦截），界面只说"请补充信息"，AI 没说为什么低、缺什么、哪项不确定——用户无从补充也无法针对性反驳。历史判定置信度 78%~92% 全部 <95%，故按用户确认：**每次判定都给置信度说明**。

**方案**：
1. `app/prompts/judge.py` 输出格式新增字段 `"confidence_reason"`：confidence < 0.95 时**必填**——说明哪里不确定（缺什么信息 / 哪项增减把握不足 / 建议补充什么细节，1~2 句，可直接指导用户下一步补充或反驳）；≥0.95 可为空字符串。输出格式注释里写明语义。
2. **数据模型**：`ai_judgments` 表新增 `confidence_reason TEXT` 列——`app/models/__init__.py`（AIJudgment）+ `sql/schema.sql` 同步。
3. **新增轻量迁移机制（重要，一次性基建）**：现在库里有真实使用数据，**禁止再要求删库重建**。在 `app/database.py`（或新建 `app/migrations.py`）加启动时列迁移：用 `PRAGMA table_info(ai_judgments)` 检查缺列则 `ALTER TABLE ai_judgments ADD COLUMN confidence_reason TEXT`。写成通用小函数（表名/列名/类型参数化），后续加列都走它。
4. `judge_service` 三个落库点（判定/补充重判）存取该字段；`judgments.py` 路由返回它。
5. 前端：`JudgmentList.vue` 判定卡置信度旁展示原因（小字）；**低置信度拦截提示（<80%）文案改为引用 confidence_reason**（如"⚠️ 置信度 78%：{confidence_reason}，可补充信息后重判或直接反驳"）；`EventForm.vue` 结果卡同步展示。
6. dispute prompt（`app/prompts/dispute.py`）注入原判定 confidence_reason，让复核 AI 知道原判的不确定点。

**验收**：新判定返回 confidence_reason 且 <95% 时非空；旧库启动自动加列、历史数据不丢；判定卡与低置信度提示都能看到原因；补充重判后该字段更新。

---

## 批次 B：判定中心交互修复（纯前端，`frontend/src/components/JudgmentList.vue`）

**问题**（已定位，2026-09-06）：①「补充信息/反驳」打开的输入框渲染在卡片最底部（模板末尾），长卡片时在视口外，点击像没反应；②提交失败时错误提示在卡片顶部（视线外），且 `runAction` 的 finally 无条件收起输入框并清空文本——双重"没反应"。

**方案**：
1. 输入框（含「提交补充/提交反驳」按钮）**移到操作按钮行正下方**（第 210~227 行操作区之后、编辑表单之前），就近渲染。
2. `runAction` 失败时：**不收起输入框、不清空已输入内容**（finally 里仅在成功路径重置 `actionTarget`/`inputText`——把重置逻辑挪到 try 成功分支）。
3. 失败错误提示**就近显示在输入框上方**（新增局部错误 ref，如 `actionError`，而非只有卡片顶部的全局 error）。
4. 成功后收起输入框并清空，行为不变。

**验收**：点「补充信息」输入框立刻出现在按钮下方；断网/停后端后提交 → 输入框不消失、内容保留、错误提示就在框上方；恢复后重提成功 → 收起清空。

---

## 批次 C：AI 接入架构（BYOK + 双模型 + 免费兜底）

**现状**（2026-09-07 核实）：`llm_service` 为全局单例，api_key/base_url/model 从 `.env` 经 `config.settings` 启动时一次性读取，无按次覆盖能力；全部 9 处调用（judge×3、onboarding×3、memory、events extract、report）统一走 `llm_service.chat_json(messages)`。`Setting` 表为 user 级 KV（key/value JSON）——存自定义配置的现成容器。

### C1 配置解析层：按用户、按用途解析 LLM 配置

新建 `app/services/llm_config.py`：

```python
@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    quality_note: str = ""   # 非空时前端标注（如"判定质量一般"）
```

解析函数 `resolve_llm_config(db, user_id, purpose) -> LLMConfig`，优先级：
1. `Setting` 表 key=`llm_primary`（判定模型组）/`llm_aux`（辅助模型组），value=`{api_key, base_url, model, enabled}`——`purpose="judge"`（judge/supplement/dispute/extract/onboarding/memory）读 primary，`purpose="aux"`（report 周报）读 aux；
2. 该组缺失/未启用 → judge 回退 aux（结果标注 `quality_note="判定质量一般（使用辅助模型）"`）；aux 缺失 → judge 回退 primary；
3. 两组都无 → 回退 `.env` 默认配置（向后兼容，现有部署零改动继续可用）；
4. `.env` 也没有（`llm_ready=False`）→ 抛现有 `LLMError`（503 提示配 Key）。

`llm_service.chat/chat_json` 加可选参数 `config: LLMConfig | None = None`：传入时覆盖 settings 默认值（client 按 (api_key, base_url) 缓存复用，不要每次新建）；不传行为完全不变。

### C2 设置页 API（`app/routers/settings.py` 扩展）

- `GET /api/llm-config`：返回两组配置，**api_key 掩码回显**（`sk-****末4位`，无 key 返回空）。
- `PUT /api/llm-config`：body=`{group: "primary"|"aux", api_key?, base_url?, model?, enabled?}`；api_key 传 `"__KEEP__"` 表示不改（配合掩码回显），传空串清除。写入 `Setting` 表 key=`llm_primary`/`llm_aux`。
- 保存 primary 且 model/base_url/key 相比旧值有变化时，响应带 `model_changed: true` + 提示语，前端弹确认："更换判定模型后，后续加点口径可能与之前不同（历史数据全部保留；长期记忆会自动注入新模型衔接上下文）。确认更换？"
- **安全红线**：key 只入 SQLite（Setting 表），严禁写入任何 git 提交文件；GET 回显必须掩码；**数据导出（`app/routers/export.py`）不得包含 llm_config**（当前导出不含 settings 表，验收时确认保持）。

### C3 设置页 UI（`frontend/src/components/SettingsView.vue` 新增「AI 模型」区块）

- 两组配置各一行卡：启用开关 + base_url（占位符给模板：判定组默认 `https://api.deepseek.com`，模型 `deepseek-chat`；辅助组占位提示可填 SiliconFlow 等任何 OpenAI 兼容端点与免费模型）+ 模型名 + API Key（password 输入框，掩码回显）+ 保存。
- **免费兜底的用法写进界面提示**：无判定模型 Key 时，判定自动降级用辅助组模型并标注"判定质量一般"——用户可把免费模型（如 SiliconFlow 免费档）配在辅助组作为兜底。
- 首次使用引导：检测到两组都未配置且 `.env` 无 Key 时，记录页/判定处 503 文案指引去设置页绑定；已用 `.env` 默认配置时，设置页显示"当前使用服务端默认模型（.env），可在此绑定你自己的 Key"。

### C4 调用方接线

- `judge_service.py` 三处 `llm_service.chat_json(messages)` → 传 `config=resolve_llm_config(db, user.id, "judge")`（db/user 均已在手）。
- `report.py` 周报 → `purpose="aux"`。
- `onboarding_service`、`memory_service`、`events.py` extract → `purpose="judge"`。
- 判定结果经降级路径（用了辅助模型）时，在 judgment 的 summary 或 analysis 末尾附 `quality_note`，前端判定卡显示小标签"判定质量一般"。

**验收**：
- 设置页填入自己的 Key/模型 → 判定走新配置（改 key 为错误值 → 判定 503，证明生效）；掩码回显正确
- 只配辅助组（免费模型）→ 判定能出结果且带"判定质量一般"标注；两组全空 → 回退 .env 正常判定
- 判定与周报可分别用不同模型；更换判定模型时出现口径变化确认弹窗
- `git grep` 确认无 key 明文入提交；导出文件不含 key

---

## 统一约束

- **禁区**：桌宠、金币商店、语音输入、首页问候卡片、多人联动、M4 上云/MySQL——一律不碰。
- **Git**：只 commit 不 push；一个逻辑单元一个 commit，中文 message（`feat:`/`fix:`/`refactor:`/`docs:`）；严禁提交 `.env`、`*.db`、`node_modules/`、`.workbuddy/`。
- **自验**：每批次完成需——后端 `python -m py_compile` 全部改动文件 + 隔离环境启动冒烟（批次 C 必须实测配置切换/降级/回退三条路径）；前端 `npm run build` 零错误；批次 A 的 prompt 改动必须用真实 DeepSeek 调用验证（报告追问触发与 confidence_reason 的实测样例）。
- **迁移红线**：库里有真实数据，任何表结构变更必须走启动时自动迁移（批次 A3 的通用迁移函数），禁止要求删库。
- 完成后回写 `docs/DECISIONS.md` 对应 backlog 条目为 `[x]` 并附实现说明；不确定处保守实现 + TODO 注释 + 登记 DECISIONS.md。

**交付顺序**：A → B → C（A/B 小改先行让用户当天可测；C 改动面大独立收尾）。
