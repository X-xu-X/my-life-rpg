# 2026-10-21 最新日常使用改版独立审查

结论：**需要补修，暂不发布本轮版本。** 本次只审查、构建及运行隔离用例，没有修改业务实现、提交、推送或更新云端。

审查对象为本地 `37e74c796b1436c9115e17bdac264f0e9eb7a6f2`（`9a05d53` 后端、`ee46d48` 前端、`37e74c7` 验收交付），相对已部署基线 `7eb96f610635f53c1a318f911a661427bd57a44d`。需求依据为 `DAILY_USE_REDESIGN_DEV_SPEC_2026-10-21.md`，不是单看 Demo 截图。本地 origin 跟踪信息未经本次联网刷新，不能据此断言 GitHub 实时状态。

## 需要补修的问题

### R1 / P1：已有计划、照顾项目在新管理页编辑后无法保存

位置：`frontend/src/components/ProjectManager.vue:17–18`；`app/services/workflow_common.py:17`。

`edit()` 将整个 `p.rule` 展开到表单，包括服务器追加的 `timezone`；`save()` 又将整个表单发给 `/projects/{origin}/{id}`。输入模型继承 `WriteIn(extra='forbid')`，不接受 `timezone`。

真实编译前端复现：创建一个指定一次的行动计划，打开“编辑项目”，只改名称后点击保存，响应为 HTTP 422：`extra_forbidden / body.timezone / Asia/Shanghai`，窗口不关闭，名称未保存。独立 HTTP 用例也确认照顾项目的相同规则回传为 422。因此不只是错误小字难看，而是常规编辑功能不可用。后端拒绝未知字段本身应保留。

修复要求：前端构造明确允许的编辑字段，不回传服务端上下文；保留版本、请求回执及严格输入校验。通过真实页面分别验证两类项目的新建、重新打开、改名、改分类、停用、保存及刷新后的持久结果，不能仅以 API 构造合法 body 代替页面验收。

### R2 / P2：未来一次性安排打开编辑时日期被默认成今天

位置：`frontend/src/components/ProjectManager.vue:17`。

展开 `p.rule` 后又用 `start:localDate()` 覆盖原始日期。实测原安排为 `2026-10-28`，在 `2026-10-21` 打开编辑，日期框已变成 `2026-10-21`，即使用户只是想改名称。

目前 R1 的 422 阻止了实际保存，**本次没有观察到已保存日期被改写**。但只修 R1 而保留此逻辑，会让普通编辑携带非用户主动选择的新日期；间隔日的起算基准也有同类风险。

修复要求：区分原排期日期与修改生效日。保留未来一次性日期和间隔起算语义；确需为历史安排选择新的生效日时显式提示，不隐式改期。验证未来一次性、间隔日、历史每日计划三种编辑，已有结果与历史不变。

### R3 / P2：自动价格检查只处理首批，后续奖励缺少继续机会

位置：`frontend/src/components/RewardShop.vue:12–13,21`；`app/services/pricing_checks.py:26–36`。

前端为同一账号同一天缓存一个请求 UUID，重新进入仍重放该 UUID；服务端每次最多创建 3 个任务，之后 worker 只执行已有任务，不续排下一批。轮询也只是 GET。结果是同日反复进入仍得到第一批旧回执，第 4 个以后的已授权奖励没有新任务。正常跨日又从较小 ID 开始，后面的项目可能反复轮不到；当天首次进入时没有待检查奖励，随后才开启的奖励也可能受旧回执影响。主动切换权限或重新登录等产生新请求的操作可能绕过，不代表正常入口覆盖完整。

独立 HTTP 复现：6 个已开启自动定价、当天尚未评估的合成奖励；第一次请求创建任务 `[1,2,3]`；相同 UUID 重放后总任务仍为 3；不同 UUID 才创建 `[4,5,6]`。这与正常前端每天复用相同 UUID 的代码组合成立，并非模型供应商失败。

修复要求：保留每项每日去重、每天预算、失败不自动重试、未知结果恢复原 UUID 等限制，同时给尚未覆盖的项目有界、可恢复的后续批次或公平轮转机制。不能简单取消所有限额或每次轮询生成新 UUID。验收至少覆盖 6 项、超过每日上限、首次空队列后新增、刷新/双标签、失败及次日公平性。

### R4 / P2：合并后丢失照顾清单显示设置及管理能力

