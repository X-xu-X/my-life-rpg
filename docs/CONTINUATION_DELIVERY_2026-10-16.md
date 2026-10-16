# P2～P6 连续实施记录

依据 `WRITER_P2_P6_CONTINUATION_2026-10-16.md`，基线 `9cc2e14`。保护工作区原有文档；仅本地实现、隔离测试和中文提交，不推送、部署、操作真实旧库或发送真实邮件/模型请求。

## P2 日记与完整辅助回顾

已实现真实 API/Vue：显式新事件类型、同日唯一晚间日记、不可变原稿版本、按原稿版本的回顾会话、来源快照、确切问题与逐题回答/跳过、独立分析快照、刷新恢复和后台任务。模型输出先入库再显示；原文编辑使旧会话不能继续发布结果。生活清单默认关闭，无事件/奖励副作用。

数据：b006_diary 增加 Event.record_kind/diary_key（唯一空值兼容），DiaryRevision、ReviewSession、ReviewTurn、ReviewAnalysis、LifeChecklist；AnalysisJob 增加 review_session_id/session_version，复用 worker、租约、调用预算及取消机制。旧记录不推测分类；升级前 UUID 指纹仍兼容。SQLite 增量任务关联由 ORM 归属校验保护，PG 另建外键。新实体的完整导出与导入拒绝策略在 P4 统一补齐。

API：`GET/PUT /diaries/{day}`、`POST /diaries/{day}/review-sessions`、`GET /review-sessions/{id}`、`PUT .../turns/{question_id}`、`POST .../analyze`、`GET/PUT /life-checklists/{day}`。写入使用 UUID/版本/同事务回执；日记回答不拼正文、不增加篇数/日数。旧 `/daily-reviews` 保留原回顾身份。

验证：`unittest tests.test_continuation tests.test_ops_next -v` 6 PASS；临时 SQLite、模型替身。真实编译 Vue 的隔离 Edge 7 PASS（日记保存、确切回答、原文分离、返回恢复、390/1440 布局、无运行异常），前端构建 PASS。独立 PG/真实模型/实机 NOT_RUN。证据在 `docs/review/continuation_2026-10-16`；后续阶段将扩展测试记录。

后续按统一任务继续 P3～P6，不要求用户逐批确认。所有未决产品策略保持可配置且正式启用关闭；不使用原型金额/额度或 owner Key。

## P3 日程、当次结果与同事实

新增 b007_plans：PlanSchedule（版本化周期/生效日期/时区/历史）、PlanOccurrence（本人日程+日期唯一、事实实际量/状态/更正历史）、FactIdentity/EventFact/FactSettlement（事实唯一结算）及 FactRelation（候选来源版本与确认/拒绝）。GET 到期查询不建事件/当次，不顺延旧任务；旧 weekly/none 项目保留独立旧语义。

API：plan-schedules GET/POST/PUT；plan-occurrences GET（day 查询到期，无 day 查询历史）；plan-schedules/{id}/occurrences/{day} PUT；fact-relations GET/POST、{id}/decision POST。完成/部分完成先存事实，可关联本人已有事件，不填虚构百分比；未完成卡片内确认锁定、无事件/奖励/成功 toast。更正需版本和原因；已结算更正保留原结算，不能借更换事实重复领奖。周期修改需明确今天或未来生效日，按版本历史查询过去规则，已保存当次保留快照。

原 judge_service.confirm 同事务认领事实唯一身份，再写属性/审计/原回执，不另建结算服务。用户确认同事实后第二次入账被拦截；旧已结算目标显式关联时建立结算保护，不重算旧账。新增成果差额结算仍关闭。

验证：P1/P2/P3 与迁移 18 PASS；真实编译 Vue 累计 12 PASS（新增创建日程、未完成卡内锁定/无事件/无成功提示、390/1440 布局），构建 PASS。SQLite 不能证明 PG 双连接竞争，独立 PG NOT_RUN。

