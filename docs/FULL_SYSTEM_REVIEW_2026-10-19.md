# LifeXP 最新开发独立审查 · 2026-10-19

对照：[完整系统开发规格](FULL_SYSTEM_DEV_SPEC_2026-10-18.md)、[Writer 任务书](WRITER_FULL_SYSTEM_2026-10-18.md)、[本次交付报告](FULL_SYSTEM_DELIVERY_2026-10-18.md)。

审查对象是 `ec5259b` 之上的**当前未提交工作区**，不是只看 Git HEAD。Writer 交付清单中的 126 个源码文件 SHA256 与当前文件全部一致，见 [比对结果](review/full_system_2026-10-19/source-comparison.json)。以下问题属于这份已交付实现，不是交付后源码漂移造成。

## 结论

主要功能已实际落到 FastAPI、worker、Vue 和迁移中；日记多事实、个人许可、清单、计时、问卷、试用经济等不是仅有 Demo。但本次独立复现 **5 项需要修正的问题（1 项 P1、4 项 P2）**，因此不能把对应需求判为完全完成，也不应直接进入正式发布。

建议把下列 N01～N05 交 Writer 定向补修，并修正交付报告相应的“已实现”范围；不需要重做整个系统，也不需要重新讨论已批准金额。

本次只读审查产品代码，新增独立审查脚本／日志／截图和本报告；未修正式程序、改规则、登录云端、发送真实邮件、调用真实模型或操作真实旧库。Writer 原交付证据未覆盖。

## N01 [P1] 旧生活清单名称绕过新的 AI 许可

定位：[review_context.py:20](../app/services/review_context.py:20)。影响 D02／D04／C03。

新 `CareConfig.ai_allowed` 对 `focus_items` 名称有过滤，但同一上下文又直接加入旧 `LifeChecklist.payload.entries`。这个 map 的 key 是用户输入的项目名称，不能一律视为不含内容的状态元数据。旧接口允许任意至多 80 字的 key，也没有项目名称的 AI 授权；即使旧清单 `enabled=false`，仍完整进入日记回顾 payload。

独立复现：

1. 合成账号没有开启新清单名称授权（`care_config=null`）。
2. `PUT /api/life-checklists/{day}` 保存 `enabled=false`、`entries={"PRIVATE_FOCUS_SENTINEL":"skipped"}`，返回 200。
3. 保存一篇允许分析的普通日记，启动辅助回顾，截获假模型实际收到的消息。
4. 消息的 `checklist.entries` 含完整 `PRIVATE_FOCUS_SENTINEL`；`focus_items` 虽为空，不能阻止这条旁路。

这里证明的是**未授权名称进入模型待发送内容**，不是声称已经向真实供应商发送。新清单正常名称许可和普通私密正文测试通过，不能据此推断旧兼容路径也安全。旧项目若包含个人健康或其他敏感关注主题，这些文字会被带入回顾。

修复：旧清单兼容数据也必须遵守名称许可。无授权时只使用必要的稳定身份／状态来抑制重复提问，或先完成显式映射与授权；不能原样发送任意 key。加入关闭旧清单、无新配置、未授权自定义名称及日记／逐事实回顾两条入口的出站 payload 回归。

## N02 [P2] JSON 取消“包含历史”后，仍包含旧日记原文

定位：[export.py:195](../app/routers/export.py:195)，以及 [export.py:199](../app/routers/export.py:199)。影响 X01／V20。

`readable_export.select()` 尊重 `include_history=false`，所以导出的 `records[].revisions` 为空；但 JSON 的 `tables` 来自全量 `_collect()`，后面只按所选事件 ID 过滤 `diary_revisions`，没有应用历史开关。用户选择看似生效，实际文件里仍藏着旧原稿。

独立复现：先保存私密日记 v1=`OLD_DIARY_HISTORY_SENTINEL`，再保存 v2=`当前版本原文`，然后请求：

```text
GET /api/export?format=json&kind=diary&include_history=false&include_game=false
```

