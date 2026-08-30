# 游戏人生（Game of Life）

AI 驱动的个人成长游戏化系统 —— 记录生活事件，AI 依据科学标准判定属性点增减，把现实人生变成一场可量化的 RPG。

> 正式需求与方案文档见 [docs/PRD.md](docs/PRD.md)

## 快速了解

- **产品形态**：Web 应用（FastAPI + SQLite + 轻量前端），本地先行，后续上云
- **AI 判定**：DeepSeek API，结构化输出（影响属性 / 增减点数 / 科学依据）
- **核心体验**：写事件 → AI 判定 → 你确认 / 补充信息 / 反驳 → 入账 → 属性成长可视化

## 开发状态

- [ ] M1：事件录入 + AI 判定闭环 + 属性面板（MVP）
- [ ] M2：自由日记、目标系统、可视化
- [ ] M3：游戏化模块化（成就 / Streak / 任务）
- [ ] M4：上云部署 + 多用户
- [ ] M5：APP（PWA）

## 本地运行（M1 之后可用）

```bash
pip install -r requirements.txt
# 复制 .env.example 为 .env 并填入 DeepSeek API Key
uvicorn app.main:app --reload
```