## P4 可读导出与独立日期指标

真实 Markdown、无脚本离线 HTML、扁平 CSV 和完整 JSON v4 已接入设置页，类型/日期、问题回答、分析、撤销、历史版本及游戏附录可选。HTML 转义并设置严格 CSP；Markdown 正文使用按内容动态增长的代码围栏；CSV 防公式注入。问答保留精确题目与回答/跳过/未回答状态，关闭问答时分析快照也不夹带问答。

默认格式保持 JSON，完整新实体使用 format_version=4；schema_version=3 显式返回旧投影并说明不含新实体。完整 JSON 含全部本人日期/游戏数据；筛选范围用于可读格式。CSV 明示一记录一行、问答 JSON 单元格，不含全部游戏表/原稿历史。导出不宣称可直接恢复；旧 SQLite importer 对含续作实体的源库/目标账号安全拒绝，避免静默丢数据。未实现 JSON v4 恢复工具。

record-metrics GET 提供事件/日记的内容覆盖日与实际保存日、最长连续覆盖、明确 candidate-date-v1 口径与旧未分类条数；不以条数冒充天数，不启用候选日期奖励。新日记不进入旧 source=journal 奖励计算，旧分类与旧账保留。

验证：P4 新增 HTML/Markdown/CSV 攻击内容、原文/问题/未回答、v3/v4 与日期集合测试通过；续作 7 PASS。既有 cloud 回归 18 PASS、2 PG SKIP（首轮导出查询 Literal 整数兼容失败已修复，新用例复跑通过）；编译 PASS，浏览器累计 14 PASS。独立 PG/真实供应商/实机 NOT_RUN。

## P5 账号、邮箱与独立管理工作区

b008_accounts 增加用户可空唯一验证邮箱/验证时间、EmailToken（仅摘要/用途/版本/过期/单次消费）、SitePolicy、Announcement、AdminAudit。默认保持邀请兼容、邮箱非必填、改密撤销全部会话；管理端可明确选直接注册/邀请/关闭与邮箱门槛。没有邮件服务不能开启强制邮箱。旧账号不被突然锁定，原恢复码兼容；改密/找回撤销旧会话和旧恢复码，返回新恢复码。

API：auth/options、auth/password；auth/email/{register-request,bind-request,verify,recover-request,reset-password}；admin/{overview,users,users/:id/status,announcements,site,audit}。沿用原 Session/Origin/CSRF；邮箱公开验证凭单次随机令牌，不返回原令牌。邮件默认显式 503，只有配置 SMTP_SSL（MAIL_HOST/PORT/FROM/USERNAME/PASSWORD）才尝试投递；测试适配器仅在测试注入。邮件服务真实投递 NOT_RUN。找回请求对不存在的邮箱和投递不确定统一返回受理结果，明确受理不代表投递成功，避免通过 SMTP 错误区分账号是否存在。

owner 映射为本轮管理能力，普通 user 服务端拒绝。管理五区和账号安全拥有独立 Vue 导航/返回，生产无本地改 role 按钮。管理只读账号元数据和操作记录，不提供他人日记/Key、改账/提权/删除接口；不能停用唯一管理人或当前自己。停用撤销认证会话，后台模型写回再次检查账号状态。受控 manage_auth_sessions 标记仅允许已鉴权管理动作撤销目标认证会话，其他业务查询仍绑定管理人本人，不解除日记归属过滤。

管理动作有版本/UUID/审计/回执及同事务写入；PG 全局管理 advisory lock 串行唯一管理人和站点策略判断。认证改密/恢复沿用 User 行锁及安全版本/单次令牌语义，不把密码或邮箱令牌明文保存到浏览器恢复缓存/普通写回执。

验证：续作与迁移 11 PASS（包括普通用户直调拒绝、管理不读朋友日记、注册开关、唯一管理人、邮箱不可发送、绑定/找回重放和改密撤销），编译 PASS；真实 Vue 浏览器累计 23 PASS，包括独立管理五区与账号安全返回、未配置邮件反馈和390/1440布局。PG 并发/真实 SMTP/手机实机 NOT_RUN。

