# 游戏人生（Game of Life）

> **2026-10-21 独立审查补修**：已按 R1～R4 修复项目编辑、排期/生效日、价格续批公平性及照顾清单管理，见[补修交付](docs/DAILY_USE_REDESIGN_FIXES_DELIVERY_2026-10-21.md)。后端169通过/2真实PG未运行，原109项与新增修复浏览器验收通过；本地自验供复审，不表示发布。

> **2026-10-21 本地开发交付**：本轮正式 Vue/API/worker 与 b025 迁移已实现，见[逐项交付及 A01～A33](docs/DAILY_USE_REDESIGN_DELIVERY_2026-10-21.md)。新版自动定价、一次问卷、长期信息/回归、项目整合、提示及日期导出已接入；保留旧权益和备案。下条“尚未完成”属于设计时点；本轮未推送/部署，真实 PG/供应商/SMTP/手机等仍单列 NOT_RUN。

> **2026-10-21 当前开发入口**：用户认可新版[完整 Demo](docs/prototypes/life-journal-complete-preview-2026-10-21/index.html)，要求交 Writer 正式开发。[本轮开发规格](docs/DAILY_USE_REDESIGN_DEV_SPEC_2026-10-21.md)及[Writer 任务书](docs/WRITER_DAILY_USE_REDESIGN_2026-10-21.md)替代下文冲突的旧方案。涵盖全站整理、问卷/回归、模型诊断、逐事实 80% 门槛、个人自动定价等；首记 3 币独立，旧权益保留。143 项检查属于本机模拟 Demo，正式应用尚未完成本轮实现/发布；此前已经上云和迁移的事实不由下文历史“未上线”状态推翻。

> **2026-10-18 本地实现交付**：已根据完整任务书开发正式API／Vue／worker及新增迁移；验收、规则与外部NOT_RUN见[完整交付记录](docs/FULL_SYSTEM_DELIVERY_2026-10-18.md)。改动尚在工作区，未推送或部署。`start.bat` 现衔接本地队列；手动启动时先启动API，再运行 `.venv/Scripts/python.exe -m app.worker --local`，否则分析任务会保持排队。下方“当前仅文档”是当天实施前状态。

> **2026-10-18 开发文档已定稿**：用户已认可[第二版完整系统 Demo](docs/prototypes/lifexp-complete-preview-2026-10-18-v2/index.html)。正式范围见[完整系统开发规格](docs/FULL_SYSTEM_DEV_SPEC_2026-10-18.md)，交接使用[Writer 任务书](docs/WRITER_FULL_SYSTEM_2026-10-18.md)；Q1／Q2／Q3 已收束。当前仅文档交付，尚未发送 Writer 或修改正式应用／云端。

> 历史（已由 10 月 18 日规格接续）：2026-10-17 下一轮：[审查补修与情境奖励/计时开发草案](docs/CONTEXT_REWARDS_TIMER_DEV_PLAN_2026-10-17.md)、[Writer 任务书](docs/WRITER_CONTEXT_REWARDS_TIMER_2026-10-17.md)。详细问卷可跳过、通用 AI 助手暂缓；金币试用规则 Q1 已批准，Q3 已确认实际保存日，仅基础娱乐形式 Q2 待答复，文档不表示已经实现或上云。

> 2026-10-16：本轮 [反馈修正开发计划](docs/TRIAL_FIX_DEV_PLAN_2026-10-16.md) 与 [Writer 任务书](docs/WRITER_TRIAL_FIX_2026-10-16.md) 已编写；依据 [完整体验 Demo](docs/prototypes/lifexp-complete-preview-2026-10-16/index.html)。当前仅文档交付，应用实现、待决规则与云端验收分别跟踪。

AI 驱动的个人成长游戏化系统 —— 记录生活事件，AI 依据科学标准判定属性点增减，把现实人生变成一场可量化的 RPG。

> 正式需求与方案文档见 [docs/PRD.md](docs/PRD.md)

## 快速了解

- **产品形态**：Web 应用（FastAPI + SQLite + 轻量前端），本地先行，后续上云
- **AI 判定**：DeepSeek API，结构化输出（影响属性 / 增减点数 / 科学依据）
- **核心体验**：写事件 → AI 判定 → 你确认 / 补充信息 / 反驳 → 入账 → 属性成长可视化

## 开发状态

