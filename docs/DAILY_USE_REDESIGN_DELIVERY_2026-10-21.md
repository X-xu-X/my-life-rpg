# 人生手账日常改版实施与验收 · 2026-10-21

依据本日任务书和完整规格，基线 `7eb96f610635f53c1a318f911a661427bd57a44d`。状态：本地实现及隔离验收完成；真实外部项目单列NOT_RUN，未推送/部署。既有品牌四文件、用户文档、Demo与运维资料保留。原始差异及246个源码哈希见 `review/daily_use_2026-10-21/baseline.json` 与 `initial-tracked.patch.gz`。

## W0 差距与复用矩阵

| 范围 | 既有能力 | 本轮待补 | 验收 |
| --- | --- | --- | --- |
| 模型 | 双组加密、配置版本、进程期限、调用预算 | 固定8token、结束原因丢失、分类、简洁摘要 | A01～A03 |
| 许可 | 原文逐篇、来源版本、出站与晚回校验 | 长期信息/回归/个人定价新来源接入 | A04、A09、A22 |
| 问卷 | 36题稳定ID、草稿、中性/AI一次建档 | 一题一屏、整体后个性补题、只读确认历史 | A05～A09 |
| 回归 | 30天策略、阶段版本与冷却 | 独立草稿向导、软删过滤、自然提示、退出缺记录处罚 | A10～A11 |
| 项目 | 计划/照顾独立稳定身份、历史结果/旧次数 | 共用管理门面、分类只改未来、分钟可空与临时计时 | A12～A14 |
| 结算 | 事实身份、0.8门槛、整组原子确认、首记独立 | 严格数值及旧入口门槛矩阵 | A15～A18 |
| 奖励 | 个人背景/真实用量定价、建议接受、券锁价 | 新户空商店、自动应用、有限持久检查、严格20%整数边界 | A19～A24 |
| 成长 | 保存日统计、属性/子维、图表、固定/动态成就 | 简卡/本人初值差、统一入口、去段位 | A25 |
| 提示 | 原教程/错误散布页面 | 登录会话去重、永久服务端偏好与恢复 | A26 |
| 日期 | 地区手配节日、资格独立 | 官方年度日历/调休、个人公历日子、跨年/闰日 | A27～A28 |
| 账号 | 中文登录、管理分离、可靠邮件队列 | mail_ready真实隐藏表单、可读日期 | A29、A33 |
| 导出 | v5四格式、附件同投影、私密选项 | 日期快捷/严格日期、新业务可选档案 | A30 |
| 全站 | 五入口、独立管理、ICP备案、详情返回 | 桌面分栏、独立奖励、模块唯一归属、全入口AI等待 | A14、A31～A32 |

## 实施结果

最终：后端 **163项执行，161通过、2项真实PG未运行**；编译Vue构建通过；浏览器 **109项通过、669次真实本地API请求、应用/worker异常0**。源码/编译产物/实际下载摘要及旧迁移未改校验见[source-manifest.json](review/daily_use_2026-10-21/source-manifest.json)。

W0～W6 的本地实现已完成。基线为 `7eb96f610635f53c1a318f911a661427bd57a44d`，初始差异、源文件摘要及品牌四文件备份在 [review/daily_use_2026-10-21](review/daily_use_2026-10-21)。未改动真实旧库、账号、生产注册/收费配置，未推送或部署。

- 模型诊断预算改为1024；保留受控结束原因、用量、空正文/其他输出布尔值。HTTP400、凭据、限流、网络、超时、截断、空输出及JSON错误分别处理；只对官方 DeepSeek 端点使用其关闭思考参数。连通测试不再被当成业务质量保证。
- 普通新账号自动进入30题基础问卷，一题一屏、可跳过/暂离；全部基础准备好后才授权整体分析，最多2轮×3题个性补问。确认时保留真实题目/回答/建议快照，一次建档。旧完成问卷只读；长期信息和回归近况独立按用途授权，不重发启动金/调属性。
- 今天/手账/计划/成长/我的加独立奖励区，管理工作区保留隔离。目标/主线只在计划维护，成就/报告集中成长；原 phase/care 路由转到计划，旧合同和特殊券仍可访问。ICP备案保留。
- 项目共用管理门面，来源仍为原 PlanSchedule/CareItem；当次结果、事件与事实身份不搬表。分钟可空，无时长计时先确认本次分钟；未来改分类不改旧完成/部分/未完成/跳过语义。计时列表使用来源加ID，避免两表数字ID相同导致节点复用。
- 逐事实使用原始 `confidence >= 0.8`，非法类型/NaN/无穷拒绝；0.799不入行动/主线币和属性，0.8仍需预览和确认。首记3币及免费基础娱乐独立，原行动6/15/25、主线4/10/15、日上限100不变。
- 新账号无预置奖励。有效初价自动建商品，后续有限POST检查排队、worker应用；每项每日最多一次，23边界19～27、31边界25～37，支持降价。每日最多10项、每次最多3项；失败只保留有效价，允许一次明确重试，无自动无限循环。旧商品自动检查默认关闭，开启需本人确认。
- 报价应用复核来源/用途/配置/日期/商品/购买力快照；兼容接受接口共用同一服务。兑换锁展示版本，旧券锁价、每张独立余量。同步报告/阶段/计时说明/照顾建议增加发送前持久标记；未知结果恢复相同UUID不重复调模型，完成结果仍由原业务回执恢复。
- 一般提示按登录会话展示并支持服务端永久关闭/恢复。旧停滞检查无新处罚路径；统计为保存日简卡，属性显示本人初值差，无熟练/精通标签。中国年度日历、个人公历日子、mail_ready隐藏失效表单、默认全部日期及严格自选日期导出已接入。