## P6 版本化经济规则与独立站点 AI

b009_policies 另为 Event 增加可空 saved_on/saved_timezone，捕获首次保存日及其时区；旧缺失值不猜测回填。保存日指标不随以后账号时区变化回算，编辑版本不增加首次保存天数。新增 EconomicRule（不可变版本）、Mainline、RewardPreview、MainlineAward、DynamicCandidate、DynamicAward、HostedAI、AIPreference、HostedUsage。前六类本人游戏实体和 AI 选择纳入 JSON v4；站点秘密、认证令牌、站点运营配置及内部预算记录不导出。任务私有配置快照中的秘密指纹也不导出。

主线可关联本人已有目标、启停关联；金额/档位/数量/上限/日期/叠加规则未确认时不能预览发币。配置后先保存实际投入/成果与事件、主线、目标、事实、判定和规则版本快照，再通过原 `judgments/:id/confirm` 同事务写入属性、金币、事实结算、奖励、审计和回执。`reward_preview_id` 可选，旧确认正文未携带时保持原指纹与旧经济；新币通过原 coin_service.grant，不创建第二套余额。支持明确选择替代旧日常奖励或叠加，按确认规则控制每事实/每天上限；规则、目标、关联、内容或日期变化拒绝旧预览。

动态候选按“指标 + 日期口径 + 累计/连续/自然月 + 目标 + 范围”生成语义身份，不按标题去重。核实当前未撤销记录及版本，单独保留证据；可以忽略/重新核实。无此身份的正式奖励配置不能领取，不能套用旧发现型 50 币。自然月需明确整月范围，不等同 30 天。配置后领取复核证据并原子写徽章/金币/回执，候选与授奖唯一约束防重；固定等价项必须由规则 `fixed_equivalences` 明确映射，禁止叠加时双向拦截固定/动态重复奖励。新记录的旧固定 50 币追授入口关闭；旧未分类记录继续原协议。

默认 AI 使用独立的 `HOSTED_SECRET_FILE` 映射与 secret_ref，不读取 owner 个人 Key。用户主动选 personal/hosted/off，保存选择不调用模型或分析历史。hosted 需供应商/模型/费用单位与价格核对日期、输入输出上限、个人/全站调用、全站 Token/费用预算、独立秘密及 approved 全部配置才可启用；否则明确未开通，不回退其他付费配置。个人模式继续原主辅组；关闭模式仍可保存原文。

每次实际尝试先在独立短事务预占调用、输入/输出 Token 和费用；复用已有全局模型并发锁。未发出请求时释放预占；供应商确认用量时按当次不可变价格快照结算；超时、取消后计费不明或缺少用量时保留完整预占，不当作免费重试。报告用量超出上限时记录实际量并停用对应版本，避免继续调用。管理监控仅聚合数量、费用单位、失败和未知数，不存原文/Key。费用是按已配置单价与供应商用量的内部预算账，不是外部账单对账验收。

模型写回校验选择版本、站点版本、个人凭据版本、账号状态及站点秘密指纹；秘密文件轮换也使旧任务失效。轮换时仍须通过配置更新递增站点版本，保持审计可追溯。

API 合约：

| 路径 | 方法/作用 | 写入约束 |
| --- | --- | --- |
| `/mainlines`、`/mainlines/{id}` | GET/POST、PUT；目标关联与启停 | 本人目标、UUID、资源版本 |
| `/reward-previews` | POST；事实与规则快照预览 | UUID，事件/主线版本、待确认判定 |
| `/judgments/{id}/confirm` | POST；可选 reward_preview_id | 原判定时间版本/UUID/回执，当前规则/快照复核与原子结算 |
| `/dynamic-candidates`、`/{id}/decision` | GET/POST、POST；核实、忽略、领取 | 本人、UUID、版本、语义唯一身份、当前证据和正式规则 |
| `/ai/preferences` | GET/PUT；个人/站点/关闭 | UUID/版本；站点需主动同意与 hosted_version |
| `/admin/rules/{mainline,dynamic}` | GET/PUT；规则历史与新版 | owner、全局规则锁、UUID/版本、明确 approved，审计与回执 |
| `/admin/hosted-ai`、`/admin/hosted-monitor` | GET/PUT、GET；配置及聚合监控 | owner；只保留秘密引用，不返回秘密值 |

