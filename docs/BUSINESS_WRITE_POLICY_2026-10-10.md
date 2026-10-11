# 本轮业务写路由与验证策略

实际清单由 `python ops/route_inventory.py docs/review/RELEASE_ROUTE_INVENTORY_2026-10-10.json` 生成：99 个 method/path，55 个业务写入口。生成器同时处理当前锁定 FastAPI 的延迟 include 路由。JSON 中 direct_* 是路由函数的直接调用标记，不能据此推断服务层没有锁。下表补充调用链的人工核对。

云端共用认证、Origin/CSRF 和绑定 user_id 的 Session；查询过滤与 before_flush 外键归属保护并用。运维导入 Session 不绑定业务账号，使用独立目标校验。锁顺序为用户 profile → 资源/任务 → 属性/余额；认证登录与恢复使用 User 行锁串行，模型实际请求另取全局 PG advisory lock。

| 路由族 | 归属、重放和版本策略 | 事务及模型边界 | 实际验证 |
|---|---|---|---|
| events POST | 用户＋客户端 UUID，输入指纹冲突 409；回执查询 | 原文及回执同提交，不请求模型 | 保存重复、响应未知、双账号、2 万字浏览器 |
| events PUT/DELETE | 内容版本；删除 UUID 回执；已入账冻结编辑 | profile 锁；按真实属性流水反向；金币不回滚；删除与回执同提交 | 确认↔删除竞争，故障回滚，旧规则回归 |
| judgments confirm | 时间版本＋UUID＋指纹；跨用户 404 | 属性、日志、金币、回执同提交 | 三处注入失败；PG 确认↔删除 |
| judgments achievement | 时间版本＋UUID；成就 code 唯一；已处理建议不重授 | profile→事件；授币及建议标记、回执同提交 | PG 追授↔删除；双账号 |
| judgments supplement/dispute、events judge | cloud旧同步入口409；前端改用后台任务；未确认结果才可改，confirmed冻结 | 模型等待前释放事务，任务写回重新锁定并核对版本 | 三个同步入口断言模型不调用；任务预算、迟到拒绝、补充不造新事件 |
| analysis-jobs submit/retry/cancel | 请求 UUID；事件版本、追问 job ID 和判定时间版本；租约 token | profile→job；建议、审计、终态同提交；不自动结算 | 双回答冲突、真实双 worker/崩溃/取消/删改换钥迟到 |
| goals create/update/terminal | 创建是显式新增目标，不发奖；更新及终态使用版本＋UUID回执；已结束不能改结算方向 | profile→goal；结算属性、审计、回执同提交 | 目标重放、旧版本拒绝、旧规则单次规划力奖励 |
| stagnation answer | 属性版本＋UUID；同维度 90 日冷却防再次扣点；重放原回执 | profile→属性；扣点、可选补课挑战、问询历史、回执同提交；无模型调用 | 失败回滚、子维活动合并、可选挑战失败不撤销已确认扣点 |
| exemptions buy | 创建 UUID 指纹、回执查询；前端未知结果保留原 payload | 快照→释放事务→模型→profile锁→配置版本校验→券/扣币/扣点/回执同提交；并发同 UUID 写前再次回放 | 同 UUID 不二次定价；换钥结果不得落库；券保护旧规则 |
| shop redeem | 物品时间版本＋UUID；账号隔离的持久操作；只用原 body 恢复 | profile→item；余额、券、流水、回执同提交 | 实际 Vue/composable/API→HTTP→PG，丢响应、刷新、双击、刷新读取失败、第二次购买 |
| shop create/reprice/update/disable | 新建/修改价格不扣币；定价回写核对物品及配置快照；设置为同值不产生金币 | profile 锁；AI 请求在事务外；旧价不能覆盖已更新物品 | 旧规则回归、跨账号动作 |
| redemptions fulfill | 券状态条件；重复兑现不扣币、不追加奖励，保留同一券 | profile/券，终态后不再结算 | 跨账号、旧规则幂等 |
| challenges generate/variant/complete | 用户/期次/候选身份；接受后档位冻结；待结算重判复用原事实/判定，模型回写验证快照 | 定价/判定等待前释放事务；写回重新锁定 | 跨用户、旧模型换钥及旧挑战回归 |
| challenges accept/settle | 时间版本＋UUID回执；状态条件认领 | profile→challenge→judgment；押金/奖励/属性及回执同事务 | PG 竞争、重复结算、余额保护 |
| challenges abandon/到期维护 | 原 challenge ID＋accepted→终态条件；重复/竞争失败明确拒绝，GET 可回读终态 | profile→challenge；退缩复用事件/判定；同事务扣点、没收/退款；带理由先模型快照校验 | PG expiry↔settle↔abandon，事实与流水单次 |
| achievements/check、coins/check-streak | 用户＋成就 code / streak 奖励身份唯一；重复 POST 无新增奖励 | 用户锁内发放；cloud GET 不发奖 | 重复奖励回归、GET 全表不变 |
| onboarding neutral/answer | 已建档一次性状态；neutral13×50＋80；旧40不补差 | 用户锁内校验未建档、属性及启动资金同提交；AI回答快照检查 | PG 双建档；问卷不能覆盖中性基线 |
| onboarding supplement/confirm | 本人画像建议；确认后更新画像/属性，不造事件；cloud reset 禁止 | 用户锁、模型等待前释放事务，建议确认时再次校验 | 旧规则、重置禁止 |
| anchors calibrate | 内置模板只读；仅用户 override | 个人唯一配置 upsert，无金币或奖励 | 双账号、模板只读 |
| items CRUD/toggle、settings | 所有外键属于本人；纯内容/展示设置采用覆盖语义，重复请求无结算副作用；toggle 读当前状态后主动切换 | 不调用奖励；配置JSON更新可最后写入覆盖 | 嵌套外键、跨账号、GET 不变 |
| subdimensions propose/accept/dismiss | 本人主维；仅接受待提议名称；不自动赋点/发奖 | AI 外部快照；接受在用户锁内核对提议 | 跨账号、旧经济回归 |
| reports POST | 每次主动生成独立保存，非重放接口；不结算 | 生成前保存源事件版本；模型等待无事务；回写核对配置 | 历史列表/详情、来源 edited/deleted/unavailable、不换成最新正文 |
| daily-reviews PUT | 日期＋保存时区＋整数版本；重复旧版本 409，草稿保留与比较 | profile锁；回顾/链接同提交，不造事件、不发奖、不调模型 | 日期/DST、版本冲突、改时区后定位 |
| llm-config PUT/test | 主/辅分别属于本人；同供应商可保留 Key；换供应商须重绑或清空停用 | 配置原子校验；每次合法变更递增版本；测试主动请求，非 GET | 两组保留/替换/清空、错误回滚、替身请求目标＋Key |
| backup POST | cloud 禁止旧 SQLite 备份入口；云备份只用受限 ops 流程 | PG 一致快照，远端及恢复分类 | 本轮仅脚本/替身，真实异地 BLOCKED |

全部 91 个业务 method/path（99 中扣除认证入口和内部 health/ready）的无会话请求逐项验证为 401。资源级双账号检查覆盖事件、项目、目标、判定及日志、挑战、商店、券、子维、报告、任务、嵌套引用和导出；配置及连通测试只解析当前账号。外部 Caddy、TLS、数据库角色权限和手机网络尚未验证，不能从此表推出公网验收通过。

创建目标、新建项目/物品、报告等主动新增接口不承诺跨不同 UUID 的语义去重；它们不因读取或模型建议自动结算。财务重放依赖同一操作身份，用户明确进行第二次购买才换 UUID。模型调用不承诺供应商侧恰好一次计费。
