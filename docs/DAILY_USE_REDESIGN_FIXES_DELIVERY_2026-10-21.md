# 日常改版独立审查补修交付 · 2026-10-21

依据 [R1～R4 审查报告](DAILY_USE_REDESIGN_REVIEW_2026-10-21.md)，修复基线为 `37e74c796b1436c9115e17bdac264f0e9eb7a6f2`。本轮完成本地修复与隔离自验，供再次独立审查；没有将原审查结论改写为“审查通过”，没有推送、部署或接触真实库。原审查脚本与证据目录保留。

代码本地提交：`cf31c9ba5b0d1a2c77da316b4def4835f09d2511`。验收文档/证据另成一条提交；没有推送。新增浏览器实际API请求 434 次，原完整浏览器 666 次，应用/worker异常均0。

## 修复对应

| 项目 | 实现 | 验收 |
| --- | --- | --- |
| R1 / P1：项目编辑422 | `ProjectManager.editable/allowedBody`明确列举可编辑字段，不展开或回传服务器rule；timezone仍由后端决定，`extra='forbid'`保留。带原版本、稳定UUID及回执提交。长编辑窗口首次聚焦名称，避免窄屏打开便滚到底部；兑换等默认确认焦点保留原行为。 | 实际编译页面分别创建plan/care来源项目，重新打开、改名、换分类、停用、保存、刷新及再次打开；实际请求字段无timezone且全部200。后端另证实未知timezone仍422、同UUID重放不重复保存。 |
| R2 / P2：编辑默认改期 | 保留排期start，另设显式`effective_from`修改生效日，编辑窗口分别展示。间隔仍以原start取模，生效日只决定采用哪版规则。新历史存顶层生效日，旧历史缺字段继续按原rule.start解释；旧无历史计划先捕获已知基线。 | 未来一次性日期原样预填并保存；历史间隔改名保留起算日和下次到期；历史每日从明天改名，今天/昨天原结果和快照不变。两类来源及旧空历史计划今天计时均通过。 |
| R3 / P2：只检查首三项 | 每批仍最多3项、每账号每日最多10个不同奖励。队列返回`has_more/remaining/budget_remaining`，页面只在上一批已知接收后续排，单次进入最多4个POST；GET轮询不发起续批。发送前保存UUID，未知结果保留，同日成功请求退役；旧已缓存回执也可恢复后继续。每个未知UUID独立存储槽，双标签不互相覆盖。 | 六项实际排满两批；首次空队列后新增可排；刷新不重复调模型；双标签13项只排10个不同项，实际假供应商调用10次。失败任务不自动重试；原明确一次重试限制继续回归。超过上限者次日优先，后端验证13项中前日未覆盖3项排在次日首批。 |
| R4 / P2：清单配置/排序/移除丢失 | `/projects`返回原CareConfig和原position，首页按当次分类及原显示开关决定显示，关闭或零到期项隐藏整张照顾卡片；完整管理仍可看项目。共用窗口维护排序、停用、移除；plan来源的分类转换项目也用原rule保存排序/移除元数据，不搬表。移除只隐藏，管理可勾选已移除项目查看原记录、结果与历史。清单显示更新保留ai_allowed。 | 原关闭选择持久有效；零项不露空卡；自定义2/40排序，改名不重置40；移除后事件ID、结果、余额和已结算流水不变。两类互换后原skipped/partial语义、当次快照及身份保持；显式更正从原partial开始。 |

补修中新增“首次部分完成”场景发现旧保存分支提前flush时尚未填PlanOccurrence的非空`outcome/facts`。已在创建行时初始化两字段，事件、结果及回执仍在同一事务提交。后端和真实页面均覆盖，未放宽数据库约束。

## 最终隔离验收

- **后端：171项执行，169通过，2项真实PG未运行。** 包括原163项及8项新复合回归；没有重复加载导入的测试类，没有新增skip/xfail。
- **前端构建通过。** 原图表chunk体积提示保留在日志，不是构建失败。
- **原完整浏览器109项通过；新增修复浏览器42项通过。** 正式编译Vue调用真实FastAPI路由/服务/worker，使用临时SQLite和假供应商；新建/编辑/确认按钮实际鼠标命中点击，含1440桌面、390编辑窗口、旧流程200%与焦点回归。
- **价格续批辅助逻辑6项通过。** 覆盖未知响应原UUID恢复、多个未知槽互不覆盖、首次空队列后的新进入、旧回执兼容与4请求硬上限；实际队列去重、日预算与公平性由后端/浏览器共同验证。
- 编译检查及差异空白检查通过。源码、编译产物及最终四格式下载摘要见 [source-manifest.json](review/daily_use_fixes_2026-10-21/source-manifest.json)。两套浏览器结果绑定同一编译产物摘要；旧Writer/独立审查证据未覆盖。

