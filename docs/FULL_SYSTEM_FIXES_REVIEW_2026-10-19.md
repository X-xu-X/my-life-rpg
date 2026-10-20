# LifeXP 五项修复独立复审 · 2026-10-19

对照 [上轮独立审查](FULL_SYSTEM_REVIEW_2026-10-19.md)、[修复交付](FULL_SYSTEM_FIXES_DELIVERY_2026-10-19.md) 和 [完整开发规格](FULL_SYSTEM_DEV_SPEC_2026-10-18.md)。审查当前 `ec5259b` 之上的未提交工作区；修复 manifest 中 128 个源码文件及所列文档、证据哈希均吻合。独立测试、构建和补充复现存入新目录，未覆盖 Writer 或上一轮审查证据。

## 结论

上轮五个原始复现场景均已通过；N01、N02、N04、N05 可以关闭原问题，N03 的新建计划及常规历史快照链路已修好，但补查的旧日程兼容边界仍有一项 P2，需要补修。未发现原隐私名称泄漏或未建档领取 500 再次出现。

本轮仅新增审查材料，没有修改正式代码、部署、提交、推送、访问真实旧库或调用真实模型／邮件。审查前后 229 个 app、前端源码、测试与迁移文件哈希未变化，见 [源码比对](review/full_system_fixes_review_2026-10-19/source-comparison.json)。

## R01 [P2] 无历史快照的旧日程未来改时长后，今天的计时入口失效

定位：[plans.py:100](../app/routers/plans.py:100)，关联 [timing_snapshot 回退](../app/routers/plans.py:61) 和 [计时启动校验](../app/routers/timers.py:47)。影响 N03 的旧日程兼容及未来生效约定。

**前提必须明确：** 日程 `history=[]` 且旧 rule 没有 `planned_minutes`。这是本轮交付声明支持、且 `test_N03_legacy_default_duration_validation_and_old_receipt_replay` 本身构造的旧结构，不是普通新建日程的普遍故障。本次没有检查真实旧库，因此不声称用户现有账号已经受影响。

独立复现：

1. 创建合成旧日程，上述旧结构读取 `/api/plan-schedules` 时，`timing.planned_minutes=30`，当天仍有效。
2. PUT 修改为 45 分钟，生效日为明天，返回 200。
3. 再读同一日程，`history` 只有明天生效的 v2，`timing=null`。
4. 当天携带当前 `source_version=2` 启动该计划计时，返回 409：`此计划尚未生效或已经停用。` 前端同时会过滤掉 `timing=null` 的计时按钮。

原因：编辑时仅把新版本追加到空历史，同时覆盖当前 rule；原本用于无历史日程的回退要求 `not row.history`，编辑后已不成立。新设置尚未到生效日，旧的当天快照却无法再找到。

建议在首次编辑这种旧记录时，先保留原有效 rule／名称／启用状态及版本快照，再追加未来版本；避免仅在读取层用新 rule 猜旧值。补充验收：未来修改前后今天仍为 30 分钟，明天新启动为 45 分钟；已开始会话保持原合同，原 UUID 重放不重复新增历史。

证据：[独立边界脚本](review/full_system_fixes_review_2026-10-19/boundary-probes.py)、[完整接口结果](review/full_system_fixes_review_2026-10-19/boundary-results.json)。

## 原问题逐项核验

| 原编号 | 本轮独立结果 | 判定 |
| --- | --- | --- |
| N01 旧清单名称绕过许可 | 原 sentinel 不再出现在模型消息，保留匿名状态计数。定向回归覆盖缺省／关闭／授权配置及日记回顾／事实分析，旧原名称本人仍可导出。 | 原问题通过 |
| N02 关闭历史仍导出旧原文 | 原 JSON 复现中 `diary_revisions=[]`，整个响应无旧原文；四格式、历史问答／分析／片段及游戏附件组合回归通过。 | 原问题通过 |
| N03 计划时长固定 30 分钟 | 独立创建 45 分钟得到 2700 秒；20／45 分钟、版本冲突、未来生效、刷新和既有会话快照回归通过。 | 常规链路通过；R01 旧结构边界待修 |
| N04 未建档首记领取 500 | 独立调用返回受控 409；中性建档后重试成功，余额 83；回归还覆盖节日、成就、事实与计时结算，资格及流水未提前改变。 | 原问题通过 |
| N05 定价看不到实际使用量 | 相同购买背景下 3600／10800 秒的完整模型消息现在不同；定向回归验证未用券为零、计划及窗口外计时排除、修正值和近两周趋势。 | 数据与 prompt 修复通过；真实价格质量未验 |

原始五场景的独立复跑：[脚本](review/full_system_fixes_review_2026-10-19/probes.py)、[结果](review/full_system_fixes_review_2026-10-19/probe-results.json)。计划启动已按新契约补上来源版本；没有用旧缺版本请求误判新实现。

## 独立验证与限制

- 后端七模块：127 项，**125 PASS、2 SKIP、0 FAIL／ERROR**。[结果](review/full_system_fixes_review_2026-10-19/backend-results.json)、[日志](review/full_system_fixes_review_2026-10-19/backend-tests.log)。两项为真实 PostgreSQL 并发／导入测试；使用临时合成 SQLite、假模型，不运行真实应用 lifespan。
- 当前 Vue 独立目录构建通过，图表约 546KB chunk 提示仍在。[构建日志](review/full_system_fixes_review_2026-10-19/frontend-build.log)。
- 新编译 Vue／隔离隐藏 Edge：**82 项 PASS**，无运行错误或未识别 API；包含 1440／390 宽度、45 分钟保存及恢复、未建档首记引导和四格式下载。[结果与哈希](review/full_system_fixes_review_2026-10-19/browser/browser-results.json)。API 全部合成，不把浏览器测试冒充真实前后端联调；45 分钟恢复截图已目视检查。
- 额外边界探针复现 R01。另核对 CSV：无回顾会话的日记即使 `include_history=true` 也不包含旧原文，JSON／Markdown／HTML 会包含。当前页面已明确说明 CSV 不含原文历史，因此本轮不作为新增产品缺陷；交付报告“四格式打开历史可读旧原文”的措辞应按此收窄，已有测试包含旧会话，不能证明 CSV 真正导出了原稿 revisions。
- 真实 PostgreSQL、供应商模型语义／定价、SMTP 收件、手机软键盘／后台，以及真实旧数据迁移仍未验。跨午夜用量按已确认结算日汇总的现行口径已由交付报告说明，本轮不把它误报成按实际跨日秒数分摊。

建议只针对 R01 继续修复并补回归，然后再进行既定的真实环境验收，无需重做五项修复。
