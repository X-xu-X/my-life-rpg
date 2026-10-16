# 私有试用修正：P1 交付记录

日期：2026-10-16。开发基线：`ba7031e96a9c91a667eaeb28b4a0a4606f5f8a15`。

依据 [Writer 任务书](WRITER_TRIAL_FIX_2026-10-16.md)“先做 P1，可独立交付”执行。本批完成现有应用的 P1 修复；E 的初始化 SQL 已修改，真实 PG 验证未执行。P2～P6 尚未实现。本记录补充实施状态，不覆盖工作区已有的总计划、规格或用户文档。

## 1. 反馈与实际行为

| 反馈 | 本批结果 | 主要文件 |
| --- | --- | --- |
| F01～F04/F16 | 主辅组展示准确已保存供应商、模型、版本、启用状态及版本化验证；我的页提供摘要。保存不调用模型，未保存表单不能测试。错误分类脱敏、就近显示；换配置或测试中编辑不会把旧结果标为当前通过 | `ModelSettings.vue`、`MyView.vue`、`settings.py`、`credentials.py`、`model_validation.py`、`model_errors.py` |
| F05/F09/F14 | 详情只读轮询活动任务；终态、离页、隐藏、切账号停止或忽略旧请求。晚完成后重读判定，保留编辑/补充草稿；已有模型时取消重复绑定提示 | `RecordDetail.vue`、`api.js` |
| F06/F07 | 默认本人时区当天、日期精度；其他日期和精确时刻折叠。普通新记录走现有 `source=form` 单事件入口，提示词只问事件相关事实，信息充分可不追问 | `RecordComposer.vue`、`events.py`、`schemas/__init__.py`、`prompts/judge.py`、`session.js` |
| F10 | 取消模型“已合并”表述，界面显示“疑似关联 · 尚未确认”；不物理合并原文或修改旧账 | `prompts/judge.py`、`JudgmentList.vue`。正式关系确认、引用校验和新结算属于 P2/P3、受 D03 约束，未实现 |
| F11 | 未评估/中性基线显示“未评估基线”，保留 13×50 和已评估画像 | `AttributePanel.vue` |
| F13/F15/F18/F20 | 今天/手账/计划/成长/我的五区导航；保留旧路由。长金额/模型可换行，手机图表标签留白、全量数值列表；底栏适应放大文字。兑换使用页面内对话框，支持取消、焦点进入/约束/恢复 | `App.vue`、`router.js`、`PlansView.vue`、`ui-layout.css`、`ConfirmDialog.vue`、`ChallengeView.vue` |
| F34 | 普通二级页全局返回，使用当前账号、本应用、同工作区的合法来源；直接进入有所属主区兜底，返回不退出。管理工作区仅预留导航元数据约束，无管理界面/接口上线 | `navigation.js`、`App.vue`、`router.js` |

`PlansView` 本批组织现有目标、旧打卡项目和数量，保留 daily/weekly/none 的原语义。指定周几、间隔日、当次三结果、晚间日记、完整问答会话不在本批实现范围，不能以新增“计划”导航视为这些能力完成。

兑换继续调用原 `useRedemption`，保留 UUID、物品版本、原请求正文、回执和未知结果恢复。弹窗取消不发送交易；确认双击只发一次。奖励券兑现仍调用原接口，不增加第二次扣币。

## 2. 最小数据/API 合约与兼容

新迁移 `b005_trial_p1`，父版本 `b004_reports`；不修改旧 revision：

| 实体 | 增量 | 旧数据策略 |
| --- | --- | --- |
| Event | 可空 `occurred_on: VARCHAR(10)`、`time_precision: VARCHAR(10)` | 不猜测回填旧时间精度/分类；旧发生时间保持。日期精度用当日本地零点的 UTC 边界锚定旧查询，显示仅日期，不宣称该锚点是实际发生时刻 |
| AIJudgment | 可空 `model_provenance: JSON` | 新分析记录安全的 provider/model/config_version/source；旧结果不补猜来源。每次审计 payload 保存当次来源快照，不跟随以后设置改变 |
| Setting | `llm_validation_primary/aux` 私有 JSON 值 | 保存组、配置版本、状态、时间及受控错误；不含 Key、供应商原始异常或正文，不纳入用户导出 |

cloud 必须显式执行 Alembic 升级；本批未连接/升级真实库。本地沿用现有 `migrate_schema` 添加兼容列。新字段没有默认值，不触发旧画像/账目回填。

