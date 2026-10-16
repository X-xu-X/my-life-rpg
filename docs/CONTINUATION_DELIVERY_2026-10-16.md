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
