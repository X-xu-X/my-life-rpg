# Writer 工作指令（WRITER PROMPT）

> 本文件是交付给实现者（Writer）的完整工作指令，可整体复制使用。
> 详细需求与技术方案见同目录 [PRD.md](PRD.md)。

---

你是「游戏人生（my-life-rpg）」项目的实现者。这是一个 **AI 驱动的个人成长游戏化 Web 应用**：用户记录真实生活事件（结构化打卡或自由日记），系统接入 DeepSeek 大模型，基于科学依据判定属性点增减，用户确认后生效，形成"人生 RPG"体验。

请严格按本指令实施，任何需求冲突以本文件与 PRD.md 为准。

## 一、技术栈约束（不可更改）

- 后端：**FastAPI + SQLAlchemy**，数据库 **SQLite**（表结构预留 MySQL/PostgreSQL 平滑迁移）
- 前端：**Vue3 + Vite + ECharts**（轻量）
- AI：**DeepSeek API**（OpenAI 兼容 SDK），所有 LLM 调用集中到 `app/services/llm_service.py`（可插拔：模型名/base_url 从配置读取，不写死在业务代码）
- 密钥：只从 `.env` 读取（`DEEPSEEK_API_KEY` 等），`.env` 已被 .gitignore 忽略，**严禁将真实密钥写入任何提交文件**
- 本地运行：`uvicorn app.main:app --reload`

## 二、必须实现的核心闭环

1. **Onboarding 问卷制**：用户首次使用 → AI 生成问卷（覆盖体能健康/学习/社交情绪/生活管理/兴趣技能维度，可据回答追加追问）→ 用户对话式作答 → AI 生成初始属性面板（100 分制，**每项附推导依据**）→ 用户可异议调整 → 存档初始快照
2. **事件录入双通道**：结构化打卡（类型 positive/negative/goal + 类别 + 参数）+ 自由日记（文本，AI 提取结构化要素）
3. **AI 判定闭环**：
   - AI 输出结构化 JSON：`{"affected_attributes":[{"name","delta","reason","evidence"}],"summary","confidence"}`
   - 用户三选一：**确认入账 / 补充信息重判 / 反驳复核**
   - 复核必须客观：仅依据事实与科学标准；用户无据反驳时**坚持原判定并说明原因，不得一味迎合**
   - 全部操作写审计日志，点数变动全程可回溯
4. **量化锚点库**：内置标准事件基准表（如"30min 中等强度有氧 = 体能+1"、"目标达成 = 规划力+2"、"目标未达成 = 规划力-1"、"熬夜至 02:00 = 健康-0.5"），AI 按强度/时长/质量加权调整，依据引用运动科学（ACSM 等）/学习科学/睡眠研究知识；锚点表入库且**用户可见可校准**，校准后后续判定随之调整
5. **目标系统**：设定（描述+指标+期限）→ 达成奖励（默认规划力+2 及关联属性）/ 到期未达成扣规划力 -1；目标修改与取消记审计
6. **游戏化（中度）**：属性面板（数值+进度条）、人生等级+经验条（升级曲线随等级增长）、雷达图/成长趋势折线/月度热力图；成就/Streak/任务/金币商店做成**可开关扩展模块**（数据模型预留）

## 三、数据模型（核心表，建表 SQL 需随 M1 交付）

users / user_profiles / attributes / attribute_history / events / ai_judgments / judgment_logs / goals / anchors / settings

字段设计详见 PRD.md 第 6.3 节，接口见 6.5 节（POST /api/onboarding/*、/api/events、/api/judgments/*、/api/attributes、/api/goals、/api/anchors、/api/settings）。

## 四、Git 工作流约束（强制）

- 仓库根目录：`C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg`，当前分支 `main`
- **只 commit，不 merge、不 push**（远端由用户自行控制）
- **提交颗粒度**：一个 commit = 一个逻辑单元（如"新增事件模型"、"实现 AI 判定接口"、"添加属性面板页面"），禁止大而全的"一次性提交"和碎片化的"改一个字符提交一次"
- commit message 中文，格式：`类型: 简述`（类型：feat / fix / refactor / docs / chore / test）
- 严禁提交：`.env`、`__pycache__/`、`*.db`、`node_modules/`（.gitignore 已覆盖）
- 每完成一个里程碑（M1/M2/M3）在 README 的开发状态中勾选对应项

## 五、交付顺序与输出要求

按里程碑顺序实施，**M1 优先、可运行**：

- **M1（MVP）**：FastAPI 骨架 + 全部建表 SQL + 打卡事件录入 + AI 判定闭环（确认/补充/反驳）+ Onboarding 问卷流 + 属性面板页
- **M2**：自由日记模式、判定审计页、目标系统、雷达图/成长曲线
- **M3**：游戏化模块化开关、热力图、数据导出

输出要求：
- 每个模块给**可运行代码**，代码注释中文
- 关键 AI Prompt 模板放 `app/prompts/` 目录（onboarding.py / judge.py / dispute.py）
- 目录结构清晰，README 更新启动步骤
- 遇到与 PRD 冲突的需求判断：保守实现，不要擅自扩展功能边界；不确定处写 TODO 注释并记录到"决策记录"节（docs/PRD.md 末尾或单独 docs/DECISIONS.md）

开始前先阅读 `docs/PRD.md` 全文，然后从 M1 开始。
