---
tid: "t078"
slug: "environment_deletion_lifecycle_and_actions"
title: "环境删除生命周期与列表操作统一"
status: "done"
branch: "t078_environment_deletion_lifecycle_and_actions"
worktree: ""
review_level: "full"
review_limit: "5"
verify_limit: "5"
diff_anchor: "9c203a631e008e6d060161a2c41551b35635cfeb"
spec_source_sha: "dffadb298c123ae77a8e8b1f224731ba59030076"
depends_on: "t076"
conflicts_with: "t075,t077,t079"
note: "用户已授权13项todo聚合立项、commit与push；只创建backlog，不实施。"
---

# Task 进展

front matter 只经 `task.py` 修改；reviewer 只写对应 `review_*.md`。

## 实施笔记

执行期记录关键步骤、决策、验证、阻塞和用户批准的新轮次上限。

创建期不预测实施步骤。只记有追溯价值的内容；无事项时写“无”。

- 实施（2026-11-18，云端，owner cloud-muse-20261117，接续主会话派发）：设计定案——删除收敛为同一持久化生命周期：新表 `profile_deletions`（每目标一行：batch_id、profile_id、名称快照、stage accepted→stopping→cleaning→done/failed、failed_stage、error、detail JSON 记各清理步结果与停止时绑定实例快照）；ProfileService 内编排（复用 profile 锁、set_desired_state 与 `_runtime_has_writer` 语义），stopping 阶段置 desired=stopped 后等无写者（超时失败、数据不动），cleaning 阶段先复核实例未被新绑定（新实例出现即失败不误删），再按 artifacts→目录→preview→DB 行顺序清理、每步结果入 detail，失败置 failed 可重试；启动时 resume 未终结意图（沿 artifact 删除意图的既有模式）。API：`POST /profile-deletions`（202，逐目标回执，重复提交返回同一意图不重复删）、`GET /profile-deletions/batches/{batch_id}`、`GET /profile-deletions/{operation_id}`、`POST /profile-deletions/{operation_id}/retry`；旧 `DELETE /profiles/{id}` 改为同步驱动同一状态机（旧的「运行中拒绝」语义废止，失败回 409 带 stage）。前端：表格删最后活跃列、页头删运行数量统计；操作区停止与删除并存、删除固定最右 danger、过渡态可用性有 title 说明；单项/批量统一走居中模态 `DeleteEnvironmentsDialog`（确认前不发请求；确认时冻结目标 ID 快照；进度/逐项结果在弹窗内，失败项带 stage 与重试入口）；批量删除不再逐条 DELETE 循环。

- AC-007 [deploy] 处置：实施阶段已按用户 2026-11-18 裁定在 task.md 契约区写入打勾处置注记，本地补验登记 p128。

- 后端落地（2026-11-18）：迁移 `0011_profile_deletions`（revision c41d9a02e6b7）；`ProfileService` 新增 request/retry/resume/await 与驱动器（per-op 锁单飞 + 后台 task），`delete_profile` 改为同步驱动同一状态机；lifespan 在 artifact resume 后接 `set_artifact_cleaner` + `resume_pending_deletions`。新增测试先行：`tests/unit/test_t078_deletion_lifecycle.py` 11 条（停止超时数据不动、实例围栏、新实例不误删、清理分步失败保留 DB 行、重复受理幂等、resume 恢复、旧单删同步语义等）、`tests/integration/test_t078_deletion_api.py` 6 条（202 回执形状、批次查询、失败后重试收敛、旧端点 409 带 stage、缺失目标 fail 于 accepted、OpenAPI 含新路径）。t035 两条旧语义测试整体替换并在测试内注明理由：`test_delete_running_profile_raises...` 改为运行中删除经停止收敛完成；`test_delete_profile_logs_directory_cleanup_failure` 改为清理失败即删除失败于 cleaning、目录错误不被吞、Profile 行保留（旧「只记日志仍报成功」与 AC-006 冲突）。

- 前端落地（2026-11-18）：生成类型重导出含 ProfileDeletion\*；client 新增 createDeletions/getDeletionBatch/getDeletion/retryDeletion；hooks 新增 useCreateDeletionsMutation/useDeletionBatchQuery（非终结轮询 1s、done 即失效列表）/useRetryDeletionMutation；`DeleteEnvironmentsDialog` 新建（共享 Dialog 焦点管理、确认前零请求、目标快照冻结、逐项 stage/失败阶段/错误/重试）；EnvironmentTable 删最后活跃列（卡片相对时间保留，p114 只点名表格列与页头统计）；EnvironmentRowActions 停止/删除并存、删除固定最右 danger、stopping 禁用停止并 title 说明、运行行删除 title 说明先停后删；EnvironmentListPage 删页头运行统计与两个 fixed-bottom 确认条，useBatchActions 移除 delete 分支。EnvironmentListPage.test.tsx 六条旧语义测试整体替换为新语义用例并逐条注明理由（八列→七列、表格相对时间移除、运行计数移除、逐条 DELETE+toast 汇总→单次批量受理+弹窗逐项结果、运行行无删除按钮→停止删除并存），另加失败保留选择与取消零请求两条；删除 fake 按真实契约推进阶段且返回快照副本（原地变异会绕过 React Query 结构共享，属测试夹具问题、非生产缺陷）。详情页 MaintenanceTab 的删除仍走旧单删端点（端点保留、语义已收敛），其「先停止再删除」禁用口径不在本 task 范围（AC 只约束环境管理列表），未改动。

