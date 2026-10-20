# 旧计划历史补修独立复审 · 2026-10-19

对照 [上轮 R01](FULL_SYSTEM_FIXES_REVIEW_2026-10-19.md)、[补修交付说明](LEGACY_PLAN_HISTORY_FIX_2026-10-19.md)，检查当前未提交工作区。

## 结论

**R01 可以关闭。本次补修范围内未发现新的可复现缺陷。** 原五项审查问题和随后发现的旧计划兼容边界均已有本地修复验证；这不等同真实云端、真实数据或供应商验收完成。

修复在已有空历史日程第一次编辑时，先捕获仍可确定的旧名称、rule、启用状态、目标与原版本，再追加新版本；保存旧目标发生在覆盖关联之前。`legacy_baseline=true` 和当前捕获时间避免把补存快照冒称未知原始历史。UUID 回执检查仍先于修改，写入沿原事务处理。

## 独立核验

| 检查 | 结果 |
| --- | --- |
| 原复现：无分钟字段、`history=[]` 的旧计划，明天起改为45分钟 | 今天 `timing` 保持旧名称／30分钟；启动返回200、1800秒，不再返回409。 |
| 次日生效与旧会话 | 回归验证次日新计时2700秒；已开始的1800秒合同不被修改，刷新仍保留。 |
| 停用、显式时长与目标 | 回归验证旧停用20分钟不会提前启用；旧目标快照保留，未来取消关联不覆盖旧快照。 |
| 独立补充写边界 | 9项通过：新建只一版；非法过去生效日拒绝且不写基线；省略分钟保留20；同UUID原样重放；过期版本409；连续有效编辑仅补一次旧基线，当天时长不变。 |

原复现直接复制到新审查目录运行，未修改上一轮脚本及证据：[原复现脚本](review/legacy_plan_history_fix_review_2026-10-19/original-boundary-probes.py)、[结果](review/legacy_plan_history_fix_review_2026-10-19/boundary-results.json)。补充边界：[脚本](review/legacy_plan_history_fix_review_2026-10-19/additional-probes.py)、[9项结果](review/legacy_plan_history_fix_review_2026-10-19/additional-results.json)。

后端七模块独立复跑：**129项，127 PASS、2 SKIP、0 FAIL／ERROR**；两个新增R01用例及原N01～N05用例全部通过。[结果](review/legacy_plan_history_fix_review_2026-10-19/backend-results.json)、[日志](review/legacy_plan_history_fix_review_2026-10-19/backend-tests.log)。两个跳过仍为真实PostgreSQL并发／导入检查，没有把未执行当作通过。

## 范围与限制

补修 manifest 中128个源码及所列文档／证据哈希全部匹配。与上轮独立审查源码相比，仅 `app/routers/plans.py` 和 `tests/test_review_repairs.py` 变化，前端和迁移未改。本次未重复运行前端构建／浏览器82项；该数字属于上一轮，不能计作本轮新结果。详见 [源码比较](review/legacy_plan_history_fix_review_2026-10-19/source-comparison.json)。

本次只使用临时合成SQLite、假模型和测试接口，未运行真实应用lifespan，未读取真实旧库、调用真实模型或邮件、部署、提交或推送。真实旧数据是否存在这种结构尚未检查；真实PostgreSQL、供应商语义与定价、SMTP收件、手机实机仍待既定验收。

本次未修改正式程序；审查前后229个源码／测试／迁移文件哈希保持一致。仅新增本报告和独立审查证据，原交付与两轮审查材料保留。