返回 200；`records[0].revisions=[]`，但 `tables.diary_revisions` 同时有 v1／v2，完整响应仍含旧正文。相同选项的 Markdown 不含旧正文，说明这是 JSON 两份投影过滤不一致，不能解释成用户选了“所有游戏历史”。

修复：用同一选择规则生成 JSON 的记录与表附件，不要在过滤后又挂回全量历史。顺带核对旧分析／会话等历史表的同一开关。增加 JSON／Markdown／HTML／CSV 对照，取消历史时检查整个响应，而非只检查 `records` 子树。

## N03 [P2] 计划不能设置预计分钟数，页面启动一律使用 30 分钟

定位：[PlanAgenda.vue:9](../frontend/src/components/PlanAgenda.vue:9)、[plans.py:17](../app/routers/plans.py:17)、[TimerView.vue:12](../frontend/src/components/TimerView.vue:12)、[timers.py:22](../app/routers/timers.py:22)。影响完整 Demo 的计划时长／P01／T01。

已确认 Demo 可以创建“英语阅读 45 分钟”等计划。正式日程表单及 `ScheduleIn` 没有预计时长字段；计时页面调用 `/timers` 时只传计划 ID，没有 `planned_minutes`，服务端因此使用默认 30。后台虽然接受计时请求上的 `planned_minutes`，实际页面没有让用户提供或从计划带入的路径。

独立复现：

- 创建日程并带 `planned_minutes=45`，返回 422 `extra_forbidden`；schema 和保存 rule 均没有其他时长字段。
- 创建名称为“英语学习45分钟”的普通日程成功，但 rule 没有时长。
- 按当前页面请求格式开始该计划，返回 `limit_seconds=1800`，而不是 2700。

修复：日程及其历史快照保存用户设定的预计时长，计划卡片／计时入口展示并携带；服务端校验本人计划和版本。若允许本次临时调整，应有清楚入口并保存本次快照，不能只在隐藏 API 参数中支持。补 20／45 分钟计划、修改未来计划但不改旧会话、刷新恢复验收。

## N04 [P2] 未建档账号可以点首记领奖，但得到服务器 500

定位：[trial.py:60](../app/routers/trial.py:60)、[trial.py:61](../app/routers/trial.py:61)，既有保护在 [coin_service.py:91](../app/services/coin_service.py:91)。影响 D03／E01 的新用户路径。

允许未建档用户先记录是正确的。当前首页也允许其采用试用规则，记录后出现首记领取按钮；领取路由未把“尚未选择角色基线”作为可恢复的业务状态处理，直接调用资金服务。底层保护抛出的 `ValueError` 没有转换，用户得到通用 500。

独立复现：新账号尚未建档 → `PUT /trial` 200 → 保存第一条事件成功 → `POST /trial/first-record/claim` 返回 **500 Internal Server Error**。底层错误为“记录已保存；游戏结算前请先选择角色基线。”随后选择中性基线仍能成功，余额为 80；本次没有观察到错误发币，不将其夸大为账目损坏。

修复：保留首记资格，未建档时显示建档入口／明确说明；后端在修改领取状态前返回受控的 409 等业务响应，禁止向用户暴露 500。补“先记后建档再领”、重复点击、失败不消耗资格，以及其他新发币入口的同类前置条件测试。

## N05 [P2] 定价没有收到实际娱乐用量，仍主要按购买次数引导涨价

定位：[shop_service.py:85](../app/services/shop_service.py:85)、[shop_service.py:87](../app/services/shop_service.py:87)、[shop.py:32](../app/prompts/shop.py:32)。影响 E02／V15。

新逻辑已经区分“买券”和“标记兑现”，但定价消息仅补了“已结束多少段计时”。没有传实际秒数、使用日期分布、娱乐与计划分类；计时数量查询也没有近 30 天限制。原 system prompt 仍明确按“近 30 天已兑换同类多次”要求提高价格。这不足以实现用户确认的“买很多券不等于已经玩很多，要根据近期实际使用”的判断。

