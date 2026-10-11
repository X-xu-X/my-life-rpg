# 旧库非外键引用登记

实现入口 `ops/import_references.py`，仅在导入合成/获准冻结副本时使用。普通外键沿各表登记映射；以下补足数据库约束看不到的引用。`ops/import-sqlite.py` 预检报告列出源表、原行ID、字段路径、目标表/原ID；缺目标或跨用户默认阻断。正式导入只使用 `mapping[target][old_id]`，不存在“找不到就保留旧ID”的退路。

| 字段 | 生产者/语义 | 目标表 | 策略 |
|---|---|---|---|
| events.params._challenge_id | challenge_service 的挑战关联事实 | challenges | 仅此语义键映射；同params的分钟/分数不变 |
| coin_ledger.ref_type=event / ref_id | coin_service，事件确认奖励 | events | type确定目标后映射 |
| coin_ledger.ref_type=challenge / ref_id | challenge_service 押金/结算 | challenges | 同上 |
| coin_ledger.ref_type=shop_item / ref_id | shop_service 兑换扣币 | shop_items | 同上，不误指向券ID |
| coin_ledger.ref_type=achievement / ref_id | achievement_service 奖励 | achievements | 同上 |
| coin_ledger.ref_type=exemption / ref_id | exemption_service 购买扣币 | exemptions | 同上；未知非空type阻断 |
| judgment_logs.payload.event_id / judgment_id / attribute_id | judge_service 审计、撤销及恢复链 | events / ai_judgments / attributes | 按登记键递归映射 |
| judgment_logs.payload.source_history_ids[] | judge_service 删除反向流水依据 | attribute_history | 列表逐项映射，不保留缺失项 |
| judgment_logs.payload.exemption.id | judge_service / exemption_service 券命中快照 | exemptions | 仅exemption上下文的id映射，普通id不替换 |
| judgment_logs.payload及goals.audit中的goal_id / item_id / challenge_id / shop_item_id / redemption_id / exemption_id / achievement_id | 已登记的审计扩展引用；goal_service的audit当前主要是动作快照 | goals / checkin_items / challenges / shop_items / redemptions / exemptions / achievements | 显式字段登记，不按任意整数替换 |
| 上述审计列中的event_ids / judgment_ids / attribute_ids / goal_ids / item_ids / challenge_ids / shop_item_ids / redemption_ids / exemption_ids / achievement_ids | 与单值同一目标的列表引用 | 对应单值目标表 | 列表逐项核对归属并映射 |
| ai_judgments.merged_with.ref | 跨来源合并的历史显示字符串 | 无可执行外键 | 原样保留历史说明，不伪造新的可点击对象身份 |
| 价格、属性值、分钟、日期、正文数字、其他普通JSON值 | 历史快照或用户内容 | 无 | 原样保留，不遍历替换碰巧等于旧ID的整数 |

RR03 实际合成验证预占目标序列，使源71与新ID故意不同，覆盖挑战、券扣币、数组、券命中嵌套、普通整数不变；缺映射/跨用户阻断，写入后注入异常整事务回滚，旧40币与源文件哈希保持。测试入口 `tests/test_release_pg.py::test_import_forced_id_difference_all_semantic_paths_and_atomic_failure`。登记是当前源码语义审计结果，不承诺未来任意JSON新增字段自动正确；生产者新增对象引用须同步登记和测试。

本轮没有读取真实旧库，历史“判定35→事件34悬空”仅作为合成阻断用例，不能视作真实问题已经核实或修复。