本地代码提交：`9a05d536be32fa9c7b2d706e9e53847e51718216`（服务端/迁移/后端回归），`ee46d48167fc08caf7812a8ce8c51dfee9275e33`（正式Vue及保留品牌）。本报告与浏览器夹具/证据另成一条验收提交；提交不表示推送或部署。

## A01～A33 验收对应

“本地通过”仅指隔离数据库/模型替身与编译Vue；真实供应商、PG、邮件、手机的边界另列。新测试位于 [test_daily_use_redesign.py](../tests/test_daily_use_redesign.py)，同时保留并运行既有安全、完整系统、续做、补修、账号及运维测试。只调整被本轮明确替代的36题/重做问卷/人工接受价格/固定商品测试前提，没有删掉旧安全断言。

| 编号 | 主要代码 | 本地证据与结果 |
| --- | --- | --- |
| A01 | settings、llm_service、model_runner、model_diagnostics、model_errors | 新A01模拟正文空/其他输出/截断及受控分类；TrialP1错误矩阵；不含隐藏思考/凭据。真实供应商NOT_RUN |
| A02 | ModelSettings、credentials、settings版本校验、session | 旧凭据/组切换/旧版本响应测试及设置截图；保存模型完整ID、启停、时间、诊断折叠 |
| A03 | RequestStatus、useWorkflowWrite、analysis_jobs、model_dispatch、questionnaire、reward_quotes | 新A03同UUID超时后只调一次、成功回执重放；真实浏览器即时定价/报告等待、worker任务持久；长耗时外部模型NOT_RUN |
| A04 | ai_context、personal_context、review_context、fact_analysis、report、shop_service | [四用途实际消息捕获](review/daily_use_2026-10-21/final-backend/captured-model-payloads.json)：每用途只有相应背景、私密原文及无来源派生记忆不出站；撤权晚回拒绝；浏览器也捕获实际消息 |
| A05 | App、auth、QuestionnaireView | 真实API注册中文新账号后自动向导，旧已评估普通用户和管理用户不进入；旧评估保留测试 |
| A06 | questionnaire、QuestionnaireView | 浏览器一屏一题、自动保存、刷新恢复、返回/跳过/余题跳过；基础未齐不分析，新问卷保存无模型调用 |
| A07 | question_catalog、questionnaire/analyze | 新A07按已回答题ID补问、数量/轮数上限、跳过主题不变说法重问；真实模型补题合理性NOT_RUN |
| A08 | questionnaire、onboarding、coin_service | 全跳过/无模型80起点、AI合成150而非固定80、13维一次确认、回执重放、不重建旧档；浏览器完成后只读 |
| A09 | personal_information、questionnaire/history/permissions | 新A04/A09增改删用途、历史题目快照、旧不完整历史明确标注；属性/余额不变 |
| A10 | phase、return_checkins、ReturnView | 新A10离开/稀少/新号/软删/冷却；近况草稿刷新恢复题目位置，跳过冷却，不造原文/启动资金 |
| A11 | daily-prompts、experience_preferences、stagnation | 新A10/A11活跃/回归互斥、暂停及永久关闭，无缺记录处罚；今天提示截图 |
| A12 | projects、plans、care、ProjectManager、TimerView | 两类别、可空分钟及全频率回归；浏览器添加两类项目，无固定时长先确认25分钟，不产生0分钟会话 |
| A13 | plans/care历史快照与原结果表 | 新A12/A13变分类保留来源/快照/事实ID；旧R01两项继续通过，包括旧计划缺快照后“明天修改”今天仍可计时 |
| A14 | router/navigation、Plans/Growth/Rewards/ChallengeView、PhaseBrief | 42个普通页面尺寸组合，旧路由转向、目标唯一归属、合同/特殊券/报告入口保留；当前主线晚回变更测试 |
| A15 | judge_service严格confidence、fact_analysis、旧确认入口 | 新A15非法值及旧入口防绕过，实际worker浏览器0.799新增0、0.8确认6币 |
| A16 | fact_analysis预览/确认 | 新A15～A18混合已奖/低置信/达标事实逐项，既有日记混合防重测试 |
| A17 | fact_notes、facts、settlements | 补充单独保存、不造事件；跨事件/日记/照顾/计划同事实一次；既有半组故障事务回滚测试 |
| A18 | trial_rules、trial/first-record/claim | 首记与分析门槛独立，回执、删除/补记/切日测试，基础娱乐独立 |
| A19 | shop_service、personal_context、RewardShop | 新A19及四用途捕获证明本人背景实际入价；新户无商品，失败保留草稿，浏览器23自动加入。真实两用户模型价格语义NOT_RUN |
| A20 | pricing_checks worker、reward_quotes/apply_quote | 新A20同日合并、重复入口有限调用、失败只一次显式重试，定价晚回无效；浏览器无人工接受步骤 |
| A21 | bounded_price、shop验证 | 新A19/A21的23/31/低价/涨降/日边界，整数取ceil/floor避免超过20% |
| A22 | ai_context、apply_quote、phase版本/主线快照 | 新A22撤背景/旧未证实建议拒绝，旧价格建议仅当前上下文可应用；旧券权益不变 |
| A23 | shop/redeem、receipts、coin_service | 新A20/A23旧购买预览冲突及原兑换重放/余额范围；浏览器两次主动购买两张券。真实PG独立双连接NOT_RUN |
| A24 | timers、VoucherAllowance、TimerView | 原25/30/25、跨日、实际说明/更正/离线测试；浏览器首券5分钟后25、新券30且实际输入清空，暂停刷新恢复 |
| A25 | attributes、RecordMetrics、AchievementsView | 昨天连续、保存日与内容日、本人旧初始值、同义成就精确legacy_code归并原回归；成长截图，无段位 |
| A26 | HintCard、auth/me login_session、preferences | 新A26服务端账号归属/新会话，浏览器永久偏好跨重新登录；必要价格/等待/错误常驻 |
| A27 | official_calendar、admin/calendars、CalendarEditor | 新A27官方2026/缺年、工作日/法定日分离；导入不新增Holiday或发币；既有同日节日一次/原加成上限测试 |
| A28 | important_days、upcoming | 新A28跨年/2月29/无出生年/非法日、引用目标期限不复制；浏览器添加年度2月29日 |
| A29 | Auth/AccountSecurity mail_ready、auth/权限 | 原身份/注册/改密/会话/恢复测试，浏览器中文注册、未就绪无发送表单、管理独立；真实SMTP/收件NOT_RUN |
| A30 | export、readable_export、ExportControls、dateInput | 四格式浏览器真实API下载，原文存在/无Key与令牌，非法2月31拒绝；原N02及附件问答/历史/分析排除、CSV公式和HTML转义继续回归 |
| A31 | b025、projects、receipts、原合同/导出/筛选 | 旧b009合成库升到head且重复升、余额40/旧券12/未知许可私密/原身份对账，新表空、旧商品默认不自动检查；手账筛选未更改；ICP备案截图 |
| A32 | 全部编译Vue、daily-use.css、ConfirmDialog | [真实API浏览器报告](review/daily_use_2026-10-21/browser/browser-results.json)：1440/390、7个核心页200%文本、键盘缩小视口、确认焦点、关键按钮实际鼠标命中、无横向溢出/运行异常；手机实机NOT_RUN |
| A33 | feedback/admin、announcements、统计筛选 | 真实浏览器普通用户反馈→管理回复、另一新号不可见；发布/撤下公告、普通账号人数过滤；旧管理权限/筛选/审计测试 |