独立复现：同一份购买／余额／阶段背景、同一张已兑现娱乐券，历史实际使用分别为 3600 秒和 10800 秒。两次请求价格建议都返回 200，但截获的**完整模型消息完全相同**：只看到购买一张、兑现一张、结束一段，没有一小时／三小时的区别。

这不表示两个场景必须给不同价格；它证明当前模型根本没有得到区分两者的用量信息，不能把所缺数据归因于真实模型质量未测。

修复：提供有界窗口内的实际娱乐使用汇总（与购买记录分开，至少包含用量及日期分布／近期频率），区分计划计时，按当前已确认的修正后结算值汇总；同步更新旧 prompt，不能只追加一句“购买不等于使用”却仍按购买次数强制涨价。补多买未用、分天使用、近期高用量后回落、计划计时不影响娱乐定价的 payload 测试，再做真实模型建议质量验收。

## 已独立验证的范围

| 项目 | 本次结果与证据 | 说明 |
| --- | --- | --- |
| 源码一致性 | [126 文件哈希一致](review/full_system_2026-10-19/source-comparison.json) | 比对 Writer 交付 manifest；没有源码漂移 |
| 后端选定回归合集 | [121 项运行：119 PASS、2 SKIP、0 FAIL／ERROR](review/full_system_2026-10-19/backend-results.json)，[日志](review/full_system_2026-10-19/backend-tests.log) | 重跑 Writer 的六模块合集，不冒称整个仓库所有测试 |
| 前端构建 | Vite build PASS，640 模块；输出到本次独立 `frontend-dist` | 仍有约 546KB 图表 chunk 提示，不是失败，也不是新增功能缺陷 |
| 编译 Vue 浏览器检查 | [76 项 PASS](review/full_system_2026-10-19/browser/browser-results.json) | 复用原浏览器检查，在本次新构建上独立执行；API 合成，不能替代真实前后端联调 |
| 新增定向复现 | [5 项具体结果](review/full_system_2026-10-19/probe-results.json)、[复现脚本](review/full_system_2026-10-19/probes.py) | 隔离 SQLite、合成账号／数据，模型消息由替身截获，未发送真实信息 |
| 目视抽查 | [手机首页](review/full_system_2026-10-19/browser/today-390.png)、[桌面计划](review/full_system_2026-10-19/browser/plans-1440.png) | 基础布局可用；截图中的固定 API 日期属于合成夹具，不作为真实日界证据 |

已有回归全部通过与本次发现不矛盾：已有测试未覆盖这些具体分支。例如问卷／资金测试先建档再采用试用规则，导出检查未验证关历史后的整个 JSON，计划计时用例仅验证了固定 30 分钟路径。应加针对行为的回归，不能修改已有断言来隐去缺口。

## 完成情况与交付报告需要校正的地方

- **已有主要实现，相关基础检查通过**：原文版本与任务、逐事实结算及原子回滚、跨来源防重、自建清单／零项、排期和目标、问卷、中性建档、试用数值／节日／成就、两张券余额独立、找回异步队列、管理／反馈及四格式下载。该结论限于本次代码抽查和合成检查范围，不保证所有组合均无缺陷。
- **需补修后再标完成**：D02／C03 的旧清单路径，P01／T01 的计划时长，D03／E01 的未建档领取路径，E02 的真实用量上下文，X01 的 JSON 历史选择。交付报告对应行应增加这些欠项。
- **外部验收未完成，原因独立于代码缺口**：独立 PostgreSQL 迁移／双连接竞争（本次两项仍 SKIP）、真实模型语义与定价、真实 SMTP 投递／收取、手机实机／软键盘／后台行为。补 b010～b024 的实际目标环境验收；不能用 SQLite 或模拟截图替代。
- **按决定暂缓，属于合理范围控制**：通用聊天、站点托管默认 AI、大规模 RAG、复杂预约分期、App／小程序、社交登录／推送、完整恢复导入、真实旧库迁移和云端发布。没有因这次审查授权启用它们。

建议顺序：先修 N01、N02 的数据范围问题，再补 N03～N05 的日常使用路径；针对五项加回归后再复验本地实现，随后另行准备真实 PG／模型／邮件／手机与云端发布验收。
