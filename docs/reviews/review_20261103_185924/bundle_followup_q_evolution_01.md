# bundle_followup_q_evolution_01

## Summary

逐行核对 docs/tasks/t010_v2_data_migration/task.md 契约区全文（范围、非范围、AC-001~AC-010、可测试性声明、测试策略、风险与回退、依赖与约束）及 note.md front matter 与 docs/tasks_index.json 的登记状态。结论：怀疑不成立——t010 契约并非标题级规划。迁移对象已逐项列明：profiles.db 侧由 AC-001（dry-run 列出 Profile/Tag/Artifact 数量、旧字段映射、无效运行模式并做文件校验）与 AC-002（计划 15.2 全部仍有效配置字段、标签/顺序、用户数据、Artifact、设置、运行事件迁移无丢失，旧运行/查看模式字段不再保留）覆盖，运行状态映射由 AC-003 单列（running 与真实容器核对、initializing 映射待检查、stopped 保持 desired stopped）；浏览器状态以 AC-002『新数据库可真实启动浏览器并保留 Cookie/设置/内部页面恢复』及范围条『数据根备份恢复』的形式纳入，artifacts 的字节与索引由 AC-001 清点、AC-002 无丢失要求与 AC-004 备份覆盖共同约束。校验方式成文：dry-run 不修改源/目标且缺字段/路径冲突明确阻断（AC-001）、备份校验后恢复到独立空数据根且源文件 hash/数量与恢复结果一致（AC-004）、真实旧格式 fixture 对 dry-run/成功迁移/重复执行/失败回滚/备份恢复独立黑盒验证（AC-005）。失败回滚成文：故障注入任一步失败恢复旧 DB 和目录、禁止不可恢复原地升级（AC-004），『风险与回退』节另定真实数据迁移前验证备份可恢复、切换失败恢复旧数据根并重新启用旧版容器（task.md:74）。当前未执行的原因是排期而非契约缺失：note.md 与 tasks_index.json 均记 t010 status=backlog、depends_on=t009，task.md:78 明定必须先取得 t009 完成产物。故 f_global_evolution_01 中『迁移契约未定义』若有此意不成立，应仅保留『切换链未启动』部分。

## Findings

No findings.

## evidence

```json
[
  "docs/tasks/t010_v2_data_migration/task.md:11（契约区·范围）：『Alembic/迁移CLI、数据根备份恢复、旧字段/运行状态映射和隔离fixture真实演练；现有用户数据仅在明确批准具体数据根并验证可恢复备份后执行』",
  "docs/tasks/t010_v2_data_migration/task.md:27（AC-001）：迁移前停旧服务并拒绝活跃写者；--dry-run 不修改源或目标，列出 Profile/Tag/Artifact 数量、旧字段映射、无效运行模式和文件校验，缺字段/路径冲突明确阻断",
  "docs/tasks/t010_v2_data_migration/task.md:28（AC-002）：计划15.2全部仍有效配置字段、标签/顺序、用户数据、Artifact、设置和运行事件迁移无丢失；旧运行模式与查看模式字段不再保留；新数据库可真实启动浏览器并保留Cookie/设置/内部页面恢复（浏览器状态纳入迁移范围）",
  "docs/tasks/t010_v2_data_migration/task.md:29（AC-003）：运行状态逐项映射规则——旧running与真实容器核对，initializing映射待检查，stopped保持desired stopped，不因旧DB标记自动假定容器存在",
  "docs/tasks/t010_v2_data_migration/task.md:30（AC-004）：备份覆盖DB/settings/profiles/artifacts/runtime-events，校验后可恢复到独立空数据根；故障注入任一步失败时恢复旧DB和目录，源文件hash/数量与恢复结果一致，禁止不可恢复原地升级（校验方式与失败回滚均成文）",
  "docs/tasks/t010_v2_data_migration/task.md:31（AC-005）：真实旧格式fixture包含各有效字段和文件，dry-run、成功迁移、重复执行、失败回滚、备份恢复均独立黑盒通过",
  "docs/tasks/t010_v2_data_migration/task.md:74（风险与回退）：『真实数据迁移前验证备份可恢复；切换失败时恢复旧数据根并重新启用旧版容器』",
  "docs/tasks/t010_v2_data_migration/task.md:46（可测试性声明）：其余AC可自动验证（迁移以真实旧格式fixture、故障注入与独立黑盒验证）；AC-005实际数据迁移与AC-010部署需用户单独授权——属执行授权门槛，非契约缺项",
  "docs/tasks/t010_v2_data_migration/note.md front matter 与 docs/tasks_index.json（t010 条目）：status=backlog、depends_on=t009；task.md:78『必须先取得t009完成产物』——契约已就绪、未启动原因是依赖排期"
]
```

## result

```json
"refuted"
```