## 可重跑的证据

```powershell
.venv/Scripts/python.exe tests/run_full_system_checks.py --repairs --daily-use --output docs/review/daily_use_2026-10-21/final-backend
cd frontend
npm run build
cd ..
node tests/browser_daily_use.mjs
git diff --check
```

- 后端最终结果：[backend-results.json](review/daily_use_2026-10-21/final-backend/backend-results.json)及完整日志；测试入口去掉重复载入账号测试，计数为独立执行数。原2项真实PG用例仍跳过，没有新增skip/xfail。
- 前端：[构建日志](review/daily_use_2026-10-21/frontend-build.log)；浏览器结果含每个编译文件SHA256。首次探索失败保留为过程记录，不纳入最终PASS；旧失败截图/DOM放在browser/exploratory。构建仍有原图表分块大于500kB的非阻塞提示。
- 浏览器：[运行汇总](review/daily_use_2026-10-21/browser/runtime-results.json)、[实际API请求](review/daily_use_2026-10-21/browser/api-requests.json)、[模型实际输入](review/daily_use_2026-10-21/browser/model-payloads.json)、[下载位置](review/daily_use_2026-10-21/browser/download-directory.json)。测试使用真实路由/服务/worker和临时SQLite，只有供应商响应与时钟为合成。
- [今天桌面](review/daily_use_2026-10-21/browser/_-1440.png)、[奖励窄屏](review/daily_use_2026-10-21/browser/_rewards-390.png)、[0.799门槛](review/daily_use_2026-10-21/browser/confidence-79.9.png)、[独立两券](review/daily_use_2026-10-21/browser/voucher-25-30.png)、[设置200%](review/daily_use_2026-10-21/browser/_settings-200-text.png)。其余页面在同目录。
- HTTP回环桥接HTTPS TestClient仅验证业务，生产TLS/Secure Cookie真实浏览器传输未验；导航取消的客户端断开单列，不作后台异常。没有启动应用lifespan或读取应用真实DB_URL。