- Round 1 审阅修复（2026-11-18）：见下方 Review 处置表 7 条。后端改动：`ProfileService._join_deletion`（加入意图归入新批次＋failed 再确认即 retry）、`update_deletion` 可选 `batch_id`、迁移 0011 与模型新增部分唯一索引；测试新增后端 5 条、集成 1 条、前端 2 条并强化 1 处断言。修复后全量门禁（日志 t078_gate7.log＋.scratch/t078_gate_evidence2/）：contract 388 过/1 跳，unit 2226 过（4 失败/10 错误与基线逐项一致），integration 216 过/7 跳（1 错误为隔离 API 就绪窗口 flaky，单跑通过），frontend 681 过（2 失败为 ConfigTab 与 SettingsPage 的负载超时 flaky，均单跑通过），其余 suite exit 0；相对基线无新增失败，新增 8 条测试全过。

- 接续收尾（2026-11-18，主会话接续，前任执行方无声结束）：审计确认上方后端/前端落地记录与实际 diff 一致（迁移 0011、单测 11 条、集成 6 条、前端组件与 hooks 均在位）。补做迁移登记两处（前任遗漏）：`test_t054_migration.py` 按该文件既定模式整体替换 head 断言为 `test_head_is_0011_and_single`（注明理由）；`test_t056_migrations.py` 的 golden schema 断言按既定模式登记 t078 intended delta（恰新增 profile_deletions 表＋两命名索引＋主键 autoindex，并逐列校验新表定义）。

- 全量门禁（2026-11-18，日志 ~/workspace/cloud-task-logs/t078_gate5.log 与 t078_gate6.log＋.scratch/t078_gate_evidence/）：protocol_drift_check、requirements_check、design_lint、design_check、frontend_build 均 exit 0；contract 388 过/1 跳；unit 2221 过/1 跳、4 失败/10 错误与 t076 基线逐项一致（t063×2 失败＋t063 built 系列 10 错误依赖本机外构建产物路径、t068×2 失败，均为老基线），evidence 并发跑另有 test_t027_release_controller 1 条 FileNotFoundError 并发 flaky（单跑通过）；integration 210 过/7 跳、6 错误均为隔离 API 子进程 10 秒就绪窗口在负载下被击穿（test_normal_exit_replay×4、test_supervisor_observation_authority×2，server.log 证明服务最终正常启动，逐条/逐文件单跑全部通过，与本 task 改动无因果）；frontend 680 过/1 失败（ConfigTab 保存回显用例 5 秒超时，已知 flaky，单跑通过）。t078 新增 unit 11 条、integration 6 条与前端新用例全部通过。相对基线无新增失败。

- 创建授权：2026-11-18T00:00:06+08:00，用户要求全部todo按已讨论架构聚合为少量task并commit/push；来源为p114、p117。本条仅登记创建事实，未实施、未验证业务AC。

- 关联spec：docs/specs/profile_management.md、docs/specs/runtime_lifecycle.md、docs/specs/storage_and_artifacts.md、docs/specs/ui_design_system.md；执行收尾时登记本tid并同步新契约，保留旧task历史。

## Review 处置

每个结构化 finding 一行。`已修` 表示本 task 已修复；`遗留` 必须指向 `pNNN` 或 follow-up tid；`撤回` 必须写清理由。critical/important 未解决时不得 PASS。

Round 1（2026-11-18）：code 轴 FAIL 3 条、test 轴 FAIL 4 条，AC-005 双轴 TICK-VOID，其余 AC TICK-VALID。全部 AC 一度撤回打勾，逐项修复后重验再打勾，进入 Round 2 复审。