## 可复核证据

证据根目录：[daily_use_fixes_2026-10-21](review/daily_use_fixes_2026-10-21/)。

| 证据 | 文件 |
| --- | --- |
| 完整后端与四用途消息回归 | [backend-results.json](review/daily_use_fixes_2026-10-21/backend-full/backend-results.json)、backend-tests.log、captured-model-payloads.json |
| 新复合回归 | [test_daily_use_review_fixes.py](../tests/test_daily_use_review_fixes.py)、targeted-backend.log |
| 价格续批恢复测试 | [pricing_sweep.test.mjs](../tests/pricing_sweep.test.mjs)、pricing-sweep-tests.log |
| 新增真实页面结果与请求 | [review-browser/browser-results.json](review/daily_use_fixes_2026-10-21/review-browser/browser-results.json)、api-requests.json、runtime-results.json、model-payloads.json；项目请求留存字段名与合成排期值 |
| 原109项完整回归 | [browser-full/browser-results.json](review/daily_use_fixes_2026-10-21/browser-full/browser-results.json)、runtime-results.json、真实下载及下载目录记录 |
| 日期窗口/清单/移除 | [一次性照顾编辑窄屏](review/daily_use_fixes_2026-10-21/review-browser/future-once-care-edit.png)、care-custom-order.png、removed-history-preserved.png |
| 六项价格及失败保留有效价 | [six-price-checks-with-one-failure.png](review/daily_use_fixes_2026-10-21/review-browser/six-price-checks-with-one-failure.png)及实际模型输入/任务状态 |
| 源码与构建 | source-manifest.json、frontend-build.log、baseline.json、initial-status.txt |

原有 `.run/review_daily_*`、`daily_use_independent_2026-10-21` 及审查报告本身不修改。补修自己的首次失败日志/截图单列exploratory，不冒充最终PASS。所有测试账号、输入、凭据字样和供应商响应都是合成；没有把预制API响应当成真实页面后端。

```powershell
.venv/Scripts/python.exe tests/run_full_system_checks.py --repairs --daily-use --output docs/review/daily_use_fixes_2026-10-21/backend-full
node --test tests/pricing_sweep.test.mjs
npm.cmd --prefix frontend run build
node tests/browser_daily_review_fixes.mjs
$env:DAILY_USE_EVIDENCE_DIR='docs/review/daily_use_fixes_2026-10-21/browser-full'
node tests/browser_daily_use.mjs
git diff --check
```

## 数据、回执和发布边界

本轮无新revision，不修改已存在的b025或任何旧migration。生效日、排序/移除在现有JSON规则/历史中扩展，旧记录、事实、合同、券、押金和流水原位保留。旧调用未提供新字段时，其回执指纹排除新增默认项；新调用仍比较版本、同操作指纹及资源归属。排序/显示/移除都不增减金币，价格队列仍逐项每日唯一，购买和旧券锁价协议未改变。

**回退注意**：新历史把排期起算日与修改生效日分开。旧37e74c7及更早代码不理解`effective_from`，有新写入后不能仅回退代码继续解释同一库的排期。统一发布匹配的API/worker/静态前端；如需回退，先停写并保留新库审计，再按升级前一致备份隔离恢复/对账。不得删JSON字段、删表、重导旧资料、重建账号或清数据库卷来回退。

当前仍未运行真实PostgreSQL的b024→b025隔离副本升级及独立双连接并发/导入。本机PATH未找到docker、pg_ctl、psql；本地SQLite通过和HTTP桥接的双标签测试不替代这些检查。真实供应商聊天/业务JSON/补题/价格语义、生产TLS/Secure Cookie、SMTP收件和手机实机仍NOT_RUN。

原审查要求的再次独立审查、真实PG升级对账及发布前门槛继续有效；本轮没有固定生产发布、构建新离线包或执行服务器更新，后续通过门槛后沿现有打包流程交付。此次完成的是R1～R4修复与本地验收。