## 迁移、兼容与回退

新增 `b025_daily_use` 接 `b024_fact_notes`，不修改已执行revision。增加7张表：个人信息/提示偏好/回归/重要日子/官方日历/价格任务/同步模型发送标记；问卷增加题目/补题/确认历史/用途和阶段；商品增加说明、评估时间与自动价格许可。旧商品 `auto_pricing=false`；旧问卷不凭空生成当时题目，缺快照如实说明；旧规则/合同/券/流水不重写。

业务规则继续使用 `trial-2026-10-18-v1`，问卷目录以代码 `CATALOG_VERSION` 留档，回归策略沿30日窗口/最短账号30日/30日冷却。定价任务及新同步发送标记不重试未知付费调用；云端报告生成要求UUID，旧本地无UUID API仅为兼容保留；当前UI始终发送UUID。旧SQLite导入器遇到这些新业务表非空会拒绝静默导入，不宣称支持新档案一键恢复。

发布前应先停写并做一致备份，在隔离副本执行升级及对账，再更新API/worker/静态前端。此轮未执行真实库迁移。回退先停新API/worker，保留升级库和审计，使用升级前一致备份做隔离恢复；迁移downgrade主动拒绝删档，不自动drop新历史。不能用本轮临时测试库替换真实库。

## 官方依据与待验项目

协议核对：[DeepSeek聊天协议](https://api-docs.deepseek.com/api/create-chat-completion/)、[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)。只存安全元数据，供应商真实聊天与业务JSON/个性补题/个人价格要分别实测，不能据合成OK声称真实模型通过。

2026日历核对：[北京市政府转载国务院办公厅通知](https://www.beijing.gov.cn/zhengce/zhengcefagui/202511/t20251104_4258873.html)、[国务院2024年修订放假办法](https://www.gov.cn/zhengce/content/202411/content_6986380.htm)。代码保留原通知URL、核验日期及镜像；发布前复核，不以全年休息区间自动扩大礼金日。

| 状态 | 内容 |
| --- | --- |
| 已实现并本地验收 | 本报告W0～W6及A01～A33本地部分，正式Vue/API/worker/迁移和历史对账 |
| 待配置/未验收 | 独立PostgreSQL双连接并发/导入；真实供应商聊天、业务JSON、补题及两用户价格语义；真实SMTP投递/收件；生产TLS/Secure Cookie及部署旧数据；真实手机键盘/系统浏览器 |
| 环境原因 | 本机无docker/pg_ctl/psql及测试PG地址；本轮隔离测试未接入可用的真实模型/SMTP验收凭据；本轮不接真实旧库、不部署 |
| 本地实现范围的已知剩余项 | 无已知阻塞本地开发的剩余项；外部未验部分不能标PASS |
| 继续暂缓 | 手账筛选新方案、重做问卷调属性、通用聊天/思考全文、共享默认模型、App/小程序、短信/社交登录、复杂预约分期、农历和重要日子额外金币 |

## 外部验收与授权边界

暂未调用真实模型/SMTP、连接真实旧库或云端。PostgreSQL独立双连接、真实供应商语义与价格、真实邮件收件、手机实机仍待环境，不以SQLite或Demo代替。任务授权本地实现/隔离验证和按逻辑提交；不自动推送、部署、改生产配置或迁移真实数据。