位置：`app/routers/projects.py:24–41`；`frontend/src/components/HomeView.vue`、`ProjectManager.vue`；`frontend/src/router.js` 的 `/care` 重定向。

新首页总是渲染照顾类别 `ProjectManager`；新 `/projects` 只检查项目自己的开关，不读取旧 `CareConfig.enabled`。实测关闭首页清单后，旧 `/care` 返回 `config.enabled=false` 且 `today=[]`，新首页仍实际显示该照顾项目。原“关闭首页清单”的选择失效。

另有明确规格遗漏：旧照顾设置页已经不再有路由入口，而新管理窗口没有排序和移除操作；列表又按 ID 读取，旧 `position` 顺序未沿用。表单 `fresh()` 的 `position=0` 也没有在编辑时回填原排序值。规格第 7 节要求照顾项目可排序、停用、移除；“停用”不能替代全部这些能力。零项/当日无安排时的新首页仍显示一个空清单卡片，与原零项隐藏行为不同。

修复要求：在共用管理入口保留需要的能力和旧配置语义，按 position 展示照顾项目，编辑不重置排序；移除只隐藏项目、保留原记录及结算身份。验证旧关闭设置、零项、自定义顺序、移除后历史仍可看、两类项目互换后的当次结果语义。不要恢复一整套重复管理页来绕过合并目标。

## 本次复核结果与证据

| 项目 | 独立运行结果 | 边界 |
|---|---|---|
| 前端 `npm.cmd run build` | 通过 | 有现存图表 chunk 体积提示，不是构建失败 |
| 后端全系统 `--repairs --daily-use` | 163 项执行，161 通过，2 跳过 | 临时合成 SQLite，无真实库 lifespan；真实 PG 并发、导入未运行 |
| 原 109 项浏览器验收独立复跑 | 109 通过 | 编译 Vue + 真实 ASGI 路由/服务/worker；合成数据库、模型，不等于生产或模型质量验收 |
| 新增独立 HTTP 边界复现 | R1 照顾编辑、R3、R4 已复现 | 不访问真实模型、生产账号或数据库 |
| 新增实际页面边界复现 | R1 计划编辑、R2 日期预填、R4 首页显示已复现 | 桌面 Edge，本机隔离环境 |

证据根目录：[daily_use_independent_2026-10-21](review/daily_use_independent_2026-10-21/)。其中：

- [backend-full/backend-results.json](review/daily_use_independent_2026-10-21/backend-full/backend-results.json)、`backend-tests.log`：完整后端测试。
- [browser/browser-results.json](review/daily_use_independent_2026-10-21/browser/browser-results.json)：原 109 项独立复跑。
- [edge-cases.json](review/daily_use_independent_2026-10-21/edge-cases.json)：新增 HTTP 复现的响应。
- [browser-edge-cases/browser-results.json](review/daily_use_independent_2026-10-21/browser-edge-cases/browser-results.json)、`api-requests.json` 和截图：真实页面新增复现；条目中的 `REPRODUCED_DEFECT` 表示已复现缺陷，不能算验收通过。
- `.run/review_daily_cases.py`、`.run/review_daily_edge_browser.mjs`、`.run/review_daily_edge_runtime.py`：本次隔离复现脚本。生成目录与原 Writer 证据分开。

初次受限环境后端测试曾停滞，已终止；获准在本机测试环境重跑的完整测试正常结束。以 `backend-full` 的完整结果为准，不将环境停滞误判为业务故障。

## 上云状态与下一步

本次自动 SSH 只读登录未通过认证；用户明确确认自己能够正常登录并执行更新命令。未索取私钥、口令或 GitHub 令牌，也未触碰云端数据。暂缓发布的原因是上述已复现业务问题，不是等待重复部署授权。

Writer 补修 R1～R4 后，重跑相应用例和完整回归。发布仍需在实际 PostgreSQL 的隔离副本验证从现有 `b024_fact_notes` 到 `b025_daily_use` 的升级及数据对账；SQLite 迁移通过不能替代它。真实供应商诊断/业务 JSON、生产 TLS、实际邮件投递与手机实机本轮未验收，尤其不能说原 DeepSeek 连通问题已经通过真实接口验证。

审查通过后再固定发布提交、构建现有离线镜像交付包，并提供服务器命令；停写、备份并校验、隔离恢复/升级对账在实际生产迁移之前完成。保留数据库卷、现有账号分离和凭据配置，不重新导入旧数据、不重建初始账号、不清卷、不以降级删表回退。
