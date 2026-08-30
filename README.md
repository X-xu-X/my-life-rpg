# 游戏人生（Game of Life）

AI 驱动的个人成长游戏化系统 —— 记录生活事件，AI 依据科学标准判定属性点增减，把现实人生变成一场可量化的 RPG。

> 正式需求与方案文档见 [docs/PRD.md](docs/PRD.md)

## 快速了解

- **产品形态**：Web 应用（FastAPI + SQLite + 轻量前端），本地先行，后续上云
- **AI 判定**：DeepSeek API，结构化输出（影响属性 / 增减点数 / 科学依据）
- **核心体验**：写事件 → AI 判定 → 你确认 / 补充信息 / 反驳 → 入账 → 属性成长可视化

## 开发状态

- [x] M1：事件录入 + AI 判定闭环 + 属性面板 + Onboarding 问卷（MVP）
- [ ] M2：自由日记、目标系统、可视化
- [ ] M3：游戏化模块化（成就 / Streak / 任务）
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
  models/                 # 10 张核心表 ORM 定义
  schemas/                # Pydantic 请求/响应模型
  services/
    llm_service.py        # LLM 统一调用（唯一 LLM 出口，可插拔）
    judge_service.py      # AI 判定闭环（确认/补充/反驳 + 审计）
    anchor_service.py     # 量化锚点库（内置基准 + 校准）
    onboarding_service.py # Onboarding 问卷流
    user_service.py       # V1 单用户
  prompts/                # 关键 Prompt 模板（judge/dispute/onboarding）
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