- `GET /api/llm-config`：增加 source、config_version、validation。已停用与验证状态分别表达，GET 不调用模型。
- `PUT /api/llm-config`：原保留/替换/清除密钥及换供应商重绑规则保留；模型 ID 拒绝空白/控制字符，每次保存递增版本，旧验证失效。
- `POST /api/llm-config/test`：只接受 `{group, expected_config_version}`。旧 group-only 或携带未保存字段返回 422 并提示刷新；版本冲突返回 409。短事务内读取同一版本配置，释放事务后执行有界聊天请求，再短事务复查版本、保存结果。返回 passed/failed、provider/model/version、tested_at、安全错误与 retryable；聊天通过不保证 JSON 分析质量。
- `POST /api/events`：可发送日期精度的 occurred_on，或分钟精度的 occurred_at；日期/时间矛盾返回 422。旧客户端省略新字段时保持原 UUID 指纹，升级前未完成请求可继续查回执。旧时间编辑客户端修改 occurred_at 时清空新精度元数据，避免留下过时日期。
- `GET /api/events/:id`、judgments、pending、analysis-jobs：详情同步复用现有只读 API，不重复提交分析。排队/运行中约 2.5 秒刷新，终态重读一次后停止。
- JSON 导出保留 v3 和既有白名单；Event/AIJudgment 新列随原实体导出，旧事件投影补充日期/精度。没有新增导出实体或泄露模型凭据。新可读格式留待 P4。

`source=form` 是现有自由输入来源，不是本批新增的 record_kind；旧 journal 不重分类、不拼接、不重算日数或金币。独立 event/diary 类型由 P2 明确实现。

## 3. 真实验证结果

测试只用合成账户、临时 SQLite、模型替身及浏览器 API mock。未读取真实旧数据库、未使用真实 Key/调用模型或邮件。没有 push、云包构建或服务器部署。

