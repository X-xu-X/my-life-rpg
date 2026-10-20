# 无历史旧计划的未来时长修改补修 · 2026-10-19

依据 [五项修复复审 R01](FULL_SYSTEM_FIXES_REVIEW_2026-10-19.md)。范围为已有计划 `history=[]`，包括旧 rule 缺少 `planned_minutes` 的兼容结构。本次仅用合成数据复现，没有读取真实旧库，**尚未确认真实旧数据是否存在这种情况**。

## 修改与验收场景

`app/routers/plans.py` 的 `save_schedule` 在首次编辑空历史的已有行时，先保存当前已知名称、rule、启用状态、目标和原版本，再追加新生效版本。基线带 `legacy_baseline=true`，`at` 是本次捕获时间，不冒充未知的原始编辑时间。两份快照与写操作回执均在原事务中保存，回执重放在修改历史前返回。

- 旧版本缺分钟字段时继续默认30分钟；明天45分钟的新规则不会提前替换今天的有效时长。
- 已开始的会话保留原合同；未来修改后，今天重新开始仍为1800秒，明天新开始为2700秒。
- 沿用本人来源、当前来源版本和实际生效版本检查；界面刷新读取的 `timing` 不再因这次未来修改变成null，当天安排也仍使用旧快照。
- 原本显式20分钟、停用的旧计划仍保留20分钟和停用状态，不会因未来启用而在今天提前可用。旧目标信息不会被新设置的取消关联覆盖。
- 同UUID重放返回原结果，不重复追加基线或未来版本；正常已有历史、新建计划沿原逻辑。

新增回归在 `tests/test_review_repairs.py`：

1. `test_R01_legacy_empty_history_future_edit_preserves_today_and_receipt`：旧版本7、无分钟字段、无历史；修改前开始30分钟，未来改45并重放；核对历史、目标、刷新、当天重新开始、明天45分钟及旧会话合同。
2. `test_R01_legacy_disabled_and_explicit_duration_are_preserved`：空历史、显式20分钟且停用；明天启用45分钟，今天仍停用且保持20分钟。

修复前新增主用例已失败于 `timing is None`：[失败日志](review/legacy_plan_history_fix_2026-10-19/before-fix.log)。修复后七模块回归结果与完整日志分别见 [backend-results.json](review/legacy_plan_history_fix_2026-10-19/backend-results.json)、[backend-tests.log](review/legacy_plan_history_fix_2026-10-19/backend-tests.log)。本次证据在新目录，不覆盖上轮交付或独立审查。

本次 **129项运行，127 PASS、2 SKIP、0 FAIL／ERROR**，两个新增R01用例均通过。两项跳过仍为真实PostgreSQL并发／导入用例，没有新增跳过或XFAIL。Python编译检查和 `git diff --check` 通过。

复跑（仓库根目录，本机 PowerShell；临时合成SQLite、假模型、不启动真实应用lifespan）：

```powershell
.venv/Scripts/python.exe tests/run_full_system_checks.py --repairs --output docs/review/legacy_plan_history_fix_2026-10-19
```

## 范围与兼容

没有新增迁移、扫描或批量回填真实数据；只在这类旧记录被正常编辑时保留仍可确定的旧设置，不猜测已经丢失的历史。原金额、领取和计时合同规则不变。没有提交、推送或部署。

本次前端代码未改，未重复构建或运行上一轮82项浏览器合成检查；此次新增证据是实际后端接口回归，不能冒称已完成真实前后端或实机验收。真实PG、模型、邮件与手机仍未验，真实旧数据是否含该结构也仍未验。

原交付、复审和本轮源码／证据哈希关联见 [补修清单](review/legacy_plan_history_fix_2026-10-19/repair-manifest.json)。本报告补充N03旧结构边界，不把上一轮已通过的常规路径误报为已覆盖本分支。