新工作流的版本为严格整数，金额/预算拒绝布尔值等错误类型。最终还补齐普通手账的类型/日期筛选、站内公告阅读、实际判定 API 的模型来源、计划时区快照与未知保存时的原文草稿保留。

## 最终功能/配置状态

| 阶段 | 已有实际后端与 Vue | 仍关闭/待配置 | 环境验收边界 |
| --- | --- | --- | --- |
| P2 | 日记原稿版本、完整持久问答/分析、恢复、可选无奖励清单、类型筛选 | 旧分类不回填，整篇日记不作为单一行动结算；行动应显式保存事件后关联 | 真实模型回顾质量 NOT_RUN |
| P3 | 三类日程、当日到期/总表/历史、三结果锁定、实际量、显式纠错、同事实关联与结算防重 | 新增成果差额奖励关闭；纠错保留已有结算，不暗中回算 | 真实 PG 双连接竞争 NOT_RUN |
| P4 | 四种实际导出、精确问题/答案/版本、安全编码、日期集合、v3兼容投影/新实体导入拒绝 | 未选正式坚持口径，不自动新增奖励；JSON v4 恢复未实现且明确不承诺 | 独立 PG 导入/迁移 NOT_RUN |
| P5 | 直接注册能力/注册开关、主动改密、邮箱绑定/验证/找回、恢复码兼容、管理五区/公告阅读与安全返回 | 默认邀请兼容、邮箱可选；SMTP 未配置不发送，不启用强制邮箱 | 真实 SMTP、PG 认证竞争 NOT_RUN |
| P6 | 规则版本/预览/原子确认、核实候选/领取/等价防重、独立站点模型解析/主动选择/预算/监控 | 正式主线/动态金额、默认供应商/预算未配置，默认不开通；不使用原型数值或 owner Key | 真实模型/账单/PG预算竞争 NOT_RUN |

D01～D11 继续是产品/运营选择：本批实现可配置策略与独立事实，不替用户确定真实金额、默认模型、免费额度、强制邮箱或正式管理扩展范围。没有为真实服务器写任何新策略。新 App/小程序、社交登录、系统推送、代读日记、清库等不在本任务实现范围。

### 最终锁与认证边界

涉及管理策略/账号停用及可配置奖励的路径按“全局管理/规则锁 → 本人 profile → 目标 profile/资源”排序；普通业务仍以本人 profile 串行。停用在同一目标 profile 锁内变更账号和撤销会话；业务取得 profile 后重读账号状态，堵住鉴权通过但等待锁的旧请求。后台模型等待释放事务，写回重新经过同一检查。

`manage_profile_locks` 仅用于已鉴权停用/恢复动作锁定目标 profile 的 ID，不读取/返回其画像；`manage_auth_sessions` 仅用于撤销认证会话；`monitor_hosted_usage` 仅用于无原文/秘密的数字聚合。其他业务归属过滤不解除。密码/恢复统一先锁 User 再处理恢复码，避免与改密反向取锁。以上包含代码与隔离验证，仍须独立 PG 演练实际竞争/死锁；不能据 SQLite 声称 PG 发布门槛通过。

## 最终验收与证据