| 命令/证据 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -B -m tests.run_trial_p1_checks` | 69 项运行：67 PASS、2 SKIP、0 FAIL/ERROR | 真实 PG 并发及导入用例跳过；不计入通过 |
| `node tests/frontend_next.mjs` | PASS | 账号切换取消/迟到包、草稿隔离、保存双击/丢响应恢复、补充队列与版本冲突参数 |
| `npm.cmd run build`（frontend） | PASS | Vite 仍提示 ECharts 大块约 544 KB；编译无错误 |
| `node tests/browser_trial_p1.mjs`（真实编译 Vue + 隔离 Edge） | 43 项 PASS、0 运行异常、0 未覆盖 API 请求 | 360/390/768/1440 五页、返回、配置编辑/失败/迟到结果、无 Key 保存、任务终态/离页停刷新、弹窗键盘/焦点/取消/双击、200% 字号 |
| `git diff --check` | PASS | LF/CRLF 提示不属于空白错误 |
| 独立 PostgreSQL/新秘密初始化 A17 | NOT_RUN | 本机没有 Docker/pg_ctl/可用隔离 PG；没有用 SQLite 或字符串替身冒充 PG 验证 |
| 真实供应商行为质量、实机手机软键盘、真实邮箱、生产部署 | NOT_RUN | 浏览器尺寸模拟不等于实机/生产验收 |

后端 HTTP 测试在普通沙箱内曾停于 asyncio 本机 socketpair 建立阶段；已用故障栈定位，获自动审批后在沙箱外执行隔离测试。浏览器也仅启动独立用户目录和本机随机端口，拦截外部请求，不使用用户常用 Edge 配置。

可追溯证据：[后端结果](review/trial_p1_2026-10-16/test-results.json)、[详细日志](review/trial_p1_2026-10-16/test-log.txt)、[浏览器结果与构建 SHA-256](review/trial_p1_2026-10-16/browser-results.json)。截图均为虚构数据：

- [桌面今天](review/trial_p1_2026-10-16/today-1440.png)、[手机今天](review/trial_p1_2026-10-16/today-390.png)
- [桌面配置](review/trial_p1_2026-10-16/settings-1440.png)、[手机配置](review/trial_p1_2026-10-16/settings-390.png)、[失败反馈](review/trial_p1_2026-10-16/model-failure.png)
- [手机雷达图](review/trial_p1_2026-10-16/radar-390.png)、[兑换弹窗](review/trial_p1_2026-10-16/redeem-modal-390.png)、[200% 字号](review/trial_p1_2026-10-16/settings-200-percent.png)

### A01～A17 场景状态

| ID | 状态及覆盖边界 |
| --- | --- |
| A01 | PASS（合成后端+浏览器）：保存不请求、失败分类、未保存输入、测试中变更版本拒绝/变更表单不冒充验证 |
| A02 | 部分 PASS：无 Key 保存/回看、受控超时/限流、既有取消/租约回归；独立新日记 P2 未实现，真实供应商 NOT_RUN |
| A03 | 提示词已修改；真实模型对部署/睡眠/同日运动的相关追问质量 NOT_RUN，不以替身结果判质量通过 |
| A04 | 部分 PASS：任务晚完成/终态/离页浏览器、worker 取消/配置变更/迟到写回及通用账号迟到包回归；未逐一浏览器演练所有失败/取消/切账号组合 |
| A05～A10 | 本批未实现新计划、关系结算、回顾问答、日数和动态授奖；旧规则回归通过不算新场景通过 |
| A11 | 部分 PASS：现有本人 JSON 导出、秘密排除与用户隔离回归；可读导出、问答与完整新格式安全矩阵留 P4 |
| A12～A13 | 新注册邮箱/管理模块未实现。仅普通二级返回及既有认证/隔离回归，不算管理场景通过 |
| A14 | 部分 PASS：真实 Vue 弹窗取消/双击、既有回执/版本回归；真实 PG 竞争和完整浏览器丢响应/跨账号兑换恢复组合 NOT_RUN |
| A15 | 部分 PASS：四档宽度、200% 字号、Tab/焦点、长金额/模型及雷达图人工复核；实机软键盘 NOT_RUN |
| A16 | 部分 PASS：SQLite 故障注入/原子回滚与既有服务回归；独立 PG 竞争 NOT_RUN |
| A17 | NOT_RUN：SQL 代码已修改，真实新库认证与安全失败验证待隔离 PG 环境 |

## 4. 工程 E 与使用边界

独立中文提交：`2155c46`。`deploy/init-app-role.sql` 改为明确剥离秘密两端空格/tab/CR/LF，再要求 24～256 个可见 ASCII 字符、无内部空白。继续使用 `%L` SQL literal；格式错误给受控错误，CREATE ROLE 异常统一安全消息，避免原始异常暴露秘密。

仅影响新空卷初始化。不对已有库执行 ALTER ROLE，不改现有密码，不删除卷、不重新初始化。A17 必须在独立 PG 新库验证 LF、CRLF、非法长度/内部空白及合法秘密认证后，才能将 E 标为验收通过。当前没有该环境，E 交付状态为“代码完成，验收未运行”。

## 5. 指南来源与使用说明

设置页按“选择供应商 → 控制台建 Key → 核对准确模型 ID/价格 → 保存并启用 → 主动测试”说明。保存不会联网；主动测试/分析可能计费。主辅沿用既有回退规则，不开启站点共享 AI，不使用 owner Key。

2026-10-16 核对官方资料，使用 `openai-docs` 技能核对 OpenAI 官方入口：

- [OpenAI 模型](https://developers.openai.com/api/docs/models)、[价格](https://developers.openai.com/api/docs/pricing)、[Key 控制台](https://platform.openai.com/api-keys)。控制台需登录，公开抓取未返回正文。
- [DeepSeek 官方模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)。Key 控制台抓取失败，不宣称已成功验证登录后的控制台。
- [SiliconFlow 官方快速开始](https://docs.siliconflow.cn/docs/userguide/quickstart)。旧文档入口重定向至此；模型控制台抓取失败，需用户账号实际核对权限/价格。

没有写死模型价格、赠送额度或永久免费承诺；网页聊天免费与免费 API 分别说明。用户后续可先保存配置，再测试已保存版本；连通通过仅代表该时间点聊天请求成功。

## 6. 剩余工作、风险与回退

D01～D11 均未由本批自行决策。D01/D02 日期统计与旧分类、D03 同事实结算、D04 邮箱策略、D05 主线经济、D06 默认 AI 预算、D07 计划更正、D08 动态奖励、D09 清单、D10 导出默认组合、D11 管理范围继续待定。对应新功能保持未实现/未启用，现有旧功能保留。

下一批 P2 先补 event/diary 明确类型、独立原文与问答实体、可恢复会话及版本快照；P3 再做日程/当次结果与结算身份。只对依赖未决项的路径停用，不把候选金额或原型值写入生产。

发布前需在独立 PG 验证 b005 升级与竞争、A17 新秘密认证，按正常流程备份/评审迁移。本批只做本地中文提交，未推送或构建云包。工作区此前的用户文档修改均保留且不纳入本批提交。

回退应用代码前先核对数据库兼容；旧代码可忽略新增可空列。已有新日期/来源写入后，优先保留新增列并前向修复，不直接降级删列导致元数据丢失。现有账本、原文和回执不得回算/清理。