|finding_id|status|fix_ref|说明|
|---|---|---|---|
|t078_code_f001|已修|-|（important）加入既有意图的目标在新批次不可见、再次确认静默失效。修：`request_deletions` 加入既有意图时经 `_join_deletion` 归入本次批次（`update_deletion` 新增可选 `batch_id`）；failed 意图被再次确认按 retry 语义从失败阶段恢复、清失败并重新驱动。新增回归：unit `test_reconfirm_failed_intent_retries_under_new_batch`、integration `test_reconfirm_after_failure_surfaces_in_new_batch`（新批次回查含该意图且收敛 done）|
|t078_code_f002|已修|-|（minor）domain.md 记载 retry_count 字段与实现不一致。修：domain.md 删除意图字段清单去掉不存在的 `retry_count`，并补记部分唯一索引与再确认即 retry 的口径|
|t078_code_f003|已修|-|（minor）查既有→新建非原子，并发可建双意图。修：迁移 0011 与 ORM 模型新增部分唯一索引 `uq_profile_deletions_open_profile`（stage != 'done'）；`request_deletions` 捕获 IntegrityError 后有界重读并加入胜出意图。新增 unit `test_second_open_intent_violates_unique_index`、`test_concurrent_requests_create_single_open_intent`；t056 golden 登记同步增该索引|
|t078_test_f001|已修|-|（important）AC-005 前端集合断言被 arrayContaining 弱化。修：批量删除用例改为长度恰 2 且排序后精确等于 ["p1","p2"]，未选中的 p3 混入即失败|
|t078_test_f002|已修|-|（minor）卡片布局与 starting/stopping/error 状态行无断言。修：新增用例覆盖五种状态（running/stopped/error/starting/stopping）删除入口存在且为操作区最右、运行/启动中 title 为先停后删说明、停止中启动禁用、异常态无停止入口，并切卡片布局逐一断言|
|t078_test_f003|已修|-|（minor）cleaning 阶段 resume 与删除后迟到事件无用例。修：新增 unit `test_resume_pending_deletions_from_cleaning`、`test_late_instance_event_does_not_resurrect_deleted`|
|t078_test_f004|已修|-|（minor）删除弹窗层未测 Escape/焦点。修：新增用例在删除弹窗层面按 Escape 关闭、断言零请求且焦点不留在已卸载弹窗内|
|t078_code_f004|遗留|p130|（minor，Round 2 新出）并发两次确认时后加入者把意图改归其批次，先确认者按其批次号轮询得到空集、弹窗回落确认态。删除本身不重复不丢失（单意图由部分唯一索引保证、单项查询与再确认可恢复），Round 2 code 轴 verdict PASS、全部 AC 打勾成立；批次成员关系与意图分离属独立改造，登记 p130 跟踪|

Round 2（2026-11-18）：code 轴 PASS（Round 1 三条已消除，新出 minor f004 一条，处置见上表遗留行）、test 轴 PASS（Round 1 四条已消除，0 条新 finding）。

## 收尾报告

### 验收与验证

- task：[`task.md`](task.md)
- 结果：云端可做部分全部完成；AC-007 [deploy] 按用户 2026-11-18 裁定＋契约修订处置打勾（非实测通过），真实环境验证留待本地统一补验 p128
- 测试：全量门禁两轮（t078_gate5/6.log、t078_gate7.log 及 evidence 目录）：contract 388 过/1 跳；unit 2226 过、4 失败/10 错误与 t076 基线逐项一致；integration 216 过/7 跳、错误均为隔离 API 就绪窗口 flaky（逐条单跑通过）；frontend 681 过、失败均为负载超时 flaky（单跑通过）；protocol/requirements/design/frontend_build 全绿。相对基线无新增失败
- 黑盒：云端无 Docker/Chrome，真实拓扑黑盒未跑；AC-007 已登记 p128 留待本地统一补验
- review：Round 1 双轴 FAIL（code 3 条、test 4 条）→ 全部修复并写入 Review 处置表 → Round 2 双轴 PASS（code 轴新出 minor f004 一条：并发双确认时先确认者批次轮询留空，删除不重复不丢失，遗留登记 p130；test 轴 0 条新 finding）
- AC 判定：见 `task.md` 行内打勾；AC-001–AC-006 依门禁与测试证据，AC-007 按契约区处置注记

### 结果摘要

- 删除收敛为持久化状态机：意图先行落库（profile_deletions），stopping 只停写者不动数据，cleaning 实例围栏后按 artifacts→目录→preview→DB 行分步清理且结果可追踪，失败保留阶段与重试入口，重启自动 resume 未终结意图；批量以确认时冻结的 ID 集合逐项成败，旧单删端点同步驱动同一状态机。前端移除运行计数与最后活跃列，停止/删除独立并存、删除固定最右 danger，确认统一走居中模态且确认前零请求。Round 1 审阅另修复：加入意图归入新批次＋failed 再确认即 retry、部分唯一索引强制单意图、前端严格集合断言与状态/卡片/Escape 覆盖补齐。

### 长期文档闭环

执行finalization时更新关联active spec的tasks清单及本task指定blueprint；创建阶段不提前声明实现或闭环。