- `.venv\Scripts\python.exe -B -m tests.run_continuation_checks`：**85 项运行，83 PASS、2 SKIP、0 FAIL/ERROR**。涵盖 P1/P2～P6、原规则和迁移。两项跳过分别是真实 PG 并发及导入，不计通过。模型和邮件全部替身；另有 SMTP 文件适配改动后的邮件安全定向复验 PASS。
- `npm.cmd --prefix frontend run build`：PASS；ECharts 大块约 545 KB 的既有警告仍在。
- `node tests/frontend_next.mjs`：PASS，保留账号切换/迟到响应、命名草稿、双击/未知结果恢复与补充队列版本检查。
- `node tests/browser_continuation.mjs`：**30 PASS**，真实编译 Vue、API mock，日记完整问答/返回恢复、计划未完成锁定、导出下载、邮箱不可发送、管理五区/返回、AI 关闭、候选保存及未配置奖励禁用、候选规则保存、390/1440 布局与长身份。
- `P1_EVIDENCE_DIR=docs/review/continuation_2026-10-16/p1-regression node tests/browser_trial_p1.mjs`：**44 PASS**，含手机雷达图已展开且可见的断言，保留旧 P1 历史报告；最终构建的四档宽度、模型版本反馈、日期精度、任务同步、弹窗/焦点/双击及200%文字回归。
- `git diff --check`：PASS。源码/日志均未包含真实数据、密钥或邮件验证码。

结果：[后端 JSON](review/continuation_2026-10-16/test-results.json)、[详细日志](review/continuation_2026-10-16/test-log.txt)、[续作浏览器及构建哈希](review/continuation_2026-10-16/browser-results.json)、[P1 浏览器及构建哈希](review/continuation_2026-10-16/p1-regression/browser-results.json)。桌面/手机截图：[晚间日记](review/continuation_2026-10-16/diary-390.png)、[桌面日记](review/continuation_2026-10-16/diary-1440.png)、[计划](review/continuation_2026-10-16/plans-390.png)、[管理账号](review/continuation_2026-10-16/admin-390.png)、[核实候选](review/continuation_2026-10-16/policy-candidate-390.png)。全部是虚构数据，手机尺寸模拟不等于实机。

### A01～A17 最终场景矩阵

| 场景 | 结果/边界 |
| --- | --- |
| A01 | PASS：保存不联网、错误反馈、版本冲突与测试中改配置；真实供应商权限 NOT_RUN |
| A02 | PASS（隔离）：无 Key 存事件/日记、失败留原文、关闭 AI、不暗中回退；真实供应商 NOT_RUN |
| A03 | 提示词与回顾结构实现，固定替身测试验证持久化；真实相关性/避重复质量 NOT_RUN |
| A04 | PASS（隔离）：旧任务/版本/取消/配置更换与离页停刷新回归；所有实机晚包组合未逐项演练 |
| A05 | PASS（隔离）：星期、间隔跨年、捕获时区的当天与历史快照；旧 weekly/none 不改期 |
| A06 | PASS（隔离）：未完成零事件锁定、直接改结果409、部分完成实际量、显式纠错历史 |
| A07 | PASS（隔离）：显式同事实一笔结算、版本/UUID；真实双设备/PG竞争 NOT_RUN，差额策略关闭 |
| A08 | PASS（隔离）：确切问答、跳过、双答冲突、原文新版/迟到结果拒绝、恢复与旧来源快照 |
| A09 | PASS（隔离）：事件/日记分别按日期集合去重；正式坚持奖励口径仍未选择 |
| A10 | PASS（隔离）：语义身份重命名防重、规则未配置拒领、领取重放、当前证据核实；真实PG领取↔删除竞争 NOT_RUN |
| A11 | PASS（隔离）：长中文/换行/HTML/CSV攻击样例、未回答问题、本人完整JSON与旧投影、含新实体源库安全拒绝且源哈希不变 |
| A12 | PASS（隔离）：直接注册开关、邮箱服务缺失/单次绑定/找回、改密撤销与旧码失效；真实邮件与PG并发 NOT_RUN |
| A13 | PASS（隔离）：普通用户直调管理拒绝、管理不读他人日记、唯一管理人保护、合法返回与停用后业务锁拒绝；真实PG竞争 NOT_RUN |
| A14 | 原财务回执/双击/未知恢复回归与真实Vue弹窗 PASS；完整真实PG交易恢复组合 NOT_RUN |
| A15 | 四档宽度、200%字号、键盘/焦点及新日记/计划/管理/长身份检查 PASS；软键盘/触摸实机 NOT_RUN |
| A16 | SQLite 原子故障回归及新增主线奖励写失败完整回滚 PASS；PG确认↔撤销/规则更新竞争 NOT_RUN |
| A17 | NOT_RUN：仍无 Docker/pg_ctl/独立 PG，新秘密 LF/CRLF 认证待验证；未触碰既有库/卷 |