- [x] M1：事件录入 + AI 判定闭环 + 属性面板 + Onboarding 问卷（MVP）
- [x] M2：自由日记、目标系统结算、判定审计页、成长曲线
- [x] M3：游戏化模块开关、月度热力图、数据导出
- [x] M3+：打卡项目体系（自定义打卡项目 / 内容化录入 / 跨来源合并 / 今日盘点 / 目标进度展示，v1.7）
- [x] M3++：游戏化经济系统（AI 定制挑战 / 押金结算 / 金币体系 / 现实奖励商店 + AI 定价 / 停滞问询 / 段位，v1.8）
- [x] M3+++：体验打磨（启动资金按问卷浮动 / 挑战一卡多档 / 全站交互反馈规范 / 手账本搜索重构 / 挑战来源徽章，v1.9）
- [x] M3++++：经济定价重构（AI 主导定价 + 行情快照）/ 成就系统 / 豁免券 / 属性满级拆子维度 / 三页合并「今日盘点」/ 可视化重做（v1.10）
- [ ] M4：上云部署 + 多用户
- [ ] M5：APP（PWA）

## 本地运行

### 后端（FastAPI）

```bash
pip install -r requirements.txt
# 复制 .env.example 为 .env 并填入 DeepSeek API Key（绝不入库）
uvicorn app.main:app --reload
# 访问 http://127.0.0.1:8000/docs 查看 API 文档
```

### 前端（Vue3 + Vite + ECharts）

```bash
cd frontend
npm install
npm run dev
# 访问 http://127.0.0.1:5173（已配置代理转发 /api 到后端 8000 端口）
```

## 目录结构

```
app/
  main.py                 # FastAPI 入口（启动自动建表 + 写入内置锚点 + 默认用户）
  config.py               # 配置（模型名/base_url/密钥均从 .env 读取，可插拔）
  database.py             # SQLAlchemy 引擎与会话
  models/                 # 17 张核心表 ORM 定义（v1.7 checkin_items；v1.8 coin_ledger/challenges/shop_items/redemptions；
                          # v1.10 achievements/exemptions；另给 attributes 加 parent_id/sub_proposal，自动迁移）
  schemas/                # Pydantic 请求/响应模型
  services/
    llm_service.py        # LLM 统一调用（唯一 LLM 出口，可插拔）
    judge_service.py      # AI 判定闭环（确认/补充/反驳 + 审计；v1.10 接入豁免券与子维度落点）
    item_service.py       # 打卡项目周期统计与目标进度（v1.7）
    coin_service.py       # 金币账户与流水（唯一写入口 grant，v1.8）
    economy_service.py    # 行情快照（余额/近 7 天收支/赚币规则/商店价位区间，v1.10 只读）
    challenge_service.py  # 挑战生成/接受/押金/完成判定/结算/过期状态机（v1.8；v1.10 奖励改 AI 定价）
    shop_service.py       # 商店常驻物资预置 + AI 定价 + 兑换券（v1.8；v1.10 与挑战同口径行情快照）
    achievement_service.py # 成就系统（累计型自动发放 + AI 发现型追授，v1.10）
    exemption_service.py  # 豁免券（时段券 + AI 判动机浮动定价 + 购买时扣点，v1.10）
    subdimension_service.py # 子维度（满 95 提议 / 多选确认 / 加点落点解析，v1.10）
    stagnation_service.py # 停滞觉察与问询（替代时间衰减，用户确认才扣分，v1.8）
    anchor_service.py     # 量化锚点库（内置基准 + 校准）
    onboarding_service.py # Onboarding 问卷流
    user_service.py       # V1 单用户
  prompts/                # 关键 Prompt 模板（judge/dispute/onboarding/challenge/shop/exemption/subdimension）
  routers/                # API 路由
sql/
  schema.sql              # 建表 SQL（随 M1 交付，MySQL 迁移参考）
frontend/                 # Vue3 + Vite + ECharts
docs/
  PRD.md                  # 需求与方案
  DECISIONS.md            # 决策记录 / TODO
```

## 核心闭环

```
记录事件（打卡/日记） → AI 判定（依据锚点库，附科学依据）
  → 用户三选一（确认入账 / 补充重判 / 反驳复核）
  → 复核客观（无据反驳坚持原判） → 全程审计可回溯 → 属性成长可视化
```
