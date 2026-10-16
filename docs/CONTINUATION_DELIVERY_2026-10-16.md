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

API：auth/options、auth/password；auth/email/{register-request,bind-request,verify,recover-request,reset-password}；admin/{overview,users,users/:id/status,announcements,site,audit}。沿用原 Session/Origin/CSRF；邮箱公开验证凭单次随机令牌，不返回原令牌。邮件默认显式 503，只有配置 SMTP_SSL（MAIL_HOST/PORT/FROM/USERNAME/PASSWORD）才尝试投递；测试适配器仅在测试注入。邮件服务真实投递 NOT_RUN。

owner 映射为本轮管理能力，普通 user 服务端拒绝。管理五区和账号安全拥有独立 Vue 导航/返回，生产无本地改 role 按钮。管理只读账号元数据和操作记录，不提供他人日记/Key、改账/提权/删除接口；不能停用唯一管理人或当前自己。停用撤销认证会话，后台模型写回再次检查账号状态。受控 manage_auth_sessions 标记仅允许已鉴权管理动作撤销目标认证会话，其他业务查询仍绑定管理人本人，不解除日记归属过滤。

管理动作有版本/UUID/审计/回执及同事务写入；PG 全局管理 advisory lock 串行唯一管理人和站点策略判断。认证改密/恢复沿用 User 行锁及安全版本/单次令牌语义，不把密码或邮箱令牌明文保存到浏览器恢复缓存/普通写回执。

验证：续作与迁移 11 PASS（包括普通用户直调拒绝、管理不读朋友日记、注册开关、唯一管理人、邮箱不可发送、绑定/找回重放和改密撤销），编译 PASS；真实 Vue 浏览器累计 23 PASS，包括独立管理五区与账号安全返回、未配置邮件反馈和390/1440布局。PG 并发/真实 SMTP/手机实机 NOT_RUN。