## 配置、迁移与回退说明

1. 本地沿用启动前备份与轻量迁移；cloud 必须显式升级 b005 → b006_diary → b007_plans → b008_accounts → b009_policies。本批仅对合成 SQLite 验证迁移；未连接真实云库。发布前补独立 PG 升级、约束、预算和竞争测试。
2. 默认部署不增加秘密文件要求。可选 `deploy/compose.hosted.yml` 仅挂独立 hosted-ai.json（secret_ref→Key）；`deploy/compose.mail.yml` 仅挂 SMTP mail-password 并传非秘密邮件设置。两者需运营者明确叠加使用，不会自行开启数据库中的服务策略。[Docker 官方合并规则](https://docs.docker.com/reference/compose-file/merge/)说明环境映射及 secrets 按目标合并；本机无 Docker，叠加文件的 config/容器实测 NOT_RUN。
3. 邮件使用 SMTP_SSL；部署叠加使用 MAIL_PASSWORD_FILE，兼容本地服务端 MAIL_PASSWORD。不要将真实秘密放入文档、浏览器或普通站点设置。HOSTED_SECRET_FILE 与个人加密凭据文件分别保管。新增可选设置见 `.env.production.example` 注释；不需启用这些服务即可使用记录/自配模型。
4. 回退优先保留新表/列，关闭条件策略并前向修复；旧代码可忽略大部分新增列，但已使用新实体后不应直接降级删除。先获得一致备份并验证恢复；历史原文、问答、账本、结算身份和回执不能丢弃或重新发奖。各新 revision 的 downgrade 明确拒绝自动删历史。
5. 本批只做本地中文提交；未 push、构建云包、部署、迁移真实数据、开通默认模型、发送真实通知或邮件。工作区原有用户文档不纳入提交。


阶段代码提交：P2 `45d0d11`、P3 `aeb3601`、P4 `ba0d8dd`、P5 `38fb40b`、P6 `6bccedd`。截图复核另增断言并修正缩放时序，不覆盖原 P1 证据。


### 本地队列兼容补验

新回顾在 cloud/local 都使用持久队列。cloud 保持原 compose worker；本地先启动 API，使其按原流程备份并补齐结构，再显式运行 `.venv\Scripts\python.exe -m app.worker --local`（单实例 worker）。只保存/回看不需要 worker，生成辅助问题与回顾需要 worker 持续运行。本地 worker 启动只读检查结构，缺表/列即拒绝，不代替 API 备份/迁移。本地轻量升级另补日记身份与邮箱的唯一索引，旧值保留 NULL；如有重复则安全失败，不合并或删除数据。

任务/新问答/邮箱令牌采用两种模式都明确 UTC 的时间类型；旧 Event/Profile/挑战的本地时间解释保持原样，不改写历史时间。租约不会再因 SQLite 本地返回无偏移时间而比较失败，本地模型组版本也纳入写回快照。定向验证了缺结构拒绝且无自动建表、真实队列 claim/process 的本地 UTC 租约与完整回顾写回；真实本地供应商仍 NOT_RUN。首轮 UTC 类型方法归属错误造成回归失败，修正后完整报告以上述最终结果为准。
